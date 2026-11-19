# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Export a verified dataset's provenance as RO-Crate 1.1 and W3C PROV-JSON.

Both exports are projections of the sealed manifest and its ledgers; they add
no facts. What the manifest does not know stays absent or is labelled: host and
plugin identities are marked ``host-reported``, the person who ran the software
is not named, and a v1 dataset exports kept renders only.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import attempts
from .provenance import IntegrityError, SCHEMA_V1, _read_jsonl, sha256_file, verify_manifest

# The 1.1 context lacks schema.org's sha256 term, so the crate declares it.
RO_CRATE_CONTEXT = ["https://w3id.org/ro/crate/1.1/context", {"sha256": "http://schema.org/sha256"}]
VOCABULARY = "https://github.com/itsuzef/vst-bench-ml-public/blob/main/docs/INTEROP.md#"
UNSTATED_LICENSE = {
    "@id": "#license-not-stated",
    "@type": "CreativeWork",
    "name": "No licence stated",
    "description": (
        "The exporter does not know the terms of this dataset. Rendered audio may be "
        "subject to the plugin's licence; ask the dataset's producer."
    ),
}
STATUS = {
    "kept": "CompletedActionStatus",
    "dropped": "CompletedActionStatus",
    "failed": "FailedActionStatus",
    "not_attempted": "PotentialActionStatus",
}


def load(manifest_path: str | Path) -> dict:
    """Verify the dataset and gather what both exports are built from."""
    path = Path(manifest_path)
    manifest = verify_manifest(path)  # strict: what is exported must itself verify
    root = path.resolve().parent
    artifacts = manifest["artifacts"]
    records = _read_jsonl(root / artifacts["records"]["path"], "records ledger")
    if manifest["schema"] == SCHEMA_V1:
        # v1 has no attempt ledger: only kept renders are known.
        coverage = "kept renders only (schema v1 has no attempt ledger)"
        rows = [
            {
                "attempt_id": attempts.attempt_id(record["patch_id"], record["signal"]),
                "patch_id": record["patch_id"],
                "signal": record["signal"],
                "tier": record.get("tier"),
                "param_vector": {str(k): v for k, v in record.get("param_vector", {}).items()},
                "disposition": "kept",
                "output": record["output"],
            }
            for record in records
        ]
    else:
        coverage = "every planned attempt"
        rows = _read_jsonl(root / artifacts["attempt_ledger"]["path"], "attempt ledger")
    return {
        "path": path,
        "root": root,
        "manifest": manifest,
        "manifest_sha256": sha256_file(path),
        "records": {attempts.attempt_id(r["patch_id"], r["signal"]): r for r in records},
        "rows": rows,
        "coverage": coverage,
    }


def _property(identifier: str, name: str, value, description: str | None = None) -> dict:
    node = {"@id": identifier, "@type": "PropertyValue", "name": name, "value": value}
    if description:
        node["description"] = description
    return node


