# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Deterministic sampling-plan seeds.

Each patch derives an independent RNG from its explicit inputs. This guarantees
plan replay on the validated dependency stack, not cross-machine audio identity.
"""

from __future__ import annotations

import hashlib
import numpy as np


def _entropy(*parts) -> int:
    """Stable 64-bit entropy from arbitrary labels (order-sensitive)."""
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big")


def patch_rng(
    master_seed: int, plugin: str, tier: str, patch_index: int
) -> np.random.Generator:
    """Independent, reproducible Generator for a single patch."""
    seq = np.random.SeedSequence([master_seed, _entropy(plugin, tier), patch_index])
    return np.random.default_rng(seq)


def master_from_label(label: str) -> int:
    """Derive a master seed from a human label (e.g. a run name)."""
    return _entropy(label)
