# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

import numpy as np

from vst_bench_ml import quality


def test_constant_dc_is_silent_audio() -> None:
    x = np.full(44100, -0.891, dtype=np.float32)

    report = quality.assess(x, 44100)

    assert report["silent"] is True
    assert report["rms_dbfs"] == -1.0
    assert report["ac_rms_dbfs"] is None
    assert report["dc_offset"] == -0.891


def test_audio_with_dc_offset_is_not_silent() -> None:
    t = np.arange(44100, dtype=np.float32) / 44100
    x = 0.4 + 0.1 * np.sin(2 * np.pi * 110 * t)

    report = quality.assess(x, 44100)

    assert report["silent"] is False
    assert report["ac_rms_dbfs"] < report["rms_dbfs"]


def test_normalization_applies_peak_ceiling() -> None:
    t = np.arange(44100, dtype=np.float32) / 44100
    x = 0.001 * np.sin(2 * np.pi * 110 * t)

    normalized, _ = quality.normalize_lufs(x, 44100)

    assert np.max(np.abs(normalized)) <= 0.891001
