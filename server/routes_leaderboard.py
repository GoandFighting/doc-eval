"""Leaderboard API routes: read evaluation reports and return ranked tool list."""

from __future__ import annotations

import json
import logging
import math
import os
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from eval.core.config import EvalConfig

logger = logging.getLogger(__name__)

router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_LEADERBOARD_DIR = Path(os.environ.get("LEADERBOARD_DIR", str(_PROJECT_ROOT / "tianti")))
_LEADERBOARD_DATASET = os.environ.get("LEADERBOARD_DATASET", "newbench")
_MIN_COVERAGE = 95.0


def _percentile(values: list[float], percentile: float) -> float:
    """Return a linearly interpolated percentile for sorted numeric values."""
    if not values:
        return 0.0
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _score_distribution(data: dict[str, Any]) -> dict[str, float]:
    """Build compact distribution statistics from successful document scores."""
    scores = sorted(
        float(item["overall_score"])
        for item in data.get("results", [])
        if isinstance(item.get("overall_score"), (int, float))
    )
    if not scores:
        return {}

    mean = statistics.fmean(scores)
    margin = 0.0
    if len(scores) > 1:
        margin = 1.96 * statistics.stdev(scores) / math.sqrt(len(scores))
    return {
        "median": round(statistics.median(scores), 2),
        "p25": round(_percentile(scores, 0.25), 2),
        "p75": round(_percentile(scores, 0.75), 2),
        "ci95_low": round(max(0.0, mean - margin), 2),
        "ci95_high": round(min(100.0, mean + margin), 2),
    }


def _report_version(data: dict[str, Any]) -> str:
    """Extract the evaluator version recorded in a report."""
    metadata = data.get("metadata", {})
    if metadata.get("version"):
        return str(metadata["version"])
    for result in data.get("results", []):
        version = result.get("metadata", {}).get("version")
        if version:
            return str(version)
    return "unknown"


@router.get("")
async def get_leaderboard() -> dict[str, Any]:
    """Return leaderboard data from stored evaluation reports.

    Reads all ``result_*.json`` files from the configured leaderboard
    directory and returns a sorted list of tools by average overall score.

    :return: Dict with ``tools`` list sorted by ``avg_overall`` descending.
    """
    if not _LEADERBOARD_DIR.exists():
        return {"tools": []}

    tools: list[dict[str, Any]] = []
    latest_updated_at: datetime | None = None
    versions: set[str] = set()

    for fp in sorted(_LEADERBOARD_DIR.glob("result_*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("Failed to read leaderboard file: %s", fp)
            continue

        tool_name = fp.stem
        if tool_name.startswith("result_"):
            tool_name = tool_name[len("result_"):]

        summary = data.get("summary", {})
        total = int(data.get("total", 0) or 0)
        evaluated = int(data.get("evaluated", 0) or 0)
        failed = int(data.get("failed", 0) or 0)
        coverage = evaluated / total * 100 if total else 0.0
        updated_at = datetime.fromtimestamp(fp.stat().st_mtime).astimezone()
        latest_updated_at = max(latest_updated_at, updated_at) if latest_updated_at else updated_at
        version = _report_version(data)
        versions.add(version)
        tools.append({
            "tool": tool_name,
            "avg_overall": summary.get("avg_overall", 0),
            "dimension_avg": summary.get("dimension_avg", {}),
            "category_stats": summary.get("category_stats", {}),
            "score_distribution": _score_distribution(data),
            "total": total,
            "evaluated": evaluated,
            "failed": failed,
            "coverage": round(coverage, 2),
            "eligible": coverage >= _MIN_COVERAGE,
            "benchmark_version": version,
            "updated_at": updated_at.isoformat(timespec="seconds"),
            "tool_version": data.get("tool_version") or data.get("metadata", {}).get("tool_version"),
            "errors": data.get("errors", [])[:5],
        })

    tools.sort(key=lambda t: (t["eligible"], t["avg_overall"]), reverse=True)
    return {
        "tools": tools,
        "meta": {
            "dataset": _LEADERBOARD_DATASET,
            "benchmark_version": ", ".join(sorted(versions)) if versions else "unknown",
            "updated_at": latest_updated_at.isoformat(timespec="seconds") if latest_updated_at else None,
            "minimum_coverage": _MIN_COVERAGE,
            "ranking_rule": "仅覆盖率达到 95% 的报告参与正式排名",
            "weights": EvalConfig().weights,
        },
    }
