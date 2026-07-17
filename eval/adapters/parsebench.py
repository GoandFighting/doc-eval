"""Adapter bridging ParseBench's ParseEvaluator for our evaluation pipeline."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import markdown as md_lib
from parse_bench.evaluation.evaluators import parse as parse_evaluator_module
from parse_bench.evaluation.evaluators.parse import ParseEvaluator
from parse_bench.schemas.evaluation import MetricValue
from parse_bench.schemas.parse_output import ParseOutput
from parse_bench.schemas.pipeline_io import InferenceRequest, InferenceResult
from parse_bench.schemas.product import ProductType
from parse_bench.test_cases import load_test_cases
from parse_bench.test_cases.schema import ParseTestCase

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")
_SEP_CELL_RE = re.compile(r"^:?-+:?$")
_METADATA_JSONL_FILES = {"manifest.jsonl"}
_SIGNAL_MAIN_THREAD_ERROR = "signal only works in main thread"


def _compute_table_metrics_inline(
    expected: str,
    actual: str,
    expected_tables: list,
    actual_tables: list,
    teds_variants: set[str] | None = None,
) -> tuple[list[MetricValue], list[MetricValue]]:
    """Compute exact TEDS and GriTS inline to avoid per-document Windows process startup."""
    return (
        parse_evaluator_module._compute_teds_standalone(expected, actual, teds_variants),
        parse_evaluator_module._compute_grits_standalone(expected_tables, actual_tables),
    )


def _load_dataset_test_cases(dataset_dir: Path) -> list:
    """Load ParseBench cases without passing package metadata to its loader.

    ParseBench treats every root-level ``*.jsonl`` file as evaluation rules.
    Dataset-builder's ``manifest.jsonl`` is package metadata, so JSONL-only
    datasets are loaded through a temporary view that omits metadata files.
    Test-case file paths are then mapped back to the real dataset directory.
    """
    metadata_files = [
        path
        for path in dataset_dir.glob("*.jsonl")
        if path.name.casefold() in _METADATA_JSONL_FILES
    ]
    has_sidecar_tests = any(dataset_dir.rglob("*.test.json"))
    if not metadata_files or has_sidecar_tests:
        return load_test_cases(root_dir=dataset_dir)

    with tempfile.TemporaryDirectory(prefix="doc_eval_jsonl_") as temp_dir:
        shadow_root = Path(temp_dir)
        for jsonl_path in dataset_dir.glob("*.jsonl"):
            if jsonl_path.name.casefold() in _METADATA_JSONL_FILES:
                continue
            shutil.copy2(jsonl_path, shadow_root / jsonl_path.name)

        expected_markdown = dataset_dir / "expected_markdown.json"
        if expected_markdown.is_file():
            shutil.copy2(expected_markdown, shadow_root / expected_markdown.name)

        test_cases = load_test_cases(root_dir=shadow_root)
        shadow_root = shadow_root.resolve()
        remapped_cases = []
        for test_case in test_cases:
            try:
                relative_path = test_case.file_path.relative_to(shadow_root)
            except ValueError:
                remapped_cases.append(test_case)
                continue
            remapped_cases.append(
                test_case.model_copy(
                    update={"file_path": (dataset_dir / relative_path).resolve()}
                )
            )
        return remapped_cases


def _is_separator_row(line: str) -> bool:
    """Check if *line* is a pipe-table separator (e.g. ``|---|:--:|---:|``)."""
    stripped = line.strip()
    if not stripped or "|" not in stripped:
        return False
    content = stripped.strip("|").strip()
    if not content:
        return False
    cells = [c.strip() for c in content.split("|")]
    return all(bool(_SEP_CELL_RE.match(c)) for c in cells)


def _is_table_row(line: str) -> bool:
    """Check if *line* could be a pipe-table data row."""
    stripped = line.strip()
    return bool(stripped) and "|" in stripped


def _convert_pipe_tables_to_html(text: str) -> str:
    """Convert pipe-style Markdown tables to HTML ``<table>`` elements.

    ParseBench's GriTS / TEDS metrics only recognise HTML ``<table>`` tags.
    This pre-processing step ensures pipe-style Markdown tables are
    converted to HTML before evaluation so that table metrics are computed
    correctly.
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0
    in_fence = False

    while i < len(lines):
        line = lines[i]

        if _FENCE_RE.match(line):
            in_fence = not in_fence
            result.append(line)
            i += 1
            continue

        if not in_fence and _is_table_row(line) and i + 1 < len(lines) and _is_separator_row(lines[i + 1]):
            table_lines = [line, lines[i + 1]]
            j = i + 2
            while j < len(lines) and _is_table_row(lines[j]):
                table_lines.append(lines[j])
                j += 1

            html = md_lib.markdown("\n".join(table_lines), extensions=["tables"])
            match = re.search(r"<table>.*</table>", html, re.DOTALL)
            if match:
                result.append(match.group(0))
            else:
                result.extend(table_lines)
            i = j
        else:
            result.append(line)
            i += 1

    return "\n".join(result)


