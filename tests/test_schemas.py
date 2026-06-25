"""Tests for the DMC schema contract module (M01_SCHEMAS).

Covers positive round-trips and negative validation cases for every required
rule in ``modules/M01_SCHEMAS.md``.
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from dmc import schemas
from dmc.schemas import (
    EXPORTED_MODELS,
    AgentState,
    ArtifactCard,
    EpisodeCard,
    EvalCase,
    EvidenceRef,
    FailureMode,
    KnowledgeRef,
    PlanGraph,
    PlanNode,
    PrecheckRequest,
    PrecheckResult,
    Provenance,
    SearchRequest,
    SearchResult,
    SkillUpdateProposal,
    TaskRequest,
    Tier0Policy,
    Tier1Workflow,
    Tier2Atom,
    TraceEvent,
    export_json_schemas,
)

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Slug / URI primitives
# ---------------------------------------------------------------------------


def _valid_provenance() -> list[dict]:
    return [{"source": "session://sess_demo"}]


@pytest.mark.parametrize("bad_id", ["", " ", "has space", "bad/slash", "-leading", "a b"])
def test_invalid_ids_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        TaskRequest(id=bad_id, task="do a thing")


@pytest.mark.parametrize("good_id", ["task_demo_bmg_perf", "event_demo_001", "M01_SCHEMAS", "a.b-c_1"])
def test_valid_ids_accepted(good_id: str) -> None:
    tr = TaskRequest(id=good_id, task="x")
    assert tr.id == good_id


def test_provenance_accepts_bare_uri_string() -> None:
    prov = Provenance.model_validate("session://sess_demo")
    assert prov.source == "session://sess_demo"


@pytest.mark.parametrize("bad_uri", ["sess_demo", "://nope", "unknownscheme://x", ""])
def test_unknown_uri_scheme_rejected(bad_uri: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(uri=bad_uri)


def test_known_uri_scheme_accepted() -> None:
    assert EvidenceRef(uri="artifact://benchmark/demo").uri == "artifact://benchmark/demo"


# ---------------------------------------------------------------------------
# TaskRequest round-trip from the example file
# ---------------------------------------------------------------------------


def test_task_request_from_sample_yaml() -> None:
    data = yaml.safe_load((REPO_ROOT / "examples" / "sample_task.yaml").read_text())
    tr = TaskRequest.model_validate(data)
    assert tr.id == "task_demo_bmg_perf"
    assert tr.hardware == ["bmg"]
    # round-trip
    assert TaskRequest.model_validate(tr.model_dump()).id == tr.id


# ---------------------------------------------------------------------------
# PlanGraph dependency validation
# ---------------------------------------------------------------------------


def _task() -> TaskRequest:
    return TaskRequest(id="task_demo", task="demo")


def _node(node_id: str, type_: str = "edit", deps: list[str] | None = None) -> PlanNode:
    return PlanNode(
        id=node_id,
        type=type_,
        goal="g",
        dependencies=deps or [],
        success_criteria=["done"],
    )


def test_plan_graph_valid_dependencies() -> None:
    pg = PlanGraph(
        id="plan_demo",
        task=_task(),
        nodes=[
            _node("n1", "brief"),
            _node("n2", "edit", deps=["n1"]),
        ],
    )
    assert len(pg.nodes) == 2


def test_plan_graph_dangling_dependency_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        PlanGraph(
            id="plan_demo",
            task=_task(),
            nodes=[_node("n1", "edit", deps=["ghost"])],
        )
    assert "unknown node" in str(exc.value)


def test_plan_graph_duplicate_node_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanGraph(
            id="plan_demo",
            task=_task(),
            nodes=[_node("n1", "edit"), _node("n1", "test")],
        )


def test_plan_graph_self_dependency_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanGraph(
            id="plan_demo",
            task=_task(),
            nodes=[_node("n1", "edit", deps=["n1"])],
        )


def test_plan_node_invalid_type_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanNode(
            id="n1", type="not_a_phase", goal="x", dependencies=[], success_criteria=[]
        )


def test_plan_graph_missing_nodes_rejected() -> None:
    # `nodes` is required per templates/plan_graph.schema.json.
    with pytest.raises(ValidationError):
        PlanGraph.model_validate({"id": "plan_demo", "task": {"id": "t", "task": "x"}})


def test_plan_node_missing_dependencies_rejected() -> None:
    # `dependencies` is a required field (may be empty list, but must be present).
    with pytest.raises(ValidationError):
        PlanNode.model_validate(
            {"id": "n1", "type": "edit", "goal": "g", "success_criteria": ["done"]}
        )


def test_plan_node_missing_success_criteria_rejected() -> None:
    # `success_criteria` is a required field per the template.
    with pytest.raises(ValidationError):
        PlanNode.model_validate(
            {"id": "n1", "type": "edit", "goal": "g", "dependencies": []}
        )


def test_plan_node_empty_required_lists_allowed() -> None:
    # Present-but-empty lists are valid; only absence is rejected.
    node = PlanNode(
        id="n1", type="edit", goal="g", dependencies=[], success_criteria=[]
    )
    assert node.dependencies == []
    assert node.success_criteria == []



# ---------------------------------------------------------------------------
# TraceEvent validation
# ---------------------------------------------------------------------------


def _event_data() -> dict:
    return yaml.safe_load((REPO_ROOT / "examples" / "sample_event.yaml").read_text())


def test_trace_event_from_sample_yaml() -> None:
    ev = TraceEvent.model_validate(_event_data())
    assert ev.session_id == "sess_demo"
    assert ev.action.kind == "benchmark_run"
    assert ev.observation.outcome == "regressed"


@pytest.mark.parametrize("missing", ["session_id", "event_id", "phase", "timestamp"])
def test_trace_event_missing_required_field_rejected(missing: str) -> None:
    data = _event_data()
    del data[missing]
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(data)


def test_trace_event_missing_action_kind_rejected() -> None:
    data = _event_data()
    data["action"] = {"command": "pytest"}
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(data)


def test_trace_event_missing_observation_outcome_rejected() -> None:
    data = _event_data()
    data["observation"] = {"metrics": {}}
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(data)


def test_trace_event_empty_provenance_rejected() -> None:
    data = _event_data()
    data["provenance"] = []
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(data)


# ---------------------------------------------------------------------------
# Durable memory objects require non-empty provenance
# ---------------------------------------------------------------------------

_DURABLE_CASES = [
    (
        EpisodeCard,
        {"id": "ep1", "session_id": "sess_demo", "summary": "s", "outcome": "ok"},
    ),
    (
        FailureMode,
        {"id": "fm1", "trigger": "t", "description": "d"},
    ),
    (
        SkillUpdateProposal,
        {"id": "sp1", "target": "skill://tier1/x", "change_kind": "update", "rationale": "r"},
    ),
    (
        KnowledgeRef,
        {"id": "k1", "kind": "spec", "uri": "knowledge://specs/x", "summary": "s"},
    ),
    (
        ArtifactCard,
        {"id": "a1", "uri": "artifact://benchmark/demo", "kind": "bench", "summary": "s"},
    ),
]


@pytest.mark.parametrize("model,base", _DURABLE_CASES)
def test_durable_object_requires_provenance(model: type[BaseModel], base: dict) -> None:
    # valid with provenance
    ok = model.model_validate({**base, "provenance": _valid_provenance()})
    assert ok.provenance[0].source == "session://sess_demo"
    # empty provenance rejected
    with pytest.raises(ValidationError):
        model.model_validate({**base, "provenance": []})
    # missing provenance rejected
    with pytest.raises(ValidationError):
        model.model_validate(base)


# ---------------------------------------------------------------------------
# EvalCase
# ---------------------------------------------------------------------------


def _eval_case_data() -> dict:
    return {
        "id": "eval_demo_001",
        "source_session": "sess_demo",
        "task": {"id": "task_demo", "task": "demo"},
        "outcome": {"status": "regressed"},
        "labels": {"hardware": "bmg"},
        "initial_plan_graph": "plan://plan_demo",
        "provenance": _valid_provenance(),
    }


def test_eval_case_valid_round_trip() -> None:
    ec = EvalCase.model_validate(_eval_case_data())
    assert ec.task.id == "task_demo"
    assert ec.initial_plan_graph == "plan://plan_demo"
    assert EvalCase.model_validate(ec.model_dump()).id == "eval_demo_001"


@pytest.mark.parametrize(
    "missing",
    ["task", "outcome", "labels", "provenance", "source_session", "initial_plan_graph"],
)
def test_eval_case_missing_required_part_rejected(missing: str) -> None:
    data = _eval_case_data()
    del data[missing]
    with pytest.raises(ValidationError):
        EvalCase.model_validate(data)


def test_eval_case_missing_plan_refs_rejected() -> None:
    # An EvalCase with no plan reference must be rejected (module card line 66).
    data = _eval_case_data()
    del data["initial_plan_graph"]
    with pytest.raises(ValidationError):
        EvalCase.model_validate(data)



def test_eval_case_empty_provenance_rejected() -> None:
    data = _eval_case_data()
    data["provenance"] = []
    with pytest.raises(ValidationError):
        EvalCase.model_validate(data)


# ---------------------------------------------------------------------------
# Precheck request from sample action
# ---------------------------------------------------------------------------


def test_precheck_request_from_sample_yaml() -> None:
    data = yaml.safe_load((REPO_ROOT / "examples" / "sample_action.yaml").read_text())
    req = PrecheckRequest.model_validate(data)
    assert req.action == "edit"
    assert req.files == ["torch/_inductor/example.py"]


def test_precheck_result_decision_enum() -> None:
    res = PrecheckResult(decision="warn", reasons=["risky"])
    assert res.decision == "warn"
    with pytest.raises(ValidationError):
        PrecheckResult(decision="maybe")


# ---------------------------------------------------------------------------
# Skills, search, project/agent state smoke construction
# ---------------------------------------------------------------------------


def test_skill_tiers_construct() -> None:
    assert Tier0Policy(id="p0", title="t", policy="always cite evidence").tier == 0
    assert Tier1Workflow(id="w1", title="t", steps=["a", "b"]).tier == 1
    assert Tier2Atom(id="a1", title="t", pattern="run X").tier == 2


def test_search_models() -> None:
    SearchRequest(query="bmg", scopes=["skills", "memory"])
    SearchResult(uri="dmc://episode/ep1", score=0.9, kind="episode")


def test_agent_state_loads_repo_file() -> None:
    import json

    data = json.loads((REPO_ROOT / "agent_state.json").read_text())
    state = AgentState.model_validate(data)
    assert "M01_SCHEMAS" in state.modules


# ---------------------------------------------------------------------------
# JSON schema export
# ---------------------------------------------------------------------------


def test_model_json_schema_for_key_models() -> None:
    for model in (PlanGraph, PlanNode, TraceEvent, EvalCase, TaskRequest):
        schema = model.model_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema


def test_generated_schema_required_aligns_with_plan_graph_template() -> None:
    # Top-level PlanGraph must require `nodes` (and id, task) per the template.
    pg = PlanGraph.model_json_schema()
    for field in ("id", "task", "nodes"):
        assert field in pg["required"], f"PlanGraph missing required {field!r}"
    # PlanNode must require dependencies and success_criteria per the template.
    pn = PlanNode.model_json_schema()
    for field in ("id", "type", "goal", "dependencies", "success_criteria"):
        assert field in pn["required"], f"PlanNode missing required {field!r}"


def test_generated_schema_required_aligns_with_trace_event_template() -> None:
    schema = TraceEvent.model_json_schema()
    for field in (
        "event_id",
        "session_id",
        "timestamp",
        "phase",
        "actor",
        "intent",
        "action",
        "observation",
        "provenance",
    ):
        assert field in schema["required"], f"TraceEvent missing required {field!r}"


def test_generated_schema_required_aligns_with_eval_case_template() -> None:
    schema = EvalCase.model_json_schema()
    for field in ("id", "source_session", "task", "outcome", "labels", "provenance"):
        assert field in schema["required"], f"EvalCase missing required {field!r}"
    # Plan ref is required per the module card.
    assert "initial_plan_graph" in schema["required"]



def test_export_json_schemas_writes_files(tmp_path) -> None:
    written = export_json_schemas(tmp_path / "gen")
    assert len(written) == len(EXPORTED_MODELS)
    for path in written:
        assert path.exists()
        assert path.read_text().endswith("\n")


def test_exported_models_cover_all_named_models() -> None:
    # every exported entry is a BaseModel subclass
    for model in EXPORTED_MODELS.values():
        assert issubclass(model, BaseModel)
    assert "plan_graph" in EXPORTED_MODELS
    # module exposes a stable __all__
    assert "PlanGraph" in schemas.__all__
