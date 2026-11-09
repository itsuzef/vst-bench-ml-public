# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

import json

import numpy as np

from vst_bench_ml import export


def test_save_npz_and_manifest(tmp_path):
    export.save_npz(
        np.array([0.0, 0.5], dtype=np.float32), 48000, str(tmp_path / "audio.npz")
    )
    loaded = np.load(tmp_path / "audio.npz")
    assert loaded["sr"] == 48000
    records = [{"patch_id": "p0", "tier": "A", "signal": "sus_c3"}]
    manifest = export.write_manifest(tmp_path, records, {"seed": 1})
    assert manifest["n_records"] == 1
    assert json.loads((tmp_path / "manifest.json").read_text())["seed"] == 1
