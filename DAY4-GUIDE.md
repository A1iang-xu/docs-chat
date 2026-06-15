# DocsChat Day 4 · 自动化测试 + 性能优化 + 容器化部署

> 目标：为前端组件和后端服务建立完整的自动化测试体系，打磨交互细节（可访问性、响应式、性能），并通过 Docker Compose 实现一键部署。
> 预计耗时：8 小时（上午 3h + 下午 3h + 晚间 2h）

---

## 第一部分：前端单元测试（上午 · 1.5h）

### 1.1 安装测试依赖

```powershell
cd E:\docs-chat\frontend
npm install -D vitest @vue/test-utils jsdom @pinia/testing
```

### 1.2 创建 Vitest 配置 `frontend\vitest.config.ts`

```typescript
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      css: true,
      setupFiles: [],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html'],
        include: ['src/**/*.{ts,vue}'],
        exclude: ['src/types/**', 'src/env.d.ts'],
      },
    },
  }),
)
```

### 1.3 更新 `package.json` 添加测试脚本

在 `frontend\package.json` 的 `"scripts"` 中添加：

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage"
  }
}
```

### 1.4 创建测试辅助文件 `frontend\src\__tests__\setup.ts`

```typescript
/**
 * 测试环境初始化 —— 配置全局 Mock、stub 浏览器 API
 */
import { config } from '@vue/test-utils'
import { vi } from 'vitest'

// ── Stub 浏览器 API 中 Vitest 未提供的部分 ──
if (typeof globalThis.crypto === 'undefined') {
  vi.stubGlobal('crypto', {
    randomUUID: () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
    }),
    getRandomValues: (arr: Uint8Array) => {
      for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256)
      return arr
    },
  })
}

// ── 全局 Mock：import.meta.env ──
vi.stubGlobal('import.meta', {
  env: {
    VITE_API_BASE_URL: 'http://localhost:8000',
  },
})

