# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""vst_bench_ml.midi_signals — the standardized MIDI test signals.

A fixed bank rendered identically across plugins so embeddings compare timbre,
not note content. Realizes the proposal's 8-item list (item 8, "two velocity
variants of C3", expands to two entries -> 9 named signals).

Each signal is a callable ``(num_samples:int, velocity:float|None) -> list[event]``
where event = {"type","channel","note","velocity","sample_position"}.
Notes: C2 = 36, C3 = 48, E3 = 52, G3 = 55, C4 = 60.

Besides the fixed bank, ``build`` accepts parameterized names (NN = MIDI note
0-127): ``sus_m<NN>`` — held note, e.g. ``sus_m41`` = held F2, used when a
target clip's pitch is estimated rather than fixed; ``hit_m<NN>`` — note held
for 25% of the window then released, so the patch's own release stage shapes a
decay. Approximates a one-shot's envelope when the reference audio decays
(W8 rung 4: sustained renders of decaying bass one-shots sound wrong even at
the right timbre and pitch).
"""

from __future__ import annotations

import re

C2, C3, E3, G3, C4 = 36, 48, 52, 55, 60
DEFAULT_VEL = 0.8


def _hold(notes, num_samples, velocity=DEFAULT_VEL):
    """All notes on at t=0, off at the end (sustained chord/interval).

    The final note_off sits at num_samples - 1: the render host processes
    [0, num_samples) in blocks and drops events at pos == block length, so an
    off at exactly num_samples never fires and the voice hangs into the next
    render (W8.2 non-determinism bug).
    """
    ev = []
    for n in notes:
        ev.append(
            {
                "type": "note_on",
                "channel": 1,
                "note": n,
                "velocity": velocity,
                "sample_position": 0,
            }
        )
    for n in notes:
        ev.append(
            {
                "type": "note_off",
                "channel": 1,
                "note": n,
                "sample_position": num_samples - 1,
            }
        )
    return ev


def _gate(note, num_samples, velocity=DEFAULT_VEL, gate_frac=0.7):
    """One note held for ``gate_frac`` of the window, then released — the tail
    exposes release-stage params that a full-length hold never renders."""
    return [
        {
            "type": "note_on",
            "channel": 1,
            "note": note,
            "velocity": velocity,
            "sample_position": 0,
        },
        {
            "type": "note_off",
            "channel": 1,
            "note": note,
            "sample_position": int(num_samples * gate_frac),
        },
    ]


def _duo(n1, n2, num_samples, velocity=DEFAULT_VEL):
    """Two-note legato phrase: the second note starts while the first is still
    held (overlap → mono/legato glide engages), then holds to the end. Exposes
    glide/portamento and pitch-dependent params (key tracking) that a single
    fixed pitch confounds."""
    half = num_samples // 2
    overlap = int(num_samples * 0.05)
    return [
        {
            "type": "note_on",
            "channel": 1,
            "note": n1,
            "velocity": velocity,
            "sample_position": 0,
        },
        {
            "type": "note_on",
            "channel": 1,
            "note": n2,
            "velocity": velocity,
            "sample_position": half,
        },
        {
            "type": "note_off",
            "channel": 1,
            "note": n1,
            "sample_position": half + overlap,
        },
        {
            "type": "note_off",
            "channel": 1,
            "note": n2,
            "sample_position": num_samples - 1,
        },
    ]


def _arp(notes, num_samples, velocity=DEFAULT_VEL):
    """Sequential notes, each occupying an equal slice of the duration."""
    ev = []
    step = num_samples // max(len(notes), 1)
    for i, n in enumerate(notes):
        on = i * step
        # last off at num_samples would fall outside the rendered range and be
        # dropped by the host (hanging voice) — same off-by-one as _hold
        off = num_samples - 1 if i == len(notes) - 1 else (i + 1) * step
        ev.append(
            {
                "type": "note_on",
                "channel": 1,
                "note": n,
                "velocity": velocity,
                "sample_position": on,
            }
        )
        ev.append({"type": "note_off", "channel": 1, "note": n, "sample_position": off})
    return ev


# name -> builder(num_samples, velocity). velocity=None uses the builder default.
SIGNALS: dict[str, callable] = {
    "sus_c2": lambda n, v=None: _hold([C2], n, v or DEFAULT_VEL),
    "sus_c3": lambda n, v=None: _hold([C3], n, v or DEFAULT_VEL),
    "maj3": lambda n, v=None: _hold([C3, E3], n, v or DEFAULT_VEL),
    "dyad_p5": lambda n, v=None: _hold([C3, G3], n, v or DEFAULT_VEL),
    "triad_maj": lambda n, v=None: _hold([C3, E3, G3], n, v or DEFAULT_VEL),
    "arp_up": lambda n, v=None: _arp([C3, E3, G3, C4], n, v or DEFAULT_VEL),
    "arp_down": lambda n, v=None: _arp([C4, G3, E3, C3], n, v or DEFAULT_VEL),
    "c3_vel_soft": lambda n, v=None: _hold([C3], n, 0.4),
    "c3_vel_hard": lambda n, v=None: _hold([C3], n, 1.0),
    # W8.3 signal study: release-tail + legato/keytrack views (bass register)
    "gate_c2": lambda n, v=None: _gate(C2, n, v or DEFAULT_VEL),
    "duo_c2": lambda n, v=None: _duo(C2, C2 + 7, n, v or DEFAULT_VEL),
    "c2_vel_soft": lambda n, v=None: _hold([C2], n, 0.4),
}


_SUS_M = re.compile(r"^sus_m(\d{1,3})$")
_HIT_M = re.compile(r"^hit_m(\d{1,3})$")


def signal_names() -> list[str]:
    return list(SIGNALS)


def _param_note(match, name: str) -> int:
    note = int(match.group(1))
    if not 0 <= note <= 127:
        raise KeyError(f"MIDI note out of range in signal name: {name}")
    return note


def build(name: str, num_samples: int, velocity: float | None = None) -> list[dict]:
    m = _SUS_M.match(name)
    if m:
        return _hold([_param_note(m, name)], num_samples, velocity or DEFAULT_VEL)
    m = _HIT_M.match(name)
    if m:
        return _gate(
            _param_note(m, name), num_samples, velocity or DEFAULT_VEL, gate_frac=0.25
        )
    return SIGNALS[name](num_samples, velocity)
