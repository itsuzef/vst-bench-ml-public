# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""vst_bench_ml.batch — dataset render orchestration.

This module drives a sampling plan sequentially through one compatible host and
yields records linking each parameter vector to rendered audio.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import midi_signals
from .client import TestHostClient
from .sampling import to_param_list


def generate(
    client: TestHostClient,
    specs,  # list[ParamSpec] varied (defines the param vector)
    sampling_plan,  # list[(tier, vector)] from sampling.plan
    out_dir: str | Path,
    signals=("sus_c3",),
    signal_mode: str = "all",  # "all": every signal per patch; "cycle": one per patch
    num_samples: int = 88_200,  # 2 s @ 44.1 kHz
    wav_dir: str | Path | None = None,
    process=None,  # optional callback(record, wav_path) -> record|None
    progress_every: int = 50,
    event_sink=None,  # optional callback for every preserved drop/failure
    records=None,  # optional caller-owned list, preserving partial success on failure
):
    """Render a sampling plan. Returns a list of record dicts.

    Base record: {patch_id, tier, signal, audio_path, num_samples, param_vector}.

    ``signal_mode``: "all" renders every signal for each patch (cartesian);
    "cycle" renders one signal per patch (patch i -> signals[i % len]), giving
    one record per patch with even signal coverage and max timbre diversity.

    If ``process`` is given, it is called per render with (record, wav_path); its
    return value replaces the record, and returning ``None`` drops the render
    (used for silence/clip filtering + npz export + dedup). ``wav_dir`` is where
    the transient WAVs are written (defaults to out_dir). Every drop or failure is
    sent to ``event_sink`` before processing continues or an exception is raised.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_dir = Path(wav_dir) if wav_dir else out_dir
    wav_dir.mkdir(parents=True, exist_ok=True)

    records = [] if records is None else records
    dropped = 0
    t0 = time.perf_counter()

    def emit(event):
        if event_sink is not None:
            event_sink(event)

    for i, (tier, vec) in enumerate(sampling_plan):
        patch_id = f"p{i:06d}"
        patch_signals = (
            signals if signal_mode == "all" else (signals[i % len(signals)],)
        )
        try:
            client.set_parameters(to_param_list(vec))
        except (Exception, KeyboardInterrupt) as exc:
            emit(
                {
                    "status": "failure",
                    "stage": "set_parameters",
                    "patch_id": patch_id,
                    "tier": tier,
                    "signal": None,
                    "error_type": type(exc).__name__,
                    "message": str(exc) or type(exc).__name__,
                }
            )
            raise
        for sig in patch_signals:
            midi = midi_signals.build(sig, num_samples)
            wav_path = wav_dir / f"{patch_id}_{sig}.wav"
            record = {
                "patch_id": patch_id,
                "tier": tier,
                "signal": sig,
                "audio_path": str(wav_path),
                "num_samples": num_samples,
                # store only the varied indices to keep records compact
                "param_vector": {int(k): round(float(v), 6) for k, v in vec.items()},
            }
            try:
                client.render_audio(num_samples, str(wav_path), midi)
                if process is not None:
                    processed = process(record, str(wav_path))
                    if processed is None:
                        dropped += 1
                        emit(
                            {
                                "status": "drop",
                                "stage": "process",
                                "patch_id": patch_id,
                                "tier": tier,
                                "signal": sig,
                                "reason": record.pop(
                                    "_drop_reason", "processor-returned-none"
                                ),
                            }
                        )
                        continue
                    record = processed
            except (Exception, KeyboardInterrupt) as exc:
                emit(
                    {
                        "status": "failure",
                        "stage": "render_or_process",
                        "patch_id": patch_id,
                        "tier": tier,
                        "signal": sig,
                        "error_type": type(exc).__name__,
                        "message": str(exc) or type(exc).__name__,
                    }
                )
                raise
            records.append(record)
        if progress_every and (i + 1) % progress_every == 0:
            rate = (i + 1) / (time.perf_counter() - t0)
            print(
                f"  {i + 1}/{len(sampling_plan)} patches  ({rate:.1f}/s, {dropped} dropped)"
            )

    elapsed = time.perf_counter() - t0
    n = len(sampling_plan)
    if n:
        print(
            f"done: {n} patches x {len(signals)} signals = {len(records)} kept "
            f"({dropped} dropped) in {elapsed:.1f}s ({n / elapsed:.1f} patches/s)"
        )
    return records
