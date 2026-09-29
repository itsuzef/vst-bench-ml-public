# vst-bench-ml

Pure-Python orchestration for sampling plugin parameters, driving a separately
installed localhost JSON-RPC test host, applying basic audio-quality checks, and
writing NumPy audio plus JSON metadata.

The Python package does **not** contain a plugin host, plugin binaries, product
schemas, presets, models, datasets, or audio. It supports the pinned Python
3.12 verification stack documented here; broader portability is not claimed.

## Install for verification

```sh
python -m pip install --require-hashes -r requirements/lock.txt
python -m pip install --no-deps .
python -m pytest -q
python -m vst_bench_ml.cli --help
python -m vst_bench_ml.cli render --help
```

`pyloudnorm` is a required dependency. Installation without dependencies is
supported only when the locked dependencies are installed first; normalization
never silently changes method because the dependency is absent.

## Host boundary

The `render` command connects to `127.0.0.1` and requires a fresh host that
implements the versioned JSON-RPC interface described in [docs/DESIGN.md](docs/DESIGN.md).
The host must report immutable source/build identity, executable hash, exact
plugin identity, deterministic-reset support, and parameter-readback support.
Missing, null, already-loaded, or mismatched identity fails closed.

```sh
vst-bench-ml render \
  --plugin /absolute/path/to/example.vst3 \
  --param-manifest parameter-manifest.json \
  --n 100 --out output --seed-label example-v1
```

The seed reproduces the sampling plan on the validated dependency stack. Audio
identity across hosts, operating systems, architectures, or plugin builds is not
claimed.

## Provenance and integrity

Every completed or interrupted render writes a sealed `manifest.json`,
`records.jsonl`, and append-only `failures.jsonl`. The manifest binds the
package source and version, host and plugin identities, parameter manifest,
runtime and direct dependencies, RNG and sampling-plan identity, normalization
method, UTC observation window, kept/drop/failure counts, and SHA-256 identities
for every output. Drops remain in the failure ledger; a render exception is
recorded before it is raised.

Verify a dataset without loading a plugin:

```sh
vst-bench-ml verify --manifest output/manifest.json
```

Verification fails closed on missing identity, a changed manifest payload,
missing artifacts, unsafe artifact paths, or byte/hash mismatches. These
identities establish the observed stack and do not imply portability,
scientific validity, or release authorization.

## License

The repository source is licensed under the [MIT License](LICENSE). Dependency
terms and redistribution notes are recorded separately in [NOTICE](NOTICE).
The license does not itself authorize a repository visibility change, public
release, dataset release, manuscript submission, or scientific claim.

## Citation and release verification

Citation metadata is provided in [CITATION.cff](CITATION.cff). The exact
release gates and companion-host validation requirement are documented in
[docs/RELEASE.md](docs/RELEASE.md).
