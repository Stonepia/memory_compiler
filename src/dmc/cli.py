"""DMC command-line interface (M11_CLI).

The CLI is the user-facing shell for V0 and the stable interface for the
integration tests. Every command is a thin wrapper: it loads/validates input,
delegates to a DMC core function (schemas, store, planner, renderer, retriever,
precheck, recorder, distiller, adapters), and writes the result. No business
logic lives in the command bodies (see ``modules/M11_CLI.md``).

Conventions shared by all commands:

* The DMC project root defaults to the current working directory and can be
  overridden with ``--dmc-root``; ``.dmc`` is created inside it.
* Commands return a non-zero exit code and print a clear, actionable error to
  stderr on any validation/IO failure.
* File outputs create parent directories. When ``--out`` is omitted, structured
  results are printed to stdout.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console

if TYPE_CHECKING:  # pragma: no cover - typing only
    from dmc.store import DMCStore

app = typer.Typer(
    name="dmc",
    help="Dev Memory Compiler: local-first coding-agent memory/context sidecar.",
    no_args_is_help=True,
    add_completion=False,
)

_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Shared helpers (kept tiny; all real work is delegated to core modules)
# ---------------------------------------------------------------------------


def _fail(message: str, *, kind: str = "Error") -> "typer.Exit":
    """Print a clear error to stderr and raise a non-zero :class:`typer.Exit`."""
    _console.print(f"[bold red]{kind}[/bold red]: {message}")
    raise typer.Exit(code=1)


def _resolve_root(dmc_root: str | None) -> Path:
    """Resolve the DMC project root: explicit ``--dmc-root`` else the cwd."""
    return Path(dmc_root).resolve() if dmc_root else Path.cwd().resolve()


def _store(dmc_root: str | None) -> "DMCStore":
    """Return an initialized :class:`DMCStore` rooted at ``--dmc-root``/cwd."""
    from dmc.store import DMCStore

    store = DMCStore(_resolve_root(dmc_root))
    store.initialize()
    return store


def _load_mapping(path: str) -> dict[str, Any]:
    """Load a YAML/JSON file into a top-level mapping, or fail clearly."""
    import yaml

    p = Path(path)
    if not p.exists():
        raise _fail(f"file not found: {path}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise _fail(f"could not parse {path}: {exc}")
    if not isinstance(data, dict):
        raise _fail(f"{path} must contain a mapping/object at the top level")
    return data


def _emit_structured(data: Any, out: str | None) -> None:
    """Write ``data`` to ``out`` (creating parents) or to stdout.

    Stdout and non-``.json`` files are rendered as human-friendly YAML. When
    ``out`` ends in ``.json`` the file is written as valid JSON instead, so a
    ``--out result.json`` really contains JSON.
    """
    import yaml

    if out:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() == ".json":
            import json

            text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        else:
            text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        target.write_text(text, encoding="utf-8")
        typer.echo(str(target))
    else:
        typer.echo(yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip("\n"))


def _emit_text(text: str, out: str | None) -> None:
    """Write rendered text to ``out`` (creating parents) or to stdout."""
    if out:
        from dmc.renderer import write_rendered

        write_rendered(text, Path(out))
        typer.echo(str(Path(out)))
    else:
        typer.echo(text.rstrip("\n"))


_DMC_ROOT_OPTION = typer.Option(
    None,
    "--dmc-root",
    help="DMC project root (defaults to cwd); '.dmc' is created inside it.",
)


# ---------------------------------------------------------------------------
# state (group): show + commit
# ---------------------------------------------------------------------------

state_app = typer.Typer(
    name="state",
    help="Inspect or update DMC project state.",
    no_args_is_help=True,
)
app.add_typer(state_app)


@state_app.command("show")
def state_show(dmc_root: str = _DMC_ROOT_OPTION) -> None:
    """Print the current project state."""
    from dmc.store import DMCError

    store = _store(dmc_root)
    try:
        state = store.get_project_state()
    except DMCError as exc:
        raise _fail(str(exc))
    _emit_structured(state.model_dump(mode="json"), None)


@state_app.command("commit")
def state_commit(
    patch_file: str = typer.Argument(
        ..., help="Path to a ProjectState YAML/JSON file to commit."
    ),
    dmc_root: str = _DMC_ROOT_OPTION,
) -> None:
    """Commit (upsert) project state from a file and print the new version."""
    from pydantic import ValidationError

    from dmc.schemas import ProjectState
    from dmc.store import DMCError

    payload = _load_mapping(patch_file)
    store = _store(dmc_root)
    try:
        state = ProjectState.model_validate(payload)
        version = store.upsert_project_state(state)
    except (ValidationError, DMCError, ValueError) as exc:
        raise _fail(str(exc))
    typer.echo(f"committed project state version {version}")


# ---------------------------------------------------------------------------
# plan / graph / brief
# ---------------------------------------------------------------------------


@app.command()
def plan(
    task_file: str = typer.Argument(..., help="Path to a task YAML file."),
    out: str = typer.Option(None, "--out", help="Output PlanGraph path."),
    dmc_root: str = _DMC_ROOT_OPTION,
) -> None:
    """Generate a deterministic PlanGraph from a task."""
    from pydantic import ValidationError

    from dmc.planner import plan_task, save_plan_graph
    from dmc.schemas import TaskRequest
    from dmc.store import DMCError

    payload = _load_mapping(task_file)
    store = _store(dmc_root)
    try:
        request = TaskRequest.model_validate(payload)
        graph = plan_task(request, store)
    except (ValidationError, DMCError, ValueError) as exc:
        raise _fail(str(exc))

    if out:
        save_plan_graph(graph, Path(out))
        typer.echo(str(Path(out)))
    else:
        _emit_structured(graph.model_dump(mode="json"), None)


@app.command()
def graph(
    plan_file: str = typer.Argument(..., help="Path to a PlanGraph YAML file."),
    format: str = typer.Option(
        "mermaid", "--format", help="Render format: mermaid or markdown."
    ),
    out: str = typer.Option(None, "--out", help="Output path."),
) -> None:
    """Render a PlanGraph to Mermaid or Markdown."""
    from dmc.planner import load_plan_graph
    from dmc.renderer import render_plan_markdown, render_plan_mermaid
    from dmc.store import DMCError

    fmt = format.lower()
    if fmt not in ("mermaid", "markdown", "md"):
        raise _fail(f"unknown format {format!r}; expected 'mermaid' or 'markdown'")

    try:
        plan_graph = load_plan_graph(Path(plan_file))
        text = (
            render_plan_mermaid(plan_graph)
            if fmt == "mermaid"
            else render_plan_markdown(plan_graph)
        )
    except (DMCError, ValueError, TypeError, OSError) as exc:
        raise _fail(str(exc))

    _emit_text(text, out)


@app.command()
def brief(
    task_file: str = typer.Argument(..., help="Path to a task YAML file."),
    out: str = typer.Option(None, "--out", help="Output briefing path."),
    dmc_root: str = _DMC_ROOT_OPTION,
) -> None:
    """Produce a Markdown task briefing (plan + best-effort local context)."""
    from pydantic import ValidationError

    from dmc.planner import plan_task
    from dmc.renderer import render_briefing
    from dmc.retriever import search as retriever_search
    from dmc.schemas import SearchRequest, TaskRequest
    from dmc.store import DMCError

    payload = _load_mapping(task_file)
    store = _store(dmc_root)
    try:
        request = TaskRequest.model_validate(payload)
        plan_graph = plan_task(request, store)
        try:  # best-effort context; a search failure must not break briefing
            context = retriever_search(SearchRequest(query=request.task), store)
        except (DMCError, ValueError):
            context = []
        text = render_briefing(request, plan_graph, context)
    except (ValidationError, DMCError, ValueError, TypeError) as exc:
        raise _fail(str(exc))

    _emit_text(text, out)


# ---------------------------------------------------------------------------
# search / precheck / record / distill
# ---------------------------------------------------------------------------


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query."),
    scope: list[str] = typer.Option(
        None,
        "--scope",
        help=(
            "Scopes to search (repeatable); defaults to all. One of: "
            "project_state, skills, knowledge, artifacts, episodes, "
            "failure_modes, eval_cases, proposals."
        ),
    ),
    dmc_root: str = _DMC_ROOT_OPTION,
) -> None:
    """Search local state, skills, memory, and artifacts."""
    from pydantic import ValidationError

    from dmc.retriever import search as retriever_search
    from dmc.schemas import SearchRequest
    from dmc.store import DMCError

    store = _store(dmc_root)
    try:
        request = SearchRequest(query=query, scopes=list(scope or []))
        results = retriever_search(request, store)
    except (ValidationError, DMCError, ValueError) as exc:
        raise _fail(str(exc))
    _emit_structured([r.model_dump(mode="json") for r in results], None)


@app.command()
def precheck(
    action_file: str = typer.Argument(..., help="Path to an action YAML file."),
    out: str = typer.Option(None, "--out", help="Output path for the result."),
    dmc_root: str = _DMC_ROOT_OPTION,
) -> None:
    """Run deterministic precheck rules over a proposed action."""
    from pydantic import ValidationError

    from dmc.precheck import precheck as run_precheck
    from dmc.schemas import PrecheckRequest
    from dmc.store import DMCError

    payload = _load_mapping(action_file)
    store = _store(dmc_root)
    try:
        request = PrecheckRequest.model_validate(payload)
        result = run_precheck(request, store)
    except (ValidationError, DMCError, ValueError, TypeError) as exc:
        raise _fail(str(exc))

    _emit_structured(result.model_dump(mode="json"), out)
    if result.decision == "block":
        raise typer.Exit(code=2)


@app.command()
def record(
    event_file: str = typer.Argument(..., help="Path to an event YAML file."),
    dmc_root: str = _DMC_ROOT_OPTION,
) -> None:
    """Record a trace event to the append-only log."""
    from pydantic import ValidationError

    from dmc.recorder import record_event
    from dmc.schemas import TraceEvent
    from dmc.store import DMCError

    payload = _load_mapping(event_file)
    store = _store(dmc_root)
    try:
        event = TraceEvent.model_validate(payload)
        uri = record_event(event, store)
    except (ValidationError, DMCError, ValueError) as exc:
        raise _fail(str(exc))
    typer.echo(uri)


@app.command()
def distill(
    session: str = typer.Option(..., "--session", help="Session id to distill."),
    out: str = typer.Option(None, "--out", help="Output path for the result."),
    dmc_root: str = _DMC_ROOT_OPTION,
) -> None:
    """Distill a session into episode/eval/failure/proposal objects."""
    from pydantic import ValidationError

    from dmc.distiller import distill_session
    from dmc.store import DMCError

    store = _store(dmc_root)
    try:
        result = distill_session(session, store)
    except (ValidationError, DMCError, ValueError) as exc:
        raise _fail(str(exc))
    _emit_structured(result.model_dump(mode="json"), out)


@app.command(name="schemas-export")
def schemas_export(
    out: str = typer.Option(
        ".dmc/generated_schemas", "--out", help="Output directory for JSON schemas."
    ),
) -> None:
    """Export DMC model JSON schemas to a directory (owned by M01_SCHEMAS)."""
    from dmc.schemas import export_json_schemas

    written = export_json_schemas(out)
    typer.echo(f"Wrote {len(written)} schema files to {out}")


@app.command()
def serve(
    root: str = typer.Option(None, "--root", help="DMC project root (defaults to cwd)."),
) -> None:
    """Run the DMC MCP server over stdio (owned by M09_MCP_SERVER)."""
    from dmc.mcp_server import main as serve_main

    serve_main(root)


@app.command(name="export-agent-bundle")
def export_agent_bundle(
    target: str = typer.Option(..., "--target", help="Adapter target, e.g. codex."),
    out: str = typer.Option(
        None,
        "--out",
        help=(
            "Output directory. Defaults to a safe staging directory "
            "(.dmc/adapters/generated/<target>) under --root; never defaults "
            "to --root itself, so existing root files are never overwritten."
        ),
    ),
    root: str = typer.Option(None, "--root", help="DMC project root (defaults to cwd)."),
) -> None:
    """Generate an adapter bundle for a target agent (owned by M10_ADAPTERS)."""
    from dmc.adapters import VALID_TARGETS, default_out_dir
    from dmc.adapters import export_agent_bundle as _export_agent_bundle

    if target not in VALID_TARGETS:
        _console.print(
            f"[bold red]ValueError[/bold red]: unknown adapter target {target!r}; "
            f"expected one of {VALID_TARGETS}"
        )
        raise typer.Exit(code=1)

    project_root = Path(root).resolve() if root is not None else Path.cwd()
    out_dir = Path(out) if out is not None else default_out_dir(project_root, target)
    written = _export_agent_bundle(target, out_dir, project_root=project_root)
    for path in written:
        typer.echo(str(path))


def main() -> None:
    """Console-script entry point for ``dmc``."""
    app()


if __name__ == "__main__":
    main()
