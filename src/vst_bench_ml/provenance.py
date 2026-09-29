"""Provenance manifests and integrity verification for rendered datasets."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "vst-bench-ml.provenance/v1"
DIRECT_DEPENDENCIES = ("numpy", "soundfile", "pyloudnorm")
DISTRIBUTED_MODULES = (
    "__init__.py",
    "batch.py",
    "cli.py",
    "client.py",
    "export.py",
    "introspect.py",
    "midi_signals.py",
    "provenance.py",
    "quality.py",
    "renderer.py",
    "sampling.py",
    "seeding.py",
)


class IntegrityError(ValueError):
    """Raised when provenance is incomplete or a bound artifact has changed."""


def observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: str | Path, root: str | Path) -> dict:
    root_path = Path(root).resolve()
    file_path = Path(path).resolve()
    try:
        relative = file_path.relative_to(root_path)
    except ValueError as exc:
        raise IntegrityError(f"artifact is outside dataset root: {file_path}") from exc
    if not file_path.is_file():
        raise IntegrityError(f"artifact does not exist: {relative}")
    return {
        "path": relative.as_posix(),
        "bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
    }


def sampling_plan_identity(plan) -> dict:
    canonical_plan = [
        {
            "patch_id": f"p{index:06d}",
            "tier": tier,
            "param_vector": {
                str(key): round(float(value), 12)
                for key, value in sorted(vector.items())
            },
        }
        for index, (tier, vector) in enumerate(plan)
    ]
    return {"patches": len(canonical_plan), "sha256": canonical_sha256(canonical_plan)}


def package_identity() -> dict:
    package_root = Path(__file__).resolve().parent
    files = [
        {"path": name, "sha256": sha256_file(package_root / name)}
        for name in DISTRIBUTED_MODULES
    ]
    try:
        version = importlib.metadata.version("vst-bench-ml")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.1+source"
    return {
        "distribution": "vst-bench-ml",
        "version": version,
        "python_sources_sha256": canonical_sha256(files),
        "python_source_files": files,
    }


def environment_identity() -> dict:
    executable = Path(sys.executable)
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable_sha256": sha256_file(executable),
        "operating_system": platform.system(),
        "operating_system_release": platform.release(),
        "architecture": platform.machine(),
    }


def dependency_identity(names=DIRECT_DEPENDENCIES) -> dict:
    items = []
    for name in sorted(names, key=str.casefold):
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise IntegrityError(
                f"required dependency is not installed: {name}"
            ) from exc
        items.append({"distribution": name, "version": version})
    return {"items": items, "sha256": canonical_sha256(items)}


def parameter_manifest_identity(path: str | Path, varied_indices: list[int]) -> dict:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"malformed parameter manifest: {source}") from exc
    if not isinstance(data, dict):
        raise IntegrityError("parameter manifest must be a JSON object")
    plugin = data.get("plugin")
    if not isinstance(plugin, str) or not plugin.strip():
        raise IntegrityError("parameter manifest identity missing: plugin")
    params = data.get("params")
    if not isinstance(params, list) or not params:
        raise IntegrityError("parameter manifest identity missing: params")
    seen = set()
    for offset, parameter in enumerate(params):
        if not isinstance(parameter, dict):
            raise IntegrityError(f"parameter identity malformed at index {offset}")
        missing = [
            key
            for key in ("index", "name", "type")
            if key not in parameter
            or parameter[key] is None
            or (isinstance(parameter[key], str) and not parameter[key].strip())
        ]
        if missing:
            raise IntegrityError(
                f"parameter identity missing at index {offset}: {', '.join(missing)}"
            )
        try:
            index = int(parameter["index"])
        except (TypeError, ValueError) as exc:
            raise IntegrityError(
                f"parameter identity has invalid index at position {offset}"
            ) from exc
        if index in seen:
            raise IntegrityError(f"duplicate parameter index: {index}")
        seen.add(index)
    unknown = sorted(set(varied_indices) - seen)
    if unknown:
        raise IntegrityError(f"varied parameter indices are absent: {unknown}")
    return {
        "source_name": source.name,
        "source_bytes": source.stat().st_size,
        "source_sha256": sha256_file(source),
        "plugin": plugin.strip(),
        "parameter_count": len(params),
        "parameters_sha256": canonical_sha256(params),
        "varied_indices": sorted(varied_indices),
    }


def normalization_identity(target_lufs: float) -> dict:
    return {
        "algorithm": "ITU-R BS.1770 integrated loudness with RMS fallback",
        "implementation": "vst_bench_ml.quality.normalize_lufs/v1",
        "dependency": {
            "distribution": "pyloudnorm",
            "version": importlib.metadata.version("pyloudnorm"),
        },
        "target_lufs": float(target_lufs),
        "peak_ceiling": 0.891,
    }


def _require_mapping(parent: dict, key: str, context: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise IntegrityError(f"missing or malformed identity: {context}.{key}")
    return value


def _require_values(value: dict, keys: tuple[str, ...], context: str) -> None:
    missing = [
        key
        for key in keys
        if key not in value
        or value[key] is None
        or (isinstance(value[key], str) and not value[key].strip())
    ]
    if missing:
        raise IntegrityError(f"missing identity: {context}.{', '.join(missing)}")


def _require_sha256(value: dict, key: str, context: str) -> None:
    digest = value.get(key)
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise IntegrityError(f"malformed SHA-256 identity: {context}.{key}")


def validate_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise IntegrityError("unsupported or missing provenance schema")
    identities = _require_mapping(manifest, "identities", "manifest")
    package = _require_mapping(identities, "package", "identities")
    host = _require_mapping(identities, "host", "identities")
    plugin = _require_mapping(identities, "plugin", "identities")
    parameters = _require_mapping(identities, "parameters", "identities")
    environment = _require_mapping(identities, "environment", "identities")
    dependencies = _require_mapping(identities, "dependencies", "identities")
    rng = _require_mapping(identities, "rng", "identities")
    normalization = _require_mapping(identities, "normalization", "identities")
    _require_values(
        package,
        ("distribution", "version", "python_sources_sha256"),
        "identities.package",
    )
    _require_values(
        host,
        (
            "protocol_version",
            "source_repository",
            "source_commit",
            "executable_sha256",
            "build_configuration",
        ),
        "identities.host",
    )
    _require_values(
        plugin,
        ("path", "sha256", "format", "name", "vendor", "identifier"),
        "identities.plugin",
    )
    _require_values(
        parameters,
        ("source_sha256", "plugin", "parameters_sha256", "parameter_count"),
        "identities.parameters",
    )
    _require_values(
        environment,
        (
            "python_version",
            "python_implementation",
            "python_executable_sha256",
            "operating_system",
            "operating_system_release",
            "architecture",
        ),
        "identities.environment",
    )
    if not isinstance(dependencies.get("items"), list) or not dependencies["items"]:
        raise IntegrityError("missing identity: identities.dependencies.items")
    _require_values(dependencies, ("sha256",), "identities.dependencies")
    _require_values(
        rng,
        ("algorithm", "seed_derivation", "master_seed", "plan_sha256"),
        "identities.rng",
    )
    _require_values(
        normalization,
        ("algorithm", "implementation", "dependency", "target_lufs"),
        "identities.normalization",
    )
    normalization_dependency = _require_mapping(
        normalization, "dependency", "identities.normalization"
    )
    _require_values(
        normalization_dependency,
        ("distribution", "version"),
        "identities.normalization.dependency",
    )
    for value, key, context in (
        (package, "python_sources_sha256", "identities.package"),
        (host, "executable_sha256", "identities.host"),
        (plugin, "sha256", "identities.plugin"),
        (parameters, "source_sha256", "identities.parameters"),
        (parameters, "parameters_sha256", "identities.parameters"),
        (environment, "python_executable_sha256", "identities.environment"),
        (dependencies, "sha256", "identities.dependencies"),
        (rng, "plan_sha256", "identities.rng"),
    ):
        _require_sha256(value, key, context)
    for dependency in dependencies["items"]:
        if not isinstance(dependency, dict):
            raise IntegrityError("malformed dependency identity")
        _require_values(
            dependency, ("distribution", "version"), "identities.dependencies.item"
        )
    if canonical_sha256(dependencies["items"]) != dependencies["sha256"]:
        raise IntegrityError("dependency identity digest mismatch")
    observation = _require_mapping(manifest, "observation", "manifest")
    _require_values(
        observation, ("started_at", "completed_at", "status"), "observation"
    )
    outcomes = _require_mapping(manifest, "outcomes", "manifest")
    for key in ("kept", "dropped", "failures"):
        if not isinstance(outcomes.get(key), int) or outcomes[key] < 0:
            raise IntegrityError(f"missing or malformed outcome count: {key}")
    artifacts = _require_mapping(manifest, "artifacts", "manifest")
    for key in ("records", "failure_ledger"):
        artifact = _require_mapping(artifacts, key, "artifacts")
        _require_values(artifact, ("path", "bytes", "sha256"), f"artifacts.{key}")
        _require_sha256(artifact, "sha256", f"artifacts.{key}")
    if not isinstance(artifacts.get("outputs"), list):
        raise IntegrityError("missing or malformed artifact identities: outputs")
    _require_values(artifacts, ("outputs_sha256",), "artifacts")
    _require_sha256(artifacts, "outputs_sha256", "artifacts")
    for output in artifacts["outputs"]:
        if not isinstance(output, dict):
            raise IntegrityError("malformed output artifact identity")
        _require_values(output, ("path", "bytes", "sha256"), "artifacts.output")
        _require_sha256(output, "sha256", "artifacts.output")
    if canonical_sha256(artifacts["outputs"]) != artifacts["outputs_sha256"]:
        raise IntegrityError("output identity digest mismatch")
    integrity = _require_mapping(manifest, "integrity", "manifest")
    _require_values(integrity, ("algorithm", "payload_sha256"), "integrity")
    _require_sha256(integrity, "payload_sha256", "integrity")
    if integrity["algorithm"] != "sha256":
        raise IntegrityError("unsupported integrity algorithm")


def seal_manifest(payload: dict) -> dict:
    manifest = dict(payload)
    manifest.pop("integrity", None)
    manifest["integrity"] = {
        "algorithm": "sha256",
        "payload_sha256": canonical_sha256(manifest),
    }
    validate_manifest(manifest)
    return manifest


def write_manifest(path: str | Path, payload: dict) -> dict:
    manifest = seal_manifest(payload)
    Path(path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def _safe_artifact(root: Path, identity: dict) -> Path:
    relative = identity.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise IntegrityError("artifact identity has malformed path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise IntegrityError(f"artifact path escapes dataset root: {relative}") from exc
    return candidate


def _verify_artifact(root: Path, identity: dict) -> Path:
    _require_values(identity, ("path", "bytes", "sha256"), "artifact")
    path = _safe_artifact(root, identity)
    if not path.is_file():
        raise IntegrityError(f"bound artifact is missing: {identity['path']}")
    if path.stat().st_size != identity["bytes"]:
        raise IntegrityError(f"artifact size mismatch: {identity['path']}")
    if sha256_file(path) != identity["sha256"]:
        raise IntegrityError(f"artifact hash mismatch: {identity['path']}")
    return path


def _read_jsonl(path: Path, label: str) -> list[dict]:
    entries = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise IntegrityError(
                    f"{label} entry is not an object at line {line_number}"
                )
            entries.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"{label} is malformed: {path}") from exc
    return entries


def verify_manifest(path: str | Path) -> dict:
    manifest_path = Path(path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(
            f"provenance manifest is unreadable: {manifest_path}"
        ) from exc
    validate_manifest(manifest)
    expected = manifest["integrity"]["payload_sha256"]
    payload = dict(manifest)
    payload.pop("integrity")
    if canonical_sha256(payload) != expected:
        raise IntegrityError("provenance manifest payload hash mismatch")
    root = manifest_path.resolve().parent
    artifacts = manifest["artifacts"]
    records_path = _verify_artifact(root, artifacts["records"])
    ledger_path = _verify_artifact(root, artifacts["failure_ledger"])
    for output in artifacts["outputs"]:
        _verify_artifact(root, output)
    records = _read_jsonl(records_path, "records ledger")
    events = _read_jsonl(ledger_path, "failure ledger")
    outcomes = manifest["outcomes"]
    if len(records) != outcomes["kept"]:
        raise IntegrityError("kept count does not match records ledger")
    record_outputs = [record.get("output") for record in records]
    if record_outputs != artifacts["outputs"]:
        raise IntegrityError("records ledger does not match output identities")
    for record in records:
        output = record.get("output")
        if (
            not isinstance(record.get("observed_at"), str)
            or not record["observed_at"].strip()
            or not isinstance(output, dict)
            or record.get("audio_path") != output.get("path")
        ):
            raise IntegrityError("records ledger contains malformed output provenance")
    for sequence, event in enumerate(events):
        if event.get("sequence") != sequence or not isinstance(
            event.get("observed_at"), str
        ):
            raise IntegrityError("failure ledger contains malformed event provenance")
        if event.get("status") == "drop" and not event.get("reason"):
            raise IntegrityError("failure ledger drop is missing a reason")
        if event.get("status") == "failure" and (
            not event.get("error_type") or not event.get("message")
        ):
            raise IntegrityError("failure ledger failure is missing error identity")
    drops = sum(event.get("status") == "drop" for event in events)
    failures = sum(event.get("status") == "failure" for event in events)
    if any(event.get("status") not in {"drop", "failure"} for event in events):
        raise IntegrityError("failure ledger contains an unknown status")
    if drops != outcomes["dropped"] or failures != outcomes["failures"]:
        raise IntegrityError("failure ledger does not match outcome counts")
    return manifest


def verify_sampling_replay(manifest: dict, specs) -> None:
    """Recreate a sampling plan and compare its bound identity."""
    from . import sampling, seeding

    validate_manifest(manifest)
    rng_identity = manifest["identities"]["rng"]
    rng = seeding.patch_rng(
        int(rng_identity["master_seed"]),
        rng_identity["plugin_identifier"],
        rng_identity["stage"],
        int(rng_identity["stream_index"]),
    )
    replayed = sampling.plan(specs, int(rng_identity["requested_patches"]), rng)
    actual = sampling_plan_identity(replayed)["sha256"]
    if actual != rng_identity["plan_sha256"]:
        raise IntegrityError("deterministic sampling replay mismatch")
