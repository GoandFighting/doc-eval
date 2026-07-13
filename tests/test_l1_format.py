"""Tests for L1 format quality evaluator."""

from eval.layers.l1_format import L1FormatEvaluator


class TestL1FormatEvaluator:
    def test_clean_markdown_scores_high(self):
        evaluator = L1FormatEvaluator()
        md = "# Title\n\nSome paragraph text here.\n\n## Section\n\nMore text.\n"
        score = evaluator.evaluate(md)
        assert score >= 90.0, f"Clean markdown should score high, got {score}"

    def test_empty_markdown_scores_zero(self):
        evaluator = L1FormatEvaluator()
        assert evaluator.evaluate("") == 0.0
        assert evaluator.evaluate("   ") == 0.0

    def test_bad_markdown_scores_lower(self):
        evaluator = L1FormatEvaluator()
        md = "# Title\n### Skipped H2\nSome text   \n\n\n\n## Back\n"
        score = evaluator.evaluate(md)
        assert score < 90.0, f"Bad markdown should score lower, got {score}"

    def test_detailed_result_has_violations(self):
        evaluator = L1FormatEvaluator()
        md = "# Title\n### Skipped\n"
        result = evaluator.evaluate_detailed(md)
        assert result.violation_count > 0
        assert len(result.violations) == result.violation_count
        assert all("rule_id" in v for v in result.violations)
