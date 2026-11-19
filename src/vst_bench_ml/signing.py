# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Sign a sealed manifest and verify the signature against outside trust.

Signatures use the OpenSSH signature format (SSHSIG), made and checked by
``ssh-keygen -Y``. The manifest file is signed as it is; it already binds
every other dataset file by hash. The signature is stored beside it as
``<manifest>.sig``.

Trust comes from an *allowed signers* file that the verifier obtained apart
from the dataset. A signature says that the holder of a listed key signed
these manifest bytes. It says nothing about how the audio was produced.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .provenance import IntegrityError, sha256_file

NAMESPACE = "vst-bench-ml-manifest"  # a signature made for another purpose is not accepted


def signature_path(manifest: str | Path) -> Path:
    manifest = Path(manifest)
    return manifest.with_name(manifest.name + ".sig")


def _ssh_keygen(arguments: list[str], *, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    tool = shutil.which("ssh-keygen")
    if tool is None:
        raise IntegrityError("ssh-keygen (OpenSSH 8.1 or newer) is required for signatures")
    try:
        return subprocess.run([tool, *arguments], input=stdin, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntegrityError(f"ssh-keygen could not run: {exc}") from exc


def _detail(result: subprocess.CompletedProcess) -> str:
    text = (result.stderr or result.stdout).decode("utf-8", "replace").strip()
    return text.splitlines()[-1] if text else f"exit status {result.returncode}"


def sign(manifest: str | Path, key: str | Path) -> Path:
    """Sign ``manifest`` with an SSH private key; return the signature path."""
    manifest, key = Path(manifest), Path(key)
    if not manifest.is_file():
        raise IntegrityError(f"manifest does not exist: {manifest}")
    if not key.is_file():
        raise IntegrityError(f"signing key does not exist: {key}")
    target = signature_path(manifest)
    target.unlink(missing_ok=True)  # ssh-keygen refuses to overwrite
    result = _ssh_keygen(["-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(manifest)])
    if result.returncode != 0 or not target.is_file():
        raise IntegrityError(f"signing failed: {_detail(result)}")
    return target


def verify(manifest: str | Path, allowed_signers: str | Path, signer: str | None = None) -> str:
    """Check the manifest signature; return the signer identity that matched.

    ``allowed_signers`` lists trusted identities and public keys in OpenSSH's
    format and must come from outside the dataset. With ``signer`` omitted, any
    identity in that file whose key made the signature is accepted.
    """
    manifest, allowed = Path(manifest), Path(allowed_signers)
    signature = signature_path(manifest)
    if not allowed.is_file():
        raise IntegrityError(f"allowed signers file does not exist: {allowed}")
    if not signature.is_file():
        raise IntegrityError(f"manifest is not signed: {signature.name} is missing")
    if signer is None:
        found = _ssh_keygen(["-Y", "find-principals", "-s", str(signature), "-f", str(allowed)])
        names = found.stdout.decode("utf-8", "replace").split()
        if found.returncode != 0 or not names:
            raise IntegrityError("signature was not made by any key in the allowed signers file")
        signer = names[0]
    result = _ssh_keygen(
        ["-Y", "verify", "-f", str(allowed), "-I", signer, "-n", NAMESPACE, "-s", str(signature)],
        stdin=manifest.read_bytes(),
    )
    if result.returncode != 0:
        raise IntegrityError(f"manifest signature is not valid for {signer}: {_detail(result)}")
    return signer


def verify_digest(manifest: str | Path, expected_sha256: str) -> None:
    """Check the manifest file against a digest recorded outside the dataset."""
    actual = sha256_file(manifest)
    if actual != expected_sha256.strip().lower():
        raise IntegrityError(f"manifest SHA-256 {actual} is not the expected {expected_sha256}")
