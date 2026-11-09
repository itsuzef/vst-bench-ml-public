# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""vst_bench_ml.sampling — three-tier parameter sampling.

Produces normalized ([0,1]) parameter vectors over a set of audio-relevant
``ParamSpec``s. Values are sent verbatim to the TestHost ``set_parameters`` RPC
(discrete types quantize internally on the plugin side).

Tiers (proposal proportions A=60% / B=25% / C=15%):
  A  preset-perturbation — Gaussian jitter (varying scale) around a base vector;
     discrete params occasionally uniformly resampled.
  B  factored sweeps     — vary one parameter at a time, others held at base.
  C  structured random   — Latin-hypercube over continuous dims, uniform discrete.

A "vector" is ``dict[index -> normalized value]``. Use ``to_param_list`` to turn
it into the ``[{"index","value"}]`` payload the RPC expects.
"""

from __future__ import annotations

import numpy as np

from .introspect import ParamSpec


def _default_norm(s: ParamSpec) -> float:
    """The plugin default expressed in normalized [0,1].

    Prefers the calibrated ``default_norm`` captured from the live plugin:
    float params can be skew-mapped, and linear conversion programs the wrong
    value (W8.2h: Filter Cutoff's 500 Hz default is normalized 0.424, but
    linear gives 0.024 ≡ 20 Hz — the v1 pool was anchored on that error).
    """
    if s.default_norm is not None:
        return float(np.clip(s.default_norm, 0.0, 1.0))
    if s.type == "bool":
        return 1.0 if s.default in (True, "true", 1, "1") else 0.0
    if s.type == "choice":
        idx = s.choices.index(s.default) if s.default in s.choices else 0
        return s.level_to_normalized(idx)
    d = s.default if isinstance(s.default, (int, float)) else s.min
    return s.real_to_norm(float(d))


def _rand_norm(s: ParamSpec, rng: np.random.Generator) -> float:
    """A random valid normalized value for this param."""
    if s.type == "float":
        return float(rng.random())
    n = s.n_levels
    return s.level_to_normalized(int(rng.integers(n))) if n > 0 else float(rng.random())


def base_vector(specs: list[ParamSpec]) -> dict[int, float]:
    """Normalized default vector — the anchor for Tier A / B."""
    return {s.index: _default_norm(s) for s in specs}


def to_param_list(vec: dict[int, float]) -> list[dict]:
    return [{"index": i, "value": float(v)} for i, v in vec.items()]


# ── tiers ────────────────────────────────────────────────────────


def tier_a(specs, rng, base, sigma_choices=(0.05, 0.15, 0.40), resample_p=0.5):
    """Preset perturbation at a randomly chosen jitter scale."""
    sigma = float(rng.choice(sigma_choices))
    out = dict(base)
    for s in specs:
        if s.type == "float":
            out[s.index] = float(
                np.clip(base[s.index] + rng.normal(0.0, sigma), 0.0, 1.0)
            )
        elif rng.random() < resample_p:
            out[s.index] = _rand_norm(s, rng)
    return out


def tier_b(specs, rng, base):
    """Factored: vary exactly one parameter (full-range), hold the rest at base."""
    out = dict(base)
    s = specs[int(rng.integers(len(specs)))]
    out[s.index] = float(rng.random()) if s.type == "float" else _rand_norm(s, rng)
    return out


def tier_c(specs, rng, n):
    """Latin-hypercube over continuous dims + uniform discrete; returns n vectors."""
    cont = [s for s in specs if s.type == "float"]
    disc = [s for s in specs if s.type != "float"]
    vecs = [dict() for _ in range(n)]
    if cont:
        # LHS without scipy: per-dim stratified permutation.
        for s in cont:
            edges = (np.arange(n) + rng.random(n)) / n  # one sample per stratum
            rng.shuffle(edges)
            for k in range(n):
                vecs[k][s.index] = float(edges[k])
    for s in disc:
        for k in range(n):
            vecs[k][s.index] = _rand_norm(s, rng)
    return vecs


def plan(specs, n, rng, base=None, anchors=None, proportions=(0.60, 0.25, 0.15)):
    """Build a sampling plan: a list of (tier, vector) of length n.

    Tier A/B perturb/hold a randomly chosen anchor from ``anchors`` (one vector
    per caller-provided anchor). Without anchors they fall back to the default
    vector (``base``). Tier C is full-range structured random regardless.
    """
    pool = anchors if anchors else [base or base_vector(specs)]
    pa, pb, _ = proportions
    n_a, n_b = int(round(n * pa)), int(round(n * pb))
    n_c = n - n_a - n_b

    def anchor():
        return pool[int(rng.integers(len(pool)))]

    out = []
    out += [("A", tier_a(specs, rng, anchor())) for _ in range(n_a)]
    out += [("B", tier_b(specs, rng, anchor())) for _ in range(n_b)]
    out += [("C", v) for v in tier_c(specs, rng, n_c)]
    return out
