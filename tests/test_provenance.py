import json
import importlib.metadata
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vst_bench_ml import cli, provenance, sampling, seeding
from vst_bench_ml.introspect import load_manifest


def test_dependency_identity_records_scipy_and_detects_its_version_change(monkeypatch):
    original = provenance.dependency_identity()
    assert next(x["version"] for x in original["items"] if x["distribution"] == "scipy") == importlib.metadata.version("scipy")
    observed_version = importlib.metadata.version
    monkeypatch.setattr(importlib.metadata, "version",
                        lambda name: "0.0.0" if name == "scipy" else observed_version(name))
    assert provenance.dependency_identity()["sha256"] != original["sha256"]


def test_offline_verification_does_not_require_matching_installed_dependencies(tmp_path, monkeypatch):
    payload = identity_payload(tmp_path, {"sha256": "3" * 64, "patches": 0})
    path = tmp_path / "manifest.json"
    provenance.write_manifest(path, payload)
    monkeypatch.setattr(importlib.metadata, "version",
                        lambda name: pytest.fail("offline verification queried the current environment"))
    assert provenance.verify_manifest(path)["outcomes"]["kept"] == 0


def identity_payload(tmp_path, plan_identity):
    records = tmp_path / "records.jsonl"
    failures = tmp_path / "failures.jsonl"
    records.write_text("")
    failures.write_text("")
    dependencies = [{"distribution": "numpy", "version": "2.2.6"}]
    return {
        "schema": provenance.SCHEMA,
        "observation": {
            "started_at": "2026-09-08T00:00:00Z",
            "completed_at": "2026-09-08T00:00:01Z",
            "status": "completed",
        },
        "identities": {
            "package": {
                "distribution": "vst-bench-ml",
                "version": "0.0.1",
                "python_sources_sha256": "a" * 64,
            },
            "host": {
                "protocol_version": "1",
                "source_repository": "https://example.invalid/host",
                "source_commit": "b" * 40,
                "executable_sha256": "c" * 64,
                "build_configuration": "Release",
            },
            "plugin": {
                "path": "/example/plugin.vst3",
                "sha256": "d" * 64,
                "format": "VST3",
                "name": "Example",
                "vendor": "Example",
                "identifier": "org.example.fixture",
            },
            "parameters": {
                "source_sha256": "e" * 64,
                "plugin": "org.example.fixture",
                "parameters_sha256": "f" * 64,
                "parameter_count": 1,
            },
            "environment": {
                "python_version": "3.12.0",
                "python_implementation": "CPython",
                "python_executable_sha256": "1" * 64,
                "operating_system": "ExampleOS",
                "operating_system_release": "1",
                "architecture": "arm64",
            },
            "dependencies": {
                "items": dependencies,
                "sha256": provenance.canonical_sha256(dependencies),
            },
            "rng": {
                "algorithm": "numpy.random.Generator(PCG64)",
                "seed_derivation": "vst_bench_ml.seeding.patch_rng/v1",
                "master_seed": seeding.master_from_label("replay"),
                "plugin_identifier": "org.example.fixture",
                "stage": "plan",
                "stream_index": 0,
                "requested_patches": 8,
                "plan_sha256": plan_identity["sha256"],
            },
            "normalization": {
                "algorithm": "ITU-R BS.1770",
                "implementation": "vst_bench_ml.quality.normalize_lufs/v1",
                "dependency": {"distribution": "pyloudnorm", "version": "0.1.1"},
                "target_lufs": -14.0,
            },
        },
        "outcomes": {"kept": 0, "dropped": 0, "failures": 0},
        "artifacts": {
            "records": provenance.file_identity(records, tmp_path),
            "failure_ledger": provenance.file_identity(failures, tmp_path),
            "outputs": [],
            "outputs_sha256": provenance.canonical_sha256([]),
        },
    }


