"""Tests for leaderboard report aggregation."""

import asyncio
import json

from server import routes_leaderboard


def _write_report(path, scores, *, total=None, failed=0, dimensions=None):
    total = total if total is not None else len(scores) + failed
    evaluated = len(scores)
    payload = {
        "total": total,
        "evaluated": evaluated,
        "failed": failed,
        "errors": [{"pdf_name": "failed.pdf", "error": "conversion failed"}] if failed else [],
        "results": [
            {
                "overall_score": score,
                "metadata": {"version": "0.2.0"},
            }
            for score in scores
        ],
        "summary": {
            "avg_overall": sum(scores) / len(scores),
            "dimension_avg": dimensions or {"tables": 80.0},
            "category_stats": {"table": {"count": len(scores), "avg": 80.0}},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_leaderboard_returns_rank_context(tmp_path, monkeypatch):
    _write_report(tmp_path / "result_A.json", [80.0, 90.0])
    _write_report(tmp_path / "result_B.json", [99.0], total=2, failed=1)
    monkeypatch.setattr(routes_leaderboard, "_LEADERBOARD_DIR", tmp_path)

    response = asyncio.run(routes_leaderboard.get_leaderboard())

    assert [tool["tool"] for tool in response["tools"]] == ["A", "B"]
    assert response["tools"][0]["coverage"] == 100.0
    assert response["tools"][0]["score_distribution"]["median"] == 85.0
    assert response["tools"][1]["eligible"] is False
    assert response["tools"][1]["errors"][0]["pdf_name"] == "failed.pdf"
    assert response["meta"]["benchmark_version"] == "0.2.0"


def test_leaderboard_ignores_invalid_reports(tmp_path, monkeypatch):
    (tmp_path / "result_broken.json").write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(routes_leaderboard, "_LEADERBOARD_DIR", tmp_path)

    response = asyncio.run(routes_leaderboard.get_leaderboard())

    assert response["tools"] == []
