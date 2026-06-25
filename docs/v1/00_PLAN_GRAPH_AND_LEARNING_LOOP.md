# V1 PlanGraph and Learning Loop

V1 adds the full loop that the user eventually wants: inspectable graphs, edited graphs, execution traces, and session-derived eval cases.

## V1 loop

```text
TaskRequest
  -> dmc_plan_task
  -> PlanGraph YAML
  -> Mermaid/HTML inspection
  -> human or agent edits graph
  -> agent executes graph nodes
  -> dmc_record_event for each meaningful action
  -> dmc_precheck before risky actions
  -> dmc_commit_state at checkpoints
  -> dmc_distill_session at end
  -> Episode + FailureMode + EvalCase + SkillUpdateProposal
  -> next task retrieves workflows/atoms/pitfalls/eval cases
```

## V1 new objects

```text
PlanGraphVersion
PlanGraphEdit
ExecutionNodeState
UsefulMemoryLabel
WrongTurnLabel
RetrievalEvalCase
GraphReviewReport
```

## V1 acceptance idea

Create two fake sessions:

1. Session A records a wrong turn and produces a failure mode.
2. Session B starts with a similar task and precheck warns before repeating that wrong turn.

V1 passes if the warning is deterministic and provenance links back to Session A.
