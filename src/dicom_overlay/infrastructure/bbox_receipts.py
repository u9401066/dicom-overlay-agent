"""Exact coordinate serialization shared by native-tool receipt consumers."""

from __future__ import annotations

import math


def canonical_bbox_coordinate(value: float) -> str:
    """Match JavaScript Math.round(value * 10000), then toFixed(4).

    floor(scaled + 0.5) is not equivalent for the float just below 0.5:
    the addition itself rounds up to 1.0. Compare the fractional part so
    image/turn receipts do not need an epsilon or relaxed digest matching.
    """
    scaled = value * 10_000
    if not math.isfinite(scaled):
        raise ValueError("bbox receipt coordinate must be finite")
    lower = math.floor(scaled)
    rounded = (lower + int(scaled - lower >= 0.5)) / 10_000
    return f"{rounded:.4f}"
