# Installation

## Ordinary installation

The Python package installs independently of the native host and plugin. Package
metadata requires Python 3.10 or newer. CI targets CPython 3.10–3.15 on Windows,
Linux, and macOS (Apple Silicon and Intel); configured CI targets are not evidence
of a completed test run. See the revision evidence for measured results.

Use a virtual environment with your installed Python. On macOS or Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install vst-bench-ml
vst-bench-ml --help
vst-bench-ml verify --help
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install vst-bench-ml
.\.venv\Scripts\vst-bench-ml.exe --help
```

The unreleased compatibility changes apply to a revised source checkout; the
published 0.1.1 distribution retains its original dependency pins. To exercise the
revised dependencies before a new release, install the revised checkout using
`python -m pip install .`, rather than installing 0.1.1 from PyPI.

Ordinary installation allows compatible versions of NumPy, SoundFile, and
pyloudnorm; pip selects versions compatible with the interpreter and platform.
SciPy is resolved as a transitive dependency of pyloudnorm. Do not install the
historical lockfile for ordinary use. Normalization is required: omitting
pyloudnorm is an error.

Verify an existing dataset with
`vst-bench-ml verify --manifest /path/to/manifest.json`. This needs the Python
package and stored files, without a native host or plugin.

## Install from source

```sh
git clone https://github.com/itsuzef/vst-bench-ml-public.git
cd vst-bench-ml-public
python -m pip install .
```

Run these commands inside your virtual environment. Installing source gets the
dependency policy from that checkout; select the intended revision explicitly.

## Rendering and the native host

Rendering additionally requires a separately installed compatible host and plugin.
The [companion walkthrough](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/QUICKSTART.md)
builds a controlled VST3 fixture and runner with a C++ toolchain, CMake, and the
pinned SDK. Native build and plugin compatibility require their own validation;
package installation alone does not establish rendering portability or identical
audio across platforms.

## Reproduce the locked release checks

`requirements/lock.txt` preserves the exact historical validation dependencies,
including SciPy 1.15.3, separately from the compatible package requirements. Use
the Python version, package commit, wheel, companion, and platform specified for
the particular release being reproduced. For the documented Python 3.12 workflow:

```sh
python3.12 -m venv ../validation-env
source ../validation-env/bin/activate
python -m pip install --require-hashes -r requirements/lock.txt
python -m pip install --no-deps .
```

On Windows, create the environment with `py -3.12 -m venv` and run its
`Scripts\python.exe` instead. That syntax does not itself establish support for
reproducing the native macOS validation on Windows.

Use `--no-deps` only after installing the complete lock. The companion's
[validation guide](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/VALIDATION.md)
binds a particular wheel, source commit, dependency lock, and expected outputs.
An ordinary installation is not evidence of that full validation run. Changing
compatible dependencies can change numerical results; exact output hashes remain
scoped to the recorded validation environment.

The historical SciPy 1.15.3 and NumPy 2.2.6 pins lack CPython 3.14/3.15 wheels.
Use the matching historical interpreter for exact reproduction, or ordinary
installation for current use. Do not update the historical lock just to make it
install on a different interpreter.

## Installation troubleshooting

If pip attempts to compile NumPy or SciPy, check the interpreter version and
architecture and upgrade pip in the virtual environment. A source build can mean
there is no compatible wheel, an incompatible exact pin was requested, or the
configured package index lacks the appropriate files. SoundFile's native library
requirements depend on the selected platform distribution.

When reporting a failure, include the full install command and error log, whether
a lockfile was supplied, and these diagnostics:

```sh
python --version
python -m pip --version
python -c 'import platform; print(platform.platform()); print(platform.machine())'
python -m pip freeze
```

On macOS also include `sw_vers`, which records the product version and build rather
than only the Darwin kernel version. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
