/**
 * useMarkdown — 将 Markdown 文本渲染为 HTML
 * 支持代码高亮、表格、GFM 语法、代码块一键复制
 *
 * 采用 post-processing 方案而非 marked.use() renderer 覆盖：
 * marked v18 的 renderer 对象字面量在 use() 中存在兼容性风险，
 * 后处理方案更稳定且不依赖 marked 内部 API。
 */
import { marked } from 'marked'
import hljs from 'highlight.js'

// ── 配置 marked 基础选项 ──
marked.setOptions({ gfm: true, breaks: true })

// ── HTML 实体解码 ──
function decodeHtml(text: string): string {
  return text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/g, "'")
}

// ── 全局自增 copy 按钮 ID ──
let copyBtnCounter = 0

export function useMarkdown() {
  function render(markdown: string): string {
    if (!markdown) return ''

    try {
      let html = marked.parse(markdown) as string

      // ── 后处理 1：代码块高亮 + 语言标签 + 复制按钮 ──
      // marked 输出的代码块格式:
      //   <pre><code class="language-python">转义后的代码</code></pre>
      //   或 <pre><code>代码</code></pre>
      html = html.replace(
        /<pre><code(?:\s+class="language-(\w+)")?>([\s\S]*?)<\/code><\/pre>/g,
        (_, lang, escapedCode) => {
          const code = decodeHtml(escapedCode)
          const validLang = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
          let highlighted: string
          try {
            highlighted = hljs.highlight(code, { language: validLang }).value
          } catch {
            highlighted = code.replace(/</g, '&lt;').replace(/>/g, '&gt;')
          }
          const copyBtnId = `copy-btn-${++copyBtnCounter}`
          const langLabel = validLang !== 'plaintext' ? validLang : ''
          return [
            `<div class="code-block-wrapper">`,
            langLabel ? `<span class="code-lang-label">${langLabel}</span>` : '',
            `<button class="copy-btn" id="${copyBtnId}" onclick="
              (function(){
                var btn=document.getElementById('${copyBtnId}');
                var code=btn.parentElement.querySelector('code');
                var text=code.textContent||code.innerText;
                navigator.clipboard.writeText(text).then(function(){
                  btn.textContent='已复制!';
                  setTimeout(function(){btn.textContent='复制代码';},2000);
                });
              })()
            ">复制代码</button>`,
            `<pre><code class="hljs language-${validLang}">${highlighted}</code></pre>`,
            `</div>`,
          ].join('')
        },
      )

      // ── 后处理 2：行内代码样式 ──
      // 注意：只替换不在 <pre> 内的行内 <code>
      html = html.replace(
        /(?<!<pre[^>]*>)(?<!<code[^>]*>)<code>([^<]+)<\/code>(?!<\/pre>)/g,
        '<code class="inline-code">$1</code>',
      )

      // ── 后处理 3：引用来源角标 [N] → <sup> ──
      // 使用更精确的匹配：
      // - 不在 HTML 标签属性内
      // - 不替换已在 <sup> 内的角标
      // - 不替换类似 Markdown 图片语法的 ![N]
      html = html.replace(
        /(?<!<sup class="citation">)(?<!!)\[(\d+)\](?!<\/sup>)/g,
        '<sup class="citation" data-citation="$1">[$1]</sup>',
      )

      return html
    } catch {
      return markdown
    }
  }

  return { render }
}
