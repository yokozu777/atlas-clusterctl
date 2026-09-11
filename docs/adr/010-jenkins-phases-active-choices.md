# ADR 010 — Jenkins deploy `PHASES` Active Choices cascade (path C)

- **Status:** Accepted
- **Date:** 2026-08-01
- **Deciders:** atlas-clusterctl maintainers
- **Related:** [jenkins-seed.md](../jenkins-seed.md) (`PHASES` follow-up),
  [jenkins.md](../jenkins.md), ADR 008 (`--phases` selector), ADR 009
  (`TAGS` / `LIMIT` single-phase)

## Context

`PHASES` follow-up Phases 0–3 delivered empty = plan SoT and a seed artifact
`cluster-phases.json` (YAML `phases:` short names). Phase 4 originally
**deferred** a reactive UI: Job DSL runs only on seed Build and cannot rewrite
param values when the operator later changes `CLUSTER_ID` in Build with
Parameters.

Operators still expected a phase **list** that updates with `CLUSTER_ID`. That
requires a controller plugin (Active Choices / equivalent), not more Job DSL
alone.

## Decision

### Unlock path C

Deploy samples may use **Active Choices Reactive** for `PHASES`, owned by the
seed Job DSL template (`examples/internal/seed/seed_deploy_jobs.groovy`).

| Topic | Lock |
|-------|------|
| **Plugin** | **Active Choices** (`uno-choice`) on the controller — required for seed samples that cascade `PHASES` |
| **Parameter shape** | `activeChoiceReactiveParam('PHASES')` with `choiceType('CHECKBOX')`, `referencedParameter('CLUSTER_ID')` |
| **Empty selection** | No boxes checked → empty `PHASES` → plan/run **without** `--phases` (**plan SoT**) — unchanged |
| **Non-empty** | Checked short names joined as ADR 008 CSV (`a,b,c`). Single check → `NAME` |
| **Data source** | Seed embeds `CLUSTER_PHASES_JSON` (same inventory-only map as `cluster-phases.json`) into the reactive Groovy script at seed time |
| **Map semantics** | Still YAML `phases:` only (no `when:`); may differ from empty-`PHASES` plan SoT |
| **`start..end`** | **Not** offered in the checkbox UI. Use empty (plan SoT) or multi CSV; inclusive ranges remain CLI / advanced |
| **`TAGS` / `LIMIT`** | Unchanged (ADR 009) — still require a **single** selected NAME |
| **`CLUSTER_ID` dropdown** | Remains Jenkins **`choice`** from Job DSL — **not** Active Choices (CLUSTER_ID Phase 0–5 lock) |
| **UI SoT** | Unchanged — deploy Jenkinsfiles omit Declarative `parameters { }`; seed owns the template |
| **Script Approval** | First seed / first Build-with-Parameters may need In-Process Script Approval for `JsonSlurper` / script body |

### Deploy Pipeline

`envParam` must normalize Active Choices multi-values: if `params.PHASES` is a
`Collection` / array, join with `,` (never Groovy `[a, b]` `toString()`).

### Exception to prior “Not used”

[jenkins-seed.md](../jenkins-seed.md) CLUSTER_ID contract still lists Active
Choices as **not used for the `CLUSTER_ID` dropdown**. This ADR is an explicit
exception for **`PHASES`**. **`LIMIT`** cascade is a sibling exception —
[ADR 011](011-jenkins-limits-active-choices.md).

## Consequences

- Controllers without `uno-choice` fail Job DSL when processing the seed template.
- Seed map refresh still requires a manual seed **Build** after inventory leaf /
  `phases:` changes (embedded JSON is snapshotted at seed time).
- Checkbox UI does not express `start..end`; docs must say so.
- PHASES follow-up Phase 4 deferral is **superseded** by this ADR + sample wiring.

## Out of scope

- Active Choices for `CLUSTER_ID` (or agent labels).
- Fetching live inventory / artifacts from the controller at form-render time
  (map is seed-embedded JSON only).
- Product-clusters root on the seed job (inventory-only map lock unchanged).
- Changing ADR 008 / 009 CLI semantics.

## Implementation

| Piece | Path |
|-------|------|
| Seed DSL | `examples/internal/seed/seed_deploy_jobs.groovy` |
| Seed Pipeline | `examples/internal/seed/Jenkinsfile` (`CLUSTER_PHASES_JSON`) |
| Deploy `envParam` | `examples/internal/Jenkinsfile`, `Jenkinsfile.local` |
| Contract / ops docs | `docs/jenkins-seed.md`, `docs/jenkins.md`, seed README |
| Gate | `tests/test_jenkins_seed_phases_param_phase4.py` (path C **delivered**) |

## Checklist

- [x] This ADR accepted
- [x] Seed embeds map + `activeChoiceReactiveParam('PHASES')`
- [x] Deploy `envParam` joins multi-select safely
- [x] Docs / plugins table list `uno-choice`
- [x] Phase 4 gate asserts cascade present (not deferral)
