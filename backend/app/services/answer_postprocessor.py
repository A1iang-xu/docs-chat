"""v4.5: 回答后处理管线 —— 对 LLM 生成的原始回答做格式化/去冗余/引用对齐

管线阶段:
1. 冗余前缀清理: 移除 "根据文档内容"、"根据提供的文档" 等无意义开头
2. 代码块修复: 未闭合的 ``` 自动补全
3. 引用编号对齐: 确保 [1] [2] ... 编号连续且与 sources 数量一致
4. 空行规范化: 合并连续空行为单个空行
5. 尾部清理: 移除多余的尾部空行
"""
from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# 无意义前缀模式（中英文）
_PREFIX_PATTERNS = [
    r"^根据(?:提供的)?(?:参考)?文档[内容]*[，,。：:\s]*",
    r"^根据(?:上述)?文档[，,。：:\s]*",
    r"^根据已有文档[，,。：:\s]*",
    r"^根据(?:以上)?参考文档[，,。：:\s]*",
    r"^基于(?:提供的)?文档[，,。：:\s]*",
    r"^Based on (?:the )?(?:provided |reference )?documents?[，,。:\s]*",
    r"^According to (?:the )?documents?[，,。:\s]*",
]


class AnswerPostprocessor:
    """回答后处理管线"""

    def process(self, answer: str, source_count: int = 0) -> str:
        """执行完整后处理管线。

        Args:
            answer: LLM 生成的原始回答
            source_count: 引用来源数量（用于引用编号对齐）

        Returns:
            处理后的回答
        """
        if not answer or not answer.strip():
            return answer

        result = answer

        # 1. 冗余前缀清理
        result = self._strip_redundant_prefix(result)

        # 2. 代码块修复
        result = self._fix_code_blocks(result)

        # 3. 引用编号对齐
        if source_count > 0:
            result = self._align_citations(result, source_count)

        # 4. 空行规范化
        result = self._normalize_blank_lines(result)

        # 5. 尾部清理
        result = self._strip_trailing(result)

        if result != answer:
            logger.debug("后处理: %d → %d chars", len(answer), len(result))

        return result

    def _strip_redundant_prefix(self, text: str) -> str:
        """移除无意义前缀"""
        for pattern in _PREFIX_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text

    def _fix_code_blocks(self, text: str) -> str:
        """修复未闭合的代码块"""
        # 统计 ``` 的数量
        fence_count = text.count("```")
        if fence_count % 2 != 0:
            # 奇数个 ``` → 补全闭合
            text = text.rstrip() + "\n```"
            logger.debug("代码块修复: 补全闭合 ```")
        return text

    def _align_citations(self, text: str, source_count: int) -> str:
        """对齐引用编号 [1] [2] ... 确保不超出 source_count"""
        # 找到所有 [N] 引用
        citations = re.findall(r"\[(\d+)\]", text)
        if not citations:
            return text

        # 检查是否有超出范围的引用
        max_citation = max(int(c) for c in citations)
        if max_citation <= source_count:
            return text

        # 将超出范围的引用标记为说明文字
        def replace_overflow(match):
            num = int(match.group(1))
            if num > source_count:
                return f"(参考{num})"
            return match.group(0)

        text = re.sub(r"\[(\d+)\]", replace_overflow, text)
        logger.debug("引用对齐: max_citation=%d, source_count=%d", max_citation, source_count)
        return text

    def _normalize_blank_lines(self, text: str) -> str:
        """合并连续空行为单个空行"""
        # 3个以上连续换行 → 2个换行（即1个空行）
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _strip_trailing(self, text: str) -> str:
        """移除多余的尾部空行"""
        return text.rstrip() + "\n" if text.rstrip() else text


answer_postprocessor = AnswerPostprocessor()