def ro_crate(source: dict, *, prefix: str = "dataset/", license: str | None = None) -> dict:
    """RO-Crate 1.1 metadata for a crate holding the dataset under ``prefix``."""
    manifest = source["manifest"]
    identities, artifacts = manifest["identities"], manifest["artifacts"]
    graph: list[dict] = []

    def file_node(identity: dict, name: str, encoding: str) -> dict:
        node = {
            "@id": prefix + identity["path"],
            "@type": "File",
            "name": name,
            "contentSize": str(identity["bytes"]),
            "sha256": identity["sha256"],
            "encodingFormat": encoding,
        }
        graph.append(node)
        return {"@id": node["@id"]}

    manifest_file = file_node(
        {"path": source["path"].name, "bytes": source["path"].stat().st_size,
         "sha256": source["manifest_sha256"]},
        "Sealed provenance manifest", "application/json")
    ledgers = [file_node(artifacts["records"], "Records of kept renders", "application/jsonl"),
               file_node(artifacts["failure_ledger"], "Drop and failure events", "application/jsonl")]
    if "attempt_ledger" in artifacts:
        ledgers.append(file_node(artifacts["attempt_ledger"], "Outcome of every planned attempt",
                                 "application/jsonl"))
    outputs = {item["path"]: file_node(item, f"Rendered audio {Path(item['path']).stem}",
                                       "application/x-npz") for item in artifacts["outputs"]}

    package, host, plugin = identities["package"], identities["host"], identities["plugin"]
    reported = "Reported by the host; not independently verified unless the identity checks say so."
    graph += [
        {"@id": "#package", "@type": "SoftwareApplication", "name": package["distribution"],
         "softwareVersion": package["version"],
         "description": "Core orchestration package that sampled parameters and sealed the manifest.",
         "identifier": "sha256:" + package["python_sources_sha256"]},
        {"@id": "#host", "@type": "SoftwareApplication", "name": "Render host",
         "softwareVersion": host["source_commit"], "url": host["source_repository"],
         "description": "Separately installed host that loaded the plugin and rendered audio. " + reported,
         "identifier": "sha256:" + host["executable_sha256"]},
        {"@id": "#plugin", "@type": "SoftwareApplication", "name": plugin["name"],
         "softwareVersion": plugin.get("version", "not recorded"),
         "description": f"Audio plugin ({plugin['format']}) by {plugin['vendor']}, "
                        f"identifier {plugin['identifier']}. " + reported,
         "identifier": "sha256:" + plugin["sha256"]},
        _property("#parameter-definitions", "Parameter definitions",
                  identities["parameters"]["source_sha256"],
                  "SHA-256 of the parameter manifest given to the run; the file is not part of the dataset."),
        _property("#sampling-plan", "Sampling plan", identities["rng"]["plan_sha256"],
                  f"SHA-256 of the {identities['rng'].get('plan_patches', 'recorded')} planned parameter "
                  f"vectors, derived from seed label {identities['rng'].get('seed_label')!r}."),
    ]
    checks = manifest.get("identity_checks")
    if checks:
        compared = sorted({item["subject"] for item in checks["comparisons"]}) or ["nothing"]
        graph.append(_property("#identity-checks", "Identity checks", checks["result"],
                               "Compared: " + ", ".join(compared) + "."))

    actions = []
    parameter_nodes: set[str] = set()  # a patch rendered with several signals shares its parameters
    for row in source["rows"]:
        identifier = row["attempt_id"]
        parameters = []
        for index, value in sorted(row["param_vector"].items(), key=lambda item: int(item[0])):
            node = _property(f"#parameter-{row['patch_id']}-{index}", f"parameter {index}", value,
                             "Normalized value in [0, 1] requested for this parameter index.")
            if node["@id"] not in parameter_nodes:
                parameter_nodes.add(node["@id"])
                graph.append(node)
            parameters.append({"@id": node["@id"]})
        action = {
            "@id": f"#attempt-{identifier}",
            "@type": "CreateAction",
            "name": f"Render attempt {identifier}",
            "description": f"Outcome: {row['disposition']}"
                           + (f" ({row['reason']})" if row.get("reason") else "")
                           + (f" ({row['error_type']} at {row['stage']})" if row.get("stage") else "")
                           + f". MIDI signal {row['signal']}, sampling tier {row['tier']}.",
            "actionStatus": {"@id": "http://schema.org/" + STATUS[row["disposition"]]},
            "object": parameters,
        }
        if row["disposition"] != "not_attempted":  # nothing was used for a render that never began
            action["instrument"] = [{"@id": "#host"}, {"@id": "#plugin"}]
        record = source["records"].get(identifier)
        if row["disposition"] == "kept":
            action["result"] = outputs[row["output"]["path"]]
            if record and record.get("observed_at"):
                action["endTime"] = record["observed_at"]
        graph.append(action)
        actions.append({"@id": action["@id"]})

    observation = manifest["observation"]
    run = {
        "@id": "#run",
        "@type": "CreateAction",
        "name": "Dataset render run",
        "description": f"Attempt coverage in this export: {source['coverage']}. "
                       "The person or agent who started the run is not recorded.",
        "startTime": observation["started_at"],
        "endTime": observation["completed_at"],
        "actionStatus": {"@id": "http://schema.org/"
                         + ("CompletedActionStatus" if observation["status"] == "completed"
                            else "FailedActionStatus")},
        "instrument": [{"@id": "#package"}, {"@id": "#host"}, {"@id": "#plugin"}],
        "object": [{"@id": "#parameter-definitions"}, {"@id": "#sampling-plan"}]
                  + ([{"@id": "#identity-checks"}] if checks else []),
        "result": [manifest_file, *ledgers, *outputs.values()],
    }
    graph.append(run)

    if license is None:
        graph.append(dict(UNSTATED_LICENSE))
    kept = manifest["outcomes"]["kept"]
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": f"{plugin['name']} renders ({kept} kept), sealed by vst-bench-ml",
        "description": f"Audio rendered from {plugin['name']} with sampled parameters, plus the "
                       f"sealed manifest and ledgers under {prefix}. Verify with "
                       f"`vst-bench-ml verify --manifest {prefix}{source['path'].name}`.",
        "datePublished": observation["completed_at"],
        "license": {"@id": license or UNSTATED_LICENSE["@id"]},
        "hasPart": [manifest_file, *ledgers, *outputs.values()],
        "mentions": [{"@id": "#run"}, *actions],
    }
    descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
        "about": {"@id": "./"},
    }
    return {"@context": RO_CRATE_CONTEXT, "@graph": [descriptor, root, *graph]}


