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
| `--expect-identities` | JSON file of expected host/plugin identities; refuse to render on mismatch | None |
| `--host-executable` | Host file you started; its hash must equal the host's report | None |

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

### Identity checks

The host reports its own identity and the plugin's. The package adds what it can
see for itself: it hashes the plugin path before and after the run, and if the host
states the same digest algorithm (`sha256_algorithm`), the two values must agree. A
plugin that changes during the run marks the run failed.

To compare against values obtained elsewhere, write an expected-identities file:

```json
{"schema": "vst-bench-ml.expected-identities/v1",
 "plugin": {"sha256": "<digest>", "identifier": "<id>", "version": "<version>"},
 "host": {"executable_sha256": "<sha256>", "source_commit": "<commit>"}}
```

Every field is optional, but the file must name at least one. Allowed plugin fields
are `sha256`, `identifier`, `name`, `vendor`, `version`, `format`; host fields are
`executable_sha256`, `source_repository`, `source_commit`, `build_configuration`,
`protocol_version`. Get a plugin digest with `vst-bench-ml identify /path/to/plugin`
on a copy you trust, and a host file hash with any SHA-256 tool. Then either

```sh
vst-bench-ml render ... --expect-identities expected.json --host-executable /path/to/host
vst-bench-ml verify --manifest output/manifest.json --expect-identities expected.json
```

`render` refuses to start on any mismatch and records the comparison in the
manifest; `verify` repeats it later against the recorded values. The verify output
ends with an `identities:` line saying what was compared and against what. Without
an expected file that line says the host-reported values are otherwise unchecked.
See [DESIGN.md](DESIGN.md#what-the-identity-checks-establish) for the limits.

### Signatures and external digests

The manifest's own digest shows internal consistency only: someone who changes a
file can recompute every hash and reseal the manifest. Two checks use material kept
outside the dataset and so survive that.

Sign with an SSH key (Ed25519 recommended). This needs OpenSSH 8.1 or newer:

```sh
vst-bench-ml sign --manifest output/manifest.json --key ~/.ssh/id_ed25519
```

This verifies the dataset, then writes `output/manifest.json.sig`. Publish your
identity and public key as one line of an allowed-signers file, somewhere the
dataset's recipients can trust independently of the dataset (a paper, a project
page, a repository you control):

```
you@example.org ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
```

A recipient checks the signature against that file:

```sh
vst-bench-ml verify --manifest output/manifest.json --allowed-signers allowed_signers
```

Add `--signer you@example.org` to require one identity. Without `--allowed-signers`
a signature is reported as present but not checked. The same check works without
this package: `ssh-keygen -Y verify -f allowed_signers -I you@example.org -n
vst-bench-ml-manifest -s manifest.json.sig < manifest.json`.

Alternatively, record the manifest's SHA-256 somewhere outside the dataset when
you produce it, and check it later with `verify --expect-manifest-sha256 <hex>`.

Keep the private key off shared machines; a passphrase, `ssh-agent` or a hardware
key all work with `ssh-keygen`. Allowed-signers lines accept `valid-after` and
`valid-before` options for key rotation. Revocation lists are not checked.
See [DESIGN.md](DESIGN.md#what-a-signature-establishes).

Datasets written by 0.1.x use schema v1 and have no attempt ledger or identity checks.
They can still be signed. They verify as
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
