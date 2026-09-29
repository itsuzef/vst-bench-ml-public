"""vst_bench_ml.introspect — typed parameter specs.

Primary source of truth is a plugin's ``param_manifest.json``. Each entry
carries the index, semantic type, range/choices,
default, group, and an ``audio_irrelevant`` flag. For plugins without a
manifest, ``specs_from_live`` derives approximate specs from a live
``list_parameters`` response using the ``num_steps`` heuristic.

"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# num_steps sentinel JUCE reports for continuous params (INT_MAX).
_CONTINUOUS_STEPS = 2147483647


@dataclass
class ParamSpec:
    """One automatable parameter, normalized across manifest/live sources."""

    index: int
    name: str
    type: str  # "float" | "int" | "choice" | "bool"
    pid: str = ""
    group: str = ""
    min: float = 0.0
    max: float = 1.0
    choices: list = field(default_factory=list)
    default: object = None
    audio_irrelevant: bool = False
    # Skew calibration (W8.2h): JUCE float params may map normalized [0,1] to
    # real units through a skew curve; converting linearly programs the wrong
    # value (Filter Cutoff: linear 0.024 vs true 0.424 for 500 Hz — the v1
    # pool's anchors were built on that error). ``default_norm`` is the live
    # plugin's normalized default; ``norm_curve`` is [[norm, real], ...]
    # sampled from the live plugin's text readback, ascending in norm.
    default_norm: float | None = None
    norm_curve: list | None = None
    # Optional semantic activation rule from a hand-authored manifest. Generic
    # live introspection cannot infer it, but downstream samplers/searches need
    # the rule to avoid treating inactive controls as independent dimensions.
    mode_dependency: dict | None = None

    @property
    def is_continuous(self) -> bool:
        return self.type == "float"

    def real_to_norm(self, value: float) -> float:
        """Real units -> normalized [0,1], via the calibrated skew curve when
        present, else linear (correct only for unskewed params)."""
        if self.norm_curve:
            norms = [p[0] for p in self.norm_curve]
            reals = [p[1] for p in self.norm_curve]
            import numpy as np

            return float(np.clip(np.interp(value, reals, norms), 0.0, 1.0))
        lo, hi = self.min, self.max
        if hi <= lo:
            return 0.0
        return float(min(max((value - lo) / (hi - lo), 0.0), 1.0))

    def norm_to_real(self, x: float) -> float:
        """Normalized [0,1] -> real units (calibrated when possible)."""
        if self.norm_curve:
            norms = [p[0] for p in self.norm_curve]
            reals = [p[1] for p in self.norm_curve]
            import numpy as np

            return float(np.interp(x, norms, reals))
        return self.min + x * (self.max - self.min)

    @property
    def n_levels(self) -> int:
        """Number of discrete levels (0 for continuous)."""
        if self.type == "choice":
            return max(len(self.choices), 1)
        if self.type == "bool":
            return 2
        if self.type == "int":
            return int(self.max - self.min) + 1
        return 0

    def level_to_normalized(self, level: int) -> float:
        """Map a discrete level index (0..n_levels-1) to a JUCE-normalized value."""
        n = self.n_levels
        if n <= 1:
            return 0.0
        return level / (n - 1)


def load_manifest(path: str | Path) -> list[ParamSpec]:
    """Load typed specs from a param_manifest.json."""
    data = json.loads(Path(path).read_text())
    specs = []
    for p in data["params"]:
        specs.append(
            ParamSpec(
                index=int(p["index"]),
                name=p["name"],
                type=p["type"],
                pid=p.get("id", ""),
                group=p.get("group", ""),
                min=float(p.get("min", 0.0)),
                max=float(p.get("max", 1.0)),
                choices=list(p.get("choices", [])),
                default=p.get("default"),
                audio_irrelevant=bool(p.get("audio_irrelevant", False)),
                default_norm=p.get("default_norm"),
                norm_curve=p.get("norm_curve"),
                mode_dependency=p.get("mode_dependency"),
            )
        )
    return specs


def specs_from_live(parameters: list[dict]) -> list[ParamSpec]:
    """Fallback: derive specs from a live list_parameters response.

    Classifies by num_steps: INT_MAX -> float (continuous); 2 -> bool;
    otherwise -> choice with that many levels. No semantic group/range info.
    """
    specs = []
    for p in parameters:
        steps = int(p.get("num_steps", _CONTINUOUS_STEPS))
        if steps >= _CONTINUOUS_STEPS or steps <= 0:
            ptype = "float"
        elif steps == 2:
            ptype = "bool"
        else:
            ptype = "choice"
        specs.append(
            ParamSpec(
                index=int(p["index"]),
                name=p.get("name", ""),
                type=ptype,
                pid=str(p.get("parameter_id", "")),
                default=p.get("default_value"),
                choices=list(range(steps)) if ptype == "choice" else [],
            )
        )
    return specs


def to_manifest_entry(s: ParamSpec) -> dict:
    """Serialize a ParamSpec to a manifest param entry (load_manifest-compatible)."""
    e = {
        "id": s.pid,
        "index": s.index,
        "name": s.name,
        "type": s.type,
        "group": s.group,
        "default": s.default,
    }
    if s.type == "choice":
        e["choices"] = s.choices
    else:
        e["min"], e["max"] = s.min, s.max
    if s.audio_irrelevant:
        e["audio_irrelevant"] = True
    if s.default_norm is not None:
        e["default_norm"] = s.default_norm
    if s.norm_curve:
        e["norm_curve"] = s.norm_curve
    if s.mode_dependency:
        e["mode_dependency"] = s.mode_dependency
    return e


def write_manifest(specs: list[ParamSpec], plugin: str, path: str | Path) -> dict:
    """Write a load-manifest-compatible parameter manifest."""
    data = {
        "version": 1,
        "plugin": plugin,
        "param_count": len(specs),
        "source": "live-introspection",
        "params": [to_manifest_entry(s) for s in specs],
    }
    Path(path).write_text(json.dumps(data, indent=2))
    return data


def audio_relevant(specs: list[ParamSpec]) -> list[ParamSpec]:
    """Specs the sampler should vary (excludes audio_irrelevant)."""
    return [s for s in specs if not s.audio_irrelevant]


def exclude_groups(specs: list[ParamSpec], groups: set[str]) -> list[ParamSpec]:
    """Drop specs whose group is in ``groups`` (e.g. {'seq','groove'} when
    driving explicit MIDI rather than the internal sequencer)."""
    return [s for s in specs if s.group not in groups]