// ── 关闭 Vue Test Utils 的全局 stubs 警告 ──
config.global.stubs = {
  transition: false,
}
```

### 1.5 创建 ChatMessage 组件测试 `frontend\src\components\__tests__\ChatMessage.spec.ts`

```typescript
/**
 * ChatMessage 组件测试
 *
 * 测试覆盖：
 * 1. 用户消息渲染（纯文本，无 Markdown）
 * 2. AI 消息渲染（Markdown 转换）
 * 3. 来源引用卡片渲染
 * 4. 代码块高亮
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessage from '../ChatMessage.vue'
import type { Message, SourceCitation } from '@/types'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    conversationId: 'conv-1',
    role: 'user',
    content: '你好',
    sources: [],
    createdAt: new Date().toISOString(),
    ...overrides,
  }
}

function makeSource(overrides: Partial<SourceCitation> = {}): SourceCitation {
  return {
    index: 1,
    content: '这是测试文档的原文片段',
    page: 3,
    documentName: 'test.pdf',
    relevanceScore: 0.87,
    ...overrides,
  }
}

describe('ChatMessage', () => {
  it('渲染用户消息为纯文本', () => {
    const msg = makeMessage({ role: 'user', content: '你好世界' })
    const wrapper = mount(ChatMessage, { props: { message: msg } })

    expect(wrapper.find('.role-label').text()).toBe('你')
    expect(wrapper.find('.text').text()).toBe('你好世界')
  })

  it('用户消息中 HTML 标签被转义', () => {
    const msg = makeMessage({ role: 'user', content: '<script>alert("xss")</script>' })
    const wrapper = mount(ChatMessage, { props: { message: msg } })

    const html = wrapper.find('.text').html()
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })

  it('AI 消息渲染 Markdown 标题', () => {
    const msg = makeMessage({ role: 'assistant', content: '## 标题\n\n正文内容' })
    const wrapper = mount(ChatMessage, { props: { message: msg } })

    expect(wrapper.find('.role-label').text()).toBe('DocsChat')
    expect(wrapper.find('.markdown-body').exists()).toBe(true)
    expect(wrapper.find('.markdown-body').html()).toContain('<h2')
  })

  it('AI 消息中代码块渲染为 pre/code', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: '```python\nprint("hello")\n```',
    })
    const wrapper = mount(ChatMessage, { props: { message: msg } })

    expect(wrapper.find('pre').exists()).toBe(true)
    expect(wrapper.find('pre code').html()).toContain('print')
  })

  it('渲染来源引用卡片', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: '根据文档 [1] 的内容',
      sources: [makeSource()],
    })
    const wrapper = mount(ChatMessage, { props: { message: msg } })

    expect(wrapper.find('.sources').exists()).toBe(true)
    expect(wrapper.find('.sources-label').text()).toBe('参考来源：')
    expect(wrapper.find('.source-badge').text()).toContain('[1]')
    expect(wrapper.find('.tooltip-body').text()).toBe('这是测试文档的原文片段')
    expect(wrapper.find('.tooltip-score').text()).toContain('87.0%')
  })

  it('无来源时不渲染来源区域', () => {
    const msg = makeMessage({ role: 'assistant', content: '无来源回答', sources: [] })
    const wrapper = mount(ChatMessage, { props: { message: msg } })

    expect(wrapper.find('.sources').exists()).toBe(false)
  })

  it('空消息不报错', () => {
    const msg = makeMessage({ role: 'assistant', content: '' })
    expect(() => mount(ChatMessage, { props: { message: msg } })).not.toThrow()
  })
})
```

### 1.6 创建 MessageInput 组件测试 `frontend\src\components\__tests__\MessageInput.spec.ts`

```typescript
/**
 * MessageInput 组件测试
 *
 * 测试覆盖：
 * 1. 输入框双向绑定
 * 2. 点击发送按钮触发 send 事件
 * 3. Enter 键发送（Shift+Enter 换行）
 * 4. 发送中状态禁用交互
 * 5. 空内容不允许发送
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageInput from '../MessageInput.vue'

describe('MessageInput', () => {
  it('输入框接受用户输入', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    const textarea = wrapper.find('textarea')
    await textarea.setValue('你好')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('你好')
  })

  it('点击发送按钮触发 send 事件并清空输入', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    const textarea = wrapper.find('textarea')
    await textarea.setValue('测试消息')

    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')![0]).toEqual(['测试消息'])
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('发送中状态禁止发送', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: true },
    })

    await wrapper.find('textarea').setValue('测试')
    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeFalsy()
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('空内容不触发发送', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    await wrapper.find('textarea').setValue('   ')
    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeFalsy()
  })

  it('Enter 键发送消息', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    await wrapper.find('textarea').setValue('Enter 测试')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: false })

    expect(wrapper.emitted('send')).toBeTruthy()
  })

  it('Shift+Enter 不发送（换行）', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    await wrapper.find('textarea').setValue('不发送')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })

    expect(wrapper.emitted('send')).toBeFalsy()
  })
})
```

### 1.7 创建 useSSE Composable 测试 `frontend\src\composables\__tests__\useSSE.spec.ts`

```typescript
/**
 * useSSE Composable 测试
 *
 * 测试覆盖：
 * 1. 初始状态
 * 2. 流式连接接收 token 事件
 * 3. 接收 source 事件更新引用
 * 4. done 事件结束流
 * 5. error 事件处理
 * 6. abort 中断连接
 * 7. 连接失败自动重试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useSSE } from '../useSSE'

describe('useSSE', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('初始状态正确', () => {
    const { content, sources, isStreaming, error } = useSSE()

    expect(content.value).toBe('')
    expect(sources.value).toEqual([])
    expect(isStreaming.value).toBe(false)
    expect(error.value).toBeNull()
  })

  it('abort 后 isStreaming 变为 false', () => {
    const { isStreaming, abort } = useSSE()

    // 模拟连接中状态
    isStreaming.value = true
    abort('用户取消')

    expect(isStreaming.value).toBe(false)
  })

  it('abort 传入 reason 时设置 error', () => {
    const { error, abort } = useSSE()

    abort('连接超时')
    expect(error.value).toBe('连接超时')
  })

  it('connect 时重置状态', async () => {
    const { content, sources, error, isStreaming, connect } = useSSE()

    content.value = '旧内容'
    sources.value = [{ index: 1, content: '旧', relevanceScore: 0.5 }]
    error.value = '旧错误'

    // 模拟 fetch 失败（不创建真实连接）
    const mockFetch = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('网络错误'))

    const connectPromise = connect('http://test/api', { key: 'value' })

    // 快进到重试完成
    await vi.runAllTimersAsync()
    await connectPromise.catch(() => {})

    // 验证状态已重置
    expect(content.value).toBe('')
    expect(sources.value).toEqual([])
    expect(error.value).toBeTruthy() // 连接失败后设置了错误

    mockFetch.mockRestore()
  })
})
```

### 1.8 运行测试验证

```powershell
cd E:\docs-chat\frontend
npx vitest run
```

期望输出：所有测试用例通过（绿色 ✓）。

---

## 第二部分：后端集成测试（上午 · 1.5h）

### 2.1 安装后端测试依赖

```powershell
cd E:\docs-chat\backend
pip install pytest pytest-asyncio httpx
```

### 2.2 创建 conftest `backend\tests\conftest.py`

```python
"""pytest 全局配置与 fixtures"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client():
    """异步 HTTP 测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

### 2.3 创建健康检查测试 `backend\tests\test_health.py`

```python
"""健康检查端点测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "DocsChat API"
```

### 2.4 创建 LLM 服务测试 `backend\tests\test_llm_service.py`

```python
"""LLM 服务层测试 —— 使用 Mock 避免真实 API 调用"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.llm_service import LLMService


class TestLLMService:
    """LLM 服务单元测试"""

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tokens(self):
        """验证流式调用能正确逐 token 返回"""
        mock_chunk = MagicMock()
        mock_chunk.choices = [
            MagicMock(delta=MagicMock(content="Hello"))
        ]

        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [mock_chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream

        service = LLMService()
        service.client = mock_client

        tokens = []
        async for token in service.chat_stream(
            messages=[{"role": "user", "content": "Hi"}]
        ):
            tokens.append(token)

        assert len(tokens) >= 1
        # 验证系统提示词被正确添加
        call_args = mock_client.chat.completions.create.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_chat_stream_with_system_prompt(self):
        """验证系统提示词被正确注入"""
        mock_chunk = MagicMock()
        mock_chunk.choices = [
            MagicMock(delta=MagicMock(content="Got it"))
        ]

        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [mock_chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream

        service = LLMService()
        service.client = mock_client

        async for token in service.chat_stream(
            messages=[{"role": "user", "content": "What is RAG?"}],
            system_prompt="You are a helpful assistant.",
        ):
            pass

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What is RAG?"

    @pytest.mark.asyncio
    async def test_chat_non_stream(self):
        """验证非流式调用返回完整内容"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="完整回答"))
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        service = LLMService()
        service.client = mock_client

        result = await service.chat(
            messages=[{"role": "user", "content": "Hello"}]
        )

        assert result == "完整回答"
        assert mock_client.chat.completions.create.called
```

### 2.5 创建文档上传测试 `backend\tests\test_documents.py`

```python
"""文档上传 API 测试"""
import pytest
import os
import tempfile
from pathlib import Path
from httpx import AsyncClient
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_upload_non_pdf_rejected(client: AsyncClient):
    """验证非 PDF 文件被拒绝"""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"not a pdf")
        temp_path = f.name

    try:
        with open(temp_path, "rb") as f:
            response = await client.post(
                "/documents/upload",
                files={"file": ("test.txt", f, "text/plain")},
            )

        assert response.status_code in [400, 422]
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_upload_without_file_rejected(client: AsyncClient):
    """验证未上传文件时返回错误"""
    response = await client.post("/documents/upload")

    assert response.status_code == 422
```

### 2.6 创建 SSE 聊天端点测试 `backend\tests\test_chat.py`

```python
"""SSE 聊天端点测试"""
import pytest
import json
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_chat_stream_returns_sse_format(client: AsyncClient):
    """验证 SSE 端点返回 data: 前缀格式"""
    mock_chunk = MagicMock()
    mock_chunk.choices = [
        MagicMock(delta=MagicMock(content="您好"))
    ]

    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = [mock_chunk]

    mock_llm = MagicMock()
    mock_llm.chat.completions.create.return_value = mock_stream

    with patch("app.services.llm_service.llm_service.client", mock_llm):
        response = await client.post(
            "/chat/stream",
            json={
                "conversation_id": "test-conv-1",
                "content": "你好",
            },
        )

        assert response.status_code == 200
        body = response.text

        # SSE 响应应包含 "data:" 前缀
        assert "data:" in body

        # 应包含 done 事件
        assert "done" in body


@pytest.mark.asyncio
async def test_chat_stream_empty_content_rejected(client: AsyncClient):
    """验证空消息被拒绝"""
    response = await client.post(
        "/chat/stream",
        json={
            "conversation_id": "test-conv-1",
            "content": "",
        },
    )

    assert response.status_code == 422
```

### 2.7 运行后端测试

```powershell
cd E:\docs-chat\backend
pytest tests/ -v --tb=short
```

期望输出：所有测试用例通过（绿色 PASSED）。

---

## 第三部分：性能优化与可访问性（下午 3h）

### 3.1 创建 Loading 骨架屏组件 `frontend\src\components\LoadingSkeleton.vue`

```vue
<script setup lang="ts">
/**
 * LoadingSkeleton —— 对话加载中的骨架屏
 * 在消息流式生成时提供视觉反馈，提升感知性能
 */
