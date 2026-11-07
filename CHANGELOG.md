# Changelog

## Unreleased

- Allow compatible runtime dependencies instead of requiring one exact NumPy,
  SoundFile, and pyloudnorm version; preserve the historical hashed validation lock.
- Add ordinary wheel installation and package tests across Windows, Linux, macOS
  arm64 and Intel, and CPython 3.10–3.15, separately from locked-environment CI.
- Build the native companion once per platform and exercise rendering and offline
  verification in the same compatibility workflow; preserve logs and fixture outputs.
- Remove the test suite's Python 3.11-only TOML import so tests can run on Python 3.10.

## 0.1.1

- Publish source as a Git repository with a documented 0.1.0 archive import.
- Add installation, commands/output, troubleshooting, and companion walkthrough links.
- Prepare PyPI distribution and correct public project URLs.
- Align the module version with distribution metadata (the 0.1.0 archive retained
  an older `__version__` value).
- Preserve the rendering, sampling, normalization, and verification algorithms.

## 0.1.0 — 2026-09-23

Initial public source archive: https://doi.org/10.5281/zenodo.22924036.
