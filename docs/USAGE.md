# Commands and output files

## Render

Start a compatible host before invoking the client. The companion host supports
its own Method Fixture instrument. Other plugins require a host that implements
the documented identity, reset, readback, and render protocol.

| Option | Meaning | Default |
| --- | --- | --- |
| `--plugin` | Absolute plugin file or bundle path | Required |
| `--param-manifest` | JSON parameter definitions matching that plugin | Required |
| `--out` | New destination directory | Required |
| `--n` | Number of sampled parameter plans | 100 |
| `--port` | Host port on 127.0.0.1 | 8765 |
| `--signals` | Comma-separated MIDI signal names | sus_c3 |
| `--signal-mode` | Render every signal per plan (`all`) or cycle signals | all |
| `--seconds` | Duration per render | 2.0 |
| `--sr` | Requested sample rate | 44100 |
| `--target-lufs` | Loudness normalization target | -14.0 |
| `--seed-label` | Text used to derive the parameter sampling seed | run |
| `--exclude-groups` | Comma-separated parameter groups to leave unvaried | Empty |
| `--keep-bad` | Retain samples flagged silent or clipped | Off |

List available MIDI names with:

```sh
python -c "from vst_bench_ml.midi_signals import signal_names; print(signal_names())"
```

With `--n 4 --signals sus_c3,gate_c2 --signal-mode all`, there are eight render
attempts. Quality filtering may reduce the number retained. The companion fixture
example uses `--keep-bad` so even intentionally disabled/silent settings are kept.
That flag is useful for the fixture and does not establish audio quality.

Always use a fresh host process and a new output directory. Existing output paths
are not protected against overwrite by the current CLI. The same seed label fixes
the sampling plan only for the same plugin identity, parameter definitions, and
compatible software stack; it does not guarantee audio identity across systems.

## Read outputs

- `manifest.json`: software/plugin identities, settings, counts, output hashes,
  and an integrity hash of the manifest payload.
- `records.jsonl`: one JSON object for each kept output, including parameters,
  MIDI signal, quality observations, and the relative audio path.
- `failures.jsonl`: core drop/failure events. It can be empty after a successful
  basic render. The separate companion validation workflow extends the ledger
  with terminal entries for all attempts and negative-case evidence.
- `audio/*.npz`: NumPy audio arrays and sample rate. These are not WAV files.

Inspect an array without assuming its shape:

```python
import numpy as np
with np.load("output/audio/p000000_sus_c3.npz", allow_pickle=False) as item:
    print(item.files)
    for key in item.files:
        print(key, item[key].shape, item[key].dtype)
```

## Verify offline

```sh
vst-bench-ml verify --manifest output/manifest.json
```

Success prints `verified: N kept, D dropped, F failures (artifact integrity only)`
and exits with status 0.
Changed/missing artifacts or invalid identity fields produce an error and nonzero
exit status. A valid failed-run manifest can still verify: check the observation
status and failure count before treating a dataset as complete.

This command checks the recorded manifest and files. It does not compare the
current Python environment with the environment used to generate them. Updating
SciPy or another dependency does not invalidate an unchanged dataset. New renders
record the installed NumPy, SoundFile, pyloudnorm, and SciPy versions.

To reproduce the exact locked environment, use the companion's
[dependency environment check](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/main/docs/VALIDATION.md#check-installed-dependency-versions).
That check compares installed versions with the lockfile and rejects mismatches.

Verification checks internal consistency; it does not authenticate the producer,
prove that an untrusted host reported honestly, or establish scientific usefulness.
See `render --help` and `verify --help` for the installed command interface.
