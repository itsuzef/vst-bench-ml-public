# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Independent checks of the host and plugin identities used for a render.

A host reports its own identity and the plugin's. This module adds two sources
that do not depend on that report:

* the package hashes the plugin path (and, if named, the host executable)
  itself, before and after the run;
* the user supplies expected identities obtained elsewhere, for example a
  digest computed from the vendor's download on another machine.

The three are compared and the comparison is bound into the manifest. A match
shows that the named files had the expected content while the package looked.
It does not show that the host process executed those files; see docs/DESIGN.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .provenance import IntegrityError, sha256_file

EXPECTED_SCHEMA = "vst-bench-ml.expected-identities/v1"
PATH_DIGEST = "vst-bench.path-tree-sha256/v1"
EXPECTED_FIELDS = {
    "plugin": ("sha256", "identifier", "name", "vendor", "version", "format"),
    "host": (
        "executable_sha256",
        "source_repository",
        "source_commit",
        "build_configuration",
        "protocol_version",
    ),
}


def path_digest(path: str | Path) -> str:
    """SHA-256 of a file, or of a bundle directory's names, kinds and contents.

    Directory entries are visited in sorted relative-path order. For each one the
    digest absorbs the path, a NUL, the kind (``file``, ``directory`` or
    ``symlink`` with its target), the file bytes, and a closing NUL.
    """
    root = Path(path)
    if root.is_file():
        return sha256_file(root)
    if not root.is_dir():
        raise IntegrityError(f"cannot identify path: {root}")
    digest = hashlib.sha256()
    for child in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(child.relative_to(root).as_posix().encode("utf-8") + b"\0")
        if child.is_symlink():
            digest.update(b"symlink\0" + os.readlink(child).encode("utf-8"))
        elif child.is_file():
            digest.update(b"file\0")
            with child.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        elif child.is_dir():
            digest.update(b"directory\0")
        digest.update(b"\0")
    return digest.hexdigest()


def load_expected(path: str | Path) -> dict:
    """Read expected identities; refuse a file that would check nothing."""
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"expected identities are unreadable: {source}") from exc
    if not isinstance(data, dict) or data.get("schema") != EXPECTED_SCHEMA:
        raise IntegrityError(f"expected identities must use schema {EXPECTED_SCHEMA}")
    content: dict[str, dict] = {}
    for subject, fields in EXPECTED_FIELDS.items():
        given = data.get(subject, {})
        if not isinstance(given, dict) or set(given) - set(fields):
            raise IntegrityError(
                f"expected {subject} identity may only name: {', '.join(fields)}"
            )
        if any(not isinstance(value, str) or not value.strip() for value in given.values()):
            raise IntegrityError(f"expected {subject} identity has an empty value")
        if given:
            content[subject] = dict(given)
    if set(data) - {"schema", *EXPECTED_FIELDS}:
        raise IntegrityError("expected identities contain an unknown section")
    if not content:
        raise IntegrityError("expected identities name nothing to check")
    return {"source_name": source.name, "sha256": sha256_file(source), "content": content}


def observe(plugin_path: str | Path, host_executable: str | Path | None) -> dict:
    """What the package itself can see on disk, independent of the host."""
    observed = {"algorithm": PATH_DIGEST, "plugin_sha256": path_digest(plugin_path)}
    if host_executable is not None:
        executable = Path(host_executable)
        if not executable.is_file():
            raise IntegrityError(f"host executable does not exist: {executable}")
        observed["host_executable_sha256"] = sha256_file(executable)
    return observed


def compare(expected: dict | None, host: dict, plugin: dict, observed: dict) -> list[dict]:
    """Compare expected, host-reported and package-observed values.

    Returns the comparisons made; raises IntegrityError on the first mismatch.
    """
    comparisons = []

    def check(subject: str, left_source: str, left, right_source: str, right) -> None:
        if left != right:
            raise IntegrityError(
                f"identity mismatch for {subject}: {left_source} {left} != {right_source} {right}"
            )
        comparisons.append({"subject": subject, "sources": [left_source, right_source], "value": left})

    host_uses_same_digest = plugin.get("sha256_algorithm") == PATH_DIGEST
    if host_uses_same_digest:
        check("plugin.sha256", "package-observed", observed["plugin_sha256"],
              "host-reported", plugin.get("sha256"))
    if "host_executable_sha256" in observed:
        check("host.executable_sha256", "package-observed", observed["host_executable_sha256"],
              "host-reported", host.get("executable_sha256"))
    for subject, reported in (("plugin", plugin), ("host", host)):
        given = (expected or {}).get("content", {}).get(subject, {})
        # Fixed field order: the result must not depend on JSON key order.
        for field, value in ((name, given[name]) for name in EXPECTED_FIELDS[subject] if name in given):
            if (subject, field) == ("plugin", "sha256"):
                check("plugin.sha256", "expected", value, "package-observed", observed["plugin_sha256"])
            else:
                check(f"{subject}.{field}", "expected", value, "host-reported", reported.get(field))
    return comparisons


def record(expected: dict | None, observed: dict, comparisons: list[dict]) -> dict:
    """The manifest section binding the checks to this run."""
    return {
        "expected": expected,
        "package_observed": observed,
        "comparisons": comparisons,
        "result": "matched-expected" if expected else "no-expected-identities",
    }


def verify_recorded(manifest: dict, expected: dict | None = None) -> dict:
    """Recheck a manifest's identity section offline, optionally against new expectations."""
    section = manifest.get("identity_checks")
    if not isinstance(section, dict) or not isinstance(section.get("package_observed"), dict):
        raise IntegrityError("manifest has no identity checks")
    observed = section["package_observed"]
    if observed.get("algorithm") != PATH_DIGEST or "plugin_sha256" not in observed:
        raise IntegrityError("manifest identity checks are malformed")
    if observed.get("plugin_sha256_after", observed["plugin_sha256"]) != observed["plugin_sha256"]:
        if manifest["observation"]["status"] != "failed":
            raise IntegrityError("plugin changed during a run that is not marked failed")
    identities = manifest["identities"]
    recomputed = compare(section.get("expected"), identities["host"], identities["plugin"], observed)
    if recomputed != section.get("comparisons") or section.get("result") != record(
        section.get("expected"), observed, recomputed
    )["result"]:
        raise IntegrityError("recorded identity comparisons do not follow from the manifest")
    if expected is not None:
        compare(expected, identities["host"], identities["plugin"], observed)
    return section
