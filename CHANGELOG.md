# Changelog

## Unreleased

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
