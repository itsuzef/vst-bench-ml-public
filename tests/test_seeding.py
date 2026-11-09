# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

from vst_bench_ml.seeding import master_from_label, patch_rng


def test_seeded_plan_rng_replays():
    seed = master_from_label("example")
    left = patch_rng(seed, "org.example.plugin", "plan", 0).random(8)
    right = patch_rng(seed, "org.example.plugin", "plan", 0).random(8)
    assert (left == right).all()
