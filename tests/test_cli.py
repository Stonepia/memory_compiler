"""Tests for the DMC Typer CLI (M11_CLI).

These tests exercise the CLI as the stable user-facing shell for V0: each
command loads/validates input, delegates to a DMC core function, and writes a
result. They assert success paths, clear non-zero failures on bad input, and
that ``--out`` targets create their parent directories.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

import dmc
from dmc.cli import app

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_TASK = str(REPO_ROOT / "examples" / "sample_task.yaml")
SAMPLE_ACTION = str(REPO_ROOT / "examples" / "sample_action.yaml")
SAMPLE_EVENT = str(REPO_ROOT / "examples" / "sample_event.yaml")


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


def test_package_imports_and_has_version() -> None:
    assert isinstance(dmc.__version__, str)
    assert dmc.__version__


def test_cli_help_works() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Dev Memory Compiler" in result.output


# ---------------------------------------------------------------------------
# state show / commit
# ---------------------------------------------------------------------------


def _state_payload() -> dict:
    return {
        "name": "demo-project",
        "status": "in_progress",
        "current_phase": "V0",
        "summary": "wiring the CLI",
    }


def test_state_commit_then_show(tmp_path) -> None:
    patch = tmp_path / "state.yaml"
    patch.write_text(yaml.safe_dump(_state_payload()), encoding="utf-8")

    commit = runner.invoke(
        app, ["state", "commit", str(patch), "--dmc-root", str(tmp_path)]
    )
    assert commit.exit_code == 0, commit.output
    assert "version 1" in commit.output

    show = runner.invoke(app, ["state", "show", "--dmc-root", str(tmp_path)])
    assert show.exit_code == 0, show.output
    assert "demo-project" in show.output


def test_state_show_without_state_fails_clearly(tmp_path) -> None:
    result = runner.invoke(app, ["state", "show", "--dmc-root", str(tmp_path)])
    assert result.exit_code != 0


def test_state_commit_invalid_payload_fails_clearly(tmp_path) -> None:
    patch = tmp_path / "bad.yaml"
    patch.write_text(
        yaml.safe_dump({"summary": "missing name/status"}), encoding="utf-8"
    )
    result = runner.invoke(
        app, ["state", "commit", str(patch), "--dmc-root", str(tmp_path)]
    )
    assert result.exit_code != 0


def test_commit_bumps_version(tmp_path) -> None:
    patch = tmp_path / "state.yaml"
    patch.write_text(yaml.safe_dump(_state_payload()), encoding="utf-8")
    first = runner.invoke(
        app, ["state", "commit", str(patch), "--dmc-root", str(tmp_path)]
    )
    second = runner.invoke(
        app, ["state", "commit", str(patch), "--dmc-root", str(tmp_path)]
    )
    assert "version 1" in first.output
    assert "version 2" in second.output


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


def test_plan_to_stdout() -> None:
    result = runner.invoke(app, ["plan", SAMPLE_TASK])
    assert result.exit_code == 0, result.output
    assert "plan_task_demo_bmg_perf" in result.output


def test_plan_writes_out_and_creates_parents(tmp_path) -> None:
    out = tmp_path / "nested" / "plan.yaml"
    result = runner.invoke(app, ["plan", SAMPLE_TASK, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded["id"] == "plan_task_demo_bmg_perf"


def test_plan_missing_file_fails_clearly(tmp_path) -> None:
    result = runner.invoke(app, ["plan", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0


def test_plan_invalid_task_fails_clearly(tmp_path) -> None:
    bad = tmp_path / "bad_task.yaml"
    bad.write_text(yaml.safe_dump({"repo": "demo"}), encoding="utf-8")  # no id/task
    result = runner.invoke(app, ["plan", str(bad)])
    assert result.exit_code != 0


def test_plan_non_mapping_fails_clearly(tmp_path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text(yaml.safe_dump([1, 2, 3]), encoding="utf-8")
    result = runner.invoke(app, ["plan", str(bad)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def _write_plan(tmp_path) -> Path:
    plan_path = tmp_path / "plan.yaml"
    result = runner.invoke(app, ["plan", SAMPLE_TASK, "--out", str(plan_path)])
    assert result.exit_code == 0, result.output
    return plan_path


def test_graph_mermaid_stdout(tmp_path) -> None:
    plan_path = _write_plan(tmp_path)
    result = runner.invoke(app, ["graph", str(plan_path), "--format", "mermaid"])
    assert result.exit_code == 0, result.output
    assert "flowchart TD" in result.output


def test_graph_markdown_out(tmp_path) -> None:
    plan_path = _write_plan(tmp_path)
    out = tmp_path / "render" / "plan.md"
    result = runner.invoke(
        app, ["graph", str(plan_path), "--format", "markdown", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("# Plan")


def test_graph_bad_format_fails_clearly(tmp_path) -> None:
    plan_path = _write_plan(tmp_path)
    result = runner.invoke(app, ["graph", str(plan_path), "--format", "svg"])
    assert result.exit_code != 0


def test_graph_missing_file_fails_clearly(tmp_path) -> None:
    result = runner.invoke(app, ["graph", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# brief
# ---------------------------------------------------------------------------


def test_brief_stdout(tmp_path) -> None:
    result = runner.invoke(app, ["brief", SAMPLE_TASK, "--dmc-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "# Briefing" in result.output


def test_brief_writes_out(tmp_path) -> None:
    out = tmp_path / "b" / "brief.md"
    result = runner.invoke(
        app, ["brief", SAMPLE_TASK, "--out", str(out), "--dmc-root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_returns_ok_even_when_empty(tmp_path) -> None:
    result = runner.invoke(
        app, ["search", "nothing-here", "--dmc-root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output


def test_search_finds_committed_state(tmp_path) -> None:
    patch = tmp_path / "state.yaml"
    patch.write_text(yaml.safe_dump(_state_payload()), encoding="utf-8")
    runner.invoke(app, ["state", "commit", str(patch), "--dmc-root", str(tmp_path)])

    result = runner.invoke(
        app, ["search", "demo-project", "--dmc-root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "project_state" in result.output


# ---------------------------------------------------------------------------
# precheck
# ---------------------------------------------------------------------------


def test_precheck_sample_action(tmp_path) -> None:
    result = runner.invoke(
        app, ["precheck", SAMPLE_ACTION, "--dmc-root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "decision" in result.output


def test_precheck_writes_out(tmp_path) -> None:
    out = tmp_path / "pc" / "result.yaml"
    result = runner.invoke(
        app,
        ["precheck", SAMPLE_ACTION, "--out", str(out), "--dmc-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_precheck_block_exits_nonzero(tmp_path) -> None:
    # A direct skill-file mutation is a block rule; the CLI signals it distinctly.
    action = tmp_path / "block.yaml"
    action.write_text(
        yaml.safe_dump(
            {
                "action": "edit",
                "files": ["skills/some_skill/SKILL.md"],
                "intent": "rewrite skill directly",
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["precheck", str(action), "--dmc-root", str(tmp_path)]
    )
    assert result.exit_code == 2
    assert "block" in result.output


def test_precheck_missing_file_fails_clearly(tmp_path) -> None:
    result = runner.invoke(
        app, ["precheck", str(tmp_path / "nope.yaml"), "--dmc-root", str(tmp_path)]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# record + distill
# ---------------------------------------------------------------------------


def test_record_then_distill(tmp_path) -> None:
    record = runner.invoke(app, ["record", SAMPLE_EVENT, "--dmc-root", str(tmp_path)])
    assert record.exit_code == 0, record.output
    assert record.output.strip().startswith("dmc://")

    distill = runner.invoke(
        app, ["distill", "--session", "sess_demo", "--dmc-root", str(tmp_path)]
    )
    assert distill.exit_code == 0, distill.output
    assert "sess_demo" in distill.output


def test_record_invalid_event_fails_clearly(tmp_path) -> None:
    bad = tmp_path / "bad_event.yaml"
    bad.write_text(yaml.safe_dump({"event_id": "x"}), encoding="utf-8")
    result = runner.invoke(app, ["record", str(bad), "--dmc-root", str(tmp_path)])
    assert result.exit_code != 0


def test_distill_writes_out(tmp_path) -> None:
    runner.invoke(app, ["record", SAMPLE_EVENT, "--dmc-root", str(tmp_path)])
    out = tmp_path / "d" / "distill.yaml"
    result = runner.invoke(
        app,
        [
            "distill",
            "--session",
            "sess_demo",
            "--out",
            str(out),
            "--dmc-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


# ---------------------------------------------------------------------------
# export-agent-bundle (owned by M10, exercised via the CLI)
# ---------------------------------------------------------------------------


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
