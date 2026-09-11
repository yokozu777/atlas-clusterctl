# ADR 011 — Jenkins deploy `LIMIT` Active Choices cascade

- **Status:** Accepted (Phase 0–5 — contract + helper + seed map + Active Choices + operator docs + acceptance)
- **Date:** 2026-08-01
- **Deciders:** atlas-clusterctl maintainers
- **Related:** [jenkins-seed.md](../jenkins-seed.md) (`LIMIT` follow-up),
  [jenkins.md](../jenkins.md), [ADR 009](009-unify-run-stage-play.md)
  (`TAGS` / `LIMIT` single-phase), [ADR 010](010-jenkins-phases-active-choices.md)
  (`PHASES` cascade pattern)

## Context

Deploy samples already pass optional Jenkins `LIMIT` through to ansible
`--limit` (ADR 009). Empty omits the flag; non-empty requires a single-phase
`PHASES` window.

Operators want the same UX as `PHASES` ([ADR 010](010-jenkins-phases-active-choices.md)):
when `CLUSTER_ID` changes in Build with Parameters, offer inventory **groups**
and **hosts** that are valid `--limit` targets for that leaf — without typing
names from memory or opening seed Artifacts.

Job DSL alone cannot rewrite param values when the operator later changes
`CLUSTER_ID`. True cascade needs Active Choices (already required for `PHASES`).

Ansible `--limit` accepts host patterns (hosts, groups, and expressions such as
`a:&b`, `~regex`). The checkbox UI can only offer a **catalog** of discrete
names; advanced patterns stay CLI / free-form (out of v1 UI).

## Decision

### Unlock `LIMIT` cascade (mirror ADR 010)

Deploy samples **will** use **Active Choices Reactive** for `LIMIT`, owned by the
seed Job DSL template — same plugin and embed pattern as `PHASES`.

| Topic | Lock |
|-------|------|
| **Plugin** | **Active Choices** (`uno-choice`) — already required for `PHASES` |
| **Parameter shape (target)** | `activeChoiceReactiveParam('LIMIT')` with `choiceType('CHECKBOX')`, `referencedParameter('CLUSTER_ID')` |
| **Empty selection** | No boxes checked → empty `LIMIT` → Run **omits** `--limit` — unchanged |
| **Non-empty** | Checked names joined with `,` → ansible `--limit a,b` (host pattern list) |
| **Catalog membership** | **Groups and hosts** from the leaf inventory file (ADR 003 `hosts` / YAML inventory under the deployable leaf) |
| **List shape (UI)** | Hierarchical Active Choices **value→label** map: for each group with direct hosts (sorted), **group** then its **hosts** (sorted); parent-only groups follow. Labels nest hosts under groups (`▸ group` / `   └ host`). No `g:` / `h:` prefixes. Flat groups-then-hosts remains the CLI default (no `--ui`) |
| **Submitted value SoT** | Checkbox **values** are inventory **group names** / **host keys** (`extract_inventory_groups` / `extract_inventory_hostnames` / limit sections) — never DNS / labels |
| **Host label (display)** | Host key, optionally with inventory `hostname:` as `(hostname: dns)` in the **label only** |
| **Group name SoT** | Inventory group names from `extract_inventory_groups` / limit sections |
| **Data source** | Seed builds an inventory-only UI map (`list_cluster_limits --all --allow-empty --ui` → ordered `[{value,label},…]` per leaf in `cluster-limits.json` / `CLUSTER_LIMITS_JSON`) and embeds a **sandbox-friendly `switch`** into the reactive Groovy at seed time (same footgun fix as `PHASES`: **no `JsonSlurper` at form-render**). Entry lists preserve hierarchy through JSON; plain JSON objects would lose key order |
| **Seed map root** | Inventory `clusters/` only — no `--product-clusters-root` / no live ansible facts |
| **`TAGS` / ADR 009** | **Unchanged** — non-empty `LIMIT` still requires a **single-phase** `PHASES` |
| **`CLUSTER_ID` dropdown** | Remains Jenkins **`choice`** — not Active Choices |
| **UI SoT** | Unchanged — deploy Jenkinsfiles omit Declarative `parameters { }`; seed owns the template |
| **Phase 0 UI (historical)** | Samples shipped `stringParam('LIMIT', '')` until implementation Phase 3 |
| **Phase 3+ UI** | `activeChoiceReactiveParam('LIMIT')` with seed-time `switch` embed |