_TABLE_METRIC_PREFIXES = (
    "grits",
    "teds",
    "table_",
    "tables_",
    "header_",
    "exp_header",
    "exp_table",
    "structural_",
    "ref_grits",
)


def _is_table_metric(name: str) -> bool:
    """Check if a metric name is table-related (GriTS, TEDS, TRM, etc.)."""
    return name.startswith(_TABLE_METRIC_PREFIXES)


class ParseBenchAdapter:
    """Bridge to ParseBench's evaluation system.

    Loads test cases from the newbench JSONL dataset, groups them by PDF
    file name, and runs ParseEvaluator against converted Markdown output.

    :param dataset_dir: Path to the newbench dataset directory.
    :param enable_teds: Enable TEDS metric for table evaluation.
    :param enable_grits: Enable GriTS metric for table evaluation.
    """

    def __init__(
        self,
        dataset_dir: Path,
        enable_teds: bool = True,
        enable_grits: bool = True,
    ) -> None:
        # ParseBench defaults optional LLM chart normalization to "judge".
        # This deployment has no Anthropic dependency/key, so every text case
        # otherwise repeats a failed import and traceback before returning the
        # unchanged rule scores. Explicit user configuration still wins.
        os.environ.setdefault("LLAMACLOUD_BENCH_LLM_NORMALIZATION", "off")
        if os.environ.get("DOC_EVAL_INLINE_TABLE_METRICS", "1").strip().casefold() not in {
            "0", "false", "no", "off"
        }:
            # ParseBench creates a fresh two-process pool for every table
            # document. Batch-level worker threads already provide bounded
            # document concurrency on Windows and Linux, so run the same exact
            # metric functions inline and avoid nested process pools.
            parse_evaluator_module._compute_table_metrics_parallel = _compute_table_metrics_inline
        self._evaluator = ParseEvaluator(
            enable_rule_based=True,
            enable_teds=enable_teds,
            enable_grits=enable_grits,
            enable_table_record_match=True,
        )
        self._rule_only_evaluator = ParseEvaluator(
            enable_rule_based=True,
            enable_teds=False,
            enable_grits=False,
            enable_structural_consistency=False,
            enable_table_record_match=False,
        )
        self._test_cases: dict[str, list[ParseTestCase]] = self._load_and_group(dataset_dir)

    def _load_and_group(self, dataset_dir: Path) -> dict[str, list[ParseTestCase]]:
        """Load JSONL test cases and group by PDF file name.

        Only ParseTestCase instances are kept; LayoutDetectionTestCase is
        skipped (Visual Grounding dimension requires bbox output).

        Additionally, ParseTestCase entries whose ``test_id`` starts with
        ``layout/`` are excluded -- these are ``order``-type rules from
        ``layout.jsonl`` that ParseBench loads as ParseTestCase but which
        belong to the layout dimension, not text/table evaluation.

        Dataset-builder also publishes ``manifest.jsonl`` as package metadata;
        :func:`_load_dataset_test_cases` excludes it before ParseBench scans the
        dataset.
        """
        all_cases = _load_dataset_test_cases(dataset_dir)
        grouped: dict[str, list[ParseTestCase]] = {}
        for tc in all_cases:
            if not isinstance(tc, ParseTestCase):
                continue
            if tc.test_id.startswith("layout/"):
                continue
            pdf_name = tc.file_path.name
            grouped.setdefault(pdf_name, []).append(tc)

        total = sum(len(v) for v in grouped.values())
        logger.info(
            "Loaded %d ParseTestCase across %d PDFs from %s",
            total,
            len(grouped),
            dataset_dir,
        )
        return grouped

    @property
    def available_pdfs(self) -> list[str]:
        """Return all PDF file names that have test cases."""
        return sorted(self._test_cases.keys())

    def has_test_case(self, pdf_name: str) -> bool:
        """Check whether test cases exist for the given PDF."""
        return pdf_name in self._test_cases

    def expected_dimensions(self, pdf_name: str) -> set[str]:
        """Return ParseBench dimensions expected for a PDF's test cases."""
        test_cases = self._test_cases.get(pdf_name)
        if not test_cases:
            raise KeyError(f"No test case found for PDF: {pdf_name}")

        dimensions: set[str] = set()
        for test_case in test_cases:
            tags = {str(tag).casefold() for tag in (test_case.tags or [])}
            if "text_content" in tags:
                dimensions.add("content_faithfulness")
            if "text_formatting" in tags:
                dimensions.add("semantic_formatting")
            if test_case.test_id.startswith("table/") or (
                test_case.expected_markdown and "<table" in test_case.expected_markdown
            ):
                dimensions.add("tables")
        return dimensions

    def evaluate(self, converted_md: str, pdf_name: str) -> list[MetricValue]:
        """Run ParseBench evaluation for a single document.

        To avoid a conflict between rule-based and table evaluation:

        - **Rule-based metrics** (content, formatting) must see the *original*
          Markdown because ``bag_of_sentence`` annotations are written against
          the user's Markdown syntax (pipe tables, not HTML).
        - **Table metrics** (GriTS, TEDS) require HTML ``<table>`` tags, so
          pipe-style tables are converted to HTML first.

        When the test case has ``expected_markdown`` with HTML tables, both
        runs are executed and the results are merged: rule-based metrics from
        the original run, table metrics from the HTML-converted run.

        :param converted_md: Markdown output from the conversion tool.
        :param pdf_name: PDF file name to look up test cases.
        :return: List of MetricValue from all matching test cases.
        :raises KeyError: If no test case exists for the given PDF.
        """
        test_cases = self._test_cases.get(pdf_name)
        if not test_cases:
            raise KeyError(f"No test case found for PDF: {pdf_name}")

        original_ir = self._wrap_input(converted_md, pdf_name)
        html_converted = _convert_pipe_tables_to_html(converted_md)
        needs_table_run = html_converted != converted_md
        html_ir = self._wrap_input(html_converted, pdf_name) if needs_table_run else None

        all_metrics: list[MetricValue] = []
        failures: list[str] = []

        for tc in test_cases:
            try:
                has_table_expected = bool(
                    tc.expected_markdown and "<table" in tc.expected_markdown
                )
                if has_table_expected and html_ir is not None:
                    # The original Markdown is needed only for rule metrics.
                    # Running the full evaluator here would calculate the
                    # expensive table metrics once on the original input and
                    # immediately discard them after the HTML-normalized run.
                    result = self._rule_only_evaluator.evaluate(original_ir, tc)
                    metrics = list(result.metrics)
                    html_result = self._evaluator.evaluate(html_ir, tc)
                    table_metrics = [
                        m for m in html_result.metrics if _is_table_metric(m.metric_name)
                    ]
                    metrics = [
                        m for m in metrics if not _is_table_metric(m.metric_name)
                    ]
                    metrics.extend(table_metrics)
                else:
                    result = self._evaluator.evaluate(original_ir, tc)
                    metrics = list(result.metrics)

                all_metrics.extend(metrics)
            except Exception as exc:
                if _SIGNAL_MAIN_THREAD_ERROR in str(exc):
                    raise RuntimeError(
                        "ParseBench signal-based evaluation must run on the main thread"
                    ) from exc
                failures.append(f"{tc.test_id}: {exc}")
                logger.exception(
                    "Evaluation failed for test_id=%s (pdf=%s)",
                    tc.test_id,
                    pdf_name,
                )

        if not all_metrics:
            detail = f" First failure: {failures[0]}" if failures else ""
            raise RuntimeError(
                f"ParseBench returned no metrics for PDF '{pdf_name}'.{detail}"
            )

        return all_metrics

    @staticmethod
    def _wrap_input(markdown: str, pdf_name: str) -> InferenceResult:
        """Wrap converted Markdown into a ParseBench InferenceResult."""
        now = datetime.now()
        example_id = Path(pdf_name).stem
        return InferenceResult(
            request=InferenceRequest(
                example_id=example_id,
                source_file_path=pdf_name,
                product_type=ProductType.PARSE,
            ),
            pipeline_name="doc-eval",
            product_type=ProductType.PARSE,
            raw_output={},
            output=ParseOutput(
                example_id=example_id,
                pipeline_name="doc-eval",
                markdown=markdown,
            ),
            started_at=now,
            completed_at=now,
            latency_in_ms=0,
        )
