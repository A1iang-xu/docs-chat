"""文档质量门禁 —— 验证 MinerU/PyPDF 解析输出的完整性。"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """单篇文档的质量评估结果。"""
    document_name: str
    total_chars: int = 0
    heading_count: int = 0
    table_count: int = 0
    page_count: int = 0
    chunk_count: int = 0
    passed: bool = True
    checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_name": self.document_name,
            "total_chars": self.total_chars,
            "heading_count": self.heading_count,
            "table_count": self.table_count,
            "page_count": self.page_count,
            "chunk_count": self.chunk_count,
            "passed": self.passed,
            "checks": self.checks,
            "warnings": self.warnings,
        }


class QualityGate:
    """文档解析结果质量校验器。所有检查项可独立开关。"""

    @property
    def enabled(self) -> bool:
        from app.core.config import settings
        return settings.QG_ENABLED

    def validate(self, document_name: str, chunks: list, markdown_source: str = "") -> QualityReport:
        report = QualityReport(document_name=document_name)
        if not chunks:
            report.passed = False
            report.warnings.append("文档解析后无有效分块")
            return report

        report.chunk_count = len(chunks)
        all_text = ""
        pages: set[int] = set()
        for chunk in chunks:
            if hasattr(chunk, "content"):
                all_text += chunk.content
                pages.add(chunk.page)
            elif isinstance(chunk, dict):
                all_text += str(chunk.get("content", ""))
                p = chunk.get("page") or 0
                pages.add(int(p) if p else 0)

        report.total_chars = len(all_text)
        report.page_count = len(pages)
        source = markdown_source or all_text
        report.heading_count = len(re.findall(r"^#{1,6}\s", source, re.MULTILINE))
        report.table_count = _count_tables(source)

        if not self.enabled:
            report.checks.append({"rule": "quality_gate", "result": "disabled"})
            report.passed = True
            return report

        from app.core.config import settings
        self._check(report, settings.QG_MIN_CHARS, report.total_chars, "总字符数")
        self._check(report, settings.QG_MIN_PAGES, report.page_count, "页数")
        if settings.QG_MIN_HEADINGS > 0:
            self._check(report, settings.QG_MIN_HEADINGS, report.heading_count, "标题数")
        if settings.QG_MIN_TABLES > 0:
            self._check(report, settings.QG_MIN_TABLES, report.table_count, "表格数")

        report.passed = len(report.warnings) == 0
        if not report.passed:
            logger.warning("质量门禁未通过: %s warnings=%s", document_name, len(report.warnings))
        return report

    def _check(self, report: QualityReport, threshold: int, actual: int, name: str) -> None:
        if threshold <= 0:
            return
        rule = f"{name} >= {threshold}"
        if actual < threshold:
            report.warnings.append(f"{rule} — 实际: {actual}")
            report.checks.append({"rule": rule, "result": "fail", "actual": actual, "threshold": threshold})
        else:
            report.checks.append({"rule": rule, "result": "pass", "actual": actual})


def _count_tables(text: str) -> int:
    lines = text.splitlines()
    count = 0
    i = 0
    while i < len(lines):
        if re.match(r"^\|.+\|", lines[i]) and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|", lines[i + 1]):
            count += 1
            i += 2
            while i < len(lines) and re.match(r"^\|.+\|", lines[i]):
                i += 1
        else:
            i += 1
    return count


quality_gate = QualityGate()
