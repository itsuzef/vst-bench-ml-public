# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Create a test-only source tree; never change the supported package metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("destination", type=Path)
args = parser.parse_args()
source = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).decode().split("\0")
args.destination.mkdir(parents=True, exist_ok=False)
for name in filter(None, paths):
    target = args.destination / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / name, target)
metadata = args.destination / "pyproject.toml"
original = metadata.read_text()
assert original.count('requires-python = ">=3.11"') == 1
metadata.write_text(original.replace('requires-python = ">=3.11"', 'requires-python = ">=3.10"'))
receipt = {
    "purpose": "BON-4277 test-only Python 3.10 candidate; not a release or support decision",
    "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
    "only_change": 'requires-python: >=3.11 -> >=3.10; all dependencies unchanged',
    "original_metadata_sha256": hashlib.sha256(original.encode()).hexdigest(),
    "candidate_metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
}
(args.destination.parent / "candidate.json").write_text(json.dumps(receipt, indent=2) + "\n")
