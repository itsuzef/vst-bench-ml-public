# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

import pytest

from vst_bench_ml import batch


class Client:
    def set_parameters(self, values):
        self.values = values

    def render_audio(self, num_samples, output_path, midi_events):
        self.rendered = (num_samples, output_path, midi_events)


class FailingClient(Client):
    def render_audio(self, num_samples, output_path, midi_events):
        raise RuntimeError("host stopped")


def test_drop_is_preserved_in_failure_ledger(tmp_path):
    events = []

    def drop(record, wav_path):
        record["_drop_reason"] = "quality:silent"
        return None

    records = batch.generate(
        Client(),
        [],
        [("A", {0: 0.5})],
        tmp_path,
        signals=("sus_c3",),
        num_samples=512,
        process=drop,
        event_sink=events.append,
        progress_every=0,
    )

    assert records == []
    assert events == [
        {
            "status": "drop",
            "stage": "process",
            "patch_id": "p000000",
            "tier": "A",
            "signal": "sus_c3",
            "reason": "quality:silent",
        }
    ]


def test_failure_is_preserved_before_raise(tmp_path):
    events = []
    with pytest.raises(RuntimeError, match="host stopped"):
        batch.generate(
            FailingClient(),
            [],
            [("A", {0: 0.5})],
            tmp_path,
            signals=("sus_c3",),
            num_samples=512,
            event_sink=events.append,
            progress_every=0,
        )

    assert events[0]["status"] == "failure"
    assert events[0]["stage"] == "render_or_process"
    assert events[0]["error_type"] == "RuntimeError"
    assert events[0]["message"] == "host stopped"


def test_keyboard_interrupt_is_preserved_before_raise(tmp_path):
    events = []

    class InterruptedClient(Client):
        def render_audio(self, num_samples, output_path, midi_events):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        batch.generate(
            InterruptedClient(),
            [],
            [("A", {0: 0.5})],
            tmp_path,
            signals=("sus_c3",),
            num_samples=512,
            event_sink=events.append,
            progress_every=0,
        )

    assert events[0]["status"] == "failure"
    assert events[0]["error_type"] == "KeyboardInterrupt"
    assert events[0]["message"] == "KeyboardInterrupt"
