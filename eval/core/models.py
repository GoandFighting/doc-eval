"""Core data models for evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalRequest:
    """Input for a single document evaluation.

    :param converted_md: Markdown output from the document conversion tool.
    :param pdf_name: PDF file name used to look up test cases
                     (e.g. "text_simple__10k.pdf").
    """

    converted_md: str
    pdf_name: str


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension.

    :param dimension: Dimension identifier (e.g. "content_faithfulness").
    :param score: Normalised score in 0-100.
    :param metrics: Detailed metric values keyed by metric name.
    :param metadata: Additional information (rule counts, timing, etc.).
    """

    dimension: str
    score: float
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResponse:
    """Aggregated evaluation result for a single document.

    :param overall_score: Weighted score across all dimensions (0-100).
    :param dimensions: Per-dimension scores.
    :param pdf_name: PDF file name that was evaluated.
    :param metadata: Run-level metadata (timing, version, etc.).
    """

    overall_score: float
    dimensions: list[DimensionScore] = field(default_factory=list)
    pdf_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON output."""
        return {
            "overall_score": round(self.overall_score, 2),
            "pdf_name": self.pdf_name,
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "score": round(d.score, 2),
                    "metrics": {k: round(v, 4) for k, v in d.metrics.items()},
                    "metadata": d.metadata,
                }
                for d in self.dimensions
            ],
            "metadata": self.metadata,
        }


@dataclass
class BatchEvalRequest:
    """Input for batch evaluation.

    :param items: List of single-document evaluation requests.
    """

    items: list[EvalRequest] = field(default_factory=list)


@dataclass
class BatchSummary:
    """Aggregated statistics for a batch evaluation.

    :param avg_overall: Mean overall score across all successful evaluations.
    :param dimension_avg: Mean score per dimension across all successful evaluations.
    :param best: Top-5 documents by overall score.
    :param worst: Bottom-5 documents by overall score.
    :param category_stats: Per-category statistics {category: {avg, count}}.
    """

    avg_overall: float = 0.0
    dimension_avg: dict[str, float] = field(default_factory=dict)
    best: list[dict[str, Any]] = field(default_factory=list)
    worst: list[dict[str, Any]] = field(default_factory=list)
    category_stats: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_overall": round(self.avg_overall, 2),
            "dimension_avg": {k: round(v, 2) for k, v in self.dimension_avg.items()},
            "best": self.best,
            "worst": self.worst,
            "category_stats": self.category_stats,
        }


@dataclass
class BatchEvalResponse:
    """Result of a batch evaluation.

    :param total: Total number of documents submitted.
    :param evaluated: Number of successfully evaluated documents.
    :param failed: Number of failed evaluations.
    :param results: List of successful EvalResponse objects.
    :param errors: List of error dicts [{pdf_name, error}].
    :param summary: Aggregated batch statistics.
    """

    total: int = 0
    evaluated: int = 0
    failed: int = 0
    results: list[EvalResponse] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    summary: BatchSummary = field(default_factory=BatchSummary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "evaluated": self.evaluated,
            "failed": self.failed,
            "results": [r.to_dict() for r in self.results],
            "errors": self.errors,
            "summary": self.summary.to_dict(),
        }
