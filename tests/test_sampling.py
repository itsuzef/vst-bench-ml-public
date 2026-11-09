# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

import numpy as np

from vst_bench_ml.introspect import ParamSpec
from vst_bench_ml.sampling import plan


def test_plan_has_requested_length_and_normalized_values():
    specs = [ParamSpec(0, "Gain", "float", default=0.5)]
    result = plan(specs, 17, np.random.default_rng(7))
    assert len(result) == 17
    assert all(0.0 <= vector[0] <= 1.0 for _, vector in result)
