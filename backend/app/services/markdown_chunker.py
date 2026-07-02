"""v4.0: 代码感知 Markdown 分块器。
两阶段分块策略：
1. 结构切分：MarkdownHeaderTextSplitter 按 h1/h2/h3 切出语义单元，保留 heading_path
2. 代码保护：围栏代码块视为原子单元不拆分，超长代码块单独成 chunk
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Dict, List, Tuple

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.document_service import DocumentChunk

logger = logging.getLogger(__name__)

# 围栏代码块正则: ```language\ncode\n```
_CODE_BLOCK_RE = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)

_HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]


class MarkdownChunker:
    """代码感知 Markdown 分块器。

    产出 DocumentChunk 时自动填充 library/version/source_url/heading_path/
    code_language/is_code_block 等 v4.0 元数据。
    """

    def __init__(self) -> None:
        self._header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=_HEADERS_TO_SPLIT_ON,
            strip_headers=False,
        )

    # ── public ──

    def split(
        self,
        markdown: str,
        source_url: str = "",
        library: str = "",
        version: str = "latest",
        document_name: str = "",
        created_at: str = "",  # v4.5
    ) -> list[DocumentChunk]:
        """主入口：Markdown 文本 → DocumentChunk 列表。"""
        if not markdown or not markdown.strip():
            return []

        # 1. 保护代码块
        protected_text, code_blocks = self._protect_code_blocks(markdown)

        # 2. MarkdownHeaderTextSplitter 按标题切分
        try:
            sections = self._header_splitter.split_text(protected_text)
        except Exception:
            logger.warning("MarkdownHeaderTextSplitter 失败，回退纯文本分块")
            sections = [type("_S", (), {"page_content": markdown, "metadata": {}})()]

        # 3. 对每个 section 做代码感知分块
        chunks: list[DocumentChunk] = []
        chunk_index = 0
        section_with_doc: list[tuple[object, str]] = []
        # 如果只有一个 section 且没有标题元数据，直接处理
        if len(sections) == 1 and not any(
            sections[0].metadata.get(h, "") for h in ("h1", "h2", "h3")
        ):
            section_with_doc = [(s, document_name) for s in sections]
        else:
            section_with_doc = [(s, document_name) for s in sections]

        for section, _doc_name in section_with_doc:
            section_text = section.page_content if hasattr(section, "page_content") else str(section)
            heading_path = self._build_heading_path(section.metadata if hasattr(section, "metadata") else {})

            if not section_text.strip():
                continue

            # 恢复代码块
            restored_text = self._restore_code_blocks(section_text, code_blocks)

            # 4. 分离代码块和文本块
            section_chunks = self._split_section(
                text=restored_text,
                heading_path=heading_path,
                source_url=source_url,
                library=library,
                version=version,
                document_name=_doc_name,
                created_at=created_at,
            )

            for ch in section_chunks:
                ch.chunk_index = chunk_index
                chunks.append(ch)
                chunk_index += 1

        logger.info(
            "代码感知分块: %d chars → %d chunks (library=%s)",
            len(markdown), len(chunks), library,
        )
        return chunks

    # ── static helpers ──

    @staticmethod
    def _make_chunk_id(
        library: str, source_url: str, heading_path: str, content: str
    ) -> str:
        """v4.0: 确定性 chunk_id（sha256），用于 upsert 去重。"""
        raw = f"{library}|{source_url}|{heading_path}|{content[:200]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def _build_heading_path(meta: dict) -> str:
        """从 Markdown 标题元数据构建 breadcrumb 路径。

        例如 {"h1": "Guide", "h2": "Reactivity"} → "Guide > Reactivity"
        """
        parts = []
        for key in ("h1", "h2", "h3"):
            val = meta.get(key, "")
            if val:
                parts.append(str(val))
        return " > ".join(parts) if parts else ""

    # ── internal ──

    def _protect_code_blocks(self, text: str) -> Tuple[str, Dict[str, dict]]:
        """提取围栏代码块，替换为占位符。

        Returns:
            (protected_text, {placeholder_id: {lang: str, code: str}})
        """
        code_blocks: Dict[str, dict] = {}

        def _replace(match):
            placeholder_id = f"__CODE_BLOCK_{len(code_blocks)}__"
            lang = match.group(1) or ""
            code = match.group(2)
            code_blocks[placeholder_id] = {"lang": lang, "code": code}
            return f"\n\n{placeholder_id}\n\n"

        protected = _CODE_BLOCK_RE.sub(_replace, text)
        return protected, code_blocks

    def _restore_code_blocks(
        self, text: str, code_blocks: Dict[str, dict]
    ) -> str:
        """将占位符还原为代码块标记。"""
        restored = text
        for pid, info in code_blocks.items():
            lang = info["lang"]
            code = info["code"]
            restored = restored.replace(pid, f"```{lang}\n{code}\n```")
        return restored

    def _split_section(
        self,
        text: str,
        heading_path: str,
        source_url: str,
        library: str,
        version: str,
        document_name: str,
        created_at: str = "",
    ) -> list[DocumentChunk]:
        """对单个 section 做代码感知递归分块。"""
        chunks: list[DocumentChunk] = []

        # 分离代码块和普通文本
        parts = self._extract_parts(text)

        current_text_parts: list[str] = []

        for part_type, content, code_lang in parts:
            if part_type == "code":
                # 先处理累积的文本
                if current_text_parts:
                    text_chunks = self._split_text_parts(
                        current_text_parts, heading_path, source_url,
                        library, version, document_name, created_at,
                    )
                    chunks.extend(text_chunks)
                    current_text_parts = []

                # 代码块作为原子 chunk
                code_chunk = self._make_code_chunk(
                    content, code_lang, heading_path, source_url,
                    library, version, document_name, created_at,
                )
                chunks.append(code_chunk)
            else:
                current_text_parts.append(content)

        # 处理剩余文本
        if current_text_parts:
            text_chunks = self._split_text_parts(
                current_text_parts, heading_path, source_url,
                library, version, document_name, created_at,
            )
            chunks.extend(text_chunks)

        return chunks

    def _extract_parts(self, text: str) -> list[Tuple[str, str, str]]:
        """从文本中提取代码块和普通文本的交替序列。

        Returns: list of (type, content, code_language)
            type ∈ {"text", "code"}
        """
        parts: list[Tuple[str, str, str]] = []
        last_end = 0

        for match in _CODE_BLOCK_RE.finditer(text):
            # 代码块之前的文本
            before = text[last_end:match.start()]
            if before.strip():
                parts.append(("text", before, ""))

            # 代码块
            lang = match.group(1) or ""
            code = match.group(2)
            parts.append(("code", code, lang))

            last_end = match.end()

        # 尾随文本
        remaining = text[last_end:]
        if remaining.strip():
            parts.append(("text", remaining, ""))

        return parts

    def _split_text_parts(
        self,
        text_parts: list[str],
        heading_path: str,
        source_url: str,
        library: str,
        version: str,
        document_name: str,
        created_at: str = "",
    ) -> list[DocumentChunk]:
        """对普通文本部分用 RecursiveCharacterTextSplitter 切分。"""
        combined = "\n\n".join(text_parts)
        if not combined.strip():
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["```", "\n\n", "\n", "。", "！", "？", "；", " ", ""],
            length_function=len,
        )

        splits = text_splitter.split_text(combined)
        chunks: list[DocumentChunk] = []
        for split_text in splits:
            if not split_text.strip():
                continue
            chunk_id = self._make_chunk_id(library, source_url, heading_path, split_text)
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                content=split_text,
                document_name=document_name or library,
                page=0,
                chunk_index=0,  # will be set by caller
                source_url=source_url,
                library=library,
                version=version,
                heading_path=heading_path,
                code_language="",
                is_code_block=False,
                created_at=created_at,
            ))
        return chunks

    def _make_code_chunk(
        self,
        code: str,
        code_language: str,
        heading_path: str,
        source_url: str,
        library: str,
        version: str,
        document_name: str,
        created_at: str = "",
    ) -> DocumentChunk:
        """创建代码块专用 DocumentChunk。"""
        # 超长代码块截断但保持标记
        content = code.strip()
        if len(content) > settings.MAX_CHUNK_CHARS:
            content = content[:settings.MAX_CHUNK_CHARS] + "\n# ... (truncated)"

        chunk_id = self._make_chunk_id(library, source_url, heading_path, content)
        return DocumentChunk(
            chunk_id=chunk_id,
            content=content,
            document_name=document_name or library,
            page=0,
            chunk_index=0,
            source_url=source_url,
            library=library,
            version=version,
            heading_path=heading_path,
            code_language=code_language,
            is_code_block=True,
            created_at=created_at,
        )


# 全局单例
markdown_chunker = MarkdownChunker()
