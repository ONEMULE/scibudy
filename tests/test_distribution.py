from pathlib import Path

import pytest

from research_mcp import __version__
from research_mcp.cli import cli_main
from research_mcp.install_state import InstallState, load_install_state, save_install_state, update_install_state
from research_mcp.release_manifest import load_release_manifest


def test_release_manifest_loads_defaults(tmp_path):
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(
        """
        {
          "installer_version": "0.2.0",
          "python": {"package_name": "scibudy", "version": "0.2.0", "requirement": "scibudy==0.2.0"}
        }
        """,
        encoding="utf-8",
    )
    manifest = load_release_manifest(manifest_path)
    assert manifest.installer_version == "0.2.0"
    assert manifest.python.package_name == "scibudy"


def test_install_state_round_trip(tmp_path, monkeypatch):
    import research_mcp.install_state as install_state_module

    state_file = tmp_path / "install_state.json"
    monkeypatch.setattr(install_state_module, "INSTALL_STATE_FILE", state_file)
    state = InstallState(install_profile="full", codex_configured=True)
    save_install_state(state)
    loaded = load_install_state()
    assert loaded.install_profile == "full"
    assert loaded.codex_configured is True

    updated = update_install_state(install_profile="base")
    assert updated.install_profile == "base"
    assert state_file.exists()


def test_cli_version_flag(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["scibudy", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        cli_main()

    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_version_command(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["scibudy", "version"])
    cli_main()

    assert __version__ in capsys.readouterr().out
