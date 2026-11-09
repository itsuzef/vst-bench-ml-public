# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

"""Check wheel installation and native fixture rendering across Python versions.

Build the companion once before invoking this script. Environments and results
must stay outside both source checkouts. Historical hashes are observations,
not the success criterion for ordinary compatible dependency installations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import time


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_paths(build):
    runner_name = "method_fixture_runner.exe" if os.name == "nt" else "method_fixture_runner"
    runners = sorted(build.rglob(runner_name))
    plugins = sorted(build.rglob("MethodFixture.vst3"), key=lambda p: len(p.parts))
    if len(runners) != 1 or not plugins:
        raise RuntimeError(f"Expected one runner and a fixture under {build}")
    return runners[0], plugins[0]


def check(version, args, runner, plugin):
    folder = args.work_dir / version
    folder.mkdir()
    logs = folder / "logs"
    logs.mkdir()
    result = {"requested_python": version, "checks": []}
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)

    def run(command, name, timeout=300):
        started = time.monotonic()
        proc = subprocess.run(
            [str(x) for x in command], env=environment, cwd=args.package_repo,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout,
        )
        (logs / f"{name}.log").write_text(proc.stdout, encoding="utf-8")
        result["checks"].append({
            "command": [str(x) for x in command], "returncode": proc.returncode,
            "seconds": round(time.monotonic() - started, 3), "log": f"logs/{name}.log",
        })
        if proc.returncode:
            print(proc.stdout, flush=True)
            raise RuntimeError(f"{name} exited {proc.returncode}")
        return proc.stdout

    server = None
    try:
        env_dir = folder / "env"
        run([args.uv, "venv", "--seed", "--python", version, env_dir], "create-environment")
        py = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        upgrade_check = (
            sys.platform == "darwin"
            and int(platform.release().split(".")[0]) >= 27
            and version == "3.12"
        )
        if upgrade_check:
            run([py, "-m", "pip", "install", "--only-binary=numpy,scipy",
                 "scipy==1.15.3"], "install-old-scipy")
            result["scipy_before_install"] = run([
                py, "-c", "import importlib.metadata; print(importlib.metadata.version('scipy'))"
            ], "old-scipy-version").strip()
        run([py, "-m", "pip", "install", "--only-binary=numpy,scipy,soundfile,cffi",
             args.wheel, "pytest>=8.4.1,<10"], "install-wheel")
        if upgrade_check:
            run([py, "-c", "from importlib.metadata import version; "
                 "from packaging.version import Version; "
                 "assert Version(version('scipy')) >= Version('1.17.1')"], "scipy-upgraded")
            result["scipy_upgrade_checked"] = True
        result["python"] = run([py, "--version"], "python").strip()
        result["packages"] = json.loads(run([py, "-m", "pip", "list", "--format=json"], "packages"))
        run([py, "-m", "pip", "check"], "dependency-consistency")
        run([py, "-c", "import importlib.metadata, vst_bench_ml; "
             "assert 'site-packages' in vst_bench_ml.__file__; "
             "assert vst_bench_ml.__version__ == importlib.metadata.version('vst-bench-ml')"],
            "installed-wheel-identity")
        run([py, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q",
             args.package_repo / "tests"], "package-tests")
        run([py, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q",
             args.companion_repo / "tests/test_dependencies.py"], "dependency-check-tests")
        run([py, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q",
             args.companion_repo / "tests/test_inventory.py"], "inventory-tests")
        run([py, "-m", "vst_bench_ml.cli", "--help"], "cli")
        run([py, "-m", "vst_bench_ml.cli", "verify", "--help"], "verify-help")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server_log = logs / "host.log"
        with server_log.open("w", encoding="utf-8") as output:
            server = subprocess.Popen([
                str(py), "-B", str(args.companion_repo / "host/server.py"),
                "--runner", str(runner), "--repo-root", str(args.companion_repo),
                "--port", str(port),
            ], env=environment, stdout=output, stderr=subprocess.STDOUT)
            for _ in range(300):
                if "READY" in server_log.read_text(encoding="utf-8"):
                    break
                if server.poll() is not None:
                    raise RuntimeError(server_log.read_text(encoding="utf-8"))
                time.sleep(0.1)
            else:
                raise RuntimeError("Native host readiness timeout")
            dataset = folder / "dataset"
            run([
                py, "-m", "vst_bench_ml.cli", "render", "--plugin", plugin,
                "--param-manifest", args.companion_repo / "fixtures/parameter-manifest.json",
                "--port", port, "--n", "4", "--signals", "sus_c3,gate_c2",
                "--signal-mode", "all", "--seconds", "0.5", "--sr", "44100",
                "--seed-label", "bon-369-v1", "--keep-bad", "--out", dataset,
            ], "render")
            run([py, "-m", "vst_bench_ml.cli", "verify", "--manifest", dataset / "manifest.json"],
                "verify-dataset")
            run([py, "-c", """