def write_ro_crate(manifest_path: str | Path, out_dir: str | Path, *, license: str | None = None) -> Path:
    """Create a crate directory: the dataset copied unchanged, plus the metadata file."""
    source = load(manifest_path)
    out = Path(out_dir)
    if out.exists():
        raise IntegrityError(f"export destination already exists: {out}")
    out.mkdir(parents=True)
    shutil.copytree(source["root"], out / "dataset")
    metadata = out / "ro-crate-metadata.json"
    metadata.write_text(json.dumps(ro_crate(source, license=license), indent=2) + "\n", encoding="utf-8")
    verify_manifest(out / "dataset" / source["path"].name)  # the copy is still a sealed dataset
    return metadata


def prov_document(source: dict) -> dict:
    """W3C PROV-JSON for the run, its attempts, software and outputs."""
    manifest = source["manifest"]
    identities, observation = manifest["identities"], manifest["observation"]
    package, host, plugin = identities["package"], identities["host"], identities["plugin"]
    doc: dict[str, dict] = {
        "prefix": {"vbm": VOCABULARY, "data": f"urn:vst-bench-ml:{source['manifest_sha256']}:"},
        "entity": {}, "activity": {}, "agent": {}, "wasGeneratedBy": {}, "used": {},
        "wasAssociatedWith": {}, "wasAttributedTo": {}, "wasDerivedFrom": {},
        "wasInformedBy": {}, "hadMember": {},
    }

    def relate(kind: str, **fields) -> None:
        doc[kind][f"_:{kind}{len(doc[kind])}"] = {f"prov:{key}": value for key, value in fields.items()}

    doc["agent"]["data:package"] = {
        "prov:type": {"$": "prov:SoftwareAgent", "type": "prov:QUALIFIED_NAME"},
        "prov:label": f"{package['distribution']} {package['version']}",
        "vbm:role": "core package", "vbm:sourcesSha256": package["python_sources_sha256"],
    }
    doc["agent"]["data:host"] = {
        "prov:type": {"$": "prov:SoftwareAgent", "type": "prov:QUALIFIED_NAME"},
        "prov:label": "render host", "vbm:role": "separately installed host",
        "vbm:identitySource": "host-reported", "vbm:sourceRepository": host["source_repository"],
        "vbm:sourceCommit": host["source_commit"], "vbm:executableSha256": host["executable_sha256"],
    }
    doc["entity"]["data:plugin"] = {
        "prov:label": plugin["name"], "vbm:vendor": plugin["vendor"],
        "vbm:identifier": plugin["identifier"], "vbm:sha256": plugin["sha256"],
        "vbm:version": plugin.get("version", "not recorded"), "vbm:identitySource": "host-reported",
    }
    checks = manifest.get("identity_checks")
    if checks:
        doc["entity"]["data:plugin"]["vbm:packageObservedSha256"] = checks["package_observed"]["plugin_sha256"]
        doc["entity"]["data:plugin"]["vbm:identityChecks"] = checks["result"]
    doc["entity"]["data:parameter-definitions"] = {
        "prov:label": "parameter definitions (not part of the dataset)",
        "vbm:sha256": identities["parameters"]["source_sha256"],
    }
    doc["entity"]["data:plan"] = {
        "prov:type": [{"$": "prov:Plan", "type": "prov:QUALIFIED_NAME"},
                      {"$": "prov:Collection", "type": "prov:QUALIFIED_NAME"}],
        "prov:label": "sampling plan", "vbm:sha256": identities["rng"]["plan_sha256"],
        "vbm:seedLabel": str(identities["rng"].get("seed_label")),
        "vbm:attemptCoverage": source["coverage"],
    }
    doc["entity"]["data:manifest"] = {
        "prov:label": source["path"].name, "vbm:sha256": source["manifest_sha256"],
        "vbm:schema": manifest["schema"],
    }
    doc["activity"]["data:run"] = {
        "prov:startTime": observation["started_at"], "prov:endTime": observation["completed_at"],
        "prov:label": "dataset render run", "vbm:status": observation["status"],
        "vbm:operator": "not recorded",
    }
    relate("wasAssociatedWith", activity="data:run", agent="data:package", plan="data:plan")
    relate("used", activity="data:run", entity="data:parameter-definitions")
    relate("wasGeneratedBy", entity="data:plan", activity="data:run")
    relate("wasDerivedFrom", generatedEntity="data:plan", usedEntity="data:parameter-definitions")
    relate("wasGeneratedBy", entity="data:manifest", activity="data:run", time=observation["completed_at"])
    relate("wasAttributedTo", entity="data:manifest", agent="data:package")

    for row in source["rows"]:
        identifier = row["attempt_id"]
        planned = f"data:planned-{identifier}"
        doc["entity"][planned] = {
            "prov:label": f"planned attempt {identifier}", "vbm:patch": row["patch_id"],
            "vbm:signal": row["signal"], "vbm:tier": str(row["tier"]),
            "vbm:disposition": row["disposition"],
            "vbm:parameters": json.dumps(row["param_vector"], sort_keys=True),
        }
        relate("hadMember", collection="data:plan", entity=planned)
        if row["disposition"] == "not_attempted":
            continue
        activity = f"data:attempt-{identifier}"
        doc["activity"][activity] = {"prov:label": f"render attempt {identifier}",
                                     "vbm:disposition": row["disposition"]}
        for key in ("reason", "stage", "error_type"):
            if row.get(key):
                doc["activity"][activity][f"vbm:{key}"] = row[key]
        relate("wasInformedBy", informed=activity, informant="data:run")
        relate("used", activity=activity, entity=planned)
        relate("used", activity=activity, entity="data:plugin")
        relate("wasAssociatedWith", activity=activity, agent="data:host")
        raw = None
        if "raw_output" in row:
            raw = f"data:host-audio-{identifier}"
            doc["entity"][raw] = {"prov:label": f"audio received from the host for {identifier}",
                                  "vbm:sha256": row["raw_output"]["sha256"],
                                  "vbm:bytes": row["raw_output"]["bytes"],
                                  "vbm:retained": "no"}
            relate("wasGeneratedBy", entity=raw, activity=activity)
            relate("wasAttributedTo", entity=raw, agent="data:host")
        if row["disposition"] == "kept":
            output = f"data:output-{identifier}"
            doc["entity"][output] = {"prov:label": row["output"]["path"],
                                     "vbm:sha256": row["output"]["sha256"],
                                     "vbm:bytes": row["output"]["bytes"]}
            record = source["records"].get(identifier, {})
            relate("wasGeneratedBy", entity=output, activity=activity,
                   **({"time": record["observed_at"]} if record.get("observed_at") else {}))
            relate("wasAttributedTo", entity=output, agent="data:package")
            if raw:
                relate("wasDerivedFrom", generatedEntity=output, usedEntity=raw)
    return {key: value for key, value in doc.items() if value}


def write_prov(manifest_path: str | Path, out_file: str | Path) -> Path:
    out = Path(out_file)
    if out.exists():
        raise IntegrityError(f"export destination already exists: {out}")
    out.write_text(json.dumps(prov_document(load(manifest_path)), indent=2) + "\n", encoding="utf-8")
    return out
