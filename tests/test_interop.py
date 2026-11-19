# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""RO-Crate and PROV exports say what the manifest and ledgers say, and no more."""

import json

import pytest

from vst_bench_ml import cli, interop, provenance

from .scripted_host import render, rows_of


def export(tmp_path, dataset):
    crate, prov = tmp_path / "crate", tmp_path / "prov.json"
    cli.main(["export", "--manifest", str(dataset / "manifest.json"), "--ro-crate", str(crate), "--prov", str(prov)])
    graph = {node["@id"]: node for node in json.loads((crate / "ro-crate-metadata.json").read_text(encoding="utf-8"))["@graph"]}
    return crate, graph, json.loads(prov.read_text(encoding="utf-8"))


def relations(document, kind, left, right):
    return {(item[f"prov:{left}"], item[f"prov:{right}"]) for item in document.get(kind, {}).values()}


def test_crate_files_and_actions_agree_with_the_source_records(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    crate, graph, _ = export(tmp_path, dataset)

    provenance.verify_manifest(crate / "dataset" / "manifest.json")  # the copy is still sealed
    root = graph["./"]
    assert graph["ro-crate-metadata.json"]["conformsTo"] == {"@id": "https://w3id.org/ro/crate/1.1"}
    assert all(root.get(key) for key in ("name", "description", "datePublished", "license"))
    listed = {part["@id"] for part in root["hasPart"]}
    for identity in [*manifest["artifacts"]["outputs"], manifest["artifacts"]["records"],
                     manifest["artifacts"]["failure_ledger"], manifest["artifacts"]["attempt_ledger"]]:
        node = graph["dataset/" + identity["path"]]
        assert (node["sha256"], node["contentSize"]) == (identity["sha256"], str(identity["bytes"]))
        assert node["@id"] in listed and (crate / node["@id"]).is_file()
    assert graph["dataset/manifest.json"]["sha256"] == provenance.sha256_file(dataset / "manifest.json")

    for row in rows_of(dataset):
        action = graph[f"#attempt-{row['attempt_id']}"]
        assert f"Outcome: {row['disposition']}" in action["description"]
        values = {graph[ref["@id"]]["name"].split()[-1]: graph[ref["@id"]]["value"] for ref in action["object"]}
        assert values == row["param_vector"]
        if row["disposition"] == "kept":
            assert graph[action["result"]["@id"]]["sha256"] == row["output"]["sha256"]
        else:
            assert "result" not in action and row["reason"] in action["description"]
    run = graph["#run"]
    assert (run["startTime"], run["endTime"]) == (manifest["observation"]["started_at"], manifest["observation"]["completed_at"])
    assert graph["#sampling-plan"]["value"] == manifest["identities"]["rng"]["plan_sha256"]
    assert graph["#package"]["softwareVersion"] == manifest["identities"]["package"]["version"]


def test_prov_relations_agree_with_the_source_records(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, fail_at=3, silent={"p000000_gate_c2"})
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    rows = rows_of(dataset)
    assert [row["disposition"] for row in rows] == ["kept", "dropped", "kept", "failed", "not_attempted", "not_attempted"]
    _, _, document = export(tmp_path, dataset)

    generated = relations(document, "wasGeneratedBy", "entity", "activity")
    derived = relations(document, "wasDerivedFrom", "generatedEntity", "usedEntity")
    members = relations(document, "hadMember", "collection", "entity")
    assert document["entity"]["data:plan"]["vbm:sha256"] == manifest["identities"]["rng"]["plan_sha256"]
    assert members == {("data:plan", f"data:planned-{row['attempt_id']}") for row in rows}
    for row in rows:
        identifier = row["attempt_id"]
        planned = document["entity"][f"data:planned-{identifier}"]
        assert planned["vbm:disposition"] == row["disposition"]
        assert json.loads(planned["vbm:parameters"]) == row["param_vector"]
        activity = f"data:attempt-{identifier}"
        assert (activity in document["activity"]) == (row["disposition"] != "not_attempted")
        if row["disposition"] == "kept":
            output = f"data:output-{identifier}"
            assert document["entity"][output]["vbm:sha256"] == row["output"]["sha256"]
            assert (output, activity) in generated
            assert (output, f"data:host-audio-{identifier}") in derived
        else:
            assert f"data:output-{identifier}" not in document["entity"]
        if "raw_output" in row:
            assert document["entity"][f"data:host-audio-{identifier}"]["vbm:sha256"] == row["raw_output"]["sha256"]
    outputs = [key for key in document["entity"] if key.startswith("data:output-")]
    assert len(outputs) == manifest["outcomes"]["kept"]
    assert document["activity"]["data:run"]["vbm:status"] == "failed"
    assert document["activity"]["data:attempt-p000001_gate_c2"]["vbm:error_type"] == "RuntimeError"


def test_unknowns_and_reported_values_are_labelled_not_invented(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"))
    _, graph, document = export(tmp_path, dataset)
    assert graph["./"]["license"] == {"@id": "#license-not-stated"}
    assert "author" not in graph["./"] and "not recorded" in graph["#run"]["description"]
    assert "Reported by the host" in graph["#host"]["description"]
    assert graph["#plugin"]["softwareVersion"] == "not recorded"  # this host reported none
    assert document["activity"]["data:run"]["vbm:operator"] == "not recorded"
    assert document["agent"]["data:host"]["vbm:identitySource"] == "host-reported"
    assert document["agent"]["data:package"]["vbm:role"] == "core package"
    assert document["entity"]["data:plugin"]["vbm:identityChecks"] == "no-expected-identities"


def test_v1_dataset_exports_kept_renders_only_and_says_so(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000000_gate_c2"})
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema"] = provenance.SCHEMA_V1
    del manifest["attempts"], manifest["artifacts"]["attempt_ledger"], manifest["identity_checks"]
    (dataset / "attempts.jsonl").unlink()
    provenance.write_manifest(dataset / "manifest.json", manifest)

    _, graph, document = export(tmp_path, dataset)
    assert "schema v1 has no attempt ledger" in graph["#run"]["description"]
    assert "#attempt-p000000_gate_c2" not in graph and "#attempt-p000000_sus_c3" in graph
    assert "schema v1" in document["entity"]["data:plan"]["vbm:attemptCoverage"]
    assert len(document["activity"]) == 1 + manifest["outcomes"]["kept"]


def test_export_refuses_a_broken_dataset_and_an_existing_destination(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"))
    (tmp_path / "prov.json").write_text("{}")
    with pytest.raises(SystemExit, match="destination already exists"):
        cli.main(["export", "--manifest", str(dataset / "manifest.json"), "--prov", str(tmp_path / "prov.json")])
    with pytest.raises(SystemExit, match="choose --ro-crate"):
        cli.main(["export", "--manifest", str(dataset / "manifest.json")])
    (dataset / "records.jsonl").write_text("")
    with pytest.raises(SystemExit, match="mismatch"):
        cli.main(["export", "--manifest", str(dataset / "manifest.json"), "--prov", str(tmp_path / "other.json")])


def test_license_url_replaces_the_unstated_notice(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"))
    graph = interop.ro_crate(interop.load(dataset / "manifest.json"), license="https://creativecommons.org/publicdomain/zero/1.0/")
    nodes = {node["@id"]: node for node in graph["@graph"]}
    assert nodes["./"]["license"] == {"@id": "https://creativecommons.org/publicdomain/zero/1.0/"}
    assert "#license-not-stated" not in nodes


def test_independent_libraries_read_the_exports(tmp_path, monkeypatch):
    """Runs where the optional `interop` extra is installed."""
    prov_model = pytest.importorskip("prov.model")
    rocrate = pytest.importorskip("rocrate.rocrate")
    dataset, _ = render(tmp_path, monkeypatch, silent={"p000001_gate_c2"})
    crate, graph, document = export(tmp_path, dataset)

    parsed = prov_model.ProvDocument.deserialize(str(tmp_path / "prov.json"), format="json")
    kinds = [type(record).__name__ for record in parsed.get_records()]
    assert kinds.count("ProvActivity") == len(document["activity"]) == 7
    assert kinds.count("ProvEntity") == len(document["entity"])
    assert kinds.count("ProvGeneration") == len(document["wasGeneratedBy"])
    assert "wasDerivedFrom(data:output-p000000_sus_c3, data:host-audio-p000000_sus_c3" in parsed.serialize(format="provn")

    loaded = rocrate.ROCrate(str(crate))
    files = {entity.id: entity for entity in loaded.data_entities}
    assert set(files) == {key for key, node in graph.items() if node["@type"] == "File"}
    assert files["dataset/audio/p000000_sus_c3.npz"]["sha256"] == graph["dataset/audio/p000000_sus_c3.npz"]["sha256"]
    assert loaded.root_dataset["license"].id == "#license-not-stated"


def test_dataset_with_extra_files_is_not_exported_and_leaves_nothing_behind(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, arguments=("--n", "1"))
    (dataset / "notes.txt").write_text("extra")
    with pytest.raises(SystemExit, match="unlisted dataset file"):
        cli.main(["export", "--manifest", str(dataset / "manifest.json"), "--ro-crate", str(tmp_path / "crate")])
    assert not (tmp_path / "crate").exists()


def test_unattempted_render_claims_no_instrument(tmp_path, monkeypatch):
    dataset, _ = render(tmp_path, monkeypatch, fail_at=1)
    _, graph, _ = export(tmp_path, dataset)
    assert "instrument" not in graph["#attempt-p000002_gate_c2"]
    assert "instrument" in graph["#attempt-p000000_sus_c3"]