defineProps<{
  lines?: number
}>()
</script>

<template>
  <div class="skeleton-message">
    <div class="skeleton-avatar"></div>
    <div class="skeleton-lines">
      <div
        v-for="i in (lines || 3)"
        :key="i"
        class="skeleton-line"
        :style="{ width: `${80 - i * 10}%`, animationDelay: `${i * 0.15}s` }"
      ></div>
    </div>
  </div>
</template>

<style scoped>
.skeleton-message {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  background: var(--bg2);
}

.skeleton-avatar {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--rule);
  animation: shimmer 1.5s infinite;
  flex-shrink: 0;
}

.skeleton-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.skeleton-line {
  height: 14px;
  border-radius: 4px;
  background: var(--rule);
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { opacity: 0.4; }
  50% { opacity: 0.8; }
  100% { opacity: 0.4; }
}
</style>
```

### 3.2 更新 ChatView 集成骨架屏

在 `frontend\src\views\ChatView.vue` 的消息列表区域，在 `ChatMessage` 循环之后、空状态之前插入骨架屏：

```vue
<!-- 骨架屏：流式生成中 -->
<LoadingSkeleton v-if="isStreaming && currentMessages.length > 0" :lines="4" />
```

同时在 `<script setup>` 顶部添加 import：

```typescript
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
```

### 3.3 更新 MessageInput 增强可访问性

在 `frontend\src\components\MessageInput.vue` 的 `<template>` 中，为关键元素添加 ARIA 属性：

- 在 `<textarea>` 上添加 `aria-label="输入消息"`、`role="textbox"`
- 在 `<button>` 上添加 `aria-label="发送消息"`
- 在发送按钮上添加 `:aria-disabled="isSending || !inputText.trim()"`

在 `<script setup>` 中添加键盘快捷键处理：

```typescript
// 在已有的 keydown 处理中补充 Escape 键
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
  if (event.key === 'Escape') {
    // 聚焦状态下按 Escape 取消输入
    (event.target as HTMLTextAreaElement).blur()
  }
}
```

### 3.4 创建响应式侧边栏更新 `frontend\src\components\ConversationSidebar.vue`

在现有侧边栏组件基础上，添加移动端折叠/展开逻辑。在 `<script setup>` 中添加：

```typescript
import { ref, onMounted, onUnmounted } from 'vue'

