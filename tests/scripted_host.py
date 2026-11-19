# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""A scripted host and dataset helpers shared by the schema v2 tests."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vst_bench_ml import attempts, cli, provenance

FIXTURE = Path(__file__).parent / "fixtures" / "parameter-manifest.json"
IDENTITY = {
    "host": {
        "protocol_version": "1",
        "source_repository": "https://example.invalid/host",
        "source_commit": "a" * 40,
        "executable_sha256": "b" * 64,
        "build_configuration": "Release",
    },
    "plugin": {
        "sha256": "c" * 64,
        "format": "VST3",
        "name": "Example",
        "vendor": "Example",
        "identifier": "org.example.fixture",
    },
    "plugin_identifier": "org.example.fixture",
}


def render(tmp_path, monkeypatch, *, silent=(), fail_at=None, fail_parameters_at=None,
           arguments=("--n", "3", "--signals", "sus_c3,gate_c2"), plugin_report=None,
           during_render=None, error=None):
    """Run the CLI against a scripted host; return (dataset, host trace rows).

    ``plugin_report`` overrides plugin identity fields the host reports,
    ``during_render`` is called once inside the first render, and ``error``
    is the expected SystemExit message when the command must fail.
    """
    trace = []

    class Host:
        def __init__(self, port):
            self.patches = 0

        def ensure_plugin(self, requested):
            return {**IDENTITY, "plugin": {**IDENTITY["plugin"], "path": requested,
                                           **(plugin_report or {})}}

        def set_parameters(self, values):
            self.patches += 1
            if self.patches == fail_parameters_at:
                raise RuntimeError("parameter rejected")

        def render_audio(self, num_samples, output_path, midi_events):
            identifier = Path(output_path).stem
            if during_render and not trace:
                during_render()
            if len(trace) == fail_at:
                trace.append({"attempt_id": identifier, "outcome": "failed"})
                raise RuntimeError("host stopped")
            phase = np.arange(num_samples, dtype=np.float32)
            level = 0.0 if identifier in silent else 0.2
            sf.write(output_path, level * np.sin(2 * np.pi * 440 * phase / 44100), 44100)
            trace.append({
                "attempt_id": identifier,
                "outcome": "rendered",
                "output": {"bytes": Path(output_path).stat().st_size,
                           "sha256": provenance.sha256_file(output_path)},
            })

    monkeypatch.setattr(cli, "TestHostClient", Host)
    plugin = tmp_path / "example.vst3"
    if not plugin.exists():
        plugin.write_bytes(b"plugin")
    dataset = tmp_path / "dataset"
    command = ["render", "--plugin", str(tmp_path / "example.vst3"), "--param-manifest",
               str(FIXTURE), "--out", str(dataset), "--seconds", "0.1", *arguments]
    if error is None and (fail_at is not None or fail_parameters_at is not None):
        error = "render failed after provenance was preserved"
    if error is None:
        cli.main(command)
    else:
        with pytest.raises(SystemExit, match=error):
            cli.main(command)
    return dataset, trace


def rows_of(dataset):
    return [json.loads(line) for line in (dataset / attempts.LEDGER_NAME).read_text().splitlines()]


def reseal(dataset, rows, **changes):
    """Rewrite the ledger and reseal the manifest coherently, as a careful editor could."""
    ledger = dataset / attempts.LEDGER_NAME
    ledger.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    manifest = json.loads((dataset / "manifest.json").read_text())
    manifest["artifacts"]["attempt_ledger"] = provenance.file_identity(ledger, dataset)
    manifest["attempts"] = attempts.counts(rows)
    for key, value in changes.items():
        manifest[key] = value
    provenance.write_manifest(dataset / "manifest.json", manifest)


def verify(dataset, **options):
    return provenance.verify_manifest(dataset / "manifest.json", **options)
