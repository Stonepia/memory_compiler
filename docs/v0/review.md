截至 2026-07-02，我按 GitHub 当前显示的默认分支审了这个仓库；虽然你说的是 `main`，但仓库页面显示当前分支是 `master`，所以以下 review 是针对当前默认分支代码。([GitHub][1])

我先说总判断：**V0 的主体方向是对的，确实完成了一个薄的、local-first 的 DMC sidecar，而不是误做成完整 agent harness / RAG 平台 / repo indexer。** 这一点符合 V0 proposal：V0 目标是做本地 `.dmc` 工作区、durable schemas、project state、trace event、artifact card、precheck、briefing、MCP/CLI 和 adapter bundle，而非云同步、完整 UI、agent harness、向量库或自研 repo graph。

但是，**我不会把现在的 V0 评为“可以放心进入长期使用”的状态**。它更像一个“模块都搭起来了、测试也不少、架构方向没偏”的 V0，但几个核心 contract 还没闭合：`.dmc/skills` / `.dmc/knowledge` 的持久化路径和 store 实现不一致；MCP `briefing/latest` resource 和 `dmc_get_briefing` 工具没有连起来；`dmc_commit_state` 名义上像 patch/commit，实际是 full replace；precheck 的自定义规则接口加载了但不执行；store 的 public path API 有路径逃逸风险；distiller 的 outcome 判断太字符串启发式，容易污染 eval/failure memory。

我没有在本地成功 clone 并跑 `uv run pytest` / `ruff`，因为当前容器对 GitHub 的 DNS 解析失败。所以测试结论我只引用仓库自己的声明：`CHANGELOG` 说 V0 delivery 时 `uv run pytest` 有 286 个测试通过，`uv run ruff check .` 通过，但我没有独立复跑验证。

---

## 1. V0 proposal 覆盖情况

### 总体覆盖：大体完成

V0 的 module sequence 是从 `M00_BOOTSTRAP` 到 `M11_CLI`，其中包括 schema、store、plan graph、renderer、retriever、precheck、recorder、distiller/evals、MCP server、adapters、CLI 和 integration/delivery gates。 `CHANGELOG` 也逐项列出了 M01 到 M11 的实现内容，包括 schemas、local store、plan graph、renderer、retriever、precheck、recorder、distiller/eval-case、MCP server、adapters、CLI。

V0 的交付目标要求这些命令可用：`dmc plan`、`dmc graph`、`dmc brief`、`dmc precheck`、`dmc record`、`dmc distill`、`dmc serve`、`dmc export-agent-bundle`，并要求 MCP server 能注册、基本 resources/prompts 可用。 当前 CLI 里确实有 `plan`、`graph`、`brief`、`precheck`、`record`、`distill`、`serve`、`schemas-export` 和 `export-agent-bundle` 命令。

### 没有明显走偏成“大平台”

这点值得肯定。`pyproject.toml` 依赖很克制：Pydantic、PyYAML、Typer、Rich、MCP SDK，没有引入向量库、web framework、agent runtime、大型 DB 或 profiler parser framework。 `retriever.py` 也明确写了它只做 DMC-owned local retrieval，不做 repo/source-code search，不做 embeddings、vector DB、任意源码索引或 LLM。 这符合 V0 non-goals。

### 主要漏掉/未闭合的 proposal contract

最关键的漏点不是“模块不存在”，而是这些模块之间的 durable contract 没接上：

1. `.dmc/skills` / `.dmc/knowledge` 被 proposal 和 config 当成 source of truth，但 store 实现主要写到 `.dmc/objects/<kind>/...`。
2. MCP `dmc_get_briefing` 只返回 briefing text，不写 `.dmc/briefing.md`；但 `dmc://briefing/latest` resource 又从 `.dmc/briefing.md` 读。
3. `dmc_commit_state` / CLI `state commit` 不是 patch，而是完整 `ProjectState` replace。
4. `load_precheck_rules()` 支持 extra rule 文件，但 `precheck()` 没有执行这些 extra rules。
5. distiller 已经能生成 episode/eval/failure/proposal，但 failure/skill proposal 太模板化，且 outcome 判定容易误标。

