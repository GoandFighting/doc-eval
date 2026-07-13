"""Tests for ParseBenchAdapter."""

from pathlib import Path

import pytest

from eval.adapters.parsebench import ParseBenchAdapter


@pytest.fixture(scope="module")
def adapter():
    return ParseBenchAdapter(dataset_dir=Path("newbench"))


class TestParseBenchAdapter:
    def test_loads_test_cases(self, adapter):
        assert len(adapter.available_pdfs) > 0

    def test_has_table_pdfs(self, adapter):
        table_pdfs = [p for p in adapter.available_pdfs if "page" in p]
        assert len(table_pdfs) > 0

    def test_has_text_pdfs(self, adapter):
        text_pdfs = [p for p in adapter.available_pdfs if p.startswith("text_")]
        assert len(text_pdfs) > 0

    def test_evaluate_table_with_expected_md(self, adapter):
        pdf_name = adapter.available_pdfs[0]
        test_cases = adapter._test_cases.get(pdf_name, [])
        expected_md = None
        for tc in test_cases:
            if tc.expected_markdown:
                expected_md = tc.expected_markdown
                break

        if not expected_md:
            pytest.skip("No table test case with expected_markdown found")

        metrics = adapter.evaluate(expected_md, pdf_name)
        assert len(metrics) > 0

        metric_names = {m.metric_name for m in metrics}
        assert "grits_con" in metric_names or "content_faithfulness" in metric_names

    def test_evaluate_blank_markdown(self, adapter):
        pdf_name = adapter.available_pdfs[0]
        metrics = adapter.evaluate("", pdf_name)
        assert len(metrics) > 0

    def test_unknown_pdf_raises_keyerror(self, adapter):
        with pytest.raises(KeyError):
            adapter.evaluate("some markdown", "nonexistent.pdf")