const isMobileOpen = ref(false)
const isMobile = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

function toggleSidebar() {
  isMobileOpen.value = !isMobileOpen.value
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
```

在 `<template>` 中，给侧边栏根元素添加 class 绑定：

```vue
<aside class="sidebar" :class="{ 'mobile-open': isMobileOpen, 'mobile-hidden': isMobile && !isMobileOpen }">
```

在 `<style scoped>` 中添加响应式媒体查询：

```css
/* 移动端：侧边栏默认隐藏，通过汉堡菜单切换 */
@media (max-width: 767px) {
  .sidebar {
    position: fixed;
    left: -280px;
    top: 0;
    bottom: 0;
    z-index: 1000;
    width: 280px;
    transition: left 0.25s ease;
    box-shadow: none;
  }

  .sidebar.mobile-open {
    left: 0;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.5);
  }

  .sidebar.mobile-hidden {
    left: -280px;
  }

  /* 移动端遮罩层 */
  .sidebar.mobile-open::after {
    content: '';
    position: fixed;
    inset: 0;
    left: 280px;
    background: rgba(0, 0, 0, 0.4);
    z-index: -1;
  }
}
```

### 3.5 更新 ChatView 添加移动端汉堡菜单按钮

在 `frontend\src\views\ChatView.vue` 的 header 区域，添加移动端菜单按钮：

```vue
<!-- 汉堡菜单按钮（仅移动端显示） -->
<button class="hamburger-btn" @click="toggleSidebar" aria-label="切换侧边栏">
  <span></span>
  <span></span>
  <span></span>