下面逐条展开。

---

## 2. P1：`.dmc/skills` / `.dmc/knowledge` 和 store 实现不一致

### 我读到的设计

`.dmc/config.yaml` 明确把 `skills` 和 `knowledge` 作为一等路径：`.dmc/skills`、`.dmc/knowledge`。 V0 架构文档也把 skill、knowledge、episode、project_state、artifact 分成不同对象边界：skill 是可复用 workflow/atom，knowledge 是事实/spec/doc 引用，episode 是 session 后蒸馏出的记录，project_state 是当前状态，artifact 是原始证据。

### 代码实际情况

`DMCStore.write_object()` 把普通对象写到 `.dmc/objects/<kind>/<object_id>.<ext>`，不是 `.dmc/skills` 或 `.dmc/knowledge`。 `read_object()` 对普通 URI 也是去 `.dmc/objects/<kind>` 找；只有 artifact、proposal、project_state、event 有特殊路径。 MCP resource `dmc://skill/tier1/{id}` 和 `dmc://skill/tier2/{id}` 又直接调用 `read_object("dmc://skill/tier1/{id}")` / `read_object("dmc://skill/tier2/{id}")`，这会落到 `.dmc/objects/skill/tier1/<id>.*` 这种路径，而不是 proposal/config 中的 `.dmc/skills/tier1/<id>.yaml`。

### 结论

这是 V0 最大的 contract gap。**skill bank 在 schema、precheck、adapter protocol、MCP resource 里都出现了，但没有作为 `.dmc/skills` source-of-truth 被 store/retriever/resource 正式接起来。**

更严重的是，precheck 会阻止直接编辑 `.dmc/skills/**`，因为它认为 accepted skills 应该走 proposal path。 但 store 本身不读 `.dmc/skills` 作为 canonical skills。结果是：文档要求技能在 `.dmc/skills`，precheck 保护 `.dmc/skills`，MCP resource 又从 `.dmc/objects/skill/...` 读，三者不一致。

### 建议修复

把 skill/knowledge 做成明确的一等 store API，而不是靠 generic object 绕：

```python
store.write_skill(tier: Literal[1,2], card: Tier1Workflow | Tier2Atom)
store.read_skill(tier: Literal[1,2], id: str)
store.list_skills(tier: int | None = None)
store.write_knowledge(ref: KnowledgeRef)
store.read_knowledge(id: str)
```

路径固定为：

```text
.dmc/skills/tier1/<id>.yaml
.dmc/skills/tier2/<id>.yaml
.dmc/knowledge/<id>.yaml
```

然后让：

```text
dmc://skill/tier1/<id>
dmc://skill/tier2/<id>
dmc://knowledge/<id>
```

全部映射到这些路径，并在 `rebuild_index()` 中扫描 `.dmc/skills` 和 `.dmc/knowledge`。现在的 `.dmc/objects` 可以保留给 generic/experimental object，但不要承载核心 durable skill/knowledge contract。

---

## 3. P1：`dmc_get_briefing` 和 `dmc://briefing/latest` 没有闭环

### 我读到的设计

V0 delivery 要求 CLI/MCP 能产生 briefing，`.dmc/briefing.md` 是 delivery artifact 之一。 MCP server 也声明有 `dmc://briefing/latest` resource。

### 代码实际情况

`dmc_get_briefing()` 里会 validate task、生成 plan、做 best-effort context search、render briefing，然后只返回 `{"briefing": text}`。它没有写 `.dmc/briefing.md`。 但 `resource_briefing_latest()` 是硬读 `store.dmc_dir / "briefing.md"`，文件不存在就返回 `"no briefing has been written yet"`。 CLI `brief` 也只有在用户传 `--out` 时才写文件，否则只 stdout。

### 结论

MCP 用户最自然的流程是调用 `dmc_get_briefing`，然后希望 `dmc://briefing/latest` 可读。但当前实现不会发生这个状态转移。**resource 暴露了 latest briefing，但 tool 不维护 latest briefing。**

