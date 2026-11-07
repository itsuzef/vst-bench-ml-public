# Troubleshooting

| Symptom | Action |
| --- | --- |
| `vst-bench-ml: command not found` | Activate the environment used by pip; try `python -m vst_bench_ml.cli --help`. |
| Pip cannot find version 0.1.1 | Check the package name and index configuration; alternatively use `python -m pip install .` from the checkout. |
| NumPy or SciPy cannot install, or pip attempts a source build | For ordinary use, install the revised package with compatible dependencies without the historical lockfile. Published 0.1.1 retains its original pins. For exact historical reproduction, use its matching Python 3.12 environment. Upgrade pip and record the complete error, Python version, and architecture. See [installation troubleshooting](INSTALL.md#installation-troubleshooting). |
| Connection refused | Start the companion host; match its port to `render --port`. |
| Plugin already loaded | Restart the host before another render. |
| Plugin identity mismatch | Use the parameter manifest for that exact plugin. The companion accepts only its Method Fixture. |
| Host identity/reset/readback capability missing | Use a protocol-compatible host; a generic JSON-RPC server is insufficient. |
| Source archive verification error | Keep the 0.1.0 archive intact and without `.git`, or use the current Git checkout. Do not mix the two layouts. |
| Package repository is dirty during validation | Commit intended source changes and keep environments/builds/results outside the checkout. |
| Wheel identity mismatch | Use the exact release wheel, package commit, and dependency lock pinned by the companion. |
| Zero/fewer outputs | Inspect quality drops and render failures; the fixture walkthrough deliberately retains silent settings with `--keep-bad`. |
| Output hash differs | Check software, dependency, SDK, architecture, and settings. Do not replace expected hashes merely to make a check pass. |
| SoundFile cannot load its native library | Check SoundFile's platform installation requirements; this project's rendering validation covers the documented macOS arm64 stack. |

When reporting an issue, include versions, the command, and the error. Use a small
fixture example and remove credentials, personal paths, and proprietary material.
