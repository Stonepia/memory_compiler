"""DMC command-line interface.

Bootstrap (M00) provides only a smoke-testable Typer application. Every
subcommand below is a placeholder that fails with a clear, user-facing error
until its owning module is implemented. This keeps ``dmc --help`` working from
a clean checkout while preventing fake/no-op behavior.
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="dmc",
    help="Dev Memory Compiler: local-first coding-agent memory/context sidecar.",
    no_args_is_help=True,
    add_completion=False,
)

_console = Console(stderr=True)


def _not_implemented(command: str, owning_module: str) -> "typer.Exit":
    """Print a clear error and return a non-zero Exit for an unimplemented command."""
    message = (
        f"`dmc {command}` is not implemented yet. "
        f"It is owned by module {owning_module} and will be available once that "
        f"module is complete."
    )
    _console.print(f"[bold red]NotImplementedError[/bold red]: {message}")
    raise typer.Exit(code=1)


@app.command()
def state(
    action: str = typer.Argument(
        "show", help="State action to perform, e.g. 'show'."
    ),
) -> None:
    """Inspect or update DMC project state (owned by M11_CLI)."""
    _not_implemented(f"state {action}", "M11_CLI")


@app.command()
def plan(
    task_file: str = typer.Argument(..., help="Path to a task YAML file."),
    out: str = typer.Option(None, "--out", help="Output PlanGraph path."),
) -> None:
    """Generate a deterministic PlanGraph from a task (owned by M03_PLAN_GRAPH)."""
    _not_implemented("plan", "M03_PLAN_GRAPH")


@app.command()
def graph(
    plan_file: str = typer.Argument(..., help="Path to a PlanGraph YAML file."),
    format: str = typer.Option("mermaid", "--format", help="Render format."),
    out: str = typer.Option(None, "--out", help="Output path."),
) -> None:
    """Render a PlanGraph to Mermaid/Markdown (owned by M04_RENDERER)."""
    _not_implemented("graph", "M04_RENDERER")


@app.command()
def brief(
    task_file: str = typer.Argument(..., help="Path to a task YAML file."),
    out: str = typer.Option(None, "--out", help="Output briefing path."),
) -> None:
    """Produce a task briefing (owned by M05_RETRIEVER)."""
    _not_implemented("brief", "M05_RETRIEVER")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query."),
    scope: list[str] = typer.Option(
        None, "--scope", help="Scopes to search, e.g. skills, memory."
    ),
) -> None:
    """Search local state, skills, memory, and artifacts (owned by M05_RETRIEVER)."""
    _not_implemented("search", "M05_RETRIEVER")


@app.command()
def precheck(
    action_file: str = typer.Argument(..., help="Path to an action YAML file."),
) -> None:
    """Run deterministic precheck rules over an action (owned by M06_PRECHECK)."""
    _not_implemented("precheck", "M06_PRECHECK")


@app.command()
def record(
    event_file: str = typer.Argument(..., help="Path to an event YAML file."),
) -> None:
    """Record a trace event (owned by M07_RECORDER)."""
    _not_implemented("record", "M07_RECORDER")


@app.command()
def distill(
    session: str = typer.Option(..., "--session", help="Session id to distill."),
) -> None:
    """Distill a session into episode/eval/proposal stubs (owned by M08_DISTILLER_EVALS)."""
    _not_implemented("distill", "M08_DISTILLER_EVALS")


@app.command(name="export-agent-bundle")
def export_agent_bundle(
    target: str = typer.Option(..., "--target", help="Adapter target, e.g. codex."),
    out: str = typer.Option(None, "--out", help="Output directory."),
) -> None:
    """Generate an adapter bundle for a target agent (owned by M10_ADAPTERS)."""
    _not_implemented("export-agent-bundle", "M10_ADAPTERS")


def main() -> None:
    """Console-script entry point for ``dmc``."""
    app()


if __name__ == "__main__":
    main()
