"""Tests for platform-aware evaluation runtime configuration."""

from eval.core import config as config_module
from eval.core.config import EvalConfig, server_process_workers


def test_windows_threading_default_is_enabled(monkeypatch):
    monkeypatch.delenv("DOC_EVAL_THREADED", raising=False)
    monkeypatch.delenv("DOC_EVAL_BATCH_CONCURRENCY", raising=False)
    monkeypatch.setattr(config_module.sys, "platform", "win32")

    config = EvalConfig()

    assert config.parsebench_threaded is True
    assert config.batch_concurrency == 4


def test_linux_threading_default_is_disabled_for_signal_compatibility(monkeypatch):
    monkeypatch.delenv("DOC_EVAL_THREADED", raising=False)
    monkeypatch.setattr(config_module.sys, "platform", "linux")

    assert EvalConfig().parsebench_threaded is False


def test_runtime_concurrency_environment_overrides(monkeypatch):
    monkeypatch.setenv("DOC_EVAL_THREADED", "false")
    monkeypatch.setenv("DOC_EVAL_BATCH_CONCURRENCY", "2")

    config = EvalConfig()

    assert config.parsebench_threaded is False
    assert config.batch_concurrency == 2


def test_invalid_concurrency_environment_uses_safe_default(monkeypatch):
    monkeypatch.setenv("DOC_EVAL_BATCH_CONCURRENCY", "invalid")

    assert EvalConfig().batch_concurrency == 4


def test_linux_server_defaults_to_two_persistent_processes(monkeypatch):
    monkeypatch.delenv("DOC_EVAL_PROCESS_WORKERS", raising=False)
    monkeypatch.setattr(config_module.sys, "platform", "linux")

    assert server_process_workers() == 2


def test_linux_process_worker_count_can_be_overridden_or_disabled(monkeypatch):
    monkeypatch.setattr(config_module.sys, "platform", "linux")
    monkeypatch.setenv("DOC_EVAL_PROCESS_WORKERS", "3")
    assert server_process_workers() == 3

    monkeypatch.setenv("DOC_EVAL_PROCESS_WORKERS", "0")
    assert server_process_workers() == 0


def test_windows_server_keeps_threaded_runtime(monkeypatch):
    monkeypatch.setattr(config_module.sys, "platform", "win32")
    monkeypatch.setenv("DOC_EVAL_PROCESS_WORKERS", "3")

    assert server_process_workers() == 0
