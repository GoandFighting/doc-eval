"""Tests for AsyncEvalRunner end-to-end."""

import asyncio
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
