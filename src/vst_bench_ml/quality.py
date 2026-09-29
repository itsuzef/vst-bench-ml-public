"""vst_bench_ml.quality — audio loading, quality filtering, normalization.

Filters that keep a dataset clean:
  * silence gate     — reject AC RMS < -60 dBFS (dead/DC-only patches)
  * clip detection   — reject sustained full-scale clipping
  * loudness          — normalize to -14 LUFS (ITU-R BS.1770 via pyloudnorm)
"""

from __future__ import annotations

import numpy as np
import soundfile as sf

SILENCE_DBFS = -60.0
CLIP_LEVEL = 0.999
CLIP_MAX_FRACTION = 0.01  # >1% of samples at full scale = sustained clipping


def load_wav(path: str):
    """Return (samples float32 in [-1,1], sample_rate). Shape (n,) or (n, ch)."""
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    return x, sr


def _mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1) if x.ndim == 2 else x


def rms(x: np.ndarray) -> float:
    m = _mono(x)
    return float(np.sqrt(np.mean(m * m))) if m.size else 0.0


def rms_dbfs(x: np.ndarray) -> float:
    r = rms(x)
    return -np.inf if r <= 0 else 20.0 * np.log10(r)


def ac_rms(x: np.ndarray) -> float:
    """RMS after removing DC; constant-valued buffers contain no audio."""
    m = _mono(x)
    if not m.size:
        return 0.0
    centered = m - np.mean(m, dtype=np.float64)
    return float(np.sqrt(np.mean(centered * centered)))


def ac_rms_dbfs(x: np.ndarray) -> float:
    r = ac_rms(x)
    return -np.inf if r <= 0 else 20.0 * np.log10(r)


def is_silent(x: np.ndarray, thresh_dbfs: float = SILENCE_DBFS) -> bool:
    return ac_rms_dbfs(x) < thresh_dbfs


def clip_fraction(x: np.ndarray, level: float = CLIP_LEVEL) -> float:
    m = _mono(x)
    return float(np.mean(np.abs(m) >= level)) if m.size else 0.0


def is_clipped(x: np.ndarray, max_fraction: float = CLIP_MAX_FRACTION) -> bool:
    return clip_fraction(x) > max_fraction


def normalize_lufs(
    x: np.ndarray, sr: int, target: float = -14.0, peak_ceiling: float = 0.891
):  # -1 dBTP (10**(-1/20))
    """Normalize to ``target`` LUFS, then apply a peak ceiling. Returns (audio, in_lufs).

    The ceiling (broadcast-standard -1 dBTP) prevents the >1.0 overshoot that
    occurs when a near-silent patch is boosted to -14 LUFS — such clips end up
    quieter than target but never clip. Falls back to RMS normalization if
    loudness can't be measured (clip shorter than the BS.1770 block size).
    """
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    try:
        loudness = meter.integrated_loudness(x)
        if not np.isfinite(loudness):
            raise ValueError
        out = pyln.normalize.loudness(x, loudness, target)
        in_lufs = float(loudness)
    except ValueError:
        r = rms(x)
        if r <= 0:
            return x.astype(np.float32), -np.inf
        out = x * ((10 ** (target / 20.0)) / r)
        in_lufs = rms_dbfs(x)

    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > peak_ceiling:
        out = out * (peak_ceiling / peak)
    return out.astype(np.float32), in_lufs


def assess(x: np.ndarray, sr: int) -> dict:
    """One-shot quality report for a clip (native, JSON-safe types)."""
    db = float(rms_dbfs(x))
    ac_db = float(ac_rms_dbfs(x))
    dc = float(np.mean(_mono(x))) if np.size(x) else 0.0
    return {
        "rms_dbfs": round(db, 2) if np.isfinite(db) else None,
        "ac_rms_dbfs": round(ac_db, 2) if np.isfinite(ac_db) else None,
        "dc_offset": round(dc, 6),
        "clip_fraction": round(float(clip_fraction(x)), 5),
        "silent": bool(is_silent(x)),
        "clipped": bool(is_clipped(x)),
    }
