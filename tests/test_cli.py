import pytest

from vst_bench_ml import cli


def test_top_level_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "render" in capsys.readouterr().out


def test_render_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["render", "--help"])
    assert exc.value.code == 0
    assert "--param-manifest" in capsys.readouterr().out


def test_render_rejects_missing_manifest(tmp_path):
    with pytest.raises(SystemExit, match="parameter manifest does not exist"):
        cli.main(
            [
                "render",
                "--plugin",
                str(tmp_path / "example.vst3"),
                "--param-manifest",
                str(tmp_path / "missing.json"),
                "--out",
                str(tmp_path / "out"),
            ]
        )


def test_render_rejects_invalid_signal(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"params": [{"index": 0, "name": "Gain", "type": "float"}]}')
    with pytest.raises(SystemExit, match="unknown signals"):
        cli.main(
            [
                "render",
                "--plugin",
                str(tmp_path / "example.vst3"),
                "--param-manifest",
                str(manifest),
                "--out",
                str(tmp_path / "out"),
                "--signals",
                "not-a-signal",
            ]
        )


def test_render_rejects_duplicate_signals(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"params": [{"index": 0, "name": "Gain", "type": "float"}]}')
    with pytest.raises(SystemExit, match="duplicate signals"):
        cli.main(
            [
                "render",
                "--plugin",
                str(tmp_path / "example.vst3"),
                "--param-manifest",
                str(manifest),
                "--out",
                str(tmp_path / "out"),
                "--signals",
                "sus_c3,sus_c3",
            ]
        )
