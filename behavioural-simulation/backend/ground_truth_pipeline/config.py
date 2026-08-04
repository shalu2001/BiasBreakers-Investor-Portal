"""Shared constants: the ground-truth personas and the generator's response model.

CRITICAL: the estimation stage MUST use the same SENT_SLOPE and HOLD_BASE that the
generator used. The original code's bug was a mismatch here (it assumed a sharper,
two-way model and dropped HOLDs), which collapsed alpha and lambda to their bounds.
"""
# ground-truth (alpha, lambda, gamma) -- the known answer key
PERSONAS = {
    "INV_01": (0.88, 2.25, 0.5),
    "INV_02": (0.70, 4.50, 0.1),
    "INV_03": (0.92, 1.25, 4.5),
    "INV_04": (0.98, 1.05, 0.0),
    "INV_05": (0.75, 2.75, 0.8),
}

SENT_SLOPE = 0.4     # how sharply feeling -> action (must match the generator)
HOLD_BASE = 0.85     # baseline patience / tendency to hold
WC_SCALE = 10_000.0  # wealth_change scaling inside the value function
