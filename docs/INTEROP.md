# RO-Crate and W3C PROV exports

`vst-bench-ml export` projects a verified dataset into two standard provenance
formats. The exports restate the sealed manifest and its ledgers; they add no
facts and are not themselves sealed. The dataset remains the source of truth.

```sh
vst-bench-ml export --manifest output/manifest.json --ro-crate crate --prov prov.json
```

- `--ro-crate DIR` creates a new [RO-Crate 1.1](https://w3id.org/ro/crate/1.1)
  directory: the dataset copied unchanged under `dataset/` (it still passes
  `verify`), and `ro-crate-metadata.json` beside it.
- `--prov FILE` writes a [PROV-JSON](https://www.w3.org/submissions/prov-json/)
  document using PROV-DM terms.
- `--license URL` states the crate's licence. Without it the crate links a notice
  that no licence is stated; rendered audio may fall under the plugin's terms.

Both destinations must not exist yet, and a dataset that fails verification is not
exported.

## Mapping

| Source | RO-Crate 1.1 | PROV |
| --- | --- | --- |
| Manifest, ledgers, each stored output | `File` with `contentSize` and `sha256`, listed in `hasPart` | `data:manifest`, `data:output-<attempt>` entities with `vbm:sha256` |
| The run (start, end, status) | `CreateAction` `#run` | activity `data:run` |
| Each planned attempt and its outcome | `CreateAction` `#attempt-<id>`; status completed, failed or potential; outcome in `description` | entity `data:planned-<id>` (member of the plan) and, if attempted, activity `data:attempt-<id>` |
| Parameter vector | one `PropertyValue` per patch and parameter index, the attempt's `object` | `vbm:parameters` on the planned-attempt entity |
| Kept output | the attempt's `result` | `wasGeneratedBy` the attempt, `wasDerivedFrom` the host audio |
| Audio as received from the host (hash only, not retained) | not represented | entity `data:host-audio-<id>`, `wasAttributedTo` the host |
| Sampling plan digest, parameter-definition digest | `PropertyValue` objects of the run | `prov:Plan` collection; entity `data:parameter-definitions` |
| Package | `SoftwareApplication` `#package` | software agent `data:package`, role `core package` |
| Host and plugin | `SoftwareApplication` `#host`, `#plugin`, described as host-reported | agent `data:host`, entity `data:plugin`, `vbm:identitySource` `host-reported` |
| Identity checks | `PropertyValue` `#identity-checks` | `vbm:identityChecks`, `vbm:packageObservedSha256` on the plugin |

The `vbm:` terms are local attribute names defined by this table. The crate adds
one term to the 1.1 context, `sha256` (`http://schema.org/sha256`).

## What is left unknown

- The person or organization who ran the software is not in the manifest, so the
  crate has no `author` or `publisher` and PROV has no person agent. RO-Crate
  recommends both; a validator reports their absence at the recommended level.
- Host and plugin identities are the host's report unless the identity checks
  compared them; the exports label them and carry the check result.
- A schema v1 dataset has no attempt ledger. Its exports contain kept renders
  only and say so in the run description and on the plan.
- The manifest records when the run completed, not a publication date. The crate's
  required `datePublished` is that completion time.
- Records written by a companion validation workflow outside the core manifest
  (for example its kept-attempt ledger) are not exported.

## Checking an export

The exports were checked with independent tools: `rocrate-validator` (profile
`ro-crate-1.1`, required severity) and `ro-crate-py` for the crate, and the Python
`prov` library (parse PROV-JSON, serialize PROV-N) for PROV. Install them with
`pip install 'vst-bench-ml[interop]'` and run for example:

```sh
rocrate-validator validate -p ro-crate-1.1 -l required crate
python -c "from prov.model import ProvDocument as D; print(D.deserialize('prov.json', format='json').serialize(format='provn'))"
```
