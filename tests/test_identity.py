# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Host and plugin identities are checked against independent sources."""

import json

import pytest
from .scripted_host import IDENTITY, render, verify

from vst_bench_ml import cli, identity, provenance


def expected_file(tmp_path, **sections):
    path = tmp_path / "expected.json"
    path.write_text(json.dumps({"schema": identity.EXPECTED_SCHEMA, **sections}))
    return path


def plugin_file(tmp_path, content=b"plugin"):
    path = tmp_path / "example.vst3"
    path.write_bytes(content)
    return path


def test_matching_expected_identities_are_bound_to_the_run(tmp_path, monkeypatch, capsys):
    digest = identity.path_digest(plugin_file(tmp_path))
    # Field order in the file must not matter once the manifest sorts its keys.
    expected = expected_file(tmp_path, plugin={"vendor": "Example", "sha256": digest, "identifier": "org.example.fixture"},
                             host={"source_commit": "a" * 40, "executable_sha256": "b" * 64})
    dataset, _ = render(tmp_path, monkeypatch,
                        arguments=("--n", "1", "--expect-identities", str(expected)))

    checks = verify(dataset)["identity_checks"]
    assert checks["result"] == "matched-expected"
    assert checks["expected"]["sha256"] == provenance.sha256_file(expected)
    assert checks["package_observed"]["plugin_sha256"] == digest == checks["package_observed"]["plugin_sha256_after"]
    assert {item["subject"] for item in checks["comparisons"]} == {
        "plugin.sha256", "plugin.vendor", "plugin.identifier", "host.executable_sha256", "host.source_commit"}
    cli.main(["verify", "--manifest", str(dataset / "manifest.json")])
    assert "expected identities given at render time" in capsys.readouterr().out


def test_substituted_plugin_is_refused_before_rendering(tmp_path, monkeypatch):
    digest = identity.path_digest(plugin_file(tmp_path))
    expected = expected_file(tmp_path, plugin={"sha256": digest})
    plugin_file(tmp_path, b"substituted plugin")
    dataset, trace = render(tmp_path, monkeypatch, arguments=("--n", "1", "--expect-identities", str(expected)),
                            error="identity mismatch for plugin.sha256: expected .* != package-observed")
    assert trace == [] and not dataset.exists()


def test_substituted_host_executable_is_refused(tmp_path, monkeypatch):
    started = tmp_path / "host.py"
    started.write_bytes(b"not the host that answered")
    render(tmp_path, monkeypatch, arguments=("--n", "1", "--host-executable", str(started)),
           error="identity mismatch for host.executable_sha256: package-observed .* != host-reported")


def test_incorrect_host_report_of_the_plugin_is_refused(tmp_path, monkeypatch):
    # The host states the shared digest algorithm, so its report is comparable.
    render(tmp_path, monkeypatch, arguments=("--n", "1"),
           plugin_report={"sha256_algorithm": identity.PATH_DIGEST, "sha256": "c" * 64},
           error="identity mismatch for plugin.sha256: package-observed .* != host-reported")


def test_correct_host_report_of_the_plugin_is_compared(tmp_path, monkeypatch):
    digest = identity.path_digest(plugin_file(tmp_path))
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"),
                        plugin_report={"sha256_algorithm": identity.PATH_DIGEST, "sha256": digest})
    comparison = verify(dataset)["identity_checks"]["comparisons"]
    assert comparison == [{"subject": "plugin.sha256", "sources": ["package-observed", "host-reported"], "value": digest}]


def test_incorrect_host_report_of_other_fields_is_refused(tmp_path, monkeypatch):
    expected = expected_file(tmp_path, plugin={"version": "1.0.6"}, host={"source_commit": "f" * 40})
    render(tmp_path, monkeypatch, arguments=("--n", "1", "--expect-identities", str(expected)),
           plugin_report={"version": "1.0.5"},
           error="identity mismatch for plugin.version: expected 1.0.6 != host-reported 1.0.5")


