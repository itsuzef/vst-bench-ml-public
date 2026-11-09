# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""vst_bench_ml.export — dataset manifest + numpy audio export.

Layout written under <out>/:
    audio/<patch>_<signal>.npz   float32 audio (key 'audio', attrs sr)   [if npz]
    records.jsonl                one JSON record per render
    manifest.json                dataset-level metadata + counts + schema

Storing audio as compressed .npz (instead of 100k WAVs) keeps the dataset
manageable on the MBA's local disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

RECORD_SCHEMA = {
    "patch_id": "str — stable per parameter vector",
    "tier": "str — A|B|C sampling tier",
    "signal": "str — MIDI signal name",
    "audio_path": "str — relative path to .npz (or .wav)",
    "num_samples": "int",
    "sample_rate": "int",
    "in_lufs": "float — measured loudness before normalization",
    "param_vector": "dict[int->float] — normalized values for varied params",
    "quality": "dict — rms_dbfs/clip_fraction/silent/clipped",
    "observed_at": "str — UTC observation time for the completed render",
    "output": "dict — relative path, byte count, and SHA-256 identity",
}


def wav_to_npz(wav_path: str, npz_path: str, sr: int) -> None:
    """Convert a rendered WAV to a compressed .npz (float32)."""
    from .quality import load_wav

    x, file_sr = load_wav(wav_path)
    np.savez_compressed(npz_path, audio=x.astype(np.float32), sr=file_sr or sr)


def save_npz(audio: np.ndarray, sr: int, npz_path: str) -> None:
    np.savez_compressed(npz_path, audio=audio.astype(np.float32), sr=sr)


def write_manifest(
    out_dir, records: list[dict], meta: dict, write_records: bool = True
) -> dict:
    """Write manifest.json (and records.jsonl unless already streamed).

    Set ``write_records=False`` when records were streamed incrementally during
    rendering (crash-safe) so they aren't rewritten.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if write_records:
        with (out / "records.jsonl").open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    tiers, signals = {}, {}
    for r in records:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
        signals[r["signal"]] = signals.get(r["signal"], 0) + 1

    manifest = {
        **meta,
        "n_records": len(records),
        "n_patches": len({r["patch_id"] for r in records}),
        "tier_counts": tiers,
        "signal_counts": signals,
        "record_schema": RECORD_SCHEMA,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
