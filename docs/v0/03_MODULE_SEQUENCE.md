# V0 Module Sequence

## Dependency graph

```mermaid
flowchart TD
    M00[M00 Bootstrap] --> M01[M01 Schemas]
    M01 --> M02[M02 Store]
    M01 --> M03[M03 PlanGraph]
    M02 --> M03
    M03 --> M04[M04 Renderer]
    M02 --> M05[M05 Retriever]
    M05 --> M06[M06 Precheck]
    M02 --> M07[M07 Recorder]
    M07 --> M08[M08 Distiller + Evals]
    M01 --> M09[M09 MCP Server]
    M02 --> M09
    M03 --> M09
    M04 --> M09
    M05 --> M09
    M06 --> M09
    M07 --> M09
    M08 --> M09
    M09 --> M10[M10 Adapters]
    M08 --> M11[M11 CLI]
    M10 --> M11
    M11 --> G01[G01 Integration]
    G01 --> G02[G02 Delivery]
```

## Parallelism

After M01 and M02 are done, M03/M05/M07 can be done by separate agents. M09 must wait until M01-M08 are done.

## Revision policy

If a downstream module discovers a schema gap, it must:

1. Write a blocker or revision request against M01.
2. Add a proposed schema diff in its handoff.
3. Not patch schemas ad hoc without tests.
