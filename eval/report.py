"""Report generation for evaluation results."""

from __future__ import annotations

import json
from typing import Any

from eval.core.models import BatchEvalResponse, EvalResponse


def to_json(response: EvalResponse, indent: int = 2) -> str:
    """Serialise an EvalResponse to a JSON string.

    :param response: Evaluation response to serialise.
    :param indent: JSON indentation level.
    :return: JSON string.
    """
    return json.dumps(response.to_dict(), indent=indent, ensure_ascii=False)


def to_dict(response: EvalResponse) -> dict[str, Any]:
    """Serialise an EvalResponse to a plain dict.

    :param response: Evaluation response to serialise.
    :return: Dict suitable for JSON encoding.
    """
    return response.to_dict()


def print_summary(response: EvalResponse) -> str:
    """Return a human-readable one-line summary.

    :param response: Evaluation response.
    :return: Summary string.
    """
    parts = [f"Overall: {response.overall_score:.1f}"]
    for d in response.dimensions:
        parts.append(f"{d.dimension}={d.score:.1f}")
    parts.append(f"({response.metadata.get('elapsed_seconds', '?')}s)")
    return " | ".join(parts)


def batch_to_json(response: BatchEvalResponse, indent: int = 2) -> str:
    """Serialise a BatchEvalResponse to a JSON string.

    :param response: Batch evaluation response to serialise.
    :param indent: JSON indentation level.
    :return: JSON string.
    """
    return json.dumps(response.to_dict(), indent=indent, ensure_ascii=False)


def batch_to_dict(response: BatchEvalResponse) -> dict[str, Any]:
    """Serialise a BatchEvalResponse to a plain dict.

    :param response: Batch evaluation response to serialise.
    :return: Dict suitable for JSON encoding.
    """
    return response.to_dict()


def batch_summary_text(response: BatchEvalResponse) -> str:
    """Return a human-readable multi-line batch summary.

    :param response: Batch evaluation response.
    :return: Formatted summary string.
    """
    lines = [
        "=" * 60,
        "  批量评测结果",
        "=" * 60,
        f"  总数: {response.total}  成功: {response.evaluated}  失败: {response.failed}",
        f"  平均分: {response.summary.avg_overall:.1f}",
        "",
        "  维度均分:",
    ]

    for dim, score in response.summary.dimension_avg.items():
        bar = _bar(score)
        lines.append(f"    {dim:25s}  {bar}  {score:.1f}")

    if response.summary.best:
        lines.append("")
        lines.append("  最佳:")
        for item in response.summary.best:
            lines.append(f"    {item['pdf_name']:40s}  {item['score']:.1f}")

    if response.summary.worst:
        lines.append("")
        lines.append("  最差:")
        for item in response.summary.worst:
            lines.append(f"    {item['pdf_name']:40s}  {item['score']:.1f}")

    if response.errors:
        lines.append("")
        lines.append("  失败列表:")
        for err in response.errors:
            lines.append(f"    {err['pdf_name']:40s}  {err['error']}")

    lines.append("=" * 60)
    return "\n".join(lines)


def _bar(score: float, width: int = 10) -> str:
    """Generate a simple text progress bar.

    :param score: Score in 0-100.
    :param width: Bar width in characters.
    :return: Bar string like '████░░░░░░'.
    """
    filled = int(score / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)
