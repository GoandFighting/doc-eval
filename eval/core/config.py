"""Evaluation configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalConfig:
    """Configuration for the evaluation runner.

    :param dataset_dir: Path to the newbench dataset directory.
    :param enable_l1: Enable L1 format quality (PyMarkdown lint).
    :param enable_l4: Enable L4 semantic similarity (sentence-transformers).
    :param enable_teds: Enable TEDS metric in ParseBench table evaluation.
    :param enable_grits: Enable GriTS metric in ParseBench table evaluation.
    :param weights: Dimension weights for overall score.
    :param semantic_model: sentence-transformers model name for L4.
    """

    dataset_dir: Path = Path("newbench")
    enable_l1: bool = True
    enable_l4: bool = False
    enable_teds: bool = True
    enable_grits: bool = True

    weights: dict[str, float] = field(default_factory=lambda: {
        "content_faithfulness": 0.30,
        "semantic_formatting": 0.25,
        "tables": 0.25,
        "format_quality": 0.10,
        "semantic": 0.10,
    })

    semantic_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    batch_concurrency: int = 4

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