@pytest.mark.parametrize("content,message", [
    (None, "expected identities are unreadable"),
    ({"schema": "other"}, "must use schema"),
    ({"schema": identity.EXPECTED_SCHEMA}, "name nothing to check"),
    ({"schema": identity.EXPECTED_SCHEMA, "plugin": {"sha256": ""}}, "empty value"),
    ({"schema": identity.EXPECTED_SCHEMA, "plugin": {"path": "/x"}}, "may only name"),
])
def test_missing_or_empty_trust_material_is_refused(tmp_path, monkeypatch, content, message):
    path = tmp_path / "expected.json"
    if content is not None:
        path.write_text(json.dumps(content))
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1", "--expect-identities", str(path)),
                        error=message)
    assert not dataset.exists()


def test_run_without_expected_identities_says_so(tmp_path, monkeypatch, capsys):
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"))
    assert verify(dataset)["identity_checks"]["result"] == "no-expected-identities"
    cli.main(["verify", "--manifest", str(dataset / "manifest.json")])
    assert "compared nothing (no expected identities; host-reported values are otherwise unchecked)" in capsys.readouterr().out


def test_plugin_changed_during_the_run_marks_the_run_failed(tmp_path, monkeypatch):
    plugin = plugin_file(tmp_path)
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"),
                        during_render=lambda: plugin.write_bytes(b"swapped mid-run"),
                        error="plugin files changed during the run")
    manifest = verify(dataset)
    assert manifest["observation"]["status"] == "failed"
    observed = manifest["identity_checks"]["package_observed"]
    assert observed["plugin_sha256"] != observed["plugin_sha256_after"]

    manifest["observation"]["status"] = "completed"
    provenance.write_manifest(dataset / "manifest.json", manifest)
    with pytest.raises(provenance.IntegrityError, match="plugin changed during a run that is not marked failed"):
        verify(dataset)


def test_expected_identities_can_be_checked_later_offline(tmp_path, monkeypatch, capsys):
    digest = identity.path_digest(plugin_file(tmp_path))
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"))
    good = expected_file(tmp_path, plugin={"sha256": digest, "identifier": IDENTITY["plugin"]["identifier"]})
    verify(dataset, expected_identities=good)
    cli.main(["verify", "--manifest", str(dataset / "manifest.json"), "--expect-identities", str(good)])
    assert "expected identities given now" in capsys.readouterr().out
    bad = expected_file(tmp_path, plugin={"sha256": "0" * 64})
    with pytest.raises(provenance.IntegrityError, match="identity mismatch for plugin.sha256"):
        verify(dataset, expected_identities=bad)


def test_edited_identity_section_is_rejected_after_resealing(tmp_path, monkeypatch):
    digest = identity.path_digest(plugin_file(tmp_path))
    expected = expected_file(tmp_path, plugin={"sha256": digest})
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1", "--expect-identities", str(expected)))
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    manifest["identity_checks"]["package_observed"]["plugin_sha256"] = "0" * 64
    manifest["identity_checks"]["package_observed"]["plugin_sha256_after"] = "0" * 64
    provenance.write_manifest(dataset / "manifest.json", manifest)
    with pytest.raises(provenance.IntegrityError, match="identity mismatch for plugin.sha256"):
        verify(dataset)

    manifest["identity_checks"]["expected"] = None  # claims a check that was never bound
    provenance.write_manifest(dataset / "manifest.json", manifest)
    with pytest.raises(provenance.IntegrityError, match="do not follow from the manifest"):
        verify(dataset)


def test_bundle_digest_covers_names_contents_and_links(tmp_path, capsys):
    bundle = tmp_path / "Example.vst3"
    (bundle / "Contents/MacOS").mkdir(parents=True)
    (bundle / "Contents/MacOS/Example").write_bytes(b"binary")
    (bundle / "Contents/Info.plist").write_text("info")
    original = identity.path_digest(bundle)
    cli.main(["identify", str(bundle)])
    assert capsys.readouterr().out.startswith(f"{original}  {identity.PATH_DIGEST}  ")

    (bundle / "Contents/Info.plist").write_text("inf0")
    changed = identity.path_digest(bundle)
    (bundle / "Contents/Info.plist").rename(bundle / "Contents/Info2.plist")
    renamed = identity.path_digest(bundle)
    assert len({original, changed, renamed}) == 3
    with pytest.raises(provenance.IntegrityError, match="cannot identify path"):
        identity.path_digest(tmp_path / "absent.vst3")
