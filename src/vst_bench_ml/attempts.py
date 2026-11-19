# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Attempt ledger: one terminal outcome for every planned render.

A sampling plan and a signal list define the planned attempts before any audio
exists. The ledger gives each of them exactly one disposition:

    kept           an output was stored; the row carries its identity
    dropped        rendered, then rejected by a quality rule
    failed         an error ended the attempt (and the run)
    not_attempted  the run stopped before this attempt began

The verifier derives the expected attempt IDs from the manifest, recomputes the
plan digest from the ledger rows, and matches every row against the records,
the drop/failure events and the stored output identities.
"""

from __future__ import annotations

from typing import Any, Iterable

from .provenance import IntegrityError, canonical_sha256

LEDGER_NAME = "attempts.jsonl"
DISPOSITIONS = ("kept", "dropped", "failed", "not_attempted")


def patch_id(index: int) -> str:
    return f"p{index:06d}"


def attempt_id(patch: str, signal: str) -> str:
    return f"{patch}_{signal}"


def signals_for_patch(index: int, signals, signal_mode: str) -> tuple[str, ...]:
    """Signals rendered for one patch: all of them, or one in rotation."""
    if signal_mode == "all":
        return tuple(signals)
    return (signals[index % len(signals)],)


def expected_ids(patches: int, signals, signal_mode: str) -> list[str]:
    """Attempt IDs in render order, from counts alone."""
    return [
        attempt_id(patch_id(index), signal)
        for index in range(patches)
        for signal in signals_for_patch(index, signals, signal_mode)
    ]


def _plan_vector(vector: dict) -> dict[str, float]:
    # Same projection as provenance.sampling_plan_identity.
    return {str(key): round(float(value), 12) for key, value in sorted(vector.items())}


def build_ledger(
    plan,
    signals,
    signal_mode: str,
    records: list[dict],
    events: list[dict],
    raw_outputs: dict[str, dict],
) -> list[dict]:
    """Give every planned attempt its disposition from what the run preserved."""
    kept = {attempt_id(r["patch_id"], r["signal"]): r for r in records}
    drops, failures, patch_failures = {}, {}, {}
    for event in events:
        if event["status"] == "drop":
            drops[attempt_id(event["patch_id"], event["signal"])] = event
        elif event.get("signal") is None:
            patch_failures[event["patch_id"]] = event
        else:
            failures[attempt_id(event["patch_id"], event["signal"])] = event

    rows = []
    for index, (tier, vector) in enumerate(plan):
        patch = patch_id(index)
        for signal in signals_for_patch(index, signals, signal_mode):
            identifier = attempt_id(patch, signal)
            row: dict[str, Any] = {
                "index": len(rows),
                "attempt_id": identifier,
                "patch_id": patch,
                "signal": signal,
                "tier": tier,
                "param_vector": _plan_vector(vector),
            }
            if identifier in raw_outputs:
                row["raw_output"] = raw_outputs[identifier]
            failure = failures.get(identifier) or patch_failures.get(patch)
            if identifier in kept:
                row["disposition"] = "kept"
                row["output"] = kept[identifier]["output"]
            elif identifier in drops:
                row["disposition"] = "dropped"
                row["event_sequence"] = drops[identifier]["sequence"]
                row["reason"] = drops[identifier]["reason"]
            elif failure is not None:
                row["disposition"] = "failed"
                row["event_sequence"] = failure["sequence"]
                row["stage"] = failure["stage"]
                row["error_type"] = failure["error_type"]
            else:
                row["disposition"] = "not_attempted"
            rows.append(row)
    return rows


def counts(rows: Iterable[dict]) -> dict[str, int]:
    rows = list(rows)
    result = {"planned": len(rows)}
    for name in DISPOSITIONS:
        result[name] = sum(row.get("disposition") == name for row in rows)
    return result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrityError(f"attempt ledger: {message}")


def verify_ledger(
    manifest: dict, rows: list[dict], records: list[dict], events: list[dict]
) -> None:
    """Check that every planned attempt has exactly one consistent outcome."""
    request = manifest.get("request")
    rng = manifest["identities"]["rng"]
    _require(
        isinstance(request, dict)
        and isinstance(request.get("signals"), list)
        and bool(request["signals"])
        and request.get("signal_mode") in {"all", "cycle"}
        and isinstance(rng.get("plan_patches"), int),
        "manifest does not state the plan size, signals and signal mode",
    )
    _require(
        rng["plan_patches"] == rng.get("requested_patches") == request.get("requested_patches"),
        "the plan does not cover the requested number of patches",
    )
    expected = expected_ids(rng["plan_patches"], request["signals"], request["signal_mode"])

    seen: set[str] = set()
    for row in rows:
        identifier = row.get("attempt_id")
        _require(isinstance(identifier, str), "row without an attempt ID")
        _require(identifier not in seen, f"duplicate attempt: {identifier}")
        seen.add(identifier)
    for identifier in expected:
        _require(identifier in seen, f"planned attempt has no outcome: {identifier}")
    for identifier in sorted(seen - set(expected)):
        _require(False, f"attempt is not in the plan: {identifier}")
    _require(
        [row["attempt_id"] for row in rows] == expected,
        "attempts are not in plan order",
    )

    plan_rows: list[dict] = []
    for position, row in enumerate(rows):
        _require(row.get("index") == position, f"malformed index at row {position}")
        _require(
            row.get("disposition") in DISPOSITIONS,
            f"unknown disposition for {row['attempt_id']}",
        )
        _require(
            attempt_id(str(row.get("patch_id")), str(row.get("signal"))) == row["attempt_id"]
            and isinstance(row.get("param_vector"), dict),
            f"malformed row for {row['attempt_id']}",
        )
        entry = {
            "patch_id": row["patch_id"],
            "tier": row.get("tier"),
            "param_vector": row["param_vector"],
        }
        if not plan_rows or plan_rows[-1]["patch_id"] != row["patch_id"]:
            plan_rows.append(entry)
        else:
            _require(
                plan_rows[-1] == entry,
                f"conflicting parameters within patch {row['patch_id']}",
            )
    _require(
        canonical_sha256(plan_rows) == rng.get("plan_sha256"),
        "parameter vectors do not match the bound sampling plan",
    )

    record_by_id = {}
    for record in records:
        identifier = attempt_id(str(record.get("patch_id")), str(record.get("signal")))
        _require(identifier not in record_by_id, f"duplicate record: {identifier}")
        record_by_id[identifier] = record
    claimed_events: dict[int, list[dict]] = {}
    stopped = False
    failure = None  # event sequence of the failure that ended the run
    for row in rows:
        identifier, disposition = row["attempt_id"], row["disposition"]
        _require(
            failure is None
            or disposition == "not_attempted"
            or (disposition == "failed" and row.get("event_sequence") == failure),
            f"{identifier} has an outcome after the failure that ended the run",
        )
        _require(
            (identifier in record_by_id) == (disposition == "kept"),
            f"conflicting outcome for {identifier}: {disposition} "
            f"{'with' if identifier in record_by_id else 'without'} a stored record",
        )
        if disposition == "not_attempted":
            stopped = True
            _require("raw_output" not in row, f"unattempted {identifier} has an output")
            continue
        _require(not stopped, f"{identifier} has an outcome after the run stopped")
        if disposition in {"kept", "dropped"}:  # both were rendered and received
            raw = row.get("raw_output")
            _require(
                isinstance(raw, dict) and isinstance(raw.get("sha256"), str) and isinstance(raw.get("bytes"), int),
                f"{disposition} {identifier} has no identity for the audio received from the host",
            )
        if disposition == "kept":
            record = record_by_id[identifier]
            _require(
                row.get("output") == record.get("output")
                and isinstance(row.get("output"), dict)
                and row["output"].get("path") == f"audio/{identifier}.npz",
                f"output identity differs from the record or the attempt for {identifier}",
            )
            vector = record.get("param_vector")
            _require(
                isinstance(vector, dict)
                and set(map(str, vector)) == set(row["param_vector"])
                and all(
                    abs(float(value) - row["param_vector"][str(key)]) <= 1e-6
                    for key, value in vector.items()
                ),
                f"record parameters differ from the plan for {identifier}",
            )
        else:
            sequence = row.get("event_sequence")
            _require(
                isinstance(sequence, int) and 0 <= sequence < len(events),
                f"{disposition} {identifier} cites no preserved event",
            )
            event = events[sequence]
            status = "drop" if disposition == "dropped" else "failure"
            _require(
                event.get("status") == status
                and event.get("patch_id") == row["patch_id"]
                and event.get("signal") in ({row["signal"]} if status == "drop" else {row["signal"], None}),
                f"{disposition} {identifier} does not match event {sequence}",
            )
            copied = ("reason",) if status == "drop" else ("stage", "error_type")
            _require(
                all(row.get(key) == event.get(key) for key in copied),
                f"{disposition} {identifier} restates event {sequence} differently",
            )
            if status == "failure":
                failure = sequence
            claimed_events.setdefault(sequence, []).append(row)
    for sequence, event in enumerate(events):
        claimed = claimed_events.get(sequence, [])
        _require(bool(claimed), f"event {sequence} belongs to no attempt")
        if event.get("status") == "drop" or event.get("signal") is not None:
            _require(len(claimed) == 1, f"event {sequence} is cited by several attempts")
        else:
            patch_rows = [row for row in rows if row["patch_id"] == event["patch_id"]]
            _require(
                len(claimed) == len(patch_rows),
                f"patch failure {sequence} does not cover every attempt of the patch",
            )

    kept_ids = {row["attempt_id"] for row in rows if row["disposition"] == "kept"}
    for identifier in sorted(set(record_by_id) - kept_ids):
        _require(False, f"record belongs to no planned attempt: {identifier}")
    declared = manifest.get("attempts")
    _require(declared == counts(rows), "manifest attempt counts do not match the ledger")
    outcomes = manifest["outcomes"]
    _require(
        (outcomes["kept"], outcomes["dropped"]) == (declared["kept"], declared["dropped"]),
        "outcome counts do not match the attempt ledger",
    )
    status = manifest["observation"]["status"]
    unfinished = declared["failed"] + declared["not_attempted"]
    _require(
        status == "failed" or (status == "completed" and unfinished == 0),
        f"run status '{status}' contradicts {unfinished} unfinished attempts",
    )


def verify_host_trace(rows: list[dict], trace: list[dict]) -> None:
    """Compare the ledger with a trace written by the host, outside the dataset.

    Each trace entry needs ``attempt_id`` and ``outcome`` (``rendered`` or
    ``failed``); a rendered entry also needs ``output.sha256`` and
    ``output.bytes`` for the audio file the host wrote.
    """
    by_id: dict[str, dict] = {}
    for entry in trace:
        identifier = entry.get("attempt_id")
        _require(isinstance(identifier, str), "host trace entry without an attempt ID")
        _require(identifier not in by_id, f"host trace repeats {identifier}")
        _require(
            entry.get("outcome") in {"rendered", "failed"},
            f"host trace has an unknown outcome for {identifier}",
        )
        by_id[identifier] = entry
    for identifier in sorted(set(by_id) - {row["attempt_id"] for row in rows}):
        _require(False, f"host trace has an unplanned attempt: {identifier}")
    for row in rows:
        identifier, disposition = row["attempt_id"], row["disposition"]
        entry = by_id.get(identifier)
        if disposition == "not_attempted":
            _require(entry is None, f"host trace shows unattempted {identifier}")
            continue
        if disposition == "failed" and (entry is None or entry["outcome"] == "failed"):
            continue
        _require(
            entry is not None and entry["outcome"] == "rendered",
            f"host trace has no render for {disposition} {identifier}",
        )
        if "raw_output" in row:
            output = entry.get("output")
            _require(isinstance(output, dict), f"host trace render has no output for {identifier}")
            _require(
                output.get("sha256") == row["raw_output"]["sha256"]
                and output.get("bytes") == row["raw_output"]["bytes"],
                f"host trace output differs from the received audio for {identifier}",
            )