</button>
```

在 `<script setup>` 中添加：

```typescript
const sidebarOpen = ref(false)

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
  // 通过事件通知侧边栏组件
  // 或使用 provide/inject
}
```

在 `<style scoped>` 中添加汉堡菜单样式：

```css
.hamburger-btn {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.4rem;
  flex-direction: column;
  gap: 4px;
}

.hamburger-btn span {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--ink);
  border-radius: 1px;
  transition: transform 0.2s;
}

@media (max-width: 767px) {
  .hamburger-btn {
    display: flex;
  }
}
```

### 3.6 创建性能优化 Composable `frontend\src\composables\useDebounce.ts`

```typescript
/**
 * useDebounce —— 防抖 Composable
 * 用于搜索输入、窗口 resize 等高频事件
 */
import { ref, watch, onUnmounted } from 'vue'

export function useDebounce<T>(source: () => T, delay: number = 300) {
  const debounced = ref(source()) as { value: T }
  let timer: ReturnType<typeof setTimeout> | null = null

  watch(
    source,
    (val) => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        debounced.value = val
      }, delay)
    },
    { immediate: true },
  )

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })

  return debounced
}
```

### 3.7 更新 `vite.config.ts` 添加构建优化

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    // 代码分割：将大型依赖拆分为独立 chunk
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'pinia'],
          'vendor-marked': ['marked', 'highlight.js'],
          'vendor-vueuse': ['@vueuse/core'],
        },
      },
    },
    // 提高 chunk 大小警告阈值（marked + highlight.js 较大）
    chunkSizeWarningLimit: 600,
    // 生成 sourcemap 用于生产环境调试
    sourcemap: false,
  },
  // 开发服务器配置
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
```

### 3.8 在 `index.html` 中添加 SEO 和性能元标签

在 `frontend\index.html` 的 `<head>` 中添加：

```html
<meta name="description" content="DocsChat - 基于 RAG 的智能文档对话系统">
<meta name="theme-color" content="#0d1117">
<link rel="preconnect" href="https://api.deepseek.com">
```

---

## 第四部分：Docker 容器化部署（晚间 2h）

### 4.1 更新后端 Dockerfile `backend\Dockerfile`

用以下内容**替换** `backend\Dockerfile`：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# ── 系统依赖 ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# ── Python 依赖 ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 应用代码 ──
COPY . .

# ── 创建数据目录 ──
RUN mkdir -p /app/chroma_data /app/uploads

# ── 健康检查 ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.2 更新前端 Dockerfile `frontend\Dockerfile`（多阶段构建）

用以下内容**替换** `frontend\Dockerfile`：

```dockerfile
# ── 阶段 1：构建 ──
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── 阶段 2：生产运行 ──
FROM node:20-alpine

WORKDIR /app

# 安装 serve 用于托管静态文件
RUN npm install -g serve

# 复制构建产物
COPY --from=builder /app/dist ./dist

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:5173/ || exit 1

CMD ["serve", "-s", "dist", "-l", "5173"]
```

