"""Singleton holder for the DatasetRegistry, accessible across routes."""

from __future__ import annotations

from pathlib import Path

from eval.core.registry import DatasetRegistry

_registry: DatasetRegistry | None = None


def init_registry(
    builtin_dir: Path,
    user_dir: Path,
    builtin_process_workers: int = 0,
) -> DatasetRegistry:
    """Initialise the global registry. Call once at startup."""
    global _registry
    _registry = DatasetRegistry(
        builtin_dir=builtin_dir,
        user_dir=user_dir,
        builtin_process_workers=builtin_process_workers,
    )
    return _registry


def get_registry() -> DatasetRegistry:
    """Get the global registry. Must call init_registry first."""
    if _registry is None:
        raise RuntimeError("Registry not initialised. Call init_registry() first.")
    return _registry
