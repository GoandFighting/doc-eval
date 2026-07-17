"""Tests for cross-platform evaluation runtime configuration."""

from eval.core.config import EvalConfig


def test_cross_platform_concurrency_defaults_are_enabled(monkeypatch):
    monkeypatch.delenv("DOC_EVAL_THREADED", raising=False)
    monkeypatch.delenv("DOC_EVAL_BATCH_CONCURRENCY", raising=False)

    config = EvalConfig()

    assert config.parsebench_threaded is True
    assert config.batch_concurrency == 4


def test_runtime_concurrency_environment_overrides(monkeypatch):
    monkeypatch.setenv("DOC_EVAL_THREADED", "false")
    monkeypatch.setenv("DOC_EVAL_BATCH_CONCURRENCY", "2")

    config = EvalConfig()

    assert config.parsebench_threaded is False
    assert config.batch_concurrency == 2


def test_invalid_concurrency_environment_uses_safe_default(monkeypatch):
    monkeypatch.setenv("DOC_EVAL_BATCH_CONCURRENCY", "invalid")

    assert EvalConfig().batch_concurrency == 4
