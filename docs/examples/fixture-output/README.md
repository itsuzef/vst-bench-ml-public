# Fixture output format examples (0.1.1)

Read [manifest.json](manifest.json) and [records.jsonl](records.jsonl) directly;
no host, SDK, plugin, Python installation, or audio download is needed.
These are **documentation excerpts, not a complete or verifiable dataset**.
They are not a parameter-manifest input to `render`.

## Origin and validity

Values were extracted from the preserved first run of the 2026-09-29 release
validation: package **0.1.1**, source `25c839ba41ec6598a844dd2bbc0e91ae47073c3b`,
companion host `783e1d9604e819ea2f10d4427a64ba7238b84bd1`, on macOS arm64,
CPython 3.12.13. The source run rendered the self-authored sample-free Method
Fixture: four patches times two MIDI signals, eight kept outputs, `keep_bad=true`.
This is historical output, not a new run or a promise of identical output on other
platforms. The source is a **companion-finalized** manifest using the core
`vst-bench-ml.provenance/v1` schema plus companion fields; it is not core-only output.

The JSON object in `manifest.json` is syntactically valid but **abbreviated**:
only `schema`, selected identity fields, `observation`, `request`, `outcomes`, and
the first `artifacts.outputs` entry are retained, with original values unchanged.
Other identities (including plugin, parameters, dependencies, RNG, and normalization),
remaining artifact entries, `record_schema`, `render`, `validation`, and `integrity`
are omitted. There is no placeholder digest and no resealing of the excerpt.
The eight-output counts describe the original run, not this one-line example.

`records.jsonl` contains exactly the first original JSONL line, byte-for-byte;
seven other lines are omitted. It is one JSON object per line, not a JSON array.
No NPZ audio or attempt ledger is distributed here. Running `verify` on this
folder is expected to fail: mandatory manifest fields and declared artifacts are
absent. Do not copy these excerpts into a real dataset directory.

## Reading the fields

| Field | Meaning in this example |
| --- | --- |
| `schema` | Core provenance format identifier, not package version. |
| `identities.package` / `host` | Recorded source revisions; host identity is host-reported, not authenticated. |
| `observation` | Start/completion timestamps and run status. |
| `request` | Requested patch count, MIDI signals, duration, sample rate, and quality-drop bypass. |
| `outcomes` | Original run's attempted/rendered/kept/dropped/failed counts. |
| `artifacts.outputs[0]` / record `output` | Same relative NPZ path, byte count and SHA-256; the digest describes audio omitted here. |
| `patch_id`, `tier`, `signal` | Patch key, A/B/C sampling tier, and MIDI signal name. |
| `param_vector` | Normalized values keyed by stringified parameter indices, not native-unit labels. |
| `sample_rate`, `num_samples` | 44100 Hz and 22050 frames (0.5 seconds) for this output. |
| `quality` | Rounded raw, pre-normalization measurements and flags; not post-normalization quality or label validity. |
| `in_lufs` | Pre-normalization loudness value; the implementation may store RMS dBFS on fallback, without a per-record method flag. |
| `observed_at` | Completion timestamp for this retained render. |

Parameter indices 0–4 are gain, tone, waveform, octave, and enabled in the
[fixture parameter definitions](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/783e1d9604e819ea2f10d4427a64ba7238b84bd1/fixtures/parameter-manifest.json).
Index 5 is excluded as audio-irrelevant. Discrete values remain normalized here:
`0.5` selects square for waveform and zero for octave; `1.0` enables the fixture.
The NPZ stores normalized audio; raw quality and `in_lufs` refer to audio before
that normalization. A non-silent, unclipped record does not establish usefulness
for training or perceptual quality.

The complete source manifest binds a records ledger, a failure/attempt ledger,
all eight outputs, and a canonical payload digest. Its companion ledger adds
kept-attempt evidence; core-only output has no such complete kept ledger.
An unkeyed manifest digest checks consistency, not origin or resistance to
coherent replacement and resealing.

See [commands and outputs](../../USAGE.md), [provenance design](../../DESIGN.md),
and [companion validation](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/revision/installation-compatibility/docs/VALIDATION.md)
for generating and checking a complete dataset. The JORS 796 revised manuscript's
“Output format examples” subsection uses shorter projections of these same values.