def test_sampling_plan_replays_deterministically(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "parameter-manifest.json"
    specs = load_manifest(fixture)
    seed = seeding.master_from_label("replay")
    rng = seeding.patch_rng(seed, "org.example.fixture", "plan", 0)
    plan = sampling.plan(specs, 8, rng)
    payload = identity_payload(tmp_path, provenance.sampling_plan_identity(plan))
    manifest = provenance.seal_manifest(payload)

    provenance.verify_sampling_replay(manifest, specs)

    manifest["identities"]["rng"]["plan_sha256"] = "0" * 64
    manifest = provenance.seal_manifest(manifest)
    with pytest.raises(provenance.IntegrityError, match="replay mismatch"):
        provenance.verify_sampling_replay(manifest, specs)


def test_verify_detects_output_corruption(tmp_path):
    output = tmp_path / "audio" / "p000000_sus_c3.npz"
    output.parent.mkdir()
    output.write_bytes(b"original")
    payload = identity_payload(tmp_path, {"sha256": "3" * 64, "patches": 1})
    payload["outcomes"]["kept"] = 1
    payload["artifacts"]["outputs"] = [provenance.file_identity(output, tmp_path)]
    payload["artifacts"]["outputs_sha256"] = provenance.canonical_sha256(
        payload["artifacts"]["outputs"]
    )
    (tmp_path / "records.jsonl").write_text(
        json.dumps(
            {
                "audio_path": payload["artifacts"]["outputs"][0]["path"],
                "observed_at": "2026-09-08T00:00:00Z",
                "output": payload["artifacts"]["outputs"][0],
            }
        )
        + "\n"
    )
    payload["artifacts"]["records"] = provenance.file_identity(
        tmp_path / "records.jsonl", tmp_path
    )
    manifest_path = tmp_path / "manifest.json"
    provenance.write_manifest(manifest_path, payload)
    provenance.verify_manifest(manifest_path)

    output.write_bytes(b"corrupt")
    with pytest.raises(provenance.IntegrityError, match="mismatch"):
        provenance.verify_manifest(manifest_path)


def test_render_writes_complete_verifiable_provenance(tmp_path, monkeypatch):
    plugin = tmp_path / "example.vst3"
    parameter_manifest = Path(__file__).parent / "fixtures" / "parameter-manifest.json"
    output = tmp_path / "dataset"

    class Host:
        def __init__(self, port):
            self.port = port

        def ensure_plugin(self, requested):
            return {
                "host": {
                    "protocol_version": "1",
                    "source_repository": "https://example.invalid/host",
                    "source_commit": "a" * 40,
                    "executable_sha256": "b" * 64,
                    "build_configuration": "Release",
                },
                "plugin": {
                    "path": requested,
                    "sha256": "c" * 64,
                    "format": "VST3",
                    "name": "Example",
                    "vendor": "Example",
                    "identifier": "org.example.fixture",
                },
                "plugin_identifier": "org.example.fixture",
            }

        def set_parameters(self, values):
            self.values = values

        def render_audio(self, num_samples, output_path, midi_events):
            phase = np.arange(num_samples, dtype=np.float32)
            audio = 0.2 * np.sin(2 * np.pi * 440 * phase / 44100)
            sf.write(output_path, audio, 44100)

    monkeypatch.setattr(cli, "TestHostClient", Host)
    cli.main(
        [
            "render",
            "--plugin",
            str(plugin),
            "--param-manifest",
            str(parameter_manifest),
            "--out",
            str(output),
            "--n",
            "1",
            "--seconds",
            "0.1",
        ]
    )

    manifest = provenance.verify_manifest(output / "manifest.json")
    assert manifest["outcomes"] == {"kept": 1, "dropped": 0, "failures": 0}
    assert set(manifest["identities"]) == {
        "package",
        "host",
        "plugin",
        "parameters",
        "environment",
        "dependencies",
        "rng",
        "normalization",
    }
    package_files = {
        item["path"]
        for item in manifest["identities"]["package"]["python_source_files"]
    }
    assert package_files == set(provenance.DISTRIBUTED_MODULES)
    provenance.verify_sampling_replay(manifest, load_manifest(parameter_manifest))


def test_render_rejects_parameter_manifest_for_different_plugin(tmp_path, monkeypatch):
    parameter_manifest = Path(__file__).parent / "fixtures" / "parameter-manifest.json"

    class Host:
        def __init__(self, port):
            self.port = port

        def ensure_plugin(self, requested):
            return {
                "host": {},
                "plugin": {"identifier": "org.example.other"},
                "plugin_identifier": "org.example.other",
            }

    monkeypatch.setattr(cli, "TestHostClient", Host)
    with pytest.raises(SystemExit, match="does not match loaded plugin"):
        cli.main(
            [
                "render",
                "--plugin",
                str(tmp_path / "other.vst3"),
                "--param-manifest",
                str(parameter_manifest),
                "--out",
                str(tmp_path / "dataset"),
            ]
        )


def test_interrupted_render_writes_verifiable_failed_manifest(tmp_path, monkeypatch):
    parameter_manifest = Path(__file__).parent / "fixtures" / "parameter-manifest.json"
    output = tmp_path / "dataset"

    class Host:
        def __init__(self, port):
            self.port = port

        def ensure_plugin(self, requested):
            return {
                "host": {
                    "protocol_version": "1",
                    "source_repository": "https://example.invalid/host",
                    "source_commit": "a" * 40,
                    "executable_sha256": "b" * 64,
                    "build_configuration": "Release",
                },
                "plugin": {
                    "path": requested,
                    "sha256": "c" * 64,
                    "format": "VST3",
                    "name": "Example",
                    "vendor": "Example",
                    "identifier": "org.example.fixture",
                },
                "plugin_identifier": "org.example.fixture",
            }

        def set_parameters(self, values):
            self.values = values

        def render_audio(self, num_samples, output_path, midi_events):
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "TestHostClient", Host)
    with pytest.raises(KeyboardInterrupt):
        cli.main(
            [
                "render",
                "--plugin",
                str(tmp_path / "example.vst3"),
                "--param-manifest",
                str(parameter_manifest),
                "--out",
                str(output),
                "--n",
                "1",
            ]
        )

    manifest = provenance.verify_manifest(output / "manifest.json")
    assert manifest["observation"]["status"] == "failed"
    assert manifest["outcomes"] == {"kept": 0, "dropped": 0, "failures": 1}


def test_missing_and_malformed_identities_fail_closed(tmp_path):
    source = tmp_path / "parameters.json"
    source.write_text(
        json.dumps({"params": [{"index": 0, "name": "Gain", "type": "float"}]})
    )
    with pytest.raises(provenance.IntegrityError, match="missing: plugin"):
        provenance.parameter_manifest_identity(source, [0])

    payload = identity_payload(tmp_path, {"sha256": "3" * 64, "patches": 0})
    payload["identities"]["host"]["source_commit"] = " "
    with pytest.raises(provenance.IntegrityError, match="source_commit"):
        provenance.seal_manifest(payload)