### 建议修复

最小修复：`dmc_get_briefing(payload, store)` 在成功时写：

```text
.dmc/briefing.md
.dmc/briefings/<timestamp-or-task-id>.md
```

并返回：

```json
{
  "briefing": "...",
  "uri": "dmc://briefing/latest",
  "path": ".dmc/briefing.md"
}
```

更好的修复：新增 `BriefingCard` schema，保存 task_id、plan_id、context result URIs、rendered markdown、created_at。这样 `latest` 不只是一个裸 Markdown 文件。

---

## 4. P1：`dmc_commit_state` 名义像 patch，实际是 full replace

### 我读到的设计

V0 里 project state 是核心对象。架构文档把 project_state 定义为“当前在哪里、下一步是什么、哪些问题未解决”。 V0 delivery 也把 `.dmc/state/project_state.yaml` 作为重要 artifact。

### 代码实际情况

`ProjectState` 目前只有 `name`、`status`、`current_phase`、`summary`、`active_task`、`open_questions`、`updated_at` 等字段。 MCP `dmc_commit_state` 直接把 payload validate 成 `ProjectState`，然后 `upsert_project_state()`，返回 version。 CLI 叫 `state commit`，参数名叫 `patch_file`，但实际同样要求文件是完整 `ProjectState` mapping。

### 结论

这不是 patch，而是 replace/upsert。当前命名会误导 agent：它可能以为可以提交局部 patch，例如新增一个 decision 或 next_action，实际上缺 `name/status` 就会 validate 失败；带了 `name/status` 又会覆盖整个 state。

### 建议修复

二选一：

1. **诚实重命名**：把当前命令叫 `state replace` / `dmc_replace_state`，保留 full-object semantics。
2. **实现 patch contract**：新增 `ProjectStatePatch`，支持 `phase`、`decisions.append`、`open_questions.add/remove`、`next_actions.set`、`evidence_refs`，并返回 diff summary。

建议 V0.1 走第二种，因为 DMC 的核心使用场景是长任务 checkpoint，而不是反复整文件 replace。

---

## 5. P1：precheck 自定义规则“加载了但不执行”

### 我读到的设计

`precheck.py` 的 public API 包含 `load_precheck_rules(store)`，注释说除了 built-ins，如果 store 里有 `.dmc/objects/precheck_rules/` 的 extra rules，会 merge 进来。

### 代码实际情况

`precheck()` 里没有调用 `load_precheck_rules()`。它直接执行五个 hardcoded predicate：failure-mode resemblance、benchmark claim、edit without task ref、direct skill mutation、memory write without evidence。 `_rule_by_id()` 也只在 `BUILTIN_RULES` 里查。 测试只验证 built-in rules 覆盖 required behaviors，没有覆盖“extra rule 能被执行”。

### 结论

这是一个典型的“接口看起来扩展了，但行为没扩展”的问题。它比简单没实现更危险，因为调用者会以为写了 extra precheck rule 就会生效。

### 建议修复

V0.1 有两条路：

如果不打算支持自定义规则，就删除 extra-rule loading，把 `load_precheck_rules()` 明确变成“返回 builtins metadata”。

如果要支持，就定义最小 declarative matcher，例如：

```yaml
id: no-benchmark-without-baseline
decision: warn
when:
  action_contains_any: ["benchmark", "speedup", "perf"]
  missing_context_any: ["baseline_artifact", "benchmark_artifact"]
required_evidence:
  - "dmc://artifact/<baseline>"
```

然后 `precheck()` 先跑 builtins，再跑 loaded declarative rules，并增加测试。

---

## 6. P1：`write_object` / `read_object` 有路径逃逸风险

### 我读到的代码

`write_object()` 只检查 `kind` 和 `object_id` 是非空字符串，没有验证它们是否包含 `..`、斜杠、绝对路径等，然后直接构造：

```python
target = self.objects_dir / kind / f"{object_id}.{norm_ext}"
```

