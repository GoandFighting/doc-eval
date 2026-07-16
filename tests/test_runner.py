"""Tests for AsyncEvalRunner end-to-end."""

import asyncio
import threading
from pathlib import Path

import pytest

from eval.core.config import EvalConfig
from eval.core.models import EvalRequest
from eval.core.runner import AsyncEvalRunner


@pytest.fixture(scope="module")
def runner():
    config = EvalConfig(
        dataset_dir=Path("newbench"),
        enable_l1=True,
        enable_l4=False,
    )
    return AsyncEvalRunner(config)


class TestAsyncEvalRunner:
    def test_available_pdfs(self, runner):
        assert len(runner.available_pdfs) > 0

    def test_evaluate_table_document(self, runner):
        """Evaluate a table PDF using its expected_markdown as converted output."""
        # Find a table PDF
        table_pdfs = [p for p in runner.available_pdfs if "page" in p]
        if not table_pdfs:
            pytest.skip("No table PDFs available")
        pdf_name = table_pdfs[0]

        # Get expected_markdown to use as converted_md (should score ~100)
        test_cases = runner._parsebench._test_cases.get(pdf_name, [])
        expected_md = None
        for tc in test_cases:
            if tc.expected_markdown:
                expected_md = tc.expected_markdown
                break
        if not expected_md:
            pytest.skip("No expected_markdown for table PDF")

        request = EvalRequest(converted_md=expected_md, pdf_name=pdf_name)
        response = asyncio.run(runner.evaluate(request))

        assert response.pdf_name == pdf_name
        assert response.overall_score > 0
        assert len(response.dimensions) > 0

        dim_names = {d.dimension for d in response.dimensions}
        assert "tables" in dim_names
        assert "format_quality" in dim_names

    def test_evaluate_blank_markdown(self, runner):
        pdf_name = runner.available_pdfs[0]
        request = EvalRequest(converted_md="", pdf_name=pdf_name)
        response = asyncio.run(runner.evaluate(request))

        assert response.overall_score >= 0
        assert len(response.dimensions) > 0

    def test_response_serialisable(self, runner):
        pdf_name = runner.available_pdfs[0]
        request = EvalRequest(converted_md="", pdf_name=pdf_name)
        response = asyncio.run(runner.evaluate(request))

        d = response.to_dict()
        assert "overall_score" in d
        assert "dimensions" in d
        assert isinstance(d["dimensions"], list)

    def test_parsebench_evaluation_runs_on_main_thread(self, runner, monkeypatch):
        """Linux signal-based timeouts require ParseBench on the main thread."""
        observed_threads = []
        pdf_name = runner.available_pdfs[0]

        def fake_evaluate(converted_md, requested_pdf):
            observed_threads.append(threading.current_thread())
            assert requested_pdf == pdf_name
            return []

        monkeypatch.setattr(runner._parsebench, "evaluate", fake_evaluate)
        monkeypatch.setattr(runner._parsebench, "expected_dimensions", lambda _: set())

        asyncio.run(runner.evaluate(EvalRequest(converted_md="# test", pdf_name=pdf_name)))

        assert observed_threads == [threading.main_thread()]

    def test_missing_parsebench_dimension_is_reported(self, runner, monkeypatch):
        """Partial ParseBench output must be explicit in the API response."""
        pdf_name = runner.available_pdfs[0]
        monkeypatch.setattr(runner._parsebench, "evaluate", lambda *_: [])
        monkeypatch.setattr(
            runner._parsebench,
            "expected_dimensions",
            lambda _: {"content_faithfulness"},
        )

        response = asyncio.run(
            runner.evaluate(EvalRequest(converted_md="# test", pdf_name=pdf_name))
        )
        payload = response.to_dict()

        assert response.complete is False
        assert response.metadata["missing_dimensions"] == ["content_faithfulness"]
        assert "内容准确性" in response.warnings[0]
        assert payload["complete"] is False
        assert payload["warnings"] == response.warnings
