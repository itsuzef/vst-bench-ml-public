#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Measure sequential render latency against a compatible running host."""

import argparse
import tempfile
import time
from pathlib import Path

from vst_bench_ml.client import TestHostClient
from vst_bench_ml.midi_signals import build


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--iters", type=int, default=10)
    parser.add_argument("--samples", type=int, default=44100)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.iters < 1 or args.samples < 1:
        parser.error("--iters and --samples must be positive")

    client = TestHostClient(port=args.port)
    client.ensure_plugin(args.plugin)
    midi = build("sus_c3", args.samples)
    with tempfile.TemporaryDirectory(prefix="vst_bench_ml_profile_") as directory:
        output = str(Path(directory) / "render.wav")
        started = time.perf_counter()
        for _ in range(args.iters):
            client.render_audio(args.samples, output, midi)
        elapsed = time.perf_counter() - started
    print(f"{elapsed / args.iters:.6f} seconds/render")


if __name__ == "__main__":
    main()
