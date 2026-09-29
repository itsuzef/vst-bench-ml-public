from pathlib import Path

import pytest

from vst_bench_ml.client import TestHostClient as HostClient
from vst_bench_ml.client import TestHostError as HostError


def identity(plugin_path: str):
    return {
        "host": {
            "protocol_version": "1",
            "source_repository": "https://example.invalid/host",
            "source_commit": "a" * 40,
            "executable_sha256": "b" * 64,
            "build_configuration": "Release",
        },
        "plugin": {
            "path": plugin_path,
            "sha256": "c" * 64,
            "format": "VST3",
            "name": "Example",
            "vendor": "Example Vendor",
            "identifier": "org.example.plugin",
        },
        "capabilities": {"deterministic_reset": True, "parameter_readback": True},
    }


def test_ensure_plugin_returns_complete_identity(tmp_path, monkeypatch):
    plugin = str(tmp_path / "example.vst3")
    client = HostClient()
    monkeypatch.setattr(client, "load_plugin", lambda _: {})
    monkeypatch.setattr(client, "call", lambda method: identity(plugin))
    result = client.ensure_plugin(plugin)
    assert result["plugin_identifier"] == "org.example.plugin"


def test_ensure_plugin_rejects_incomplete_identity(tmp_path, monkeypatch):
    client = HostClient()
    monkeypatch.setattr(client, "load_plugin", lambda _: {})
    monkeypatch.setattr(client, "call", lambda method: {"host": {}, "plugin": {}})
    with pytest.raises(HostError, match="host identity missing"):
        client.ensure_plugin(str(tmp_path / "example.vst3"))


def test_ensure_plugin_rejects_null_host_identity_value(tmp_path, monkeypatch):
    plugin = str(tmp_path / "example.vst3")
    incomplete = identity(plugin)
    incomplete["host"]["source_commit"] = None
    client = HostClient()
    monkeypatch.setattr(client, "load_plugin", lambda _: {})
    monkeypatch.setattr(client, "call", lambda method: incomplete)
    with pytest.raises(HostError, match="host identity missing: source_commit"):
        client.ensure_plugin(plugin)


def test_ensure_plugin_rejects_missing_plugin_identity(tmp_path, monkeypatch):
    plugin = str(tmp_path / "example.vst3")
    incomplete = identity(plugin)
    del incomplete["plugin"]
    client = HostClient()
    monkeypatch.setattr(client, "load_plugin", lambda _: {"path": plugin})
    monkeypatch.setattr(client, "call", lambda method: incomplete)
    with pytest.raises(HostError, match="plugin identity missing"):
        client.ensure_plugin(plugin)


def test_ensure_plugin_rejects_empty_plugin_identity_value(tmp_path, monkeypatch):
    plugin = str(tmp_path / "example.vst3")
    incomplete = identity(plugin)
    incomplete["plugin"]["identifier"] = ""
    client = HostClient()
    monkeypatch.setattr(client, "load_plugin", lambda _: {})
    monkeypatch.setattr(client, "call", lambda method: incomplete)
    with pytest.raises(HostError, match="plugin identity missing: identifier"):
        client.ensure_plugin(plugin)


def test_ensure_plugin_rejects_path_mismatch(tmp_path, monkeypatch):
    requested = str(tmp_path / "requested.vst3")
    observed = str(tmp_path / "observed.vst3")
    client = HostClient()
    monkeypatch.setattr(client, "load_plugin", lambda _: {})
    monkeypatch.setattr(client, "call", lambda method: identity(observed))
    with pytest.raises(HostError, match="does not match"):
        client.ensure_plugin(requested)


def test_already_loaded_fails_closed(monkeypatch):
    client = HostClient()

    def fail(_):
        raise HostError(-32002, "already loaded")

    monkeypatch.setattr(client, "load_plugin", fail)
    with pytest.raises(HostError, match="fresh host"):
        client.ensure_plugin(str(Path("example.vst3")))
