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