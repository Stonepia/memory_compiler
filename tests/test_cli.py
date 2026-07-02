"""Smoke tests for the DMC bootstrap CLI.

These tests assert that the package imports and that the Typer CLI exposes a
working ``--help`` without crashing. Placeholder subcommands must fail with a
clear, non-zero error until their owning module is implemented.
"""

from __future__ import annotations

from typer.testing import CliRunner

import dmc
from dmc.cli import app

runner = CliRunner()


def test_package_imports_and_has_version() -> None:
    assert isinstance(dmc.__version__, str)
    assert dmc.__version__


def test_cli_help_works() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Dev Memory Compiler" in result.output


def test_placeholder_command_fails_clearly() -> None:
    # A not-yet-implemented command must exit non-zero with a clear message.
    result = runner.invoke(app, ["plan", "examples/sample_task.yaml"])
    assert result.exit_code != 0


def test_export_agent_bundle_writes_files(tmp_path) -> None:
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "export-agent-bundle",
            "--target",
            "codex",
            "--root",
            str(tmp_path),
            "--out",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0
    assert (out_dir / "AGENTS.md").exists()
    assert str(out_dir / "AGENTS.md") in result.output


def test_export_agent_bundle_invalid_target_fails_clearly(tmp_path) -> None:
    result = runner.invoke(
        app, ["export-agent-bundle", "--target", "bogus", "--root", str(tmp_path)]
    )
    assert result.exit_code != 0


def test_export_agent_bundle_without_out_uses_staging_dir_not_root(tmp_path) -> None:
    # A pre-existing root AGENTS.md must never be overwritten by a bundle
    # export that does not pass --out explicitly.
    root_agents = tmp_path / "AGENTS.md"
    root_agents.write_text("do not overwrite me", encoding="utf-8")

    result = runner.invoke(
        app, ["export-agent-bundle", "--target", "codex", "--root", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert root_agents.read_text(encoding="utf-8") == "do not overwrite me"
    staged = tmp_path / ".dmc" / "adapters" / "generated" / "codex" / "AGENTS.md"
    assert staged.exists()
    assert str(staged) in result.output
