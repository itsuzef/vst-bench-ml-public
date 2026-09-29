from pathlib import Path
import tomllib

import numpy as np
import pytest

from vst_bench_ml import quality


def test_quarantined_modules_are_not_imported():
    source = Path(__file__).parents[1] / "src" / "vst_bench_ml" / "cli.py"
    text = source.read_text()
    for name in ("pool", "presets", "sensitivity", "spectral"):
        assert f"import {name}" not in text


def test_pyloudnorm_is_a_required_exact_dependency():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    dependencies = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    assert "pyloudnorm==0.1.1" in dependencies


def test_missing_pyloudnorm_fails_clearly(monkeypatch):
    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "pyloudnorm":
            raise ModuleNotFoundError("No module named 'pyloudnorm'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    with pytest.raises(ModuleNotFoundError, match="pyloudnorm"):
        quality.normalize_lufs(np.ones(48000, dtype=np.float32), 48000)
