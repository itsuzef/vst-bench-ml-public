# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

from importlib.metadata import requires
from pathlib import Path

import numpy as np
from packaging.requirements import Requirement
import pytest

from vst_bench_ml import quality


def test_quarantined_modules_are_not_imported():
    source = Path(__file__).parents[1] / "src" / "vst_bench_ml" / "cli.py"
    text = source.read_text()
    for name in ("pool", "presets", "sensitivity", "spectral"):
        assert f"import {name}" not in text


def test_pyloudnorm_is_a_required_runtime_dependency():
    dependencies = [Requirement(item) for item in requires("vst-bench-ml")]
    assert any(item.name == "pyloudnorm" and item.marker is None for item in dependencies)


def test_missing_pyloudnorm_fails_clearly(monkeypatch):
    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "pyloudnorm":
            raise ModuleNotFoundError("No module named 'pyloudnorm'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    with pytest.raises(ModuleNotFoundError, match="pyloudnorm"):
        quality.normalize_lufs(np.ones(48000, dtype=np.float32), 48000)
