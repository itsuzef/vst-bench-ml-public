#!/usr/bin/env python3
"""Write a generic parameter manifest from a compatible running host."""

import argparse
from pathlib import Path

from vst_bench_ml import introspect
from vst_bench_ml.client import TestHostClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--exclude-prefix", action="append", default=[])
    args = parser.parse_args()

    client = TestHostClient(port=args.port)
    identity = client.ensure_plugin(args.plugin)
    specs = introspect.specs_from_live(client.list_parameters())
    prefixes = tuple(value.lower() for value in args.exclude_prefix)
    for spec in specs:
        spec.group = spec.name.split()[0].lower() if spec.name.split() else ""
        spec.audio_irrelevant = bool(
            prefixes and spec.name.lower().startswith(prefixes)
        )
    introspect.write_manifest(specs, identity["plugin_identifier"], Path(args.out))


if __name__ == "__main__":
    main()
