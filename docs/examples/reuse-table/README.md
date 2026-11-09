# Worked reuse: prepare candidate parameter labels

**Demonstrated here:** a standard-library Python projection of the preserved
0.1.1 Method Fixture records excerpt to CSV. No host, audio, model, or training
is used. **Proposed downstream use:** preparing verified audio/parameter pairs
for a parameter-estimation study. Neither model performance nor scientific label
validity is demonstrated. Third-party plugin adaptation below is proposed, not
implemented or tested; the optional repeatability experiment remains deferred.

## 1. Run the no-build example

Prerequisites: Python 3.10 or newer and this package source checkout. From its root:

```sh
python docs/examples/reuse-table/export.py \
  docs/examples/fixture-output/records.jsonl > /tmp/fixture-labels.csv
cat /tmp/fixture-labels.csv
```

Expected stderr: `records=1 selected=1 excluded=0`. Expected CSV:

```csv
patch_id,signal,audio_path,gain_norm,tone_norm,waveform_norm,octave_norm,enabled_norm
p000000,sus_c3,audio/p000000_sus_c3.npz,0.495611,0.529401,0.5,0.5,1.0
```

These values come from the [unchanged historical record](../fixture-output/README.md),
not a new render. The referenced audio is omitted. The excerpt cannot pass
`verify` and this projection does not validate it. Indices 0–4 are fixture-specific;
values remain normalized, not native units or universal plugin labels. Index 5
is audio-irrelevant and not a target. In this row, waveform 0.5 selects square,
octave 0.5 selects zero, enabled 1.0 is on. Tone controls pulse width in square
mode: record the dependency rather than treating it as an independent timbral axis.

## 2. Apply the projection to a complete fixture dataset

Follow the companion [quickstart](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/7d1079154635f19fe1c47309bd4035a52bf7ea2c/docs/QUICKSTART.md)
for the macOS arm64 toolchain, Python environment, pinned SDK build, server and
render command. Its four patches × two signals produce eight kept records using
`--keep-bad`; this deliberately preserves disabled/silent settings. This document
does not add a fresh rendering or repeatability result. With that environment
active and back at the package source root:

```sh
DATASET=/absolute/path/to/vst-bench-example/output
vst-bench-ml verify --manifest "$DATASET/manifest.json"
python docs/examples/reuse-table/export.py "$DATASET/records.jsonl" \
  > /tmp/fixture-labels.csv
```

Keep the CSV **outside** the sealed dataset: extra files fail the default inventory
check. Continue only if verification exits zero, the observation status is successful,
and attempted/kept/dropped/failed counts are reconciled. On the quickstart's successful
path verification reports eight kept, zero dropped and zero failures. The exporter
then excludes rows flagged silent or clipped; the selected count can be less than
eight and is not a quality score. Inspect those counts and the bound failure ledger
before interpreting the candidate table. Do not substitute the excerpt for this dataset.

To consume audio later, join `audio_path` relative to the verified dataset root;
inspect the NPZ keys/shape/sample rate as in [USAGE](../../USAGE.md), without assuming
a channel layout. Reuse `patch_id` as a grouping key so the two MIDI observations
of a patch do not leak across study splits. Verify that such a split suits the study;
this grouping alone does not guarantee generalization. Stored audio is normalized,
whereas quality flags describe pre-normalization audio. Neither a non-silent record
nor hash agreement establishes identifiable parameters, perceptual quality or useful
training labels. No splitting, audio analysis or training pipeline is supplied here.

## 3. Proposed adaptation to another instrument

A freely available VST3 is not a drop-in replacement for Method Fixture. Do not
disable the companion identity gate and describe that as support. For a specific
lawfully obtained instrument, an adapter implementer would need to:

1. Pin plugin source/binary/version, licence and output permissions, native
   toolchain, SDK, platform and dependencies. Open source alone does not grant
   rights to bundled samples or all generated outputs.
2. Replace the fixture-specific loading/identity logic in `host/server.py` and
   six-parameter/ID assumptions in `host/runner.cpp` with plugin-specific logic.
   Preserve identity validation, not fixture UID/name/vendor expectations.
   Implement the [protocol](https://github.com/itsuzef/vst-bench-dataset-host-public/blob/7d1079154635f19fe1c47309bd4035a52bf7ea2c/docs/PROTOCOL.md)
   lifecycle, finite normalized parameters, controller readback, MIDI/render contract,
   and declared reset/attempt-ID capabilities. Document random seeds, state restoration,
   tails, voices and resources needed by that instrument.
3. Supply a new parameter manifest: observed controller indices, ranges/discrete
   mappings, defaults, mode dependencies and audio-irrelevant exclusions. Replace
   the exporter's fixed indices and column names with those meanings; do not copy
   the fixture's gain/tone/waveform labels blindly.
4. Before batch generation, check identity rejection, parameter boundary/discrete
   readback, reset isolation using interleaved settings, MIDI scheduling, sample
   count/rate/channels, finite output and meaningful quality thresholds. Preserve
   failures. Repeat a fixed small plan in fresh processes, report exact hashes
   where equal; otherwise report predeclared numeric differences/tolerances, not
   a retrofitted claim of perceptual equivalence. These are proposed checks, not results.
5. Only then use the documented `render` command with the adapted plugin path,
   manifest, compatible host port and a fresh output directory; verify the complete
   dataset and project labels as above. Expected evidence is bound identities,
   parameter/MIDI/reset settings, counts, kept records, drop/failure events and
   hashed audio. Core `verify` checks stored consistency, not execution or origin.
   Companion finalization/conformance scripts and expected hashes are fixture-specific too:
   they must be adapted and validated separately before claiming a complete kept
   attempt ledger or conformance for another instrument.

No specific third-party instrument, compatibility, output identity, general host
adapter or new conformance result is claimed. This route makes the implementation
and success criteria explicit without representing the deferred experiment as done.