### 4.3 创建 `.env` 文件 `backend\.env`

```powershell
cd E:\docs-chat\backend
```

如果尚未创建 `.env`，基于 `.env.example` 创建：

```env
DEEPSEEK_API_KEY=sk-your-actual-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
EMBEDDING_MODEL=text-embedding-3-small
```

### 4.4 更新 `docker-compose.yml` 增强生产配置

用以下内容**替换** `docker-compose.yml`：

```yaml
version: "3.9"

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend/uploads:/app/uploads
      - chroma_data:/app/chroma_data
    env_file:
      - ./backend/.env
    environment:
      - CHROMA_PERSIST_DIR=/app/chroma_data
      - UPLOAD_DIR=/app/uploads
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks:
      - docschat-net

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    environment:
      - VITE_API_BASE_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - docschat-net

volumes:
  chroma_data:

networks:
  docschat-net:
    driver: bridge
```

### 4.5 创建 `.dockerignore` 提高构建效率

**`backend\.dockerignore`**：

```
__pycache__
*.pyc
*.pyo
.env.example
.git
.gitignore
tests/
chroma_data/
uploads/*
!uploads/.gitkeep
venv/
.venv/
*.egg-info
```

**`frontend\.dockerignore`**：

```
node_modules
dist
.git
.gitignore
*.md
!README.md
```

### 4.6 创建 `uploads\.gitkeep` 确保目录存在

```powershell
cd E:\docs-chat\backend
New-Item -ItemType File -Path uploads\.gitkeep -Force
```

### 4.7 构建并启动

```powershell
cd E:\docs-chat
docker compose build
docker compose up -d
```

验证服务：

```powershell
# 检查后端健康
curl http://localhost:8000/health

# 查看容器状态
docker compose ps

# 查看日志
docker compose logs -f
```

### 4.8 停止与清理

```powershell
# 停止服务
docker compose down

# 停止并清除数据卷（谨慎操作）
docker compose down -v
```

---

## 第五部分：验收与验证

### 5.1 验收清单

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| 1 | 前端测试通过 | `npx vitest run` | 所有测试用例 PASS |
| 2 | 后端测试通过 | `pytest tests/ -v` | 所有测试用例 PASS |
| 3 | Markdown 渲染无回归 | 发送 Markdown 消息 | 代码高亮、表格等正常渲染 |
| 4 | SSE 连接无回归 | 发送消息 | 流式打字机效果正常 |
| 5 | 骨架屏展示 | 发送消息等待响应 | 显示加载动画 |
| 6 | 移动端响应式 | 缩小浏览器窗口至 375px | 侧边栏隐藏，可汉堡菜单切换 |
| 7 | 键盘无障碍 | Tab 聚焦到输入框、Enter 发送 | 全程无需鼠标可完成对话 |
| 8 | ARIA 属性 | 浏览器开发者工具检查 | 输入框、按钮有 aria-label |
| 9 | Docker 构建 | `docker compose build` | 无错误，构建成功 |
| 10 | Docker 运行 | `docker compose up -d` | 后端 8000、前端 5173 可访问 |
| 11 | 健康检查 | `curl http://localhost:8000/health` | 返回 `{"status":"ok"}` |

### 5.2 常见问题排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `vitest` 找不到 `@vue/test-utils` | 未安装 | `npm install -D @vue/test-utils` |
| `pytest` 找不到 `httpx` | 未安装 | `pip install httpx` |
| 测试中 `crypto.randomUUID` 报错 | jsdom 未提供 | 已在 `setup.ts` 中 mock |
| Docker 构建前端时 `npm ci` 失败 | `package-lock.json` 缺失 | 先 `npm install` 生成 lock 文件 |
| Docker 构建后端时 `gcc` 报错 | slim 镜像缺少编译工具 | 确认 Dockerfile 中有 `apt-get install gcc` 行 |
| 容器间通信失败 | 网络未配置 | 确认 `docker-compose.yml` 中 `networks` 配置正确 |
| `chroma_data` 卷权限问题 | Windows 挂载权限 | 在 Docker Desktop 中设置文件共享 |

