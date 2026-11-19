# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Every planned attempt has exactly one verified outcome (schema v2)."""

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
           arguments=("--n", "3", "--signals", "sus_c3,gate_c2")):
    """Run the CLI against a scripted host; return (dataset, host trace rows)."""
    trace = []

    class Host:
        def __init__(self, port):
            self.patches = 0

        def ensure_plugin(self, requested):
            return {**IDENTITY, "plugin": {**IDENTITY["plugin"], "path": requested}}

        def set_parameters(self, values):
            self.patches += 1
            if self.patches == fail_parameters_at:
                raise RuntimeError("parameter rejected")

        def render_audio(self, num_samples, output_path, midi_events):
            identifier = Path(output_path).stem
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
    dataset = tmp_path / "dataset"
    command = ["render", "--plugin", str(tmp_path / "example.vst3"), "--param-manifest",
               str(FIXTURE), "--out", str(dataset), "--seconds", "0.1", *arguments]
    if fail_at is None and fail_parameters_at is None:
        cli.main(command)
    else:
        with pytest.raises(SystemExit, match="render failed after provenance was preserved"):
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


def test_completed_run_gives_every_planned_attempt_one_outcome(tmp_path, monkeypatch, capsys):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})

    manifest = verify(dataset)
    assert manifest["schema"] == "vst-bench-ml.provenance/v2"
    assert manifest["attempts"] == {"planned": 6, "kept": 5, "dropped": 1, "failed": 0, "not_attempted": 0}
    rows = rows_of(dataset)
    assert [row["attempt_id"] for row in rows] == attempts.expected_ids(3, ["sus_c3", "gate_c2"], "all")
    dropped = rows[3]
    assert (dropped["disposition"], dropped["reason"]) == ("dropped", "quality:silent")
    assert all(len(row["raw_output"]["sha256"]) == 64 for row in rows)
    assert [row["output"] for row in rows if row["disposition"] == "kept"] == manifest["artifacts"]["outputs"]

    cli.main(["verify", "--manifest", str(dataset / "manifest.json")])
    assert "6 planned, each with one outcome: 5 kept, 1 dropped, 0 failed, 0 not attempted" in capsys.readouterr().out


def test_cycle_mode_plans_one_signal_per_patch(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch,
                        arguments=("--n", "3", "--signals", "sus_c3,gate_c2", "--signal-mode", "cycle"))
    verify(dataset)
    assert [row["attempt_id"] for row in rows_of(dataset)] == ["p000000_sus_c3", "p000001_gate_c2", "p000002_sus_c3"]


def test_missing_attempt_is_rejected_after_coherent_resealing(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    rows = [row for row in rows_of(dataset) if row["attempt_id"] != "p000002_gate_c2"]
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="planned attempt has no outcome: p000002_gate_c2"):
        verify(dataset)


def test_duplicate_attempt_is_rejected(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch)
    rows = rows_of(dataset)
    reseal(dataset, rows + [rows[0]])
    with pytest.raises(provenance.IntegrityError, match="duplicate attempt: p000000_sus_c3"):
        verify(dataset)


def test_unplanned_attempt_is_rejected(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch)
    rows = rows_of(dataset)
    reseal(dataset, rows + [{**rows[0], "attempt_id": "p000003_sus_c3", "patch_id": "p000003", "index": 6}])
    with pytest.raises(provenance.IntegrityError, match="not in the plan: p000003_sus_c3"):
        verify(dataset)


@pytest.mark.parametrize("target,disposition,message", [
    ("p000000_sus_c3", "dropped", "conflicting outcome for p000000_sus_c3: dropped with a stored record"),
    ("p000001_gate_c2", "kept", "conflicting outcome for p000001_gate_c2: kept without a stored record"),
])
def test_conflicting_outcomes_are_rejected(tmp_path, monkeypatch, target, disposition, message):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    rows = rows_of(dataset)
    for row in rows:
        if row["attempt_id"] == target:
            row["disposition"] = disposition
            row["event_sequence"] = 0
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match=message):
        verify(dataset)


def test_drop_event_must_belong_to_exactly_one_attempt(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    rows = rows_of(dataset)
    rows[3]["event_sequence"] = 5
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="cites no preserved event"):
        verify(dataset)


def test_changed_parameters_no_longer_match_the_bound_plan(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_sus_c3", "p000001_gate_c2"})
    rows = rows_of(dataset)
    for row in rows:
        if row["patch_id"] == "p000001":  # both attempts dropped: no record repeats the vector
            row["param_vector"] = {"0": 0.123}
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="do not match the bound sampling plan"):
        verify(dataset)