### Map vs empty `LIMIT`

| Source | Meaning |
|--------|---------|
| **`cluster-limits.json` / helper (seed)** | Static catalog of group + host keys parsed from leaf inventory at seed Build |
| **Deploy empty `LIMIT`** | No `--limit` on `./cluster run` |

The catalog may include names the operator never selects. It is **not** a promise
that every name is reachable after provision, nor that dynamic inventories match.

### Exception to “Not used”

[jenkins-seed.md](../jenkins-seed.md) still lists Active Choices as **not used for
the `CLUSTER_ID` dropdown**. This ADR is an explicit exception for **`LIMIT`**,
alongside [ADR 010](010-jenkins-phases-active-choices.md) for **`PHASES`**.

## Consequences

- Controllers already need `uno-choice` for `PHASES`; `LIMIT` cascade adds no new
  plugin dependency once Phase 3 ships.
- Seed must re-run after inventory host/group changes (embedded switch snapshot).
- Operators cannot pick `&` / `~` / `!` patterns from checkboxes; empty `LIMIT` or
  a future optional free-form param (out of this ADR) would be required.
- Leaves without a usable inventory file yield an empty checkbox list (empty
  `LIMIT` remains valid).

## Out of scope

- Active Choices for `CLUSTER_ID` or `TAGS` (tags cascade = separate ADR).
- Advanced ansible host patterns in the checkbox UI (`&`, `!`, `~`, ranges).
- True nested checkbox widgets (uno-choice `CHECKBOX` is flat; nesting is
  **label indentation** only).
- Using `hostname:` / DNS as the submitted `--limit` value (labels only).
- Live `ansible-inventory` / dynamic inventory / controller-side mirror at form
  render.
- Product-clusters root on the seed job.
- Changing ADR 009 classify / single-phase rules.
- Optional companion `stringParam` for free-form `--limit` (possible later ADR).

## Implementation plan (follow-up Phases 1–5)

| Phase | Work | Status |
|-------|------|--------|
| **0** | This ADR + [jenkins-seed.md](../jenkins-seed.md) `LIMIT` follow-up + gate | **Done** |
| **1** | Helper `list_cluster_limits` + fixture tests | **Done** |
| **2** | Seed writes / archives `cluster-limits.json`; pass JSON into Job DSL | **Done** |
| **3** | DSL: reactive `LIMIT` checkboxes + seed-time `switch` embed | **Done** |
| **4** | Operator docs / troubleshooting (empty UI, IP keys, re-seed) | **Done** |
| **5** | Acceptance (offline gate + live checklist) | **Done** |

## Checklist

- [x] This ADR accepted (Phase 0 contract)
- [x] Normative locks: empty / multi CSV / groups+hosts / hierarchical UI labels /
  host-key value SoT (`hostname:` display-only)
- [x] Form-render = switch only (no JsonSlurper) — learned from ADR 010
- [x] ADR 009 single-phase rule unchanged
- [x] Phase 0 gate: `tests/test_jenkins_seed_limits_param_phase0.py`
- [x] Phase 1 helper: `clusterctl.tools.list_cluster_limits` +
  `tests/test_list_cluster_limits.py` +
  `tests/test_jenkins_seed_limits_param_phase1.py`
- [x] Phase 2 seed map: `cluster-limits.json` + `CLUSTER_LIMITS_JSON` +
  `tests/test_jenkins_seed_limits_param_phase2.py`
- [x] Phase 3 DSL UI: `activeChoiceReactiveParam('LIMIT')` +
  `tests/test_jenkins_seed_limits_param_phase3.py`
- [x] Phase 4 operator docs: jenkins.md + seed README +
  `tests/test_jenkins_seed_limits_param_phase4.py`
- [x] Phase 5 acceptance: offline gate + live checklist —
  `tests/test_jenkins_seed_limits_param_phase5.py`