`read_object()` 的 URI regex 允许 `id` 是 `.+`，`_find_object_file()` 直接拼 `directory / f"{obj_id}.{ext}"`。

### 结论

这是本地工具，但仍是 public store API，而且 MCP/CLI 最终会接受外部输入。当前实现可能被传入 `kind="../outside"` 或 `object_id="../../foo"` 之类路径，导致写/读越过预期目录。即使现有高层模型的 ID 大多是 slug，store 层也不应该依赖上层永远正确。

### 建议修复

新增统一路径安全函数：

```python
def _safe_child(base: Path, *parts: str) -> Path:
    target = (base / Path(*parts)).resolve()
    base_resolved = base.resolve()
    if not target.is_relative_to(base_resolved):
        raise DMCValidationError(...)
    return target
```

并且：

```text
kind: 只允许 slug/path whitelist
object_id: 默认 Slug；如需 nested id，逐段校验，不允许 ..、空段、绝对路径
```

`read_object()` 也要同样做 containment check。

---

## 7. P2：distiller 的 outcome 分类太脆弱，容易污染 memory/eval

### 我读到的代码

失败事件通过 outcome string 中是否包含 `fail`、`regress`、`error`、`blocked`、`broke` 判断。成功 validation 则在 `test` / `validate` / `benchmark` phase 中检查 outcome 是否包含 `success`、`passed`、`pass`、`ok`、`green`，且不包含 failure markers。

### 结论

这会误判：

```text
"not passed"      -> 包含 pass，可能被当成功
"not ok"          -> 包含 ok，可能被当成功
"0 failures"      -> 包含 fail，可能被当失败
"expected failure passed" -> 很难分类
"inconclusive"    -> 不清楚
```

DMC 的 memory pollution 风险主要来自这里：一旦 wrong_turn/useful_memory 标错，后续 precheck、proposal、eval 都会被带偏。

### 建议修复

在 `TraceObservation` 里新增显式枚举字段：

```python
status: Literal["success", "failure", "regression", "blocked", "inconclusive"]
```

`outcome` 保留人类可读文本。`is_failure_event()` / `is_success_validation_event()` 优先读 `status`，老数据再 fallback 到字符串启发式。这样既兼容 V0，又避免新事件继续污染。

---

## 8. P2：adapter bundle 输出路径会出现奇怪嵌套

### 我读到的代码

`render_codex_bundle()` 返回的文件包括 `AGENTS.md`、`.codex/config.toml.template`，然后又把 README 放到 `.dmc/adapters/codex/README.md`。 Copilot/OpenCode 也是类似，把 README 作为 `.dmc/adapters/<target>/README.md` 放进 bundle。

`export_agent_bundle()` 会把这些 relative paths 全部写到 `out_dir / rel_path`。 CLI 默认 `out_dir` 是 `.dmc/adapters/generated/<target>`，也允许用户传 `--out`。

### 结论

如果用户传：

```bash
dmc export-agent-bundle --target copilot --out .dmc/adapters/copilot
```

README 会落到：

```text
.dmc/adapters/copilot/.dmc/adapters/copilot/README.md
```

这不是功能崩溃，但明显不是预期 bundle layout。这里属于“文件生成器过度复用 repo-relative 路径”的设计问题。

### 建议修复

让 renderer 返回 bundle-relative paths：

```text
README.md
AGENTS.md
.codex/config.toml.template
.github/copilot-instructions.md
...
```

如果确实要导出到 repo root，再由 CLI 明确提供 `--install-to-root`，并做 overwrite confirmation / dry-run。当前 `out_dir` 语义应该保持为“bundle root”。

---

## 9. P2：retriever 的 filter 和错误处理需要更清楚

### 我读到的代码

`retriever.search()` 会把 unknown scopes 忽略，空 query 返回空列表，这部分可接受。 但它捕获所有 `DMCError` 后直接返回 `[]`。 `dmc_get_briefing` 的 `search_request_results()` 也把 search error 吃掉，返回空 context。

