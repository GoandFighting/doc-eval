"""Evaluation configuration."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment flag with a safe default."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in {"0", "false", "no", "off"}


def _env_positive_int(name: str, default: int) -> int:
    """Read a positive integer environment setting with a safe default."""
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_nonnegative_int(name: str, default: int) -> int:
    """Read a non-negative integer environment setting with a safe default."""
    try:
        return max(0, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def server_process_workers() -> int:
    """Return the server's persistent worker count for the current platform."""
    if sys.platform == "win32":
        return 0
    return _env_nonnegative_int("DOC_EVAL_PROCESS_WORKERS", 2)


@dataclass
class EvalConfig:
    """Configuration for the evaluation runner.

    :param dataset_dir: Path to the newbench dataset directory.
    :param enable_l1: Enable L1 format quality (PyMarkdown lint).
    :param enable_l4: Enable L4 semantic similarity (sentence-transformers).
    :param enable_teds: Enable TEDS metric in ParseBench table evaluation.
    :param enable_grits: Enable GriTS metric in ParseBench table evaluation.
    :param parsebench_threaded: Run ParseBench in worker threads so batches execute concurrently.
    :param process_workers: Persistent signal-safe worker processes used by server batches.
    :param weights: Dimension weights for overall score.
    :param semantic_model: sentence-transformers model name for L4.
    """

    dataset_dir: Path = Path("newbench")
    enable_l1: bool = True
    enable_l4: bool = False
    enable_teds: bool = True
    enable_grits: bool = True
    parsebench_threaded: bool = field(
        default_factory=lambda: _env_flag("DOC_EVAL_THREADED", sys.platform == "win32")
    )
    process_workers: int = 0

    weights: dict[str, float] = field(default_factory=lambda: {
        "content_faithfulness": 0.30,
        "semantic_formatting": 0.25,
        "tables": 0.25,
        "format_quality": 0.10,
        "semantic": 0.10,
    })

    semantic_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    batch_concurrency: int = field(
        default_factory=lambda: _env_positive_int("DOC_EVAL_BATCH_CONCURRENCY", 4)
    )

    def active_weights(self, available_dimensions: set[str]) -> dict[str, float]:
        """Return weights for available dimensions, re-normalised to sum 1.

        When a dimension is missing (e.g. L4 disabled), its weight is
        redistributed proportionally across the remaining dimensions.
        """
        active = {
            k: v for k, v in self.weights.items()
            if k in available_dimensions and v > 0
        }
        total = sum(active.values())
        if total == 0:
            return {}
        return {k: v / total for k, v in active.items()}
