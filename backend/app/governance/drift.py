"""Population stability index for the drift monitor."""

from __future__ import annotations

import numpy as np


def population_stability(expected: np.ndarray, actual: np.ndarray) -> float:
    expected = np.clip(np.asarray(expected, dtype=float), 1e-6, None)
    actual = np.clip(np.asarray(actual, dtype=float), 1e-6, None)
    expected = expected / expected.sum()
    actual = actual / actual.sum()
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def histogram(values, edges) -> np.ndarray:
    counts, _ = np.histogram(np.asarray(values, dtype=float), bins=np.asarray(edges, dtype=float))
    return counts.astype(float)
