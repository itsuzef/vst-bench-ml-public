# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Every planned attempt has exactly one verified outcome (schema v2)."""

import json

import pytest
from .scripted_host import render, reseal, rows_of, verify

from vst_bench_ml import attempts, cli, provenance


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
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema"] = provenance.SCHEMA_V1  # what 0.1.x wrote: no ledger, no counts
    del manifest["attempts"], manifest["artifacts"]["attempt_ledger"]
    (dataset / attempts.LEDGER_NAME).unlink()
    provenance.write_manifest(dataset / "manifest.json", manifest)

    verify(dataset)
    cli.main(["verify", "--manifest", str(dataset / "manifest.json")])
    assert "attempts: not recorded by schema v1" in capsys.readouterr().out
    with pytest.raises(provenance.IntegrityError, match="v1 manifest has no attempt ledger"):
        verify(dataset, host_trace=tmp_path / "absent.jsonl")


# Cases from an independent review: each edit is coherently resealed and must still fail.


def edit_manifest(dataset, change):
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    change(manifest)
    provenance.write_manifest(dataset / "manifest.json", manifest)


def test_record_outside_the_plan_is_rejected(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch)
    extra = dataset / "audio" / "p999999_sus_c3.npz"
    extra.write_bytes(b"smuggled")
    identity = provenance.file_identity(extra, dataset)
    records = dataset / "records.jsonl"
    first = json.loads(records.read_text(encoding="utf-8").splitlines()[0])
    records.write_text(records.read_text(encoding="utf-8") + json.dumps(
        {**first, "patch_id": "p999999", "audio_path": identity["path"], "output": identity}) + "\n")

    def change(manifest):
        manifest["artifacts"]["records"] = provenance.file_identity(records, dataset)
        manifest["artifacts"]["outputs"].append(identity)
        manifest["artifacts"]["outputs_sha256"] = provenance.canonical_sha256(manifest["artifacts"]["outputs"])
        manifest["outcomes"]["kept"] += 1

    edit_manifest(dataset, change)
    with pytest.raises(provenance.IntegrityError, match="record belongs to no planned attempt: p999999_sus_c3"):
        verify(dataset)


def test_silently_shortened_plan_is_rejected(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000002_sus_c3", "p000002_gate_c2"})
    rows = rows_of(dataset)[:4]  # drop the last patch entirely, with its two drop events
    (dataset / "failures.jsonl").write_text("")
    plan = [{"patch_id": row["patch_id"], "tier": row["tier"], "param_vector": row["param_vector"]}
            for row in rows[::2]]

    def change(manifest):
        manifest["identities"]["rng"]["plan_patches"] = 2
        manifest["identities"]["rng"]["plan_sha256"] = provenance.canonical_sha256(plan)
        manifest["outcomes"]["dropped"] = 0
        manifest["artifacts"]["failure_ledger"] = provenance.file_identity(dataset / "failures.jsonl", dataset)

    edit_manifest(dataset, change)
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="does not cover the requested number of patches"):
        verify(dataset)


def test_no_outcome_may_follow_the_failure_that_ended_the_run(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, fail_at=1, silent={"p000000_sus_c3"})
    rows = rows_of(dataset)
    assert [row["disposition"] for row in rows[:3]] == ["dropped", "failed", "not_attempted"]
    # Move the failure before the drop: the drop then follows the end of the run.
    rows[0], rows[1] = ({**rows[1], "index": 0, "attempt_id": rows[0]["attempt_id"], "signal": rows[0]["signal"]},
                        {**rows[0], "index": 1, "attempt_id": rows[1]["attempt_id"], "signal": rows[1]["signal"]})
    events = [json.loads(line) for line in (dataset / "failures.jsonl").read_text(encoding="utf-8").splitlines()]
    events[0]["signal"], events[1]["signal"] = events[1]["signal"], events[0]["signal"]
    (dataset / "failures.jsonl").write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events))
    edit_manifest(dataset, lambda manifest: manifest["artifacts"].update(
        failure_ledger=provenance.file_identity(dataset / "failures.jsonl", dataset)))
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="has an outcome after the failure that ended the run"):
        verify(dataset)


