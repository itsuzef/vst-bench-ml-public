# Package and host boundary

`vst-bench-ml` is a pure-Python client. The host is a separately built and
versioned executable reachable only through localhost JSON-RPC.

Before rendering, the client calls `load_plugin` and then `get_identity`.
`get_identity` must return:

- `host`: `protocol_version`, `source_repository`, `source_commit`,
  `executable_sha256`, and `build_configuration`;
- `plugin`: canonical `path`, `sha256`, `format`, `name`, `vendor`, and stable
  `identifier`;
- `capabilities`: true `deterministic_reset` and `parameter_readback` values.

The canonicalized plugin path must equal the requested path. A host that reports
an already-loaded plugin or incomplete identity is rejected. This package does
not select or distribute a host implementation.

The public-candidate source surface is limited to the package configuration,
this documentation, two generic source examples, the generic modules included
by the build configuration, and their tests. Private research modules remain in
repository history but are excluded from source and wheel artifacts.

## Provenance contract

A render manifest uses `vst-bench-ml.provenance/v1` and binds four layers:

1. execution identity: package source/version, runtime environment, installed
   NumPy, SoundFile, pyloudnorm, and SciPy versions, RNG derivation, and normalization method;
2. external identity: fail-closed host, plugin, and parameter-manifest
   identities;
3. observation: UTC start/completion times and completed or failed status;
4. evidence: the sampling-plan digest, records, append-only failure/drop ledger,
   per-output byte count and SHA-256, aggregate counts, and manifest payload
   digest.

The verifier resolves only relative artifact paths under the dataset root and
checks all bound sizes and hashes. Sampling replay regenerates the plan from the
recorded master seed, plugin identifier, stage, stream index, requested count,
and parameter specs. Replay is asserted only for that recorded dependency
stack. Failures and quality drops are evidence and are never inferred from
missing output files.
