# Installation

## Normal use

The documented environment is macOS on Apple Silicon and Python 3.12. The package
metadata permits Python >=3.10; broader rendering portability is not established.
Python tools do not bundle the native host or a plugin.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install vst-bench-ml==0.1.1
vst-bench-ml --help
vst-bench-ml verify --help
```

For installation from a checkout, use `python -m pip install .`. Pip installs
NumPy, SoundFile, pyloudnorm, and their
required dependencies. Keep normalization available: omitting pyloudnorm is an error.

To render, continue with the [complete companion walkthrough](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/QUICKSTART.md).
To verify an existing dataset, run `vst-bench-ml verify --manifest /path/to/manifest.json`.

## Install from source

```sh
git clone https://github.com/itsuzef/vst-bench-ml-public.git
cd vst-bench-ml-public
python3.12 -m venv ../vst-bench-env
source ../vst-bench-env/bin/activate
python -m pip install .
```

## Reproduce the locked release checks

The direct dependencies are pinned in package metadata. The complete transitive
and development environment used by the validation workflow is separately pinned
with hashes in `requirements/lock.txt`.

```sh
python -m pip install --require-hashes -r requirements/lock.txt
python -m pip install --no-deps .
```

Use `--no-deps` only after installing the complete lock. The companion's
[validation guide](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/VALIDATION.md) binds a particular wheel,
source commit, dependency lock, and expected outputs. An ordinary installation
is not evidence of that full validation run.
