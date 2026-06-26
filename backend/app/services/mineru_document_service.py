"""MinerU 兼容文档解析服务。

v3.3 升级:
- 语义分块前置化: 先按句子 Embedding 相似度找语义边界，在边界处切分，
  替代旧版"盲切后合并"（合并无法修复已拦腰截断的句子）
- 按场景自动选择: MinerU (标题层级) → 语义前置分块; PyPDF (盲切) → 传统固定大小

支持三种解析路径（按优先级）:
1. mineru_api: 通过 HTTP API 调用远程 MinerU 服务
2. mineru:      本地 subprocess 执行 magic-pdf CLI
3. pypdf:       PyPDF2 纯文本解析（兜底降级）
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import List

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

from app.core.config import settings
from app.services.document_service import DocumentChunk

logger = logging.getLogger(__name__)


class MinerUDocumentService:
    """PDF -> Markdown/文本 -> 层级 chunk 的解析服务。"""

    def __init__(self) -> None:
        self.upload_dir = settings.UPLOAD_DIR
        self.output_dir = Path(settings.MINERU_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def load_and_split(self, file_path: Path) -> List[DocumentChunk]:
        """主入口：按 PARSER_TYPE / MINERU_URL 选择解析路径。"""
        parser_type = settings.PARSER_TYPE

        if parser_type == "mineru" and settings.MINERU_URL:
            try:
                markdown = await self._parse_with_mineru_api(file_path)
                if markdown:
                    chunks = self._split_markdown(markdown, file_path.name)
                    if chunks:
                        logger.info("MinerU API 解析成功: %s chunks=%s", file_path.name, len(chunks))
                        return chunks
                logger.warning("MinerU API 输出为空，尝试 CLI 降级: %s", file_path)
            except Exception as exc:
                logger.exception("MinerU API 解析失败，尝试 CLI 降级: %s", exc)

        if parser_type == "mineru" and settings.MINERU_COMMAND:
            try:
                markdown = await self._parse_with_mineru(file_path)
                chunks = self._split_markdown(markdown, file_path.name)
                if chunks:
                    logger.info("MinerU CLI 解析成功: %s chunks=%s", file_path.name, len(chunks))
                    return chunks
                logger.warning("MinerU 输出为空，回退 PyPDFLoader: %s", file_path)
            except Exception as exc:
                logger.exception("MinerU 解析失败，回退 PyPDFLoader: %s", exc)

        chunks = await asyncio.to_thread(self._parse_with_pypdf, file_path)
        logger.info("PyPDF 解析完成: %s chunks=%s", file_path.name, len(chunks))
        return chunks

    # ═══ MinerU HTTP API ═══

    async def _parse_with_mineru_api(self, file_path: Path) -> str:
        if not settings.MINERU_URL:
            raise RuntimeError("PARSER_TYPE=mineru 需要配置 MINERU_URL")

        import httpx
        api_url = settings.MINERU_URL.rstrip("/")
        logger.info("调用 MinerU API: %s file=%s effort=%s", api_url, file_path.name, settings.MINERU_EFFORT)

        async with httpx.AsyncClient(timeout=float(settings.MINERU_API_TIMEOUT)) as client:
            with file_path.open("rb") as f:
                resp = await client.post(
                    f"{api_url}/api/v1/parse",
                    files={"file": (file_path.name, f, "application/pdf")},
                    data={
                        "backend": settings.MINERU_BACKEND,
                        "effort": settings.MINERU_EFFORT,
                        "output_format": "markdown",
                    },
                )
            if resp.status_code != 200:
                with file_path.open("rb") as f:
                    resp = await client.post(
                        f"{api_url}/parse",
                        files={"file": (file_path.name, f, "application/pdf")},
                    )
                if resp.status_code != 200:
                    raise RuntimeError(f"MinerU API 返回 {resp.status_code}: {resp.text[:500]}")

            data = resp.json()
            markdown = data.get("markdown") or data.get("content") or data.get("text", "")
            if not markdown:
                raise RuntimeError("MinerU API 返回空 markdown")
            return str(markdown)

    async def check_mineru_api_health(self) -> dict:
        if not settings.MINERU_URL:
            return {"available": False, "reason": "MINERU_URL 未配置"}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.MINERU_URL.rstrip('/')}/health",
                    headers={"Accept": "application/json"},
                )
                return {"available": resp.status_code < 500, "status_code": resp.status_code}
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

    # ═══ MinerU CLI ═══

    async def _parse_with_mineru(self, file_path: Path) -> str:
        if not settings.MINERU_COMMAND:
            raise RuntimeError("DOCUMENT_PARSER=mineru 需要配置 MINERU_COMMAND")

        target_dir = self.output_dir / file_path.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        command = settings.MINERU_COMMAND.format(
            input=str(file_path),
            output=str(target_dir),
            backend=settings.MINERU_BACKEND,
            effort=settings.MINERU_EFFORT,
        )
        logger.info("执行 MinerU 命令: %s", command)

        completed = await asyncio.to_thread(
            subprocess.run, shlex.split(command),
            capture_output=True, text=True, timeout=1800, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "MinerU 命令执行失败")

        markdown_files = sorted(
            target_dir.rglob("*.md"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not markdown_files:
            raise FileNotFoundError(f"MinerU 未在 {target_dir} 生成 Markdown")
        return markdown_files[0].read_text(encoding="utf-8")

    # ═══ PyPDF (兜底) ═══

    def _parse_with_pypdf(self, file_path: Path) -> List[DocumentChunk]:
        loader = PyPDFLoader(str(file_path))
        raw_docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            length_function=len,
        )
        split_docs = splitter.split_documents(raw_docs)
        chunks: List[DocumentChunk] = []
        for idx, doc in enumerate(split_docs):
            content = doc.page_content.strip()
            if len(content) < settings.MIN_CHUNK_CHARS:
                continue
            chunks.append(DocumentChunk(
                chunk_id=hashlib.sha256(
                    f"{file_path.name}|{file_path}|{idx}|{content[:200]}".encode()
                ).hexdigest()[:32],
                content=content,
                document_name=file_path.name,
                page=int(doc.metadata.get("page", 0)) + 1,
                chunk_index=idx,
                metadata={
                    "source": doc.metadata.get("source", ""),
                    "total_pages": len(raw_docs),
                    "parser": "pypdf",
                },
            ))
        return chunks

    # ═══ Markdown 分块（v3.3: 语义分块前置化）═══

    def _split_markdown(self, markdown: str, document_name: str) -> List[DocumentChunk]:
        """v3.3: 语义分块前置化。

        流程: Markdown → 按标题层级分节 → 每节按句子拆分 → Embedding 找语义边界
              → 在边界处切分 → 产出 chunk

        标题边界 + 语义边界 双重保障，不会拦腰截断句子。
        """
        sections = self._markdown_sections(markdown)
        if not sections and markdown.strip():
            sections = [{"h1": "", "h2": "", "h3": "", "content": markdown, "page": 0}]

        all_sub_sections: list[dict] = []
        for section in sections:
            content = section["content"].strip()
            if len(content) < settings.MIN_CHUNK_CHARS:
                continue
            # v3.3: 按句子拆分为子节
            subs = self._split_into_sentences(content)
            for sub in subs:
                if len(sub) >= settings.MIN_CHUNK_CHARS:
                    all_sub_sections.append({**section, "content": sub})

        if not all_sub_sections:
            return []

        # v3.3: 语义边界检测（前置）
        if settings.SEMANTIC_CHUNK_ENABLED and len(all_sub_sections) >= 2:
            all_sub_sections = self._merge_by_semantic_boundaries(
                all_sub_sections, document_name
            )

        # 二次处理：超长 section 递归切分
        chunks: List[DocumentChunk] = []
        for idx, section in enumerate(all_sub_sections):
            content = section["content"].strip()
            if len(content) > settings.MAX_CHUNK_CHARS:
                sub_chunks = self._split_long_section(
                    content=content, document_name=document_name,
                    base_page=section.get("page", 0),
                    h1=section.get("h1", ""),
                    h2=section.get("h2", ""),
                    h3=section.get("h3", ""),
                )
                chunks.extend(sub_chunks)
            else:
                chunks.append(self._make_chunk(
                    content=content, document_name=document_name,
                    page=section.get("page", 0), chunk_index=idx,
                    h1=section.get("h1", ""), h2=section.get("h2", ""),
                    h3=section.get("h3", ""),
                ))

        return chunks

    def _split_into_sentences(self, text: str) -> list[str]:
        """v3.3: 将文本按句子边界拆分。"""
        raw = re.split(r'(?<=[。！？\n])\s*', text)
        sentences = [s.strip() for s in raw if s.strip()]
        if len(sentences) <= 1:
            return [text]
        # 合并过短句子到上一句或形成足够大的块
        merged: list[str] = []
        buf = ""
        for s in sentences:
            combined = buf + s
            if len(combined) >= settings.MIN_CHUNK_CHARS:
                if buf:
                    merged.append(buf.strip())
                buf = s
            else:
                buf = combined
        if buf.strip():
            if merged:
                merged[-1] = merged[-1] + " " + buf.strip()
            else:
                merged.append(buf.strip())
        return merged if merged else [text]

    def _merge_by_semantic_boundaries(
        self,
        sections: list[dict],
        document_name: str,
    ) -> list[dict]:
        """v3.3: 语义分块前置化核心。

        先计算所有相邻 section 的 Embedding 相似度，
        找到语义边界（相似度骤降处），在边界处保持分块，
        连续相似 section 合并。

        与 v3.2 的关键区别:
        v3.2: 盲切出 chunk → 后置合并（已断的句子无法修复）
        v3.3: 先找语义边界 → 在边界处切分（从未断句）
        """
        if len(sections) < 2:
            return sections

        try:
            from app.services.vector_store import vector_store

            texts = [s["content"][:2000] for s in sections]
            embeddings = vector_store.embedding_function(texts)

            merged_sections: list[dict] = [sections[0]]
            current_buf = sections[0]["content"]

            for i in range(1, len(sections)):
                prev_emb = np.array(embeddings[i - 1])
                curr_emb = np.array(embeddings[i])
                similarity = float(
                    np.dot(prev_emb, curr_emb)
                    / (np.linalg.norm(prev_emb) * np.linalg.norm(curr_emb) + 1e-8)
                )

                if similarity >= settings.SEMANTIC_CHUNK_THRESHOLD:
                    # 语义连续 → 合并当前内容
                    current_buf += "\n\n" + sections[i]["content"]
                    # 更新最后一个 merged section 的内容
                    merged_sections[-1]["content"] = current_buf
                else:
                    # 语义断点 → 新 chunk
                    merged_sections.append(sections[i])
                    current_buf = sections[i]["content"]

            logger.info(
                "语义前置分块: %d sections → %d chunks (threshold=%.2f)",
                len(sections), len(merged_sections), settings.SEMANTIC_CHUNK_THRESHOLD,
            )
            return merged_sections

        except Exception as exc:
            logger.warning("语义前置分块不可用，使用原始分节: %s", exc)
            return sections

    def _split_long_section(
        self, content: str, document_name: str,
        base_page: int, h1: str, h2: str, h3: str,
    ) -> List[DocumentChunk]:
        """对超过 MAX_CHUNK_CHARS 的 section 按自然段落二次切分。"""
        max_chars = settings.MAX_CHUNK_CHARS
        sentences = re.split(r'(?<=[。！？\n])\s*', content)
        sub_chunks: List[DocumentChunk] = []
        current_buf: list[str] = []
        current_len = 0

        for sent in sentences:
            sent_len = len(sent)
            if not sent.strip():
                continue
            if current_len + sent_len > max_chars and current_buf:
                sub_chunks.append(self._make_chunk(
                    content="".join(current_buf).strip(),
                    document_name=document_name, page=base_page,
                    chunk_index=len(sub_chunks),
                    h1=h1, h2=h2, h3=h3,
                ))
                current_buf = [sent]
                current_len = sent_len
            else:
                current_buf.append(sent)
                current_len += sent_len

        if current_buf:
            sub_chunks.append(self._make_chunk(
                content="".join(current_buf).strip(),
                document_name=document_name, page=base_page,
                chunk_index=len(sub_chunks),
                h1=h1, h2=h2, h3=h3,
            ))

        logger.info("长 section 二次切分: %d chars → %d sub-chunks", len(content), len(sub_chunks))
        return sub_chunks

    def _make_chunk(
        self, content: str, document_name: str,
        page: int, chunk_index: int,
        h1: str = "", h2: str = "", h3: str = "",
    ) -> DocumentChunk:
        breadcrumb = self._build_breadcrumb({"h1": h1, "h2": h2, "h3": h3})
        return DocumentChunk(
            chunk_id=hashlib.sha256(
                f"{document_name}|{breadcrumb}|{chunk_index}|{content[:200]}".encode()
            ).hexdigest()[:32],
            content=content,
            document_name=document_name, page=page,
            chunk_index=chunk_index,
            metadata={
                "parser": "mineru",
                "h1": h1, "h2": h2, "h3": h3,
                "breadcrumb": breadcrumb,
            },
        )

    @staticmethod
    def _build_breadcrumb(section: dict) -> str:
        parts = [section.get(k, "") for k in ("h1", "h2", "h3") if section.get(k)]
        return " > ".join(parts)

    def _markdown_sections(self, markdown: str) -> list[dict]:
        current = {"h1": "", "h2": "", "h3": "", "content": "", "page": 0}
        sections: list[dict] = []
        for line in markdown.splitlines():
            heading = re.match(r"^(#{1,3})\s+(.+)$", line)
            if heading and current["content"].strip():
                sections.append(current.copy())
                current["content"] = ""
            if heading:
                level = len(heading.group(1))
                title = heading.group(2).strip()
                if level == 1:
                    current.update({"h1": title, "h2": "", "h3": ""})
                elif level == 2:
                    current.update({"h2": title, "h3": ""})
                else:
                    current["h3"] = title
            current["content"] += line + "\n"
        if current["content"].strip():
            sections.append(current.copy())
        if not sections and markdown.strip():
            sections.append({"h1": "", "h2": "", "h3": "", "content": markdown, "page": 0})
        return sections


# 全局单例
mineru_document_service = MinerUDocumentService()
