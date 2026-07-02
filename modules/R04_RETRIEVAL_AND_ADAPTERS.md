# R04_RETRIEVAL_AND_ADAPTERS — Strict/best-effort search + bundle-relative adapters

## Agent contract

You are a fresh module implementation agent. Do not rely on prior chat. Read the
state file, claim this module, implement only this module, run acceptance, write
handoff, update state.

## Origin

V0 review (`docs/v0/review.md`), P2 output-correctness fixes:

- **§9 retriever**: `search()` swallows all `DMCError` and returns `[]`, so corrupt
  index / read / FTS errors look like "no results" even for explicit search. Tag
  filtering only inspects `title`/`snippet`/`uri`; `build_context_pack` returns
  `""` for non-positive budgets, masking failures.
- **§8 adapters**: renderer output keys mix bundle-relative (`AGENTS.md`) and
  repo-relative (`.dmc/adapters/<target>/README.md`) paths, so `--out
  .dmc/adapters/copilot` yields nested `.dmc/adapters/copilot/.dmc/adapters/...`.

## Dependencies

- (V0 complete)

## Must-read context

- `docs/v0/review.md` (sections 8, 9; §15 retriever)
- `src/dmc/retriever.py` (`search`, `build_context_pack`, `_attach_provenance`, tag filter)
- `src/dmc/adapters.py` (`render_*_bundle`, `export_agent_bundle`, `default_out_dir`)
- `src/dmc/mcp_server.py` (`dmc_search`), `src/dmc/cli.py` (`search`, export)
- `tests/test_retriever.py`, `tests/test_adapters.py`, `modules/M10_ADAPTERS.md`

## Scope

Make explicit search errors visible and make bundle output paths sane. Preserve
the M10 safety contract (explicit `out_dir` required; no silent root overwrite).

## Required work

1. **Retriever modes.** `search(..., best_effort: bool = False)`: briefing uses
   `best_effort=True` (returns warnings); explicit `dmc_search` / CLI `search`
   default to strict and surface errors in the envelope. Tag filtering reads real
   object metadata. `build_context_pack` with non-positive budget returns a clear
   error / explicit placeholder, not a silent empty string.

   **API shape (decide up front — do not half-change).** `search()` today returns
   `list[SearchResult]`. To carry warnings/errors, EITHER introduce
   `SearchResponse(results, warnings, errors)` and update ALL callers (MCP/CLI/
   tests) together, OR keep `search()` strict + list-returning and add a separate
   `search_best_effort(...) -> SearchResponse`. Do not silently change the return
   type of `search()` while leaving some callers on the old shape.
2. **Adapter paths.** Renderers return bundle-relative keys only (`README.md`,
   `AGENTS.md`, `.codex/config.toml.template`, `.github/copilot-instructions.md` —
   no `.dmc/adapters/<target>/...` prefixes). `export_agent_bundle()` writes
   `out_dir / rel_path` with `out_dir` = bundle root. Any repo-root install stays
   behind an explicit opt-in flag with overwrite protection.

## Acceptance commands

- `uv run pytest tests/test_retriever.py tests/test_adapters.py tests/test_cli.py tests/test_mcp_server.py`
- `uv run pytest`
- `uv run ruff check .`
- `uv run dmc --help`

## Required tests (add)

- strict `search` surfaces a corrupt-index/read error; best-effort returns warnings
- tag filter matches on metadata absent from the snippet
- `test_export_agent_bundle_readme_is_bundle_relative` (no nested `<dir>/.dmc/...`)

## Module-specific forbidden shortcuts

- Do not mask real retrieval errors as "no results" in the explicit search path.
- Do not reintroduce a default that can overwrite the repo's own root files.

## Required handoff

```text
reports/handoffs/R04_RETRIEVAL_AND_ADAPTERS_<attempt_id>.md
reports/acceptance/R04_RETRIEVAL_AND_ADAPTERS_<attempt_id>.md
```

Update `agent_state.json` (module status, reports, changed files, blockers).
