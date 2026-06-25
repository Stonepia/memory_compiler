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