filter 里 `tags` 过滤只看 `title`、`snippet`、`uri`，不读完整对象；如果 tag 没进入 snippet，就可能误过滤。

### 结论

briefing 的 best-effort search 可以吞错误，但显式 `dmc_search` / CLI `search` 不应该把 corrupt index、read_object failure、FTS error 都伪装成“没有结果”。这会让 agent 在 memory 损坏时继续工作，且不知道 context 缺失。

### 建议修复

分两个模式：

```python
search(..., best_effort: bool = False)
```

* briefing 默认 `best_effort=True`，返回 warnings。
* CLI/MCP `dmc_search` 默认 `best_effort=False`，错误进入 envelope/errors。
* `tags` filter 应该在 `_attach_provenance()` 时顺便 attach metadata，或者过滤时读完整 object。

---

## 10. P2：`record_artifact` 保存 absolute file URI，削弱可移植性

### 我读到的设计

V0 成功标准之一是输出不能依赖 hardcoded absolute paths。

### 代码实际情况

`record_artifact()` 复制 raw file 到 `.dmc/artifacts/raw/<card.id>/<filename>`，并写入相对路径 `raw_artifact_path`，这很好；但同时写入 `raw_artifact_uri = dest.resolve().as_uri()`，这是绝对 `file://...` URI。

### 结论

这不是严重 bug，但会让 artifact card 在换机器、移动 repo、共享 `.dmc` 时带着旧机器绝对路径。DMC 的 durable memory 最好只存 stable relative ref。

### 建议修复

保存：

```text
raw_artifact_path: .dmc/artifacts/raw/<id>/<filename>
raw_artifact_uri: dmc://artifact/raw/<id>/<filename>
```

需要打开本地文件时再由 runtime 解析成 `Path`.

---

## 11. P2：architecture 文档提到 `src/dmc/evals.py`，但实现集中在 `distiller.py`

### 我读到的设计

架构文档把 `src/dmc/evals.py` 列为负责 eval cases / regression fixtures / metrics 的模块。 但 M08 module card 的 required API 是 `distill_session()`、`build_episode_card()`、`build_eval_case()`、`propose_failure_modes()`、`propose_skill_updates()`，并没有要求单独 `evals.py`。 当前代码也确实把 eval case generation 放在 `distiller.py`。

### 结论

这是 doc/code drift，不是 runtime blocker。V0 可以接受 `build_eval_case()` 在 `distiller.py` 里，但架构文档不应该继续暗示存在一个 `evals.py`。

### 建议修复

二选一：

```text
A. 更新 docs/v0/02_ARCHITECTURE.md，说明 eval-case generation 属于 distiller.py；
B. 加一个很薄的 evals.py re-export / metrics module。
```

如果下一步要做 continual learning metrics，再加 `evals.py` 更合理；如果 V0 只做 eval-case card，就改文档。

---

## 12. P2：PlanGraph / briefing 目前只是固定流程，不是真正 workflow/atom selection

### 我读到的代码

`planner.py` 明确说 `plan_task` 是 deterministic fixed template，没有 LLM、没有 execution、没有 orchestrator。 `_PLAN_TEMPLATE` 是固定线性链：

```text
brief -> inspect -> plan -> edit -> test -> review -> decide -> distill
```

`plan_task()` 只是把这个模板实例化。

`render_briefing()` 的 “Selected workflows” 来自 plan nodes，而不是 skill bank；“Atoms” 来自 success criteria，而不是 Tier-2 atoms。

### 结论

这在 V0 是可接受的，因为 `CHANGELOG` 也把“planner is deterministic template, not an executing orchestrator”列为 known limitation。 但不能把它宣传成已经完成了真正的 workflow/atom retrieval。当前是“占位式 plan/briefing skeleton”，不是“根据 task 选出 Tier-1/Tier-2 skill pack”。

### 建议修复

V0.1 不需要上 LLM。可以先做 deterministic selector：

```text
task text / mode / hardware / changed_files
  -> match skill.applies_to / tags / trigger_conditions
  -> selected Tier-1 workflows
  -> required Tier-2 atoms
  -> knowledge refs
```