import json, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
command = [sys.executable, '-m', 'vst_bench_ml.cli', 'verify', '--manifest', str(root / 'manifest.json')]
def verify(expected, *options):
    result = subprocess.run(command + list(options), capture_output=True, text=True)
    assert (result.returncode == 0) == expected, result.stdout + result.stderr
    return result.stdout + result.stderr
extra = root / 'audio' / 'unlisted.npz'
extra.write_bytes(b'unlisted')
try:
    assert 'unlisted dataset file' in verify(False)
    assert 'listed artifact integrity only' in verify(True, '--allow-extra-files')
finally:
    extra.unlink()
manifest = json.loads((root / 'manifest.json').read_text())
output = root / manifest['artifacts']['outputs'][0]['path']
original = output.read_bytes()
try:
    output.write_bytes(original + b'changed')
    verify(False)
    verify(False, '--allow-extra-files')
    output.unlink()
    verify(False)
    verify(False, '--allow-extra-files')
finally:
    output.write_bytes(original)
verify(True)
print('PASS: added file rejected; explicit opt-out accepted; modified/deleted audio rejected in both modes; restored dataset verified')
""", dataset], "file-inventory-cli")
            manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
            result["outcomes"] = manifest["outcomes"]
            expected = json.loads((args.companion_repo / "fixtures/expected-output.json").read_text())
            if result["outcomes"] != expected["outcomes"]:
                raise RuntimeError(f"Unexpected fixture outcomes: {result['outcomes']}")
            result["outputs"] = [{"path": item["path"], "historical_sha256": item["sha256"],
                                  "actual_sha256": sha256(dataset / item["path"])}
                                 for item in expected["outputs"]]
            result["historical_hash_matches"] = sum(
                x["actual_sha256"] == x["historical_sha256"] for x in result["outputs"]
            )
        result["passed"] = True
    except Exception as exc:
        result.update(passed=False, error=str(exc))
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"python": version, "passed": result["passed"],
                      "error": result.get("error"),
                      "historical_hash_matches": result.get("historical_hash_matches")}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package-repo", "companion-repo", "build-dir", "wheel", "work-dir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--versions", nargs="+", default=["3.11", "3.12", "3.13", "3.14", "3.15"])
    parser.add_argument("--uv", default=shutil.which("uv"))
    args = parser.parse_args()
    for name in ("package_repo", "companion_repo", "build_dir", "wheel", "work_dir"):
        setattr(args, name, getattr(args, name).resolve())
    if not args.uv:
        parser.error("Install uv to provision separate Python interpreters")
    for repo in (args.package_repo, args.companion_repo):
        if args.work_dir == repo or repo in args.work_dir.parents:
            parser.error("Keep environments and results outside source checkouts")
    args.work_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    runner, plugin = native_paths(args.build_dir)
    results = [check(version, args, runner, plugin) for version in args.versions]
    report = {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system": platform.platform(), "architecture": platform.machine(),
        "macos": subprocess.check_output(["sw_vers"], text=True) if sys.platform == "darwin" else None,
        "package_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.package_repo, text=True).strip(),
        "companion_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.companion_repo, text=True).strip(),
        "wheel_sha256": sha256(args.wheel), "runner_sha256": sha256(runner),
        "seconds": round(time.monotonic() - started, 3), "results": results,
        "all_passed": all(x["passed"] for x in results),
    }
    (args.work_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
            output.write(f"### {report['system']} / {report['architecture']}\n\n")
            output.write("| Python | Install, tests, render, verify | Historical file hashes |\n| --- | --- | --- |\n")
            for result in results:
                output.write(f"| {result.get('python', result['requested_python'])} | "
                             f"{'Passed' if result['passed'] else 'FAILED'} | "
                             f"{result.get('historical_hash_matches', '—')}/8 |\n")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
