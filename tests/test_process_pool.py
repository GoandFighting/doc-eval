"""Integration tests for the persistent ParseBench process pool."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from eval.core.config import EvalConfig
from eval.core.models import EvalRequest
from eval.core.process_pool import PersistentEvalProcessPool
from eval.core.runner import AsyncEvalRunner


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only server process path")
def test_worker_process_is_reused_across_evaluations():
    """A warm worker should handle later requests without being recreated."""
    config = EvalConfig(
        dataset_dir=Path("newbench"),
        enable_l1=False,
        parsebench_threaded=False,
        process_workers=1,
    )
    pdf_name = AsyncEvalRunner(config).available_pdfs[0]

    async def exercise_pool():
        pool = PersistentEvalProcessPool(config=config, max_workers=1)
        try:
            first = await pool.evaluate([EvalRequest(converted_md="# first", pdf_name=pdf_name)])
            second = await pool.evaluate([EvalRequest(converted_md="# second", pdf_name=pdf_name)])
            return first, second
        finally:
            await pool.close()

    first, second = asyncio.run(exercise_pool())

    assert not isinstance(first[0], BaseException)
    assert not isinstance(second[0], BaseException)
    assert first[0].metadata["worker_pid"] == second[0].metadata["worker_pid"]
