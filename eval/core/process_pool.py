"""Persistent process pool for signal-safe Linux ParseBench evaluation."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from functools import partial

from eval.core.config import EvalConfig
from eval.core.models import EvalRequest, EvalResponse

logger = logging.getLogger(__name__)

_worker_runner = None


def _initialise_worker(config: EvalConfig) -> None:
    """Load one reusable runner in each child process."""
    global _worker_runner

    from eval.core.runner import AsyncEvalRunner

    worker_config = replace(
        config,
        parsebench_threaded=False,
        batch_concurrency=1,
        process_workers=0,
    )
    _worker_runner = AsyncEvalRunner(worker_config)
    logger.info("ParseBench worker %d ready for %s", os.getpid(), config.dataset_dir)


def _warm_worker() -> int:
    """Return the worker PID after a short delay so all workers can start."""
    time.sleep(0.05)
    return os.getpid()


def _evaluate_in_worker(request: EvalRequest) -> EvalResponse:
    """Evaluate one document on the child process's main thread."""
    if _worker_runner is None:
        raise RuntimeError("ParseBench worker was not initialised")

    response = asyncio.run(_worker_runner.evaluate(request))
    response.metadata["worker_pid"] = os.getpid()
    return response


class PersistentEvalProcessPool:
    """Keep a bounded set of ParseBench workers alive across batch requests."""

    def __init__(self, config: EvalConfig, max_workers: int) -> None:
        self._config = config
        self._max_workers = max_workers
        self._executor: ProcessPoolExecutor | None = None
        self._start_lock: asyncio.Lock | None = None

    def _lock(self) -> asyncio.Lock:
        if self._start_lock is None:
            self._start_lock = asyncio.Lock()
        return self._start_lock

    def _create_executor(self) -> ProcessPoolExecutor:
        # spawn avoids forking a running Uvicorn event loop and guarantees
        # that each ParseBench instance owns the child process's main thread.
        context = multiprocessing.get_context("spawn")
        return ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=context,
            initializer=_initialise_worker,
            initargs=(self._config,),
        )

    async def start(self) -> None:
        """Create and pre-warm the persistent workers once."""
        async with self._lock():
            if self._executor is not None:
                return

            executor = self._create_executor()
            self._executor = executor
            try:
                loop = asyncio.get_running_loop()
                pids = await asyncio.gather(
                    *(loop.run_in_executor(executor, _warm_worker) for _ in range(self._max_workers))
                )
            except BaseException:
                self._executor = None
                executor.shutdown(wait=True, cancel_futures=True)
                raise
            logger.info(
                "Persistent ParseBench pool started with %d workers: %s",
                self._max_workers,
                sorted(set(pids)),
            )

    async def evaluate(self, items: list[EvalRequest]) -> list[EvalResponse | BaseException]:
        """Evaluate documents across persistent workers, restarting once if the pool breaks."""
        await self.start()
        raw_results = await self._submit(items)

        broken_indexes = [
            index for index, result in enumerate(raw_results)
            if isinstance(result, BrokenProcessPool)
        ]
        if not broken_indexes:
            return raw_results

        logger.error("ParseBench process pool broke; restarting %d failed tasks", len(broken_indexes))
        await self.restart()
        retry_items = [items[index] for index in broken_indexes]
        retry_results = await self._submit(retry_items)
        for index, retry_result in zip(broken_indexes, retry_results, strict=True):
            raw_results[index] = retry_result
        return raw_results

    async def _submit(self, items: list[EvalRequest]) -> list[EvalResponse | BaseException]:
        executor = self._executor
        if executor is None:
            raise RuntimeError("ParseBench process pool is not running")

        loop = asyncio.get_running_loop()
        futures = [loop.run_in_executor(executor, _evaluate_in_worker, item) for item in items]
        return list(await asyncio.gather(*futures, return_exceptions=True))

    async def restart(self) -> None:
        """Replace a broken worker pool."""
        await self.close()
        self._start_lock = None
        await self.start()

    async def close(self) -> None:
        """Stop all workers and release process resources."""
        async with self._lock():
            executor = self._executor
            self._executor = None
            if executor is not None:
                shutdown = partial(executor.shutdown, wait=True, cancel_futures=True)
                await asyncio.to_thread(shutdown)
