# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

import json

from vst_bench_ml.introspect import load_manifest, to_manifest_entry, write_manifest


def test_mode_dependency_survives_manifest_roundtrip(tmp_path):
    dependency = {
        "or": [
            {"op": "eq", "param": "osc_mode", "value": "FM"},
            {"op": "gt", "param": "fm_amount", "value": 0},
        ]
    }
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "params": [
                    {
                        "index": 7,
                        "id": "fm_ratio",
                        "name": "FM Ratio",
                        "type": "float",
                        "min": 0.5,
                        "max": 16.0,
                        "default": 1.0,
                        "mode_dependency": dependency,
                    }
                ]
            }
        )
    )

    spec = load_manifest(source)[0]
    assert spec.mode_dependency == dependency
    assert to_manifest_entry(spec)["mode_dependency"] == dependency

    output = tmp_path / "output.json"
    write_manifest([spec], "Example", output)
    assert load_manifest(output)[0].mode_dependency == dependency
