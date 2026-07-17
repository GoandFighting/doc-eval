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

    def test_expected_dimensions_follow_test_case_types(self, adapter):
        table_pdf = next(p for p in adapter.available_pdfs if "page" in p)
        text_pdf = next(p for p in adapter.available_pdfs if p.startswith("text_"))

        assert adapter.expected_dimensions(table_pdf) == {"tables"}
        assert adapter.expected_dimensions(text_pdf) == {
            "content_faithfulness",
            "semantic_formatting",
        }

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

    @pytest.mark.parametrize(
        "pdf_name",
        [
            "text_simple__contract2.pdf",
            "text_simple__myctophidae.pdf",
            "text_simple__reso.pdf",
            "text_simple__share.pdf",
            "text_simple__smithville.pdf",
            "text_simple__wired.pdf",
        ],
    )
    def test_italic_and_underline_cases_receive_formatting_composite(self, adapter, pdf_name):
        """Unsupported ParseBench styling types must still affect formatting."""
        metrics = adapter.evaluate("", pdf_name)
        formatting = [metric for metric in metrics if metric.metric_name == "semantic_formatting"]

        assert len(formatting) == 1
        assert formatting[0].value == 0.0
        assert formatting[0].metadata["fallback"] is True

    def test_unknown_pdf_raises_keyerror(self, adapter):
        with pytest.raises(KeyError):
            adapter.evaluate("some markdown", "nonexistent.pdf")

    def test_all_parsebench_failures_are_not_silenced(self, adapter, monkeypatch):
        """A total ParseBench failure must not degrade to an L1-only result."""
        pdf_name = adapter.available_pdfs[0]

        def fail_with_signal_error(*_):
            raise ValueError("signal only works in main thread of the main interpreter")

        monkeypatch.setattr(adapter._evaluator, "evaluate", fail_with_signal_error)

        with pytest.raises(RuntimeError, match="must run on the main thread"):
            adapter.evaluate("# test", pdf_name)
