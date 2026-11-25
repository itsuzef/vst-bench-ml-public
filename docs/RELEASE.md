# Development and releases

Use a clean Git checkout and put environments, build outputs, and results outside
it. The normal user install is described in [INSTALL.md](INSTALL.md).

```sh
python -m pip install --require-hashes -r requirements/lock.txt
python -m pip install build twine
python -m build --no-isolation --outdir ../dist
python -m twine check ../dist/*
python -m pip install --no-deps ../dist/vst_bench_ml-*.whl
python -B -m pytest -p no:cacheprovider -q
python -m ruff check --no-cache src scripts tests
```

The full release also requires the [companion validation](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/VALIDATION.md),
which checks the exact source commit, installed wheel, locked dependencies, two
render runs, expected output hashes, and negative cases. Record that evidence
against the release commit before publishing. Do not move an existing release tag.

The ordinary-install compatibility matrix resolves compatible dependencies without
the historical lock. Require its results as well as locked validation before
publishing the compatibility revision. Preserve the original lockfile and release
tags; choose a new release version rather than replacing the published 0.1.1 files.

Version 0.2.0 writes schema v2 manifests. The companion's exact-hash fixture
conformance reads schema v1 and stays pinned to the 0.1.1 package identity, so
0.2.0 was released on the compatibility matrix, the locked-environment tests and
native fixture, Vital and u-he runs checked by the core verifier.

The `publish.yml` GitHub Actions workflow uses PyPI Trusted Publishing. Configure
a pending publisher for project `vst-bench-ml`, owner `itsuzef`, repository
`vst-bench-ml-public`, workflow `publish.yml`, and environment `pypi`.
The workflow checks package metadata/tests and publishes from a `v*` release tag.
The maintainer creates that release only after the companion checks pass.

Published archives/distributions are versioned records. Keep the original 0.1.0
Zenodo archive and its evidence; use a new version for later changes. See
[HISTORY.md](HISTORY.md) for import provenance.