这也会顺手推动前面提到的 `.dmc/skills` store contract 修复。

---

## 13. P2：`dmc_get_briefing` 输出结构比原 MCP contract 简化太多

### 我读到的当前代码

MCP `dmc_get_briefing` 只返回：

```json
{"briefing": "..."}
```

### 结论

这能满足“给人看 Markdown”的 V0，但不太满足“给 coding agent 用的 context pack”这个接口目标。agent 更需要结构化字段，例如 selected workflows、selected atoms、knowledge refs、pitfalls、next actions、provenance。当前这些内容虽然被渲染进 Markdown，但没有以 machine-readable JSON 返回。

### 建议修复

保留 Markdown，同时加结构：

```json
{
  "briefing_markdown": "...",
  "plan_graph": {...},
  "selected_workflows": [...],
  "selected_atoms": [...],
  "knowledge_refs": [...],
  "pitfalls": [...],
  "open_questions": [...],
  "next_actions": [...],
  "provenance": [...]
}
```

短期可以先让 renderer 产出一个 `BriefingData`，再 render Markdown。

---

## 14. P3：CI 缺失是已知限制，但应该补上

`CHANGELOG` 已经把“no CI workflow yet”列为 known limitation。 对 V0 个人项目可以接受，但现在你要做 code review、准备继续迭代，CI 应该补。

最小 GitHub Actions：

```yaml
- uv sync --all-extras --dev
- uv run pytest
- uv run ruff check .
```

再加一个 CLI smoke test：

```bash
uv run dmc plan examples/sample_task.yaml
uv run dmc brief examples/sample_task.yaml
uv run dmc precheck examples/sample_action.yaml
uv run dmc record examples/sample_event.yaml
uv run dmc distill --session <sample-session>
```

---

## 15. 普通 code review：模块级评价

### `schemas.py`

优点：schema 集中，`Slug` / `Uri` / provenance 约束清楚，durable memory objects 要求 non-empty provenance，这个方向对。`TraceEvent` 强制 `session_id`、`event_id`、`phase`、`action.kind`、`observation.outcome` 和 provenance，符合 trace-to-memory 的核心需求。

问题：`ProjectState` 太薄，不足以承载 decisions、next_actions、blocked、evidence、phase history；`Tier1Workflow` / `Tier2Atom` 也太薄，缺少 trigger/applicability、evidence_contract、inputs/outputs、knowledge refs、validation/failure_modes 等字段。现在这些字段可以通过 `extra="allow"` 混进去，但 schema 没把它们变成 first-class contract。

建议：V0.1 把 project state、Tier1/Tier2 skill 的关键字段显式化，而不是都靠 extras。

### `store.py`

优点：local-first 思路清楚，文件是 source of truth，SQLite/FTS5 是可重建 index/cache；append-only events/artifact index 也对。 `rebuild_index()` 能从 events、artifact cards、generic objects、pending proposals、project state 重建索引。

问题：核心 durable layout 和 `.dmc/skills`/`.dmc/knowledge` 不一致；public path API 缺少 containment；artifact index append-only 但 card file 会覆盖同名 artifact，这个行为需要明确是“latest card + append index history”，否则用户会误以为 artifact card 也是 immutable。

建议：加 dedicated skill/knowledge APIs、路径安全、artifact ID collision policy。

### `planner.py`

优点：非常明确地不做 orchestrator，不执行 node，不调用 LLM，fixed template 简单可测。

问题：`store` 参数当前只做类型检查，不参与 plan enrichment。 这没问题，但 API 暗示未来会用 store。现在 `plan_task(request, store)` 和 `plan_task(request, None)` 完全一样，使用者可能误以为有 memory-aware planning。

建议：文档和返回结果中明确 `memory_context_used: false`，或者 V0.1 接上 skill selector。

### `renderer.py`

优点：纯函数、确定性、Markdown/Mermaid 足够轻。

