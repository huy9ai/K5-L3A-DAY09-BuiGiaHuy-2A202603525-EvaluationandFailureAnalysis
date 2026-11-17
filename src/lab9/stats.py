"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import scipy.stats

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(labels: Sequence[str]) -> list[str]:
    return [str(x).strip().upper() for x in labels]


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError(f"length mismatch: human={len(human)}, judge={len(judge)}")
    h_norm = _norm(human)
    j_norm = _norm(judge)
    tp = sum(1 for h, j in zip(h_norm, j_norm) if h == POS and j == POS)
    fp = sum(1 for h, j in zip(h_norm, j_norm) if h != POS and j == POS)
    fn = sum(1 for h, j in zip(h_norm, j_norm) if h == POS and j != POS)
    tn = sum(1 for h, j in zip(h_norm, j_norm) if h != POS and j != POS)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    tp, fp, fn, tn = cm["tp"], cm["fp"], cm["fn"], cm["tn"]
    n = tp + fp + fn + tn
    if n == 0:
        raise ValueError("Cohen's kappa is undefined for empty inputs")
    p_o = (tp + tn) / n
    p_e = ((tp + fn) * (tp + fp) + (fp + tn) * (fn + tn)) / (n * n)
    if abs(1.0 - p_e) < 1e-12:
        raise ValueError("Cohen's kappa is undefined when p_e == 1")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if abs(denom) < 1e-12:
        raise ValueError("Rogan-Gladen estimator is undefined when sensitivity + specificity == 1")
    est = (observed_rate + specificity - 1.0) / denom
    return max(0.0, min(1.0, float(est)))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if arr_a.shape != arr_b.shape or arr_a.ndim != 1:
        raise ValueError("a and b must be 1D sequences of equal length")
    if len(arr_a) == 0:
        raise ValueError("a and b must not be empty")
    if np.array_equal(arr_a, arr_b):
        return (0.0, 0.0, 0.0)
    diff = float(np.mean(arr_a) - np.mean(arr_b))
    if len(arr_a) == 1:
        return (diff, diff, diff)
    res = scipy.stats.bootstrap(
        (arr_a, arr_b),
        lambda x, y, axis=0: np.mean(x, axis=axis) - np.mean(y, axis=axis),
        paired=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    return (diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if n <= 0 or k <= 0 or k > n or c < 0 or c > n:
        raise ValueError(f"invalid (n={n}, c={c}, k={k}): require 0 <= c <= n and 1 <= k <= n")
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    if n <= 0 or k <= 0 or k > n or c < 0 or c > n:
        raise ValueError(f"invalid (n={n}, c={c}, k={k}): require 0 <= c <= n and 1 <= k <= n")
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)