def test_interrupted_run_accounts_for_failed_and_unattempted(tmp_path, monkeypatch, capsys):
    dataset, _ = render(tmp_path, monkeypatch, fail_at=2)

    manifest = verify(dataset)
    assert manifest["observation"]["status"] == "failed"
    assert manifest["attempts"] == {"planned": 6, "kept": 2, "dropped": 0, "failed": 1, "not_attempted": 3}
    rows = rows_of(dataset)
    assert [row["disposition"] for row in rows] == ["kept", "kept", "failed"] + ["not_attempted"] * 3
    assert (rows[2]["stage"], rows[2]["error_type"]) == ("render_or_process", "RuntimeError")
    cli.main(["verify", "--manifest", str(dataset / "manifest.json")])
    assert "2 kept, 0 dropped, 1 failed, 3 not attempted" in capsys.readouterr().out

    # An interrupted run cannot be relabelled as complete, even when resealed.
    manifest["observation"]["status"] = "completed"
    reseal(dataset, rows, observation=manifest["observation"])
    with pytest.raises(provenance.IntegrityError, match="contradicts 4 unfinished attempts"):
        verify(dataset)


def test_kept_attempt_cannot_be_relabelled_unattempted(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, fail_at=2)
    rows = rows_of(dataset)
    rows[0]["disposition"] = "not_attempted"
    del rows[0]["raw_output"], rows[0]["output"]
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="conflicting outcome for p000000_sus_c3"):
        verify(dataset)


def test_parameter_failure_covers_every_attempt_of_the_patch(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, fail_parameters_at=2)
    verify(dataset)
    rows = rows_of(dataset)
    assert [row["disposition"] for row in rows] == ["kept", "kept", "failed", "failed", "not_attempted", "not_attempted"]
    assert {row["stage"] for row in rows[2:4]} == {"set_parameters"}

    rows[3]["disposition"] = "not_attempted"
    del rows[3]["event_sequence"], rows[3]["stage"], rows[3]["error_type"]
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="does not cover every attempt of the patch"):
        verify(dataset)


def test_host_trace_agrees_with_the_ledger(tmp_path, monkeypatch, capsys):
    dataset, trace = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    path = tmp_path / "host-trace.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in trace))
    verify(dataset, host_trace=path)
    cli.main(["verify", "--manifest", str(dataset / "manifest.json"), "--host-trace", str(path)])
    assert "host trace agrees" in capsys.readouterr().out


@pytest.mark.parametrize("change,message", [
    ("drop-entry", "host trace has no render for kept p000000_sus_c3"),
    ("change-hash", "host trace output differs from the received audio for p000000_sus_c3"),
    ("repeat-entry", "host trace repeats p000000_sus_c3"),
    ("extra-entry", "host trace has an unplanned attempt: p000009_sus_c3"),
])
def test_host_trace_disagreement_is_rejected(tmp_path, monkeypatch, change, message):
    dataset, trace = render(tmp_path, monkeypatch)
    if change == "drop-entry":
        trace = trace[1:]
    elif change == "change-hash":
        trace[0] = {**trace[0], "output": {**trace[0]["output"], "sha256": "0" * 64}}
    elif change == "repeat-entry":
        trace = trace + [trace[0]]
    else:
        trace = trace + [{**trace[0], "attempt_id": "p000009_sus_c3"}]
    path = tmp_path / "host-trace.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in trace))
    with pytest.raises(provenance.IntegrityError, match=message):
        verify(dataset, host_trace=path)


def test_host_trace_of_an_interrupted_run(tmp_path, monkeypatch):
    dataset, trace = render(tmp_path, monkeypatch, fail_at=2)
    path = tmp_path / "host-trace.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in trace))
    verify(dataset, host_trace=path)
    path.write_text("".join(json.dumps(entry) + "\n" for entry in trace + [
        {"attempt_id": "p000002_gate_c2", "outcome": "rendered", "output": {"bytes": 1, "sha256": "0" * 64}}]))
    with pytest.raises(provenance.IntegrityError, match="host trace shows unattempted p000002_gate_c2"):
        verify(dataset, host_trace=path)


def test_historical_v1_dataset_still_verifies_and_states_the_gap(tmp_path, monkeypatch, capsys):
    dataset, _ = render(tmp_path, monkeypatch)
    manifest = json.loads((dataset / "manifest.json").read_text())
    manifest["schema"] = provenance.SCHEMA_V1  # what 0.1.x wrote: no ledger, no counts
    del manifest["attempts"], manifest["artifacts"]["attempt_ledger"]
    (dataset / attempts.LEDGER_NAME).unlink()
    provenance.write_manifest(dataset / "manifest.json", manifest)

    verify(dataset)
    cli.main(["verify", "--manifest", str(dataset / "manifest.json")])
    assert "attempts: not recorded by schema v1" in capsys.readouterr().out
    with pytest.raises(provenance.IntegrityError, match="v1 manifest has no attempt ledger"):
        verify(dataset, host_trace=tmp_path / "absent.jsonl")
