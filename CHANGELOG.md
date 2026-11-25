# Changelog

## 0.2.0

- Manifest schema `vst-bench-ml.provenance/v2`: every planned render attempt now
  has exactly one outcome in a new bound `attempts.jsonl` ledger (kept, dropped,
  failed or not attempted). Verification derives the expected attempt IDs from the
  manifest, recomputes the sampling-plan digest from the ledger, and matches each
  row against the records, drop/failure events and output identities. Missing,
  duplicate, unplanned and conflicting attempts are rejected, and an interrupted
  run cannot verify as complete.
- `verify --host-trace FILE` compares the ledger with an attempt trace written by
  the host outside the dataset, including the hash of the audio the host wrote.
- Identity checks, bound into v2 manifests: the package hashes the plugin path
  itself before and after the run and compares it with the host's report when the
  host states the same digest algorithm. `render --host-executable PATH` does the
  same for the host file, and `--expect-identities FILE` (on `render` and `verify`)
  compares both with independently obtained values. A mismatch stops the render
  before any audio is requested. `identify PATH` prints the digest of a plugin.
- Manifest signing: `sign --manifest M --key KEY` writes `M.sig`, an OpenSSH
  signature (SSHSIG, `ssh-keygen -Y`) of the manifest file.
  `verify --allowed-signers FILE [--signer NAME]` requires a valid signature by a
  key listed in a trust file kept outside the dataset, and
  `verify --expect-manifest-sha256 HEX` checks the manifest against an externally
  recorded digest. Either rejects a dataset that was changed and coherently
  resealed. No new Python dependency.
- `export --ro-crate DIR --prov FILE` projects a verified dataset into an RO-Crate
  1.1 directory and a W3C PROV-JSON document: files, the run, every attempt and
  its parameters, software and recorded identities. Unknowns stay unknown and
  host-reported values are labelled. See docs/INTEROP.md. The optional `interop`
  extra installs independent readers used to test the exports.
- Verifier hardening after an independent review: records outside the plan, a
  plan shorter than requested, outcomes after the failure that ended a run, an
  output that is not the attempt's own file, and ledger fields that differ from
  their event are rejected; malformed metadata is reported as an integrity
  error; `sign` and `export` refuse datasets that would not verify strictly.
- Schema v1 datasets from 0.1.x still verify; the verifier states that they
  carry no per-attempt outcomes.

- Reject unlisted dataset files, symbolic links, and non-regular entries during
  verification by default; add an explicit `--allow-extra-files` opt-out.
- Record SciPy alongside the other runtime dependencies. Clarify that offline
  verification checks stored artifacts rather than the current Python environment.
- Allow compatible runtime dependencies instead of requiring one exact NumPy,
  SoundFile, and pyloudnorm version; preserve the historical hashed validation lock.
- Add ordinary wheel installation and package tests across Windows, Linux, macOS
  arm64 and Intel, and CPython 3.11–3.15, separately from locked-environment CI.
- Build the native companion once per platform and exercise rendering and offline
  verification in the same compatibility workflow; preserve logs and fixture outputs.
- Check required normalization against installed distribution metadata rather than
  requiring a particular dependency pin in the source configuration.
- Require Python 3.11 or newer: Python 3.10's SciPy 1.15.3 cannot load its native
  PROPACK extension on macOS 27. Require SciPy >=1.17.1 on Darwin 27 and newer,
  including when upgrading an environment with an older SciPy already installed.
- Write portable dataset paths consistently in records and manifests so Windows
  renders pass their own integrity verification.

## 0.1.1

- Publish source as a Git repository with a documented 0.1.0 archive import.
- Add installation, commands/output, troubleshooting, and companion walkthrough links.
- Prepare PyPI distribution and correct public project URLs.
- Align the module version with distribution metadata (the 0.1.0 archive retained
  an older `__version__` value).
- Preserve the rendering, sampling, normalization, and verification algorithms.

## 0.1.0 — 2026-09-23

Initial public source archive: https://doi.org/10.5281/zenodo.22924036.
