# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Manifest signatures are checked against trust kept outside the dataset."""

import json
import shutil
import subprocess

import pytest

from vst_bench_ml import cli, provenance, signing

from .scripted_host import render

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is not installed")


def make_key(folder, name):
    key = folder / name
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key


@pytest.fixture
def signed(tmp_path, monkeypatch):
    """A rendered, signed dataset plus the producer's trust file kept elsewhere."""
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "2"))
    trust = tmp_path / "trust"
    trust.mkdir()
    key = make_key(trust, "producer")
    allowed = trust / "allowed_signers"
    allowed.write_text(f"producer@example.org {key.with_suffix('.pub').read_text()}")
    cli.main(["sign", "--manifest", str(dataset / "manifest.json"), "--key", str(key)])
    return dataset, trust, allowed


def check(dataset, *options):
    cli.main(["verify", "--manifest", str(dataset / "manifest.json"), *map(str, options)])


def test_authentic_signature_verifies_and_names_the_signer(signed, capsys):
    dataset, _, allowed = signed
    assert (dataset / "manifest.json.sig").read_text().startswith("-----BEGIN SSH SIGNATURE-----")
    check(dataset, "--allowed-signers", allowed)
    assert "signature: valid, signed by producer@example.org" in capsys.readouterr().out
    check(dataset, "--allowed-signers", allowed, "--signer", "producer@example.org")
    with pytest.raises(SystemExit, match="not valid for someone@else"):
        check(dataset, "--allowed-signers", allowed, "--signer", "someone@else")


def test_modified_output_is_rejected(signed):
    dataset, _, allowed = signed
    output = next((dataset / "audio").iterdir())
    output.write_bytes(output.read_bytes() + b"x")
    with pytest.raises(SystemExit, match="artifact size mismatch"):
        check(dataset, "--allowed-signers", allowed)


def test_fully_resealed_dataset_passes_the_digest_but_not_the_signature(signed, capsys):
    dataset, _, allowed = signed
    output = next((dataset / "audio").iterdir())
    output.write_bytes(output.read_bytes() + b"x")
    # Recompute every hash that binds the changed file, then reseal the manifest.
    identity = provenance.file_identity(output, dataset)
    manifest = json.loads((dataset / "manifest.json").read_text())

    def rebind(name):
        path = dataset / name
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if (row.get("output") or {}).get("path") == identity["path"]:
                row["output"] = identity
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        return provenance.file_identity(path, dataset)

    manifest["artifacts"]["records"] = rebind("records.jsonl")
    manifest["artifacts"]["attempt_ledger"] = rebind("attempts.jsonl")
    manifest["artifacts"]["outputs"] = [
        identity if item["path"] == identity["path"] else item for item in manifest["artifacts"]["outputs"]]
    manifest["artifacts"]["outputs_sha256"] = provenance.canonical_sha256(manifest["artifacts"]["outputs"])
    provenance.write_manifest(dataset / "manifest.json", manifest)

    check(dataset)  # internally consistent again: the digest alone cannot tell
    assert "signature: present but not checked" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="manifest signature is not valid for producer@example.org"):
        check(dataset, "--allowed-signers", allowed)


def test_signature_by_an_untrusted_key_is_rejected(signed):
    dataset, trust, allowed = signed
    other = make_key(trust, "other")
    cli.main(["sign", "--manifest", str(dataset / "manifest.json"), "--key", str(other)])
    with pytest.raises(SystemExit, match="not made by any key in the allowed signers file"):
        check(dataset, "--allowed-signers", allowed)
    with pytest.raises(SystemExit, match="not valid for producer@example.org"):
        check(dataset, "--allowed-signers", allowed, "--signer", "producer@example.org")


def test_missing_trust_material_is_rejected(signed, tmp_path, capsys):
    dataset, _, allowed = signed
    with pytest.raises(SystemExit, match="allowed signers file does not exist"):
        check(dataset, "--allowed-signers", tmp_path / "absent")
    with pytest.raises(SystemExit, match="--signer needs --allowed-signers"):
        check(dataset, "--signer", "producer@example.org")
    empty = tmp_path / "empty_signers"
    empty.write_text("")
    with pytest.raises(SystemExit, match="not made by any key"):
        check(dataset, "--allowed-signers", empty)
    (dataset / "manifest.json.sig").unlink()
    with pytest.raises(SystemExit, match="manifest is not signed"):
        check(dataset, "--allowed-signers", allowed)
    check(dataset)
    assert "signature: none" in capsys.readouterr().out


def test_signature_for_another_purpose_is_rejected(signed):
    dataset, trust, allowed = signed
    manifest = dataset / "manifest.json"
    (dataset / "manifest.json.sig").unlink()
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(trust / "producer"), "-n", "file", str(manifest)],
                   check=True, capture_output=True)
    with pytest.raises(SystemExit, match="manifest signature is not valid"):
        check(dataset, "--allowed-signers", allowed)


def test_expected_manifest_digest_anchors_the_dataset(signed, capsys):
    dataset, _, _ = signed
    digest = provenance.sha256_file(dataset / "manifest.json")
    check(dataset, "--expect-manifest-sha256", digest)
    assert "manifest digest: equals the expected SHA-256" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="is not the expected"):
        check(dataset, "--expect-manifest-sha256", "0" * 64)


def test_broken_dataset_is_not_signed(signed):
    dataset, trust, _ = signed
    (dataset / "records.jsonl").write_text("")
    with pytest.raises(SystemExit, match="mismatch"):
        cli.main(["sign", "--manifest", str(dataset / "manifest.json"), "--key", str(trust / "producer")])


def test_signature_file_does_not_break_the_inventory(signed):
    dataset, _, _ = signed
    assert signing.signature_path(dataset / "manifest.json").name == "manifest.json.sig"
    provenance.verify_manifest(dataset / "manifest.json")


def test_dataset_with_unlisted_files_is_not_signed(signed):
    dataset, trust, _ = signed
    (dataset / "notes.txt").write_text("extra")
    with pytest.raises(SystemExit, match="unlisted dataset file"):
        cli.main(["sign", "--manifest", str(dataset / "manifest.json"), "--key", str(trust / "producer")])


def test_failed_signing_keeps_the_previous_signature(signed, tmp_path):
    dataset, _, allowed = signed
    before = (dataset / "manifest.json.sig").read_bytes()
    not_a_key = tmp_path / "not-a-key"
    not_a_key.write_text("this is not a private key")
    with pytest.raises(SystemExit, match="signing failed"):
        cli.main(["sign", "--manifest", str(dataset / "manifest.json"), "--key", str(not_a_key)])
    assert (dataset / "manifest.json.sig").read_bytes() == before
    check(dataset, "--allowed-signers", allowed)


@pytest.mark.parametrize("option", ["--allowed-signers", "--expect-manifest-sha256"])
def test_empty_trust_value_fails_instead_of_skipping_the_check(signed, option):
    dataset, _, _ = signed
    with pytest.raises(SystemExit):
        check(dataset, option, "")


def test_key_listed_under_two_identities_needs_the_signer_named(signed):
    # ssh-keygen reports only the first identity of a key, here one limited to another namespace.
    dataset, trust, allowed = signed
    key = (trust / "producer.pub").read_text()
    allowed.write_text(f'other@example.org namespaces="file" {key}producer@example.org {key}')
    with pytest.raises(SystemExit, match="name it with --signer"):
        check(dataset, "--allowed-signers", allowed)
    check(dataset, "--allowed-signers", allowed, "--signer", "producer@example.org")
