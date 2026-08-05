"""Expected return computation for narrative views (vendored)."""

from __future__ import annotations

import numpy as np


def logistic_transform(value: float, k: float, c: float) -> float:
    """Apply a bounded logistic transform to a [0, 1] input.

    ``f(pi) = 1 / (1 + exp(-k * (pi - c)))``

    Used to shape persistence in `compute_qi` and for the diffusion-fit diagnostics.
    """

    clipped_value = float(np.clip(value, 0.0, 1.0))
    exponent = float(np.clip(-k * (clipped_value - c), -60.0, 60.0))
    return float(1.0 / (1.0 + np.exp(exponent)))


def compute_qi(
    alpha: float,
    si_normalized: float,
    lambda_: float,
    pi: float,
    attention: int,
    *,
    k: float = 4.0,
    c: float = 0.5,
) -> float:
    """Compute the narrative-derived expected return view Qi.

    ``Qi = alpha * si_normalized * (1 + lambda_ * f(pi)) * log1p(attention)``
    where ``f(pi) = 1 / (1 + exp(-k * (pi - c)))`` is a logistic transform of the
    persistence ratio.

    Direction is carried solely by ``si_normalized`` (= ``tanh(mean sentiment)``); every
    other factor is non-negative so it can only scale magnitude, never flip sign.
    """

    f_pi = logistic_transform(pi, k, c)
    return float(alpha * si_normalized * (1.0 + lambda_ * f_pi) * np.log1p(attention))
