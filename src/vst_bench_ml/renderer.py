# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Shared render, quality-assessment, and normalization path."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import midi_signals, quality
from .sampling import to_param_list


class Renderer:
    """Sequential renderer backed by a compatible host client."""

    def __init__(
        self, client, num_samples: int, sr: int = 44100, target_lufs: float = -14.0
    ):
        self.client = client
        self.num_samples = num_samples
        self.sr = sr
        self.target_lufs = target_lufs
        self._tmp = tempfile.mkdtemp(prefix="vst_bench_ml_renderer_")
        self._counter = 0

    def render(
        self,
        vector: dict,
        signal: str,
        *,
        with_audio: bool = False,
        with_raw_audio: bool = False,
    ) -> dict:
        self.client.set_parameters(to_param_list(vector))
        self._counter += 1
        path = Path(self._tmp) / f"render-{self._counter}.wav"
        self.client.render_audio(
            self.num_samples,
            str(path),
            midi_signals.build(signal, self.num_samples),
        )
        samples, sample_rate = quality.load_wav(str(path))
        path.unlink()
        normalized, input_lufs = quality.normalize_lufs(
            samples, sample_rate, self.target_lufs
        )
        result = {
            "quality": quality.assess(samples, sample_rate),
            "sample_rate": sample_rate,
            "input_lufs": input_lufs,
        }
        if with_audio:
            result["audio"] = normalized
        if with_raw_audio:
            result["raw_audio"] = samples.astype("float32", copy=False)
        return result

    def close(self) -> None:
        if os.path.isdir(self._tmp):
            import shutil

            shutil.rmtree(self._tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
