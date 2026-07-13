"""Tests for batch evaluation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from eval.core.config import EvalConfig
from eval.core.models import BatchEvalRequest, EvalRequest
from eval.core.runner import AsyncEvalRunner
from eval.report import batch_summary_text, batch_to_json


@pytest.fixture(scope="module")
def runner():
    config = EvalConfig(
        dataset_dir=Path("newbench"),
        enable_l1=True,
        enable_l4=False,
        batch_concurrency=2,
    )
    return AsyncEvalRunner(config)


class TestBatchEval:
    def test_batch_eval_multiple_files(self, runner):
        """Evaluate multiple table PDFs using expected_markdown."""
        table_pdfs = [p for p in runner.available_pdfs if "page" in p][:3]
        if len(table_pdfs) < 2:
            pytest.skip("Need at least 2 table PDFs")

        items = []
        for pdf_name in table_pdfs:
            test_cases = runner._parsebench._test_cases.get(pdf_name, [])
            for tc in test_cases:
                if tc.expected_markdown:
                    items.append(EvalRequest(
                        converted_md=tc.expected_markdown,
                        pdf_name=pdf_name,
                    ))
                    break

        if len(items) < 2:
            pytest.skip("Not enough expected_markdown found")

        response = asyncio.run(runner.evaluate_batch(BatchEvalRequest(items=items)))

        assert response.total == len(items)
        assert response.evaluated == len(items)
        assert response.failed == 0
        assert len(response.results) == len(items)
        assert response.summary.avg_overall > 0

    def test_batch_eval_with_invalid_pdf_name(self, runner):
        """Invalid PDF name should go to errors, not crash the batch."""
        items = [
            EvalRequest(converted_md="# test", pdf_name="nonexistent.pdf"),
        ]
        response = asyncio.run(runner.evaluate_batch(BatchEvalRequest(items=items)))

        assert response.total == 1
        assert response.failed == 1
        assert len(response.errors) == 1
        assert response.errors[0]["pdf_name"] == "nonexistent.pdf"

    def test_batch_eval_mixed_valid_invalid(self, runner):
        """Mix of valid and invalid items: valid succeeds, invalid errors."""
        table_pdfs = [p for p in runner.available_pdfs if "page" in p][:1]
        if not table_pdfs:
            pytest.skip("No table PDFs")

        pdf_name = table_pdfs[0]
        test_cases = runner._parsebench._test_cases.get(pdf_name, [])
        expected_md = None
        for tc in test_cases:
            if tc.expected_markdown:
                expected_md = tc.expected_markdown
                break
        if not expected_md:
            pytest.skip("No expected_markdown")

        items = [
            EvalRequest(converted_md=expected_md, pdf_name=pdf_name),
            EvalRequest(converted_md="# bad", pdf_name="nonexistent.pdf"),
        ]
        response = asyncio.run(runner.evaluate_batch(BatchEvalRequest(items=items)))

        assert response.total == 2
        assert response.evaluated == 1
        assert response.failed == 1
        assert len(response.results) == 1
        assert len(response.errors) == 1

    def test_batch_summary_stats(self, runner):
        """Summary should have avg_overall, dimension_avg, best, worst."""
        table_pdfs = [p for p in runner.available_pdfs if "page" in p][:2]
        if len(table_pdfs) < 2:
            pytest.skip("Need 2 table PDFs")

        items = []
        for pdf_name in table_pdfs:
            test_cases = runner._parsebench._test_cases.get(pdf_name, [])
            for tc in test_cases:
                if tc.expected_markdown:
                    items.append(EvalRequest(
                        converted_md=tc.expected_markdown,
                        pdf_name=pdf_name,
                    ))
                    break

        response = asyncio.run(runner.evaluate_batch(BatchEvalRequest(items=items)))

        s = response.summary
        assert s.avg_overall > 0
        assert isinstance(s.dimension_avg, dict)
        assert len(s.dimension_avg) > 0
        assert len(s.best) <= 5
        assert len(s.worst) <= 5

    def test_batch_serialisation(self, runner):
        """BatchEvalResponse should serialise to dict and JSON."""
        items = [
            EvalRequest(converted_md="# test", pdf_name="nonexistent.pdf"),
        ]
        response = asyncio.run(runner.evaluate_batch(BatchEvalRequest(items=items)))

        d = response.to_dict()
        assert "total" in d
        assert "evaluated" in d
        assert "failed" in d
        assert "results" in d
        assert "errors" in d
        assert "summary" in d

        json_str = batch_to_json(response)
        assert isinstance(json_str, str)
        assert '"total"' in json_str

    def test_batch_summary_text(self, runner):
        """batch_summary_text should produce readable output."""
        items = [
            EvalRequest(converted_md="# test", pdf_name="nonexistent.pdf"),
        ]
        response = asyncio.run(runner.evaluate_batch(BatchEvalRequest(items=items)))

        text = batch_summary_text(response)
        assert "批量评测结果" in text
        assert "总数" in text

    def test_batch_empty_request(self, runner):
        """Empty batch should return zero counts."""
        response = asyncio.run(
            runner.evaluate_batch(BatchEvalRequest(items=[]))
        )
        assert response.total == 0
        assert response.evaluated == 0
        assert response.failed == 0
        assert response.summary.avg_overall == 0.0
