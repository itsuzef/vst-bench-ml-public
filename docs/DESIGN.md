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

A render manifest uses `vst-bench-ml.provenance/v2` and binds four layers
(v1, written by 0.1.x, lacks the attempt ledger and is still verified):

1. execution identity: package source/version, runtime environment, installed
   NumPy, SoundFile, pyloudnorm, and SciPy versions, RNG derivation, and normalization method;
2. external identity: fail-closed host, plugin, and parameter-manifest
   identities;
3. observation: UTC start/completion times and completed or failed status;
4. evidence: the sampling-plan digest, records, append-only failure/drop ledger,
   the attempt ledger with one outcome per planned attempt, per-output byte count
   and SHA-256, aggregate counts, and manifest payload digest.

The verifier resolves only relative artifact paths under the dataset root and
checks all bound sizes and hashes. Sampling replay regenerates the plan from the
recorded master seed, plugin identifier, stage, stream index, requested count,
and parameter specs. Replay is asserted only for that recorded dependency
stack. Failures and quality drops are evidence and are never inferred from
missing output files.

## What the identity checks establish

Three sources describe the host and plugin. The host reports both. The package
hashes the plugin path, and the host file if `--host-executable` names it. The user
may supply expected values obtained elsewhere. The manifest records every
comparison made and which two sources agreed.

A match shows that the files at those paths had the expected content when the
package read them, before and after the run, and that the host's report was
consistent with them. It does not show that the process answering on the port was
started from that host file, or that it loaded those plugin bytes rather than a
copy elsewhere. The package talks to the host over localhost and cannot inspect the
process. Fields other than the two hashes (name, vendor, version, commit) are only
ever the host's word compared with the expected word.

These checks concern execution. They are separate from the manifest digest, which
shows the dataset is internally consistent. Neither says who produced the dataset.

## What a signature establishes

`sign` produces an OpenSSH signature of the manifest file under the namespace
`vst-bench-ml-manifest`. Because the manifest binds every other file by hash, a
valid signature covers the whole dataset. Verified against an allowed-signers file
obtained apart from the dataset, it shows that the holder of a listed private key
signed exactly this manifest. A changed and fully resealed dataset fails, as does a
signature by any other key or one made for another namespace.

It shows nothing about how the dataset was made. The signer vouches for the bytes,
not for the host's reports, the identity checks above, or the audio's fidelity. A
stolen key signs as well as its owner, and trust is only as good as the channel the
allowed-signers file came through. Key custody, rotation and revocation are the
producer's responsibility; this package stores no keys.

## Dataset file inventory

Verification rejects files absent from the artifact inventory, including hidden
files, and rejects symbolic links and other non-regular entries. Only the manifest,
records ledger, failure ledger, attempt ledger, declared outputs, and the manifest's
detached signature (`<manifest>.sig`) are allowed. Empty directories
are ignored. Keep auxiliary material outside the dataset root. The explicit
`--allow-extra-files` option retains listed-artifact verification without directory
completeness or link checks; it never permits missing or changed declared artifacts.
