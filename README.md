# vst-bench-ml

Generate audio-plugin datasets with records of how each output was produced.
`vst-bench-ml` samples plugin parameters, coordinates offline rendering, records
software and render settings, and checks stored artifacts for changes or missing files.

## Install

Use a Python virtual environment (Python 3.11 or newer):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install vst-bench-ml
vst-bench-ml --help
```

Alternatively, install a source checkout with `python -m pip install .`.

The unreleased source allows compatible dependency versions; published 0.1.1
retains its original pins until a new release is published. CI targets ordinary
wheel installation and package tests on Windows, Linux, and macOS (arm64 and
Intel), across CPython 3.11–3.15. Native rendering and exact output-hash reproduction
have separate validation requirements. See the [installation guide](docs/INSTALL.md)
for Windows commands, source installation, and the historical reproduction lock.

## First dataset

Rendering needs a separately installed host and a plugin. The
[sample-free companion walkthrough](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/QUICKSTART.md)
provides both and takes you from installation to eight small generated outputs.
The broader `vst-bench` MCP testing application is not required.

For a configured compatible host:

```sh
vst-bench-ml render --plugin /absolute/path/to/example.vst3 \
  --param-manifest parameter-manifest.json --n 4 --out output \
  --seed-label example-v1
vst-bench-ml verify --manifest output/manifest.json
```

Use a new output directory and a fresh host for each render. Offline verification
needs only this Python package and the stored dataset, without running a plugin.

Inspect the [0.1.1 output format examples](docs/examples/fixture-output/README.md)
without building the host or downloading audio.

## Learn more

- [User documentation](https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/README.md)
- [Installation](https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/INSTALL.md)
- [Commands and outputs](https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/USAGE.md)
- [Troubleshooting](https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/TROUBLESHOOTING.md)
- [Architecture and host protocol](https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/DESIGN.md)
- [Issues](https://github.com/itsuzef/vst-bench-ml-public/issues) and [contributing](https://github.com/itsuzef/vst-bench-ml-public/blob/main/CONTRIBUTING.md)

The package contains Python tools; the host, plugin binaries, datasets, presets,
and audio are supplied or generated separately. Hashes establish artifact
integrity. Matching output bytes have only been demonstrated on pinned environments;
scientific suitability and cross-platform audio identity require separate evaluation.

## Source, licence, and citation

MIT source; dependency notices are in [NOTICE](https://github.com/itsuzef/vst-bench-ml-public/blob/main/NOTICE).
The [0.1.0 Zenodo archive](https://doi.org/10.5281/zenodo.22924036) remains the
historical release. See [public source history](https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/HISTORY.md)
and [CITATION.cff](https://github.com/itsuzef/vst-bench-ml-public/blob/main/CITATION.cff) for version-specific attribution.
