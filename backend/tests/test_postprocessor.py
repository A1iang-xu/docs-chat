"""v4.5: 回答后处理管线测试"""
import pytest
from app.services.answer_postprocessor import AnswerPostprocessor


class TestStripRedundantPrefix:
    """冗余前缀清理测试"""

    def setup_method(self):
        self.pp = AnswerPostprocessor()

    def test_strip_chinese_prefix(self):
        """移除中文冗余前缀"""
        assert self.pp._strip_redundant_prefix("根据文档内容，ref 是响应式引用。") == "ref 是响应式引用。"

    def test_strip_provided_docs_prefix(self):
        """移除"根据提供的文档"前缀"""
        result = self.pp._strip_redundant_prefix("根据提供的文档，reactive 用于对象。")
        assert "reactive" in result
        assert not result.startswith("根据")

    def test_keep_normal_answer(self):
        """无前缀的回答不应被修改"""
        text = "ref() 是 Vue 3 的响应式 API。"
        assert self.pp._strip_redundant_prefix(text) == text

    def test_strip_english_prefix(self):
        """移除英文冗余前缀"""
        result = self.pp._strip_redundant_prefix("Based on the documents, ref is reactive.")
        assert result.startswith("ref is")


class TestFixCodeBlocks:
    """代码块修复测试"""

    def setup_method(self):
        self.pp = AnswerPostprocessor()

    def test_fix_unclosed_code_block(self):
        """未闭合代码块应补全"""
        text = "示例:\n```python\nref(0)\n"
        result = self.pp._fix_code_blocks(text)
        assert result.count("```") % 2 == 0

    def test_keep_closed_code_block(self):
        """已闭合代码块不应被修改"""
        text = "示例:\n```python\nref(0)\n```"
        result = self.pp._fix_code_blocks(text)
        assert result == text


class TestAlignCitations:
    """引用编号对齐测试"""

    def setup_method(self):
        self.pp = AnswerPostprocessor()

    def test_valid_citations_unchanged(self):
        """引用编号不超出范围时不修改"""
        text = "ref 是响应式 [1]，reactive 也是 [2]。"
        result = self.pp._align_citations(text, source_count=3)
        assert result == text

    def test_overflow_citation_replaced(self):
        """超出范围的引用应被替换"""
        text = "ref [1] 和 reactive [5]。"
        result = self.pp._align_citations(text, source_count=2)
        assert "[5]" not in result
        assert "(参考5)" in result


class TestNormalizeBlankLines:
    """空行规范化测试"""

    def setup_method(self):
        self.pp = AnswerPostprocessor()

    def test_collapse_multiple_blank_lines(self):
        """3+连续换行合并为2个"""
        text = "段落1\n\n\n\n\n段落2"
        result = self.pp._normalize_blank_lines(text)
        assert "\n\n\n" not in result

    def test_keep_single_blank_line(self):
        """单个空行保持不变"""
        text = "段落1\n\n段落2"
        assert self.pp._normalize_blank_lines(text) == text


class TestFullPipeline:
    """完整管线测试"""

    def test_full_process(self):
        """完整后处理流程"""
        pp = AnswerPostprocessor()
        text = "根据文档内容，ref 是响应式 [1]。\n\n\n\nreactive [5] 是对象代理。"
        result = pp.process(text, source_count=2)
        assert not result.startswith("根据")
        assert "[5]" not in result
        assert "\n\n\n" not in result

    def test_empty_input(self):
        """空输入应原样返回"""
        pp = AnswerPostprocessor()
        assert pp.process("") == ""
        assert pp.process(None) is None  # type: ignore