问题：briefing 中 “Selected workflows” 和 “Atoms” 是从 plan skeleton 派生，不是真正 workflow/atom。 这会让用户看到“workflow/atom”字样但实际并没有 skill bank selection。

建议：把 section 名改成 “Plan spine” / “Checks” 直到 skill retrieval 接上；或者接上 `.dmc/skills` 后再保留 workflows/atoms 命名。

### `retriever.py`

优点：明确不做 repo search；scope mapping 和 deterministic ranking 对 V0 合适。

问题：显式 search 不应吞掉所有 DMCError；tags filter 只看 snippet/title/uri 容易误过滤；`build_context_pack` 在 `budget_tokens <= 0` 时返回空字符串，而不是报错或返回明确 placeholder，这可能让调用者误以为 pack 构建成功。

建议：区分 best-effort 和 strict search；让 `build_context_pack` 对非正 budget 返回清晰错误或最小 placeholder envelope。

### `precheck.py`

优点：built-in rules 是 V0 最有价值的模块之一，尤其是 performance claim without artifact、direct skill mutation、memory write without evidence。

问题：extra rules 加载不执行；malformed failure mode 被静默 skip。`_load_failure_modes()` 注释明确说 malformed files are skipped rather than crashing。 对 precheck 来说，跳过损坏 memory 也许避免阻塞，但至少应该返回 warning 或 telemetry，否则长期记忆损坏没人知道。

建议：`match_failure_modes()` 返回 `(matches, errors)` 或 precheck result 增加 `data_warnings`。

### `recorder.py`

优点：action-level event，而不是 transcript-only memory，这个方向非常正确。allowed phases/action kinds 明确。

问题：`TraceAction.kind` schema 是 open string，但 recorder 再收窄 allowed kinds；这会让绕过 recorder 直接 `store.append_event()` 的事件可以带任意 kind。  如果 recorder 是唯一入口，没问题；但 store 是 public API。

建议：要么把 allowed action kind 放进 schema，要么 `DMCStore.append_event()` 也调用 recorder-style validation，避免旁路。

### `distiller.py`

优点：pending proposal only，不直接 mutate accepted skills；durable outputs 都带 provenance。 `distill_session()` 写 episode/eval/failure/proposal 的路径清楚。

问题：proposal 只是“avoid phase/action kind”或“reinforce phase/action kind”，没有真正定位到已有 Tier-1/Tier-2 skill，也没有 add/merge/revise/drop 判断。  这符合 M08 “deterministic/stub distillation”，但还不是 skill lifecycle manager。

建议：V0.1 让 proposal target 从 generic `skill://tier1/avoid-...` 变成可解释匹配结果：

```text
target existing skill if matched
else target new candidate skill
include operation: add | revise | merge | drop_candidate
include why_not_directly_apply
```

### `mcp_server.py`

优点：tool/resource/prompt 列得完整，wrapper 很薄，返回 envelope。

问题：`dmc_export_agent_bundle` 的 docstring 还说 M10 absent 时 lazy fallback，但 M10 已存在；注释可以更新。 更重要的是前面提到的 briefing latest/resource mismatch、skill resource path mismatch。

建议：增加 MCP contract tests，尤其是：

```text
call dmc_get_briefing -> resource dmc://briefing/latest returns same content
write .dmc/skills/tier1/x.yaml -> resource dmc://skill/tier1/x reads it
```

### `cli.py`

优点：thin wrapper，错误从 stderr 出，命令覆盖 V0 delivery。

问题：`state commit patch_file` 命名误导；`graph` 命令没有 `--dmc-root`，虽然它只读 plan file，问题不大；`record` 只能 record event，不能直接 record artifact，虽然 recorder.py 有 `record_artifact()`。

建议：CLI 加：

```text
dmc artifact record <card-file> [--raw path]
dmc state patch <patch-file>
dmc state replace <state-file>
```

---

## 16. 有没有自己造轮子 / 发明不必要的东西？

### 没有严重造轮子