def test_output_must_be_the_attempts_own_file(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "2"))
    records = dataset / "records.jsonl"
    lines = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()]
    lines[1]["output"] = lines[0]["output"]  # second attempt claims the first attempt's audio
    lines[1]["audio_path"] = lines[0]["output"]["path"]
    records.write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))
    rows = rows_of(dataset)
    rows[1]["output"] = lines[0]["output"]
    (dataset / "audio" / "p000001_sus_c3.npz").unlink()

    def change(manifest):
        manifest["artifacts"]["records"] = provenance.file_identity(records, dataset)
        manifest["artifacts"]["outputs"] = [lines[0]["output"], lines[0]["output"]]
        manifest["artifacts"]["outputs_sha256"] = provenance.canonical_sha256(manifest["artifacts"]["outputs"])

    edit_manifest(dataset, change)
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="differs from the record or the attempt for p000001_sus_c3"):
        verify(dataset)


def test_ledger_must_restate_its_event_exactly(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    rows = rows_of(dataset)
    rows[3]["reason"] = "quality:clipped"
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="restates event 0 differently"):
        verify(dataset)


def test_dropped_attempt_needs_the_received_audio_identity(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    rows = rows_of(dataset)
    del rows[3]["raw_output"]
    reseal(dataset, rows)
    with pytest.raises(provenance.IntegrityError, match="dropped p000001_gate_c2 has no identity for the audio"):
        verify(dataset)


def test_v1_manifest_cannot_whitelist_an_unbound_ledger(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch)

    def change(manifest):
        manifest["schema"] = provenance.SCHEMA_V1
        del manifest["attempts"]

    with pytest.raises(provenance.IntegrityError, match="v1 manifest cannot name an attempt ledger"):
        edit_manifest(dataset, change)


@pytest.mark.parametrize("damage", ["row-not-object-fields", "nan", "bad-utf8", "vector-text"])
def test_malformed_ledger_is_an_integrity_error_not_a_crash(tmp_path, monkeypatch, damage):
    dataset, _ = render(tmp_path, monkeypatch)
    rows = rows_of(dataset)
    if damage == "row-not-object-fields":
        rows[0]["raw_output"] = "text"
    elif damage == "nan":
        rows[0]["param_vector"] = {"0": float("nan")}
    elif damage == "vector-text":
        rows[0]["param_vector"] = {"0": "loud"}
    reseal(dataset, rows)
    if damage == "bad-utf8":
        ledger = dataset / "attempts.jsonl"
        ledger.write_bytes(b"\xff\xfe" + ledger.read_bytes())
        edit_manifest(dataset, lambda manifest: manifest["artifacts"].update(
            attempt_ledger=provenance.file_identity(ledger, dataset)))
    with pytest.raises(provenance.IntegrityError):
        verify(dataset)
    with pytest.raises(SystemExit):
        cli.main(["verify", "--manifest", str(dataset / "manifest.json")])


def test_interruption_while_storing_an_output_leaves_a_verifiable_dataset(tmp_path, monkeypatch):
    stored = []
    original = provenance.file_identity

    def interrupt_second(path, root):
        if str(path).endswith(".npz"):
            stored.append(path)
            if len(stored) == 2:
                raise KeyboardInterrupt
        return original(path, root)

    monkeypatch.setattr(cli.provenance, "file_identity", interrupt_second)
    with pytest.raises(KeyboardInterrupt):
        render(tmp_path, monkeypatch)
    dataset = tmp_path / "dataset"
    monkeypatch.setattr(cli.provenance, "file_identity", original)
    manifest = verify(dataset)
    assert manifest["attempts"]["kept"] == 1 and manifest["attempts"]["failed"] == 1
    assert sorted(path.name for path in (dataset / "audio").iterdir()) == ["p000000_sus_c3.npz"]
