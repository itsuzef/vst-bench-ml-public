# Release checklist

The first public release candidate is `0.1.0` on the pinned Python 3.12 stack.

Before a public tag or release:

1. Verify `main` is clean and synchronized with `origin/main`.
2. Require the `CI` workflow to pass at the exact release commit.
3. Build the wheel and source distribution from that commit.
4. Verify wheel metadata reports `License-Expression: MIT` and includes
   `LICENSE` and `NOTICE`.
5. Run the companion host's complete deterministic and negative validation
   against those exact distribution bytes.
6. Record repository, commit, tree, wheel, dependency-lock, and companion-host
   identities in the release receipt.
7. Confirm the public artifact contains no quarantined research modules,
   plugins, binaries, product schemas, presets, models, datasets, or audio.
8. Obtain Chef's explicit public-release authorization.

Repository visibility, tags, releases, archives, manuscripts, submissions, and
scientific claims are separate actions. A passing build or software license
does not authorize them.