这点我给正面评价。当前没有自研 repo graph、没有自研 code indexer、没有 GraphRAG/LightRAG/RAPTOR、没有 vector DB、没有 agent harness、没有 sandbox、没有 UI。这符合 V0 non-goals。 `retriever.py` 也明确把 repo/code navigation 交给 Serena/GitHub/Sourcegraph/Basic Memory 这类外部 adapters。

### 有几个“小型过度抽象”

1. **precheck extra rules**：接口有了，engine 没有，是 false extensibility。
2. **adapter bundle path**：为了生成 root-relative 文件，导致 bundle-relative 输出变奇怪。
3. **briefing resource**：resource 存在，但生成工具不维护它。
4. **generic object store**：作为基础工具可以，但把 skill/knowledge 也塞进 generic object，会和 `.dmc/skills`/`.dmc/knowledge` contract 冲突。

这些都不是“大重构级别”的问题，但会让 V0 后续使用时出现“看起来有，实际不通”的体验。

---

## 17. 测试覆盖评价

仓库测试覆盖面不差。`tests/test_store.py` 覆盖了初始化、事件 append-only、object roundtrip、project state、artifact card、search、index rebuild、pending proposals rebuild/list/corrupt handling。  `tests/test_precheck.py` 覆盖了 failure-mode resemblance、benchmark claim、edit without task ref、skill mutation block、memory write evidence、determinism、decision precedence。

但我建议补这些测试：

```text
test_mcp_get_briefing_writes_latest_resource
test_skill_resource_reads_dmc_skills_tier1
test_knowledge_scope_reads_dmc_knowledge
test_precheck_extra_rule_actually_fires
test_write_object_rejects_path_traversal
test_read_object_rejects_path_traversal
test_distiller_does_not_mark_not_passed_as_success
test_distiller_does_not_mark_not_ok_as_success
test_record_artifact_uses_portable_dmc_uri
test_export_agent_bundle_readme_is_bundle_relative
test_state_commit_patch_does_not_replace_whole_state
```

---

## 18. 我建议的修复优先级

### 必须在 V0.1 前修

1. **统一 durable layout**：`.dmc/skills`、`.dmc/knowledge`、`.dmc/state`、`.dmc/artifacts`、`.dmc/proposals` 必须和 store/MCP/retriever 一致。
2. **修 `dmc_get_briefing` / `dmc://briefing/latest` 闭环**。
3. **修 `dmc_commit_state` 语义**：要么 rename replace，要么实现 patch。
4. **修 precheck extra rules**：要么删除，要么执行。
5. **加 path containment validation**。

### 应该尽快修

6. **TraceObservation 加 explicit status enum**，避免 memory/eval 污染。
7. **adapter bundle 改 bundle-relative path**。
8. **retriever strict/best-effort 分离**。
9. **artifact raw URI 改 portable DMC URI**。
10. **docs 里 `evals.py` drift 修掉**。

### 可以放到 V0.2

11. 真正的 Tier-1/Tier-2 skill selection。
12. structured briefing JSON。
13. skill proposal add/merge/revise/drop lifecycle。
14. CI + release smoke tests。
15. eval metrics beyond EvalCase generation。

---

## 最终结论

我会把当前 `master` 的 V0 评为：

```text
架构方向：通过
V0 模块覆盖：基本通过
不造大轮子：通过
作为长期 DMC memory substrate：暂不通过，需要 V0.1 修 contract
测试/交付可信度：仓库声明通过，但我未能本地复验
```

最核心的判断是：**这版没有走偏成大而全 agent 平台，这是很好的；但它现在最大的问题是 durable contract 没完全闭合。** DMC 这种项目最怕“memory 看起来写了、resource 看起来有、skill 看起来存在，但下一次 session 读不到正确对象”。所以 V0.1 不应该急着加 LLM distillation、vector search 或 UI，而应该先把 `.dmc` layout、MCP resources、state patch、skill/knowledge store、precheck rule engine、path safety 这些地基打实。

[1]: https://github.com/Stonepia/memory_compiler "GitHub - Stonepia/memory_compiler · GitHub"
