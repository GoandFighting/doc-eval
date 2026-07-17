"""Tests for AsyncEvalRunner end-to-end."""

import asyncio
import threading
import time
from pathlib import Path

import pytest

from eval.core.config import EvalConfig
from eval.core.models import BatchEvalRequest, EvalRequest
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
        """The compatibility mode keeps ParseBench on the main thread."""
        observed_threads = []
        pdf_name = runner.available_pdfs[0]

        def fake_evaluate(converted_md, requested_pdf):
            observed_threads.append(threading.current_thread())
            assert requested_pdf == pdf_name
            return []

        monkeypatch.setattr(runner._parsebench, "evaluate", fake_evaluate)
        monkeypatch.setattr(runner._parsebench, "expected_dimensions", lambda _: set())

        previous = runner._config.parsebench_threaded
        runner._config.parsebench_threaded = False
        try:
            asyncio.run(runner.evaluate(EvalRequest(converted_md="# test", pdf_name=pdf_name)))
        finally:
            runner._config.parsebench_threaded = previous

        assert observed_threads == [threading.main_thread()]

    def test_windows_threaded_mode_runs_batch_parsebench_concurrently(self, runner, monkeypatch):
        """Threaded mode must make the batch concurrency setting effective."""
        active = 0
        max_active = 0
        lock = threading.Lock()
        pdf_name = runner.available_pdfs[0]

        def fake_evaluate(*_):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return []

        monkeypatch.setattr(runner._parsebench, "evaluate", fake_evaluate)
        monkeypatch.setattr(runner._parsebench, "expected_dimensions", lambda _: set())

        previous_threaded = runner._config.parsebench_threaded
        previous_concurrency = runner._config.batch_concurrency
        runner._config.parsebench_threaded = True
        runner._config.batch_concurrency = 4
        try:
            response = asyncio.run(
                runner.evaluate_batch(
                    BatchEvalRequest(
                        items=[
                            EvalRequest(converted_md=f"# test {index}", pdf_name=pdf_name)
                            for index in range(4)
                        ]
                    )
                )
            )
        finally:
            runner._config.parsebench_threaded = previous_threaded
            runner._config.batch_concurrency = previous_concurrency

        assert response.evaluated == 4
        assert max_active >= 2

    def test_batch_uses_configured_persistent_process_pool(self, runner):
        """The process-pool path preserves batch aggregation and lifecycle."""
        pdf_name = runner.available_pdfs[0]

        class FakePool:
            def __init__(self):
                self.started = 0
                self.closed = 0

            async def start(self):
                self.started += 1

            async def evaluate(self, items):
                return [
                    type("Response", (), {
                        "pdf_name": item.pdf_name,
                        "warnings": [],
                        "overall_score": 80.0,
                        "dimensions": [],
                    })()
                    for item in items
                ]

            async def close(self):
                self.closed += 1

        fake_pool = FakePool()
        previous_workers = runner._config.process_workers
        previous_pool = runner._process_pool
        runner._config.process_workers = 2
        runner._process_pool = fake_pool
        try:
            response = asyncio.run(
                runner.evaluate_batch(
                    BatchEvalRequest(
                        items=[EvalRequest(converted_md="# test", pdf_name=pdf_name)]
                    )
                )
            )
            asyncio.run(runner.close())
        finally:
            runner._config.process_workers = previous_workers
            runner._process_pool = previous_pool

        assert response.evaluated == 1
        assert response.failed == 0
        assert fake_pool.started == 1
        assert fake_pool.closed == 1

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
