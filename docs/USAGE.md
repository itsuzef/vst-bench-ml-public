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
- `failures.jsonl`: drop and failure events. It can be empty after a successful
  render.
- `attempts.jsonl`: one line for every planned attempt, in render order, with its
  parameters and exactly one outcome: `kept` (with the output identity), `dropped`
  (with the quality reason), `failed` (with the error) or `not_attempted` (the run
  stopped first). Kept and dropped lines also carry the size and SHA-256 of the
  audio as received from the host, before normalization.
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

Success prints `verified: N kept, D dropped, F failures (artifact integrity and file inventory)`,
then one line accounting for the planned attempts, and exits with status 0.
Added files, changed/missing artifacts, or invalid identity fields produce an error and nonzero
exit status. A valid failed-run manifest can still verify: the attempts line then
reports failed and unattempted renders, and the observation status is `failed`.

### Attempt accounting

The plan size, signal list and signal mode in the manifest fix the attempt IDs
(`p000000_sus_c3`, ...) before rendering. Verification requires one ledger line per
planned ID, in order, with no duplicates or additions. It recomputes the sampling-plan
digest from the ledger's parameter vectors, matches every kept line to its record and
stored output, and matches every dropped or failed line to its event. A run with a
failed or unattempted render cannot carry the status `completed`.

If the host wrote its own attempt trace outside the dataset, compare the two:

```sh
vst-bench-ml verify --manifest output/manifest.json --host-trace host-trace.jsonl
```

Each trace line needs `attempt_id` and `outcome` (`rendered` or `failed`); a rendered
line also needs `output.bytes` and `output.sha256` of the audio file the host wrote.
Every kept or dropped attempt must have a rendered trace line with the same audio
hash the package received; an unattempted one must have none; a failed one may
have a failed line or none, since a host can die before writing it. The companion host
writes such a trace with `--attempt-trace`. The trace is only as trustworthy as the
host and the place it was kept.

Datasets written by 0.1.x use schema v1 and have no attempt ledger. They verify as
before, and the attempts line says so: a v1 dataset accounts for kept outputs and
recorded events, but a planned attempt with neither would go unnoticed.

By default the dataset directory may contain only the manifest itself, the two
bound ledgers, and declared outputs. Hidden files are checked too. Symbolic links
(including directory and dangling links) and other non-regular entries are rejected;
empty directories are ignored. Keep notes, logs, and other auxiliary files outside
the dataset directory. Renaming the manifest is allowed.

For an intentional directory containing additional files, use
`verify --manifest output/manifest.json --allow-extra-files`. Its success message
says `listed artifact integrity only`: it skips file-inventory and link checks,
but still requires every declared artifact to pass all existing integrity checks.

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

## Inspect output without a host

[Fixture output examples](examples/fixture-output/README.md) provide an abbreviated
0.1.1 manifest and an unchanged records line, with field explanations and explicit
omissions. These are format examples, not a dataset accepted by `verify`.
