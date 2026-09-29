# Development and releases

Use a clean Git checkout and put environments, build outputs, and results outside
it. The normal user install is described in [INSTALL.md](INSTALL.md).

```sh
python -m pip install --require-hashes -r requirements/lock.txt
python -m pip install build twine
python -m build --outdir ../dist
python -m twine check ../dist/*
python -m pip install --no-deps ../dist/vst_bench_ml-0.1.1-py3-none-any.whl
python -B -m pytest -p no:cacheprovider -q
python -m ruff check --no-cache src scripts tests
```

The full release also requires the [companion validation](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/VALIDATION.md),
which checks the exact source commit, installed wheel, locked dependencies, two
render runs, expected output hashes, and negative cases. Record that evidence
against the release commit before publishing. Do not move an existing release tag.

The `publish.yml` GitHub Actions workflow uses PyPI Trusted Publishing. Configure
a pending publisher for project `vst-bench-ml`, owner `itsuzef`, repository
`vst-bench-ml-public`, workflow `publish.yml`, and environment `pypi`.
The workflow checks package metadata/tests and publishes from a `v*` release tag.
The maintainer creates that release only after the companion checks pass.

Published archives/distributions are versioned records. Keep the original 0.1.0
Zenodo archive and its evidence; use a new version for later changes. See
[HISTORY.md](HISTORY.md) for import provenance.
