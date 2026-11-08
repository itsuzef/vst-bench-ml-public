"""Command-line interface for the generic rendering core."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

from . import batch, export, introspect, provenance, quality, sampling, seeding
from .client import TestHostClient, TestHostError
from .midi_signals import signal_names


def _processor(
    audio_dir: Path, target_lufs: float, keep_bad: bool, sink, dataset_root: Path
):
    audio_dir.mkdir(parents=True, exist_ok=True)

    def process(record: dict, wav_path: str):
        samples, sample_rate = quality.load_wav(wav_path)
        report = quality.assess(samples, sample_rate)
        if not keep_bad and (report["silent"] or report["clipped"]):
            record["_drop_reason"] = (
                "quality:silent" if report["silent"] else "quality:clipped"
            )
            os.remove(wav_path)
            return None
        normalized, input_lufs = quality.normalize_lufs(
            samples, sample_rate, target_lufs
        )
        npz_path = audio_dir / (Path(wav_path).stem + ".npz")
        export.save_npz(normalized, sample_rate, str(npz_path))
        os.remove(wav_path)
        output_identity = provenance.file_identity(npz_path, dataset_root)
        record.update(
            {
                "audio_path": output_identity["path"],
                "sample_rate": int(sample_rate),
                "in_lufs": (
                    round(float(input_lufs), 2) if math.isfinite(input_lufs) else None
                ),
                "quality": report,
                "observed_at": provenance.observed_at(),
                "output": output_identity,
            }
        )
        sink.write(json.dumps(record, sort_keys=True) + "\n")
        sink.flush()
        return record

    return process


def cmd_render(args: argparse.Namespace) -> None:
    started_at = provenance.observed_at()
    manifest_path = Path(args.param_manifest)
    if not manifest_path.is_file():
        raise SystemExit(f"parameter manifest does not exist: {manifest_path}")
    if args.n < 1 or args.seconds <= 0 or args.sr < 1:
        raise SystemExit("--n, --seconds, and --sr must be positive")
    signals = tuple(filter(None, args.signals.split(",")))
    unknown = sorted(set(signals) - set(signal_names()))
    if not signals or unknown:
        raise SystemExit(f"invalid --signals value; unknown signals: {unknown}")
    if len(signals) != len(set(signals)):
        raise SystemExit("invalid --signals value; duplicate signals are not allowed")

    try:
        specs_all = introspect.load_manifest(manifest_path)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"malformed parameter manifest: {manifest_path}") from exc
    specs = introspect.audio_relevant(specs_all)
    if args.exclude_groups:
        specs = introspect.exclude_groups(specs, set(args.exclude_groups.split(",")))
    if not specs:
        raise SystemExit("parameter manifest has no parameters eligible for rendering")
    varied_indices = [spec.index for spec in specs]
    try:
        parameter_identity = provenance.parameter_manifest_identity(
            manifest_path, varied_indices
        )
    except provenance.IntegrityError as exc:
        raise SystemExit(str(exc)) from exc

    client = TestHostClient(port=args.port)
    try:
        identity = client.ensure_plugin(args.plugin)
    except (OSError, TestHostError) as exc:
        raise SystemExit(str(exc)) from exc
    if parameter_identity["plugin"] != identity["plugin_identifier"]:
        raise SystemExit(
            "parameter manifest plugin does not match loaded plugin: "
            f"{parameter_identity['plugin']} != {identity['plugin_identifier']}"
        )

    seed = seeding.master_from_label(args.seed_label)
    rng = seeding.patch_rng(seed, identity["plugin_identifier"], "plan", 0)
    plan = sampling.plan(specs, args.n, rng)
    plan_identity = provenance.sampling_plan_identity(plan)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    records_path = out / "records.jsonl"
    ledger_path = out / "failures.jsonl"
    records = []
    events = []
    caught = None

    with (
        records_path.open("w", encoding="utf-8") as record_sink,
        ledger_path.open("w", encoding="utf-8") as ledger_sink,
    ):

        def preserve_event(event):
            entry = {
                "sequence": len(events),
                "observed_at": provenance.observed_at(),
                **event,
            }
            events.append(entry)
            ledger_sink.write(json.dumps(entry, sort_keys=True) + "\n")
            ledger_sink.flush()

        process = _processor(
            out / "audio", args.target_lufs, args.keep_bad, record_sink, out
        )
        try:
            with tempfile.TemporaryDirectory(prefix="vst_bench_ml_") as wav_dir:
                batch.generate(
                    client,
                    specs,
                    plan,
                    out,
                    signals=signals,
                    signal_mode=args.signal_mode,
                    num_samples=int(args.seconds * args.sr),
                    wav_dir=wav_dir,
                    process=process,
                    event_sink=preserve_event,
                    records=records,
                )
        except (Exception, KeyboardInterrupt) as exc:
            caught = exc

    dropped = sum(event["status"] == "drop" for event in events)
    failures = sum(event["status"] == "failure" for event in events)
    outputs = [record["output"] for record in records]
    payload = {
        "schema": provenance.SCHEMA,
        "observation": {
            "started_at": started_at,
            "completed_at": provenance.observed_at(),
            "status": "failed" if caught else "completed",
        },
        "identities": {
            "package": provenance.package_identity(),
            "host": identity["host"],
            "plugin": identity["plugin"],
            "parameters": parameter_identity,
            "environment": provenance.environment_identity(),
            "dependencies": provenance.dependency_identity(),
            "rng": {
                "algorithm": "numpy.random.Generator(PCG64)",
                "seed_derivation": "vst_bench_ml.seeding.patch_rng/v1",
                "master_seed": seed,
                "seed_label": args.seed_label,
                "plugin_identifier": identity["plugin_identifier"],
                "stage": "plan",
                "stream_index": 0,
                "requested_patches": args.n,
                "plan_patches": plan_identity["patches"],
                "plan_sha256": plan_identity["sha256"],
            },
            "normalization": provenance.normalization_identity(args.target_lufs),
        },
        "request": {
            "requested_patches": args.n,
            "signals": list(signals),
            "signal_mode": args.signal_mode,
            "seconds": args.seconds,
            "sample_rate": args.sr,
            "keep_bad": args.keep_bad,
            "excluded_groups": sorted(filter(None, args.exclude_groups.split(","))),
        },
        "outcomes": {
            "kept": len(records),
            "dropped": dropped,
            "failures": failures,
        },
        "artifacts": {
            "records": provenance.file_identity(records_path, out),
            "failure_ledger": provenance.file_identity(ledger_path, out),
            "outputs": outputs,
            "outputs_sha256": provenance.canonical_sha256(outputs),
        },
        "record_schema": export.RECORD_SCHEMA,
    }
    provenance.write_manifest(out / "manifest.json", payload)
    provenance.verify_manifest(out / "manifest.json")
    if isinstance(caught, KeyboardInterrupt):
        raise caught
    if caught is not None:
        raise SystemExit(
            f"render failed after provenance was preserved: {caught}"
        ) from caught


def cmd_verify(args: argparse.Namespace) -> None:
    try:
        manifest = provenance.verify_manifest(args.manifest)
    except provenance.IntegrityError as exc:
        raise SystemExit(str(exc)) from exc
    outcomes = manifest["outcomes"]
    print(
        f"verified: {outcomes['kept']} kept, {outcomes['dropped']} dropped, "
        f"{outcomes['failures']} failures (artifact integrity only)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vst-bench-ml")
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render", help="render a deterministic sampling plan")
    render.add_argument("--plugin", required=True)
    render.add_argument("--param-manifest", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--n", type=int, default=100)
    render.add_argument("--port", type=int, default=8765)
    render.add_argument("--signals", default="sus_c3")
    render.add_argument("--signal-mode", choices=("all", "cycle"), default="all")
    render.add_argument("--seconds", type=float, default=2.0)
    render.add_argument("--sr", type=int, default=44100)
    render.add_argument("--target-lufs", type=float, default=-14.0)
    render.add_argument("--seed-label", default="run")
    render.add_argument("--exclude-groups", default="")
    render.add_argument("--keep-bad", action="store_true")
    render.set_defaults(func=cmd_render)

    verify = sub.add_parser(
        "verify", help="verify stored manifest and artifact integrity",
        description="Check stored artifacts without comparing this machine's installed dependency versions.",
    )
    verify.add_argument("--manifest", required=True)
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
