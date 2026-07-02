"""Tests for src/dmc/adapters.py (M10_ADAPTERS).

Positive and negative coverage for the three bundle renderers and the
``export_agent_bundle`` writer: content shape, static/no-dynamic-facts
invariant, disk writes, default output directory resolution via a store-like
object, and invalid-target handling.
"""

from __future__ import annotations

import pytest

from dmc.adapters import (
    VALID_TARGETS,
    export_agent_bundle,
    render_codex_bundle,
    render_copilot_bundle,
    render_opencode_bundle,
)
from dmc.store import DMCStore


# ---------------------------------------------------------------------------
# render_codex_bundle
# ---------------------------------------------------------------------------


def test_render_codex_bundle_expected_files(tmp_path):
    files = render_codex_bundle(tmp_path)
    assert set(files) == {
        "AGENTS.md",
        ".codex/config.toml.template",
        ".dmc/adapters/codex/README.md",
    }
    assert "dmc_plan_task" in files["AGENTS.md"]
    assert "dmc_precheck" in files["AGENTS.md"]
    assert "dmc_distill_session" in files["AGENTS.md"]
    assert "[mcp_servers.dmc]" in files[".codex/config.toml.template"]


def test_render_codex_bundle_is_deterministic(tmp_path):
    assert render_codex_bundle(tmp_path) == render_codex_bundle(tmp_path)


def test_render_codex_bundle_no_dynamic_project_facts(tmp_path):
    files = render_codex_bundle(tmp_path)
    for content in files.values():
        assert str(tmp_path) not in content


# ---------------------------------------------------------------------------
# render_copilot_bundle
# ---------------------------------------------------------------------------


def test_render_copilot_bundle_expected_files(tmp_path):
    files = render_copilot_bundle(tmp_path)
    assert set(files) == {
        ".github/copilot-instructions.md",
        ".github/skills/dmc-start-task/SKILL.md",
        ".dmc/adapters/copilot/README.md",
    }
    assert "dmc_record_event" in files[".github/copilot-instructions.md"]
    skill = files[".github/skills/dmc-start-task/SKILL.md"]
    assert skill.startswith("---\n")
    assert "name: dmc-start-task" in skill
    assert "description:" in skill


def test_render_copilot_bundle_never_mutate_skills_language(tmp_path):
    files = render_copilot_bundle(tmp_path)
    assert "never" in files[".github/copilot-instructions.md"].lower()
    assert "dmc_propose_skill_update" in files[".github/copilot-instructions.md"]


# ---------------------------------------------------------------------------
# render_opencode_bundle
# ---------------------------------------------------------------------------


def test_render_opencode_bundle_expected_files(tmp_path):
    files = render_opencode_bundle(tmp_path)
    assert set(files) == {
        "AGENTS.md",
        "opencode.jsonc.template",
        ".dmc/adapters/opencode/agents/dmc-agent.md",
        ".dmc/adapters/opencode/skills/dmc-start-task/SKILL.md",
        ".dmc/adapters/opencode/README.md",
    }
    assert '"dmc"' in files["opencode.jsonc.template"]
    assert "dmc_get_briefing" in files["AGENTS.md"]


def test_render_opencode_bundle_agent_and_skill_have_frontmatter(tmp_path):
    files = render_opencode_bundle(tmp_path)
    agent = files[".dmc/adapters/opencode/agents/dmc-agent.md"]
    skill = files[".dmc/adapters/opencode/skills/dmc-start-task/SKILL.md"]
    assert agent.startswith("---\n")
    assert skill.startswith("---\n")
    assert "name: dmc-start-task" in skill


# ---------------------------------------------------------------------------
# export_agent_bundle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", VALID_TARGETS)
def test_export_agent_bundle_writes_all_files(tmp_path, target):
    out_dir = tmp_path / "out"
    written = export_agent_bundle(target, out=out_dir, project_root=tmp_path)
    assert written  # non-empty
    for path in written:
        assert path.exists()
        assert path.is_file()
        assert path.is_relative_to(out_dir)


def test_export_agent_bundle_creates_parent_dirs(tmp_path):
    out_dir = tmp_path / "does" / "not" / "exist" / "yet"
    written = export_agent_bundle("copilot", out=out_dir, project_root=tmp_path)
    assert all(p.exists() for p in written)


def test_export_agent_bundle_content_matches_renderer(tmp_path):
    written = export_agent_bundle("codex", out=tmp_path, project_root=tmp_path)
    rendered = render_codex_bundle(tmp_path)
    for rel_path, content in rendered.items():
        assert (tmp_path / rel_path).read_text(encoding="utf-8") == content
    assert len(written) == len(rendered)


def test_export_agent_bundle_invalid_target_raises(tmp_path):
    with pytest.raises(ValueError):
        export_agent_bundle("not-a-real-target", out=tmp_path, project_root=tmp_path)


def test_export_agent_bundle_defaults_out_to_project_root(tmp_path):
    written = export_agent_bundle("codex", project_root=tmp_path)
    assert (tmp_path / "AGENTS.md") in written
    assert (tmp_path / "AGENTS.md").exists()


def test_export_agent_bundle_resolves_root_from_store(tmp_path):
    store = DMCStore(tmp_path)
    store.initialize()
    written = export_agent_bundle("opencode", store=store)
    assert all(p.is_relative_to(tmp_path) for p in written)
    assert (tmp_path / "AGENTS.md").exists()


def test_export_agent_bundle_defaults_root_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    written = export_agent_bundle("codex")
    assert all(p.is_relative_to(tmp_path) for p in written)
