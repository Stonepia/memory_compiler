#!/usr/bin/env bash
set -euo pipefail

uv init --package dmc
uv add pydantic pydantic-settings pyyaml typer rich
uv add --dev pytest ruff
mkdir -p src/dmc tests/golden .dmc/state .dmc/plans/active .dmc/memory/sessions .dmc/memory/episodes .dmc/memory/failure_modes .dmc/memory/eval_cases .dmc/skills/tier0 .dmc/skills/tier1 .dmc/skills/tier2 .dmc/knowledge/{repo,tests,perf,hw,specs} .dmc/artifacts/raw .dmc/proposals/{pending,accepted,rejected} .dmc/adapters/{codex,copilot,opencode} reports/{handoffs,acceptance,integration} examples
