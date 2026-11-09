# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Youssef Hemimy
"""Project Method Fixture records to candidate labels; not a verifier."""

import argparse
import csv
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    args = parser.parse_args()
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow([
        "patch_id", "signal", "audio_path", "gain_norm", "tone_norm",
        "waveform_norm", "octave_norm", "enabled_norm",
    ])
    seen = selected = 0
    with args.records.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            seen += 1
            quality = record["quality"]
            if quality["silent"] or quality["clipped"]:
                continue
            params = record["param_vector"]
            writer.writerow([
                record["patch_id"], record["signal"], record["audio_path"],
                *(params[str(index)] for index in range(5)),
            ])
            selected += 1
    print(f"records={seen} selected={selected} excluded={seen-selected}", file=sys.stderr)


if __name__ == "__main__":
    main()
