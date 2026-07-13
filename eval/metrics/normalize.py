"""Score normalisation utilities."""

from __future__ import annotations


def to_100(value: float) -> float:
    """Map a 0-1 score to 0-100, clamping to valid range."""
    return max(0.0, min(100.0, value * 100.0))


def clamp_100(value: float) -> float:
    """Clamp an arbitrary score to 0-100."""
    return max(0.0, min(100.0, value))
