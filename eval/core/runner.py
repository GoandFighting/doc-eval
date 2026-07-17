"""Async evaluation runner that orchestrates all evaluation dimensions."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from parse_bench.schemas.evaluation import MetricValue

from eval.adapters.parsebench import ParseBenchAdapter
from eval.core.config import EvalConfig
from eval.core.models import (
    BatchEvalRequest,
    BatchEvalResponse,
    BatchSummary,
    DimensionScore,
    EvalRequest,
    EvalResponse,
)
from eval.metrics.normalize import to_100

logger = logging.getLogger(__name__)


class AsyncEvalRunner:
    """Orchestrates ParseBench + L1 (+ L4) evaluation asynchronously.

    :param config: Evaluation configuration.
    """

    def __init__(self, config: EvalConfig | None = None) -> None:
        self._config = config or EvalConfig()
        self._parsebench = ParseBenchAdapter(
            dataset_dir=self._config.dataset_dir,
            enable_teds=self._config.enable_teds,
            enable_grits=self._config.enable_grits,
        )
        self._l1: Any = None
        self._l4: Any = None

    @property
    def available_pdfs(self) -> list[str]:
        """Return all PDF file names that have test cases."""
        return self._parsebench.available_pdfs

    def _ensure_l1(self) -> None:
        """Lazily initialise L1 evaluator."""
        if self._l1 is None:
            from eval.layers.l1_format import L1FormatEvaluator

            self._l1 = L1FormatEvaluator()

    def _ensure_l4(self) -> None:
        """Lazily initialise L4 evaluator."""
        if self._l4 is None:
            from eval.layers.l4_semantic import L4SemanticEvaluator

            self._l4 = L4SemanticEvaluator(model_name=self._config.semantic_model)

    async def evaluate(self, request: EvalRequest) -> EvalResponse:
        """Run full evaluation for a single document.

        :param request: Evaluation request with converted Markdown and PDF name.
        :return: Aggregated evaluation response.
        """
        t_start = time.monotonic()

        # ParseBench uses signal-based rule timeouts on Linux, which must run
        # on the main interpreter thread. Windows has no SIGALRM and can move
        # the blocking work to worker threads so batch concurrency is effective.
        # DOC_EVAL_THREADED remains an explicit compatibility override.
        if self._config.parsebench_threaded:
            pb_metrics: list[MetricValue] = await asyncio.to_thread(
                self._parsebench.evaluate,
                request.converted_md,
                request.pdf_name,
            )
        else:
            pb_metrics = self._parsebench.evaluate(
                request.converted_md,
                request.pdf_name,
            )

        # 2. Extract dimension scores from ParseBench metrics
        dimensions = self._extract_dimensions(pb_metrics)
        expected_dimensions = self._parsebench.expected_dimensions(request.pdf_name)
        actual_dimensions = {dimension.dimension for dimension in dimensions}
        missing_dimensions = sorted(expected_dimensions - actual_dimensions)
        warnings = self._missing_dimension_warnings(missing_dimensions)

        # 3. L1 format quality (fast, synchronous)
        if self._config.enable_l1:
            self._ensure_l1()
            l1_score = self._l1.evaluate(request.converted_md)
            dimensions.append(
                DimensionScore(
                    dimension="format_quality",
                    score=l1_score,
                    metrics={},
                    metadata={"evaluator": "pymarkdownlnt"},
                )
            )

        # 4. L4 semantic similarity (optional, CPU-bound → thread)
        if self._config.enable_l4:
            self._ensure_l4()
            ref_text = self._extract_reference_text(pb_metrics, request)
            if ref_text:
                l4_score = await asyncio.to_thread(
                    self._l4.evaluate,
                    ref_text,
                    request.converted_md,
                )
                dimensions.append(
                    DimensionScore(
                        dimension="semantic",
                        score=l4_score,
                        metrics={},
                        metadata={"evaluator": "sentence-transformers"},
                    )
                )

        # 5. Weighted aggregation
        overall = self._aggregate(dimensions)

        elapsed = time.monotonic() - t_start

        return EvalResponse(
            overall_score=overall,
            dimensions=dimensions,
            pdf_name=request.pdf_name,
            complete=not missing_dimensions,
            warnings=warnings,
            metadata={
                "elapsed_seconds": round(elapsed, 3),
                "version": "0.1.0",
                "metric_count": len(pb_metrics),
                "missing_dimensions": missing_dimensions,
            },
        )

    @staticmethod
    def _missing_dimension_warnings(missing_dimensions: list[str]) -> list[str]:
        """Build a clear warning when ParseBench returns partial metrics."""
        if not missing_dimensions:
            return []

        labels = {
            "content_faithfulness": "内容准确性",
            "semantic_formatting": "格式保真度",
            "tables": "表格还原",
        }
        missing = "、".join(labels.get(name, name) for name in missing_dimensions)
        return [f"评测结果不完整，缺少维度：{missing}。当前总分仅基于已返回维度计算。"]

    def _extract_dimensions(self, metrics: list[MetricValue]) -> list[DimensionScore]:
        """Map ParseBench MetricValue list to DimensionScore list.

        A single PDF may have multiple test cases (text_content +
        text_formatting), each producing overlapping metric names
        (e.g. both emit ``rule_pass_rate``).  We split metrics into
        per-dimension buckets using the dimension-specific composite
        scores as anchors, then build DimensionScore from each bucket.

        Key metric names produced by ParseEvaluator:
        - content_faithfulness (from text_content rules)
        - semantic_formatting (from text_formatting rules)
        - grits_trm_composite / grits_con (from table expected_markdown)
        """
        # Split metrics into segments.  Each ParseEvaluator.evaluate() call
        # produces a contiguous block of metrics.  We detect boundaries by
        # looking for the composite score names that act as "anchors".
        segments: list[list[MetricValue]] = []
        current: list[MetricValue] = []
        anchor_names = {
            "content_faithfulness",
            "semantic_formatting",
        }
        for m in metrics:
            current.append(m)
            if m.metric_name in anchor_names:
                segments.append(current)
                current = []
        if current:
            segments.append(current)

        dimensions: list[DimensionScore] = []

        for seg in segments:
            seg_map: dict[str, float] = {m.metric_name: m.value for m in seg}

            # Content Faithfulness
            if "content_faithfulness" in seg_map:
                dimensions.append(
                    DimensionScore(
                        dimension="content_faithfulness",
                        score=to_100(seg_map["content_faithfulness"]),
                        metrics={
                            "normalized_text_correctness": seg_map.get("normalized_text_correctness", 0.0),
                            "normalized_order": seg_map.get("normalized_order", 0.0),
                            "rule_pass_rate": seg_map.get("rule_pass_rate", 0.0),
                        },
                        metadata={
                            "source": "parsebench:text_content",
                        },
                    )
                )

            # Semantic Formatting
            elif "semantic_formatting" in seg_map:
                dimensions.append(
                    DimensionScore(
                        dimension="semantic_formatting",
                        score=to_100(seg_map["semantic_formatting"]),
                        metrics={
                            "normalized_text_styling": seg_map.get("normalized_text_styling", 0.0),
                            "normalized_title_accuracy": seg_map.get("normalized_title_accuracy", 0.0),
                            "normalized_latex": seg_map.get("normalized_latex", 0.0),
                            "normalized_code_block": seg_map.get("normalized_code_block", 0.0),
                            "rule_pass_rate": seg_map.get("rule_pass_rate", 0.0),
                        },
                        metadata={
                            "source": "parsebench:text_formatting",
                        },
                    )
                )

        # Table metrics are not split by anchor — collect from all segments
        all_map: dict[str, float] = {m.metric_name: m.value for m in metrics}
        table_score = all_map.get("grits_trm_composite")
        if table_score is None:
            table_score = all_map.get("grits_con")
        if table_score is not None:
            dimensions.append(
                DimensionScore(
                    dimension="tables",
                    score=to_100(table_score),
                    metrics={
                        "grits_con": all_map.get("grits_con", 0.0),
                        "table_record_match": all_map.get("table_record_match", 0.0),
                        "grits_trm_composite": all_map.get("grits_trm_composite", 0.0),
                        "teds": all_map.get("teds", 0.0),
                    },
                    metadata={
                        "source": "parsebench:table",
                        "tables_expected": all_map.get("tables_expected", 0.0),
                        "tables_actual": all_map.get("tables_actual", 0.0),
                    },
                )
            )

        return dimensions

    def _extract_reference_text(
        self,
        metrics: list[MetricValue],
        request: EvalRequest,
    ) -> str:
        """Extract reference text for L4 semantic comparison.

        For table test cases, the expected_markdown (HTML tables) is used.
        For text test cases, there is no single reference markdown, so L4
        is skipped (returns empty string).
        """
        # Check if this is a table case by looking for table metrics
        has_table_metrics = any(m.metric_name.startswith("grits") for m in metrics)
        if not has_table_metrics:
            return ""

        # For table cases, the expected_markdown is stored in the test case
        test_cases = self._parsebench._test_cases.get(request.pdf_name, [])
        for tc in test_cases:
            if tc.expected_markdown:
                return tc.expected_markdown
        return ""

    def _aggregate(self, dimensions: list[DimensionScore]) -> float:
        """Compute weighted overall score from dimension scores.

        Weights are re-normalised when some dimensions are missing.
        """
        if not dimensions:
            return 0.0

        available = {d.dimension for d in dimensions}
        active_weights = self._config.active_weights(available)
        if not active_weights:
            return 0.0

        total = 0.0
        for d in dimensions:
            weight = active_weights.get(d.dimension, 0.0)
            total += d.score * weight

        return round(total, 2)

    async def evaluate_batch(self, request: BatchEvalRequest) -> BatchEvalResponse:
        """Run evaluation for multiple documents concurrently.

        Uses a semaphore to limit concurrency and prevent memory exhaustion.
        Individual failures are captured without aborting the batch.

        :param request: Batch request with multiple EvalRequest items.
        :return: Batch response with results, errors, and summary.
        """
        sem = asyncio.Semaphore(self._config.batch_concurrency)

        async def _eval_one(req: EvalRequest) -> EvalResponse:
            async with sem:
                return await self.evaluate(req)

        tasks = [_eval_one(item) for item in request.items]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[EvalResponse] = []
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        for req, raw in zip(request.items, raw_results, strict=False):
            if isinstance(raw, Exception):
                errors.append({"pdf_name": req.pdf_name, "error": str(raw)})
            else:
                results.append(raw)
                warnings.extend(
                    {"pdf_name": raw.pdf_name, "warning": warning}
                    for warning in raw.warnings
                )

        summary = self._build_summary(results)

        return BatchEvalResponse(
            total=len(request.items),
            evaluated=len(results),
            failed=len(errors),
            results=results,
            errors=errors,
            warnings=warnings,
            summary=summary,
        )

    def _build_summary(self, results: list[EvalResponse]) -> BatchSummary:
        """Build aggregated statistics from successful results.

        :param results: List of successful EvalResponse objects.
        :return: BatchSummary with averages, rankings, and category stats.
        """
        if not results:
            return BatchSummary()

        # Overall average
        scores = [r.overall_score for r in results]
        avg_overall = sum(scores) / len(scores)

        # Dimension averages
        dim_scores: dict[str, list[float]] = {}
        for r in results:
            for d in r.dimensions:
                dim_scores.setdefault(d.dimension, []).append(d.score)
        dimension_avg = {
            k: sum(v) / len(v) for k, v in dim_scores.items()
        }

        # Best / worst (top/bottom 5)
        sorted_results = sorted(results, key=lambda r: r.overall_score, reverse=True)
        best = [
            {"pdf_name": r.pdf_name, "score": round(r.overall_score, 2)}
            for r in sorted_results[:5]
        ]
        worst = [
            {"pdf_name": r.pdf_name, "score": round(r.overall_score, 2)}
            for r in sorted_results[-5:][::-1]
        ]

        # Category stats (text vs table based on PDF name prefix)
        category_stats: dict[str, dict[str, Any]] = {}
        for r in results:
            category = self._categorize_pdf(r.pdf_name)
            if category not in category_stats:
                category_stats[category] = {"scores": [], "count": 0}
            category_stats[category]["scores"].append(r.overall_score)
            category_stats[category]["count"] += 1

        for _, stats in category_stats.items():
            cat_scores = stats.pop("scores")
            stats["avg"] = round(sum(cat_scores) / len(cat_scores), 2) if cat_scores else 0.0

        return BatchSummary(
            avg_overall=round(avg_overall, 2),
            dimension_avg=dimension_avg,
            best=best,
            worst=worst,
            category_stats=category_stats,
        )

    def _categorize_pdf(self, pdf_name: str) -> str:
        """Categorise a PDF as 'text' or 'table' based on its test case types.

        If the PDF has table test cases (expected_markdown with HTML tables),
        it's 'table'; otherwise 'text'.
        """
        test_cases = self._parsebench._test_cases.get(pdf_name, [])
        for tc in test_cases:
            if tc.expected_markdown and "<table" in tc.expected_markdown:
                return "table"
        return "text"