### 5.3 测试覆盖率报告

```powershell
# 前端覆盖率
cd E:\docs-chat\frontend
npx vitest run --coverage
# 报告在 coverage/index.html

# 后端覆盖率
cd E:\docs-chat\backend
pip install pytest-cov
pytest tests/ --cov=app --cov-report=html
# 报告在 htmlcov/index.html
```

---

## Day 4 完成标志

- 前端 3 个组件/Composable 测试套件全部通过
- 后端 4 个测试文件覆盖健康检查、LLM 服务、文档上传、SSE 端点
- 骨架屏在流式响应时正常显示
- 移动端（375px 宽）布局正常，侧边栏可折叠
- 全程键盘操作可完成对话（Tab 导航 + Enter 发送）
- `docker compose up` 一键启动成功

完成后，项目结构新增/更新：

```
docs-chat/
├── backend/
│   ├── Dockerfile              ← 更新（生产优化）
│   ├── .dockerignore           ← 新增
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py         ← 新增
│   │   ├── test_health.py      ← 新增
│   │   ├── test_llm_service.py ← 新增
│   │   ├── test_documents.py   ← 新增
│   │   └── test_chat.py        ← 新增
│   └── uploads/
│       └── .gitkeep            ← 新增
├── frontend/
│   ├── Dockerfile              ← 更新（多阶段构建）
│   ├── .dockerignore           ← 新增
│   ├── vitest.config.ts        ← 新增
│   └── src/
│       ├── components/
│       │   ├── LoadingSkeleton.vue         ← 新增
│       │   ├── ConversationSidebar.vue     ← 更新（响应式）
│       │   ├── MessageInput.vue            ← 更新（无障碍）
│       │   └── __tests__/
│       │       ├── ChatMessage.spec.ts     ← 新增
│       │       └── MessageInput.spec.ts    ← 新增
│       ├── composables/
│       │   ├── useDebounce.ts              ← 新增
│       │   └── __tests__/
│       │       └── useSSE.spec.ts          ← 新增
│       ├── views/
│       │   └── ChatView.vue                ← 更新（骨架屏 + 汉堡菜单）
│       └── __tests__/
│           └── setup.ts                    ← 新增
├── docker-compose.yml          ← 更新（健康检查 + 网络）
└── .gitignore                  ← 更新（排除 chroma_data）
```

### Day 4 面试准备要点

1. **为什么需要组件测试？** 组件测试验证 UI 逻辑的正确性，防止重构时引入回归。相比 E2E 测试，组件测试运行快、定位准，适合在 CI 中频繁执行。Vue 生态中 Vitest 是 Vite 的原生测试框架，比 Jest 更快、配置更简单。

2. **SSE 端点如何测试？** SSE 是一种长连接协议，测试时需要验证：响应 Content-Type 为 `text/event-stream`，每行以 `data:` 开头，正确解析 `token`/`source`/`done`/`error` 事件类型。使用 `httpx.AsyncClient` 可以发起异步请求并逐行读取流式响应。

3. **多阶段 Docker 构建的好处？** 构建阶段（builder）包含完整 Node.js 和 npm 依赖，用于编译前端代码。运行阶段只包含编译后的静态文件和一个轻量 serve 工具，镜像体积减少 80% 以上，且不包含源代码和 node_modules，安全性更高。

4. **docker-compose 中的 `depends_on` 和 `healthcheck` 有什么区别？** `depends_on` 只保证容器启动顺序，不等待服务就绪。`healthcheck` 定期检查服务是否真正可用（如 HTTP 200），`condition: service_healthy` 确保依赖服务就绪后才启动当前容器，避免启动顺序导致的连接失败。

5. **前端代码分割（Code Splitting）的原理？** Vite/Rollup 的 `manualChunks` 将第三方依赖拆分为独立文件。用户首次访问时浏览器会缓存这些 vendor chunk，二次访问无需重新下载。这是 Lighthouse 性能评分中"减少 JavaScript 负载"的核心优化手段。

完成后告诉我，进入 Day 5：项目打磨 + 简历素材准备。