"""预置示例文档库脚本。

从本地 Markdown 文件入库一套精简的 Vue 3 指南，
让新人无需爬取外部网站即可体验完整功能。

用法:
    cd backend
    python ../scripts/seed_example_library.py

入库内容:
    - Vue 3 响应式基础（ref / reactive / computed / watch）
    - 组合式 API 概述
    - 生命周期钩子
    约 20-30 个 chunk，覆盖事实/概念/综合/代码四类查询。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保 backend 在 sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.markdown_chunker import markdown_chunker
from app.services.vector_store import vector_store
from app.services.retrieval_service import retrieval_service


SEED_DOC = Path(__file__).resolve().parent / "seed_docs" / "vue3-guide.md"
LIBRARY_SLUG = "vue"
VERSION = "3"
SOURCE_URL = "https://vuejs.org/guide/reactivity/"


async def seed():
    """入库 Vue 3 指南示例库。"""
    if not SEED_DOC.exists():
        print(f"[ERROR] 种子文档不存在: {SEED_DOC}")
        return

    markdown = SEED_DOC.read_text(encoding="utf-8")
    print(f"[1/4] 读取种子文档: {len(markdown)} 字符")

    chunks = markdown_chunker.split(
        markdown,
        source_url=SOURCE_URL,
        library=LIBRARY_SLUG,
        version=VERSION,
    )
    print(f"[2/4] 代码感知分块: {len(chunks)} chunks")
    code_chunks = [c for c in chunks if getattr(c, "is_code_block", False)]
    print(f"      代码块: {len(code_chunks)}, 文本块: {len(chunks) - len(code_chunks)}")

    added = vector_store.add_chunks(chunks)
    print(f"[3/4] 入库 ChromaDB: {added} chunks (upsert)")

    # 构建 BM25 索引
    lib_chunks = vector_store.get_library_chunks(LIBRARY_SLUG)
    retrieval_service.build_bm25_index(lib_chunks, library=LIBRARY_SLUG)
    print(f"[4/4] BM25 索引构建: {len(lib_chunks)} chunks for library='{LIBRARY_SLUG}'")

    # 验证
    libs = vector_store.get_libraries()
    print(f"\n已入库的文档库:")
    for lib in libs:
        print(f"  - {lib['library']}@{lib['version']}: {lib['chunk_count']} chunks")

    print(f"\n示例库就绪! 现在可以提问:")
    print(f'  curl -X POST http://localhost:8000/chat/stream \\')
    print(f'    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"message": "what is ref() in Vue", "library": "{LIBRARY_SLUG}"}}\'')


if __name__ == "__main__":
    asyncio.run(seed())
