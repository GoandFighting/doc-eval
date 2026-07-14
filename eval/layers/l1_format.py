"""L1: Markdown format quality evaluator using PyMarkdown lint."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass

from pymarkdown.api import PyMarkdownApi, PyMarkdownScanFailure

logger = logging.getLogger(__name__)

# Penalty per violation, keyed by rule severity heuristics.
# MD001-MD041 are structural rules (higher penalty),
# MD0xx style rules are lower penalty.
_PENALTY_MAP: dict[str, float] = {
    "MD001": 3.0,  # Heading increment
    "MD003": 1.5,  # Heading style consistency
    "MD009": 0.5,  # Trailing spaces
    "MD010": 1.0,  # Hard tabs
    "MD012": 0.5,  # Multiple blank lines
    "MD022": 2.0,  # Headings surrounded by blank lines
    "MD023": 2.0,  # Headings must start at line beginning
    "MD024": 2.0,  # No duplicate headings
    "MD025": 2.0,  # Only one H1
    "MD026": 1.0,  # Trailing punctuation in heading
    "MD029": 1.5,  # Ordered list prefix
    "MD031": 1.5,  # Fenced code blocks surrounded by blank lines
    "MD032": 1.5,  # Lists surrounded by blank lines
    "MD033": 0.5,  # Inline HTML
    "MD040": 1.0,  # Fenced code blocks need language
    "MD041": 2.0,  # First line should be heading
}

_DEFAULT_PENALTY = 1.0
_MAX_PENALTY = 100.0
_SCAN_TIMEOUT_SECONDS = 15.0


@dataclass
class L1Result:
    """Detailed L1 evaluation result."""

    score: float
    violation_count: int
    violations: list[dict[str, object]]


class L1FormatEvaluator:
    """Evaluate Markdown format quality using PyMarkdown lint.

    Runs lint rules against the converted Markdown and computes a 0-100
    score by accumulating penalties per violation.
    """

    def __init__(self) -> None:
        self._api = PyMarkdownApi()

    def evaluate(self, markdown: str) -> float:
        """Run lint and return a 0-100 score.

        :param markdown: Converted Markdown to evaluate.
        :return: Format quality score (0-100, higher is better).
        """
        result = self.evaluate_detailed(markdown)
        return result.score

    def evaluate_detailed(self, markdown: str) -> L1Result:
        """Run lint and return detailed result with violation list.

        :param markdown: Converted Markdown to evaluate.
        :return: L1Result with score and violation details.
        """
        if not markdown.strip():
            return L1Result(score=0.0, violation_count=0, violations=[])

        failures = self._scan_string(markdown)

        penalty = 0.0
        violations: list[dict[str, object]] = []
        for fail in failures:
            p = _PENALTY_MAP.get(fail.rule_id, _DEFAULT_PENALTY)
            penalty += p
            violations.append({
                "rule_id": fail.rule_id,
                "line": fail.line_number,
                "column": fail.column_number,
                "description": fail.rule_description,
                "penalty": p,
            })

        score = max(0.0, 100.0 - min(penalty, _MAX_PENALTY))

        return L1Result(
            score=round(score, 2),
            violation_count=len(failures),
            violations=violations,
        )

    def _scan_string(self, markdown: str) -> list[PyMarkdownScanFailure]:
        """Scan Markdown string via temporary file.

        A timeout is enforced via a daemon thread: PyMarkdown can hang
        indefinitely on deeply nested lists or malformed HTML.
        """
        fd, tmp_path = tempfile.mkstemp(suffix=".md", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(markdown)

            result_holder: list[PyMarkdownScanFailure] | Exception | None = None

            def _scan() -> None:
                nonlocal result_holder
                try:
                    scan_result = self._api.scan_path(tmp_path)
                    result_holder = list(scan_result.scan_failures)
                except Exception as exc:
                    result_holder = exc

            worker = threading.Thread(target=_scan, daemon=True)
            worker.start()
            worker.join(timeout=_SCAN_TIMEOUT_SECONDS)

            if worker.is_alive():
                logger.warning(
                    "PyMarkdown scan timed out after %ss, skipping L1",
                    _SCAN_TIMEOUT_SECONDS,
                )
                return []

            if isinstance(result_holder, Exception):
                logger.exception("PyMarkdown scan failed", exc_info=result_holder)
                return []

            return result_holder or []
        except Exception:
            logger.exception("PyMarkdown scan failed")
            return []
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
