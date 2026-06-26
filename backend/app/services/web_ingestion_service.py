"""v4.0: URL 文档站自动抓取入库服务。
基于 Crawl4AI 实现 Sitemap 优先 + 同域受控 BFS 爬取，
产出 Fit Markdown，经代码感知分块后入库。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from app.core.config import settings
from app.models.schemas import DocumentJob
from app.services.ingestion_service import JobStatus

logger = logging.getLogger(__name__)


class WebIngestionService:
    """URL 文档站异步抓取编排服务。

    复用 ingestion_service 的 JobStatus 状态机和
    INGESTION_MAX_CONCURRENT_JOBS 信号量控制并发。
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, dict] = {}
        self._sem = asyncio.Semaphore(settings.INGESTION_MAX_CONCURRENT_JOBS)

    # ── public API ──

    async def ingest_url(
        self, url: str, library_slug: str, version: str = "latest"
    ) -> str:
        """提交文档站 URL，异步抓取入库。返回 job_id。"""
        job_id = uuid4().hex
        now = datetime.now()
        self._jobs[job_id] = {
            "job_id": job_id,
            "library_slug": library_slug,
            "version": version,
            "url": url,
            "status": JobStatus.QUEUED,
            "page_count": 0,
            "chunk_count": 0,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        asyncio.create_task(self._run_job(job_id, url, library_slug, version))
        return job_id

    def get_job(self, job_id: str) -> DocumentJob | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        return DocumentJob(
            job_id=job["job_id"],
            filename=f"{job['library_slug']} ({job['url'][:60]})",
            status=job["status"].value,
            page_count=job["page_count"],
            chunk_count=job["chunk_count"],
            error=job.get("error"),
            created_at=job["created_at"],
            updated_at=job["updated_at"],
        )

    def list_jobs(self) -> list[DocumentJob]:
        return [self.get_job(jid) for jid in self._jobs if self._jobs[jid]]

    # ── internal helpers ──

    def _mark(self, job_id: str, status: JobStatus) -> None:
        self._jobs[job_id]["status"] = status
        self._jobs[job_id]["updated_at"] = datetime.now()

    async def _run_job(
        self, job_id: str, url: str, library_slug: str, version: str
    ) -> None:
        """异步管道: sitemap→抓取→分块→质量门禁→入库→BM25 按库重建"""
        async with self._sem:
            self._mark(job_id, JobStatus.RUNNING)
            try:
                # 1. 解析 URL 清单
                urls = await self._resolve_urls(url)

                # 2. Crawl4AI 抓取
                pages = await self._crawl(urls)
                if not pages:
                    raise ValueError("抓取未产出任何页面，请检查目标站点是否可访问")

                # 3. 代码感知分块
                from app.services.markdown_chunker import markdown_chunker

                all_chunks = []
                for page in pages:
                    chunks = markdown_chunker.split(
                        markdown=page["markdown"],
                        source_url=page["url"],
                        library=library_slug,
                        version=version,
                        document_name=page.get("title", library_slug),
                    )
                    all_chunks.extend(chunks)

                if not all_chunks:
                    raise ValueError("分块后无有效内容")

                # 4. 质量门禁
                from app.services.quality_gate import quality_gate

                qg_report = quality_gate.validate(
                    document_name=library_slug,
                    chunks=all_chunks,
                    markdown_source="\n\n".join(p["markdown"] for p in pages),
                )
                logger.info(
                    "质量门禁 [%s]: passed=%s chunks=%d",
                    library_slug, qg_report.passed, len(all_chunks),
                )

                # 5. 增量检查（跳过未变更页）
                from app.services.vector_store import vector_store

                existing_lib_chunks = await asyncio.to_thread(
                    vector_store.get_library_chunks, library_slug
                )
                existing_urls = {c.get("source_url") for c in existing_lib_chunks}
                new_chunks = [
                    c for c in all_chunks
                    if getattr(c, "source_url", "") not in existing_urls
                ]
                if new_chunks:
                    logger.info(
                        "增量摄取: %d/%d 个新页面对 %d chunks",
                        len({c.source_url for c in new_chunks}),
                        len(pages),
                        len(new_chunks),
                    )
                else:
                    logger.info(
                        "所有 %d 页已在库中，仅重建索引", len(pages)
                    )
                    # 无新页但仍标记为 ready
                    self._jobs[job_id]["page_count"] = len(pages)
                    self._jobs[job_id]["chunk_count"] = len(existing_lib_chunks)
                    self._mark(job_id, JobStatus.READY)
                    return

                # 6. 入库
                self._jobs[job_id]["page_count"] = len(pages)
                self._jobs[job_id]["chunk_count"] = await asyncio.to_thread(
                    vector_store.add_chunks, new_chunks
                )

                # 7. 按库重建 BM25
                from app.services.retrieval_service import retrieval_service

                lib_chunks = await asyncio.to_thread(
                    vector_store.get_library_chunks, library_slug
                )
                await asyncio.to_thread(
                    retrieval_service.build_bm25_index, lib_chunks, library=library_slug
                )

                self._mark(job_id, JobStatus.READY)
                logger.info(
                    "URL 摄取完成: library=%s pages=%d chunks=%d",
                    library_slug, len(pages), self._jobs[job_id]["chunk_count"],
                )

            except Exception as exc:
                logger.exception(
                    "URL 摄取失败: job=%s library=%s", job_id, library_slug
                )
                self._jobs[job_id]["error"] = str(exc)
                self._mark(job_id, JobStatus.FAILED)

    async def _resolve_urls(self, url: str) -> list[str]:
        """Sitemap 优先解析，无 sitemap 则退回单 URL 触发 BFS。"""
        sitemap_url = urljoin(url.rstrip("/"), "/sitemap.xml")
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(sitemap_url)
                if resp.status_code == 200 and "<?xml" in resp.text[:200]:
                    import advertools as adv

                    df = adv.sitemap_to_df(resp.text)
                    if "loc" in df.columns and len(df) > 0:
                        urls = df["loc"].dropna().tolist()
                        limited = urls[: settings.WEB_INGEST_MAX_PAGES]
                        logger.info(
                            "Sitemap: %d URLs, 使用 %d 条", len(urls), len(limited)
                        )
                        return limited
        except Exception as exc:
            logger.info("Sitemap 解析失败 (将使用 BFS): %s", exc)

        return [url]

    async def _crawl(self, urls: list[str]) -> list[dict]:
        """调用 Crawl4AI 抓取页面，返回 [{url, markdown, title}]。

        - 单 URL 模式: BFSDeepCrawlStrategy 同域搜索
        - 多 URL 模式: 逐个直接抓取（sitemap 已给清单）
        """
        try:
            from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
            from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
            from crawl4ai.content_filter_strategy import PruningContentFilter
        except ImportError:
            raise RuntimeError(
                "crawl4ai 未安装，请运行: pip install crawl4ai && crawl4ai-setup"
            )

        prune_filter = PruningContentFilter(threshold=0.48, threshold_type="fixed")
        markdown_gen = DefaultMarkdownGenerator(content_filter=prune_filter)

        if len(urls) == 1:
            return await self._crawl_bfs(urls[0], markdown_gen)
        else:
            return await self._crawl_direct(urls, markdown_gen)

    async def _crawl_bfs(self, seed_url: str, markdown_gen) -> list[dict]:
        """BFS 深度爬取（单 URL 种子模式）。"""
        try:
            from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
            from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
            from crawl4ai.deep_crawling.filters import FilterChain, DomainFilter
        except ImportError:
            raise RuntimeError("crawl4ai deep_crawling 模块不可用")

        domain = urlparse(seed_url).netloc

        strategy = BFSDeepCrawlStrategy(
            max_depth=settings.WEB_INGEST_MAX_DEPTH,
            max_pages=settings.WEB_INGEST_MAX_PAGES,
            include_external=False,
            filter_chain=FilterChain([DomainFilter(allowed_domains=[domain])]),
        )

        config = CrawlerRunConfig(
            deep_crawl_strategy=strategy,
            markdown_generator=markdown_gen,
            cache_mode=CacheMode.BYPASS,
        )

        async with AsyncWebCrawler() as crawler:
            results = await crawler.arun(seed_url, config=config)
            if not isinstance(results, list):
                results = [results]

            pages = []
            for r in results:
                if r.success and r.markdown and r.markdown.fit_markdown:
                    pages.append({
                        "url": r.url,
                        "markdown": r.markdown.fit_markdown.strip(),
                        "title": getattr(getattr(r, "metadata", None), "title", "")
                                 or r.url.rsplit("/", 2)[-1],
                    })
            logger.info("BFS 抓取: %d pages from %s", len(pages), domain)
            return pages

    async def _crawl_direct(self, urls: list[str], markdown_gen) -> list[dict]:
        """直接抓取已知 URL 列表（Sitemap 模式）。"""
        from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

        config = CrawlerRunConfig(
            markdown_generator=markdown_gen,
            cache_mode=CacheMode.BYPASS,
        )

        pages: list[dict] = []
        async with AsyncWebCrawler() as crawler:
            for url in urls:
                if len(pages) >= settings.WEB_INGEST_MAX_PAGES:
                    break
                try:
                    result = await crawler.arun(url, config=config)
                    if result.success and result.markdown and result.markdown.fit_markdown:
                        pages.append({
                            "url": url,
                            "markdown": result.markdown.fit_markdown.strip(),
                            "title": getattr(getattr(result, "metadata", None), "title", "")
                                     or url.rsplit("/", 2)[-1],
                        })
                    else:
                        logger.warning("抓取失败: %s", url)
                except Exception as exc:
                    logger.warning("抓取异常 %s: %s", url, exc)
                    continue

        logger.info("直接抓取: %d/%d 成功", len(pages), len(urls))
        return pages


# 全局单例
web_ingestion_service = WebIngestionService()
