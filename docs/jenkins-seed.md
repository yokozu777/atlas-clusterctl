# Jenkins seed job — `CLUSTER_ID` choice (contract)

> **CLUSTER_ID Phase 0–5 done (2026-08-01).** Normative contract for a **manual**
> seed job that refreshes the deploy Pipeline’s `CLUSTER_ID` dropdown. Samples:
> [`examples/internal/seed/`](../examples/internal/seed/). Deploy samples omit
> Declarative `parameters {}` (UI SoT = seed):
> [`examples/internal/Jenkinsfile`](../examples/internal/Jenkinsfile) /
> [`Jenkinsfile.local`](../examples/internal/Jenkinsfile.local). Operator overview:
> [jenkins.md](jenkins.md). Separate tracks: [PHASES follow-up](#follow-up-phases-parameter-contract),
> [LIMIT follow-up](#follow-up-limits-parameter-contract).

## Goal

When the operator opens **Build with Parameters** on the deploy job, `CLUSTER_ID`
is a **choice** list of deployable inventory leaves — without Active Choices,
without a controller inventory mirror for UI, and without waiting for a prior
deploy run to “learn” parameters.

## Decision (normative)

| Topic | Lock |
|-------|------|
| Mechanism | **Seed job** + **Job DSL** (or equivalent job-config API) updates deploy-job parameter `CLUSTER_ID` as Jenkins **`choice`** |
| Trigger | **Manual Build only** — no cron, no inventory webhook (automation = later, out of Phase 0–5 scope) |
| Not used | Active Choices / Extensible Choice for the **`CLUSTER_ID` dropdown**; controller-side inventory mirror solely for that dropdown. (**Exceptions:** `PHASES` cascade — [ADR 010](adr/010-jenkins-phases-active-choices.md) **delivered**; `LIMIT` cascade — [ADR 011](adr/011-jenkins-limits-active-choices.md) **delivered**) |
| UI SoT | Seed / DSL owns deploy-job **parameter definitions** (full template, including `CLUSTER_ID` choices). Deploy Jenkinsfile must **not** declare `parameters { }` (and must **not** redeclare `string(name: 'CLUSTER_ID')`) — Declarative would reset UI after a deploy run |
| Empty scan | Seed **fails**; must **not** overwrite existing `choices` with an empty list |
| Other params | Seed applies a **full parameter template** (preserve `TAGS`, `LIMIT`, `EXTRA_VARS`, inventory git fields, booleans, …) — not a lone replace of `CLUSTER_ID` that drops siblings |

### Job naming (convention)

| Role | Suggested Jenkins job name | Script / config |
|------|----------------------------|-----------------|
| Seed | `atlas-clusterctl-seed` | `examples/internal/seed/Jenkinsfile` |
| Deploy (Docker agent sample) | `atlas-clusterctl` (org-local) | `examples/internal/Jenkinsfile` |
| Deploy (bare agent sample) | `atlas-clusterctl-local` (org-local) | `examples/internal/Jenkinsfile.local` |

Orgs may rename jobs; seed must target the **configured** deploy job name(s) via
seed parameters (`DEPLOY_SPECS`) or DSL constants.

### Operator workflow

Crisp copy for operators also lives in [jenkins.md](jenkins.md) (**Operator
workflow**) and [`examples/internal/seed/README.md`](../examples/internal/seed/README.md).

| Moment | Action |
|--------|--------|
| **Bootstrap** | Create seed job → **Build** seed once → open deploy → **Build with Parameters** |
| **Day-to-day** | Deploy job only — pick `CLUSTER_ID` (and `PHASES` / `TAGS` / `LIMIT` / …) |
| **Inventory leaf change** | Push inventory → **Build** seed again (manual) → dropdown updates |

Deploy samples error in **Prepare** if seed-managed params are missing
(`CLUSTER_ID` or booleans `RUN_SMOKE` / `SKIP_DEPLOY` / `RUN_CI_PREFLIGHT`) —
seed never applied / incomplete UI.

### Seed side effects (deploy job rewrite)

Each successful **Build** of the seed job runs Job DSL `pipelineJob(…)` for every
`DEPLOY_SPECS` entry and **rewrites** that deploy job’s:

- full **parameter definitions** (including `choice CLUSTER_ID` and defaults);
- **SCM** (`CLUSTERCTL_GIT_URL` / `_REF`, credentials).

Do **not** rely on manual UI tweaks to the deploy job after seeding — they are
overwritten on the next seed run. Change the seed DSL template,
`DEPLOY_SPECS`, or seed parameters instead.

Default sample git URLs use the **`ssh://git@host/path`** form (inventory and
atlas-clusterctl alike). `INVENTORY_GIT_REF` / `CLUSTERCTL_GIT_REF` are
**branch names** only — shallow checkout uses `git clone --depth 1 --branch`;
commit SHAs are out of scope for these samples.

Deploy Jenkinsfiles omit Declarative `parameters { }` so a **deploy** run does not
reset the seed-managed UI (that is separate from seed rewrite above).

### `CLUSTER_ID` membership rule

Include only **deployable layout** leaves under the inventory `clusters/` root
(same notion as `./cluster list` entries **without** `[policy]` /
`[policy/template]`):

- Shared helper: `clusterctl.tools.list_deployable_clusters.collect_deployable_cluster_ids`
  (CLI: `python3 -m clusterctl.tools.list_deployable_clusters --clusters-root …`).
  Wraps `clusterctl.cluster_layout.list_deployable_cluster_ids`.
- Sorted ascending for stable UI (`--prefer ID` / `prefer=` optionally pins first).
- Offline fixture: `tests/fixtures/jenkins_seed_inventory/clusters/`
  (unit: `tests/test_list_deployable_clusters.py`).

**Choice membership ≠ health guarantee.** An id in the dropdown means the leaf
is a usable deployable layout for the scanner (e.g. `cluster.yaml` and/or
ADR 003 `hosts`). It does **not** promise that `./cluster validate`, smoke, or
deploy will succeed — incomplete `group_vars`, bad overlays, or runtime issues
still fail in the deploy Pipeline stages.

Empty / unusable dirs and `_template/…` are omitted; org baseline
`default/default` and env policy `*/default` are not deployable.

### Required controller plugins (seed)

| Plugin | ID | Why |
|--------|----|-----|
| **Job DSL** | `job-dsl` | Seed updates deploy-job parameters |
| **Active Choices** | `uno-choice` | Reactive `PHASES` checkboxes off `CLUSTER_ID` ([ADR 010](adr/010-jenkins-phases-active-choices.md)) |

(Plus plugins already required by deploy samples — see [jenkins.md](jenkins.md).)
Script Approval may be required the first time the embedded Active Choices Groovy
runs (`JsonSlurper` / script body).

## Out of scope (CLUSTER_ID Phase 0–5)

- Cron / webhook auto-seed.
- Active Choices + controller inventory mirror (for `CLUSTER_ID` dropdown).
- Full CasC takeover of the controller.
- ~~Dynamic `AGENT` choice~~ — seed fills deploy `choiceParam('AGENT', …)` from
  inventory jenkins `hostname:` (plus controller computers when readable).
  Artifact `agent-choices.txt`. Re-seed after agents / inventory change.

Reactive `PHASES` (path C) is **in scope** via [ADR 010](adr/010-jenkins-phases-active-choices.md)
— see [Follow-up: `PHASES`](#follow-up-phases-parameter-contract).

## Implementation plan

| Phase | Work | Done when |
|-------|------|-----------|
| **Phase 0** | This contract + docs links + gate | Contract locked — **done** |
| **Phase 1** | Seed sample under `examples/internal/seed/` (checkout inventory → id list → DSL) | Manual seed updates `choice CLUSTER_ID` on a test deploy job — **done** |
| **Phase 2** | Align deploy Jenkinsfile(s): omit Declarative `parameters {}`; UI SoT = seed | Deploy run does not reset dropdown — **done** |
| **Phase 3** | Operator docs polish (manual-only triggers already locked) | README / jenkins.md workflow crisp — **done** |
| **Phase 4** | Shared list helper + unit tests (fixture inventory) hardening | Scanner gate green — **done** |
| **Phase 5** | Acceptance: add leaf → manual seed → id in UI → deploy picks it | Checklist complete — **done** |

### Phase 1–5 artifacts

| Path | Role |
|------|------|
| `examples/internal/seed/Jenkinsfile` | Seed Pipeline (inventory → list → `jobDsl`) |
| `examples/internal/seed/seed_deploy_jobs.groovy` | Job DSL: full params + `choiceParam('CLUSTER_ID', …)` + `cpsScm` |
| `clusterctl/tools/list_deployable_clusters.py` | `collect_deployable_cluster_ids` + CLI (empty → exit 1) |
| `tests/fixtures/jenkins_seed_inventory/` | Offline inventory fixture for scanner tests |
| `tests/test_list_deployable_clusters.py` | Unit / CLI coverage of the helper |
| `examples/internal/Jenkinsfile` (+ `.local`) | Deploy stages only — **no** `parameters {}` |
| `tests/test_jenkins_seed_phase5.py` | Offline acceptance chain lock |

## Phase 5 acceptance

| Track | Status |
|-------|--------|
| **Offline** | **Done** — locked by `tests/test_jenkins_seed_phase5.py` (no controller) |
| **Live controller** | Org checklist below — **not** exercised by this repo’s CI / gates |

### Offline proof (gate — done)

`tests/test_jenkins_seed_phase5.py` simulates the acceptance chain without a
controller:

1. **Add leaf** under a copy of `jenkins_seed_inventory` → scanner lists the new id.
2. **Seed list artifact** (`cluster-ids.txt` format) includes the id (prefer first).
3. **UI contract** — Job DSL `choiceParam('CLUSTER_ID', …)` + seed `jobDsl` bindings;
   empty scan still fails.
4. **Deploy picks it** — deploy Jenkinsfiles omit `parameters {}`, bind
   `params.CLUSTER_ID` → env / `./cluster --cluster`, Prepare fails if missing.

### Live controller (operator checklist — org-local)

Org-local sign-off on a real Jenkins (manual Build only). Completing this table
is an **operator** task; the offline gate above does **not** prove live UI.

1. Install Job DSL; create `atlas-clusterctl-seed`; **Build** once (bootstrap).
2. Open deploy job → **Build with Parameters** → confirm `CLUSTER_ID` is a **choice**.
3. Add a deployable leaf in inventory → push → **Build** seed again.
4. Confirm the new id appears in the dropdown.
5. Select it and run deploy Prepare (or a short `SKIP_DEPLOY` build) — job uses that id.

## Phase 0 checklist

- [x] Seed + Job DSL vs Active Choices decided — **seed + Job DSL**
- [x] Manual trigger only (no cron/webhook in scope)
- [x] Job naming convention + UI SoT (`CLUSTER_ID` choice from seed)
- [x] Deploy JF must not redeclare `string CLUSTER_ID` (decision locked)
- [x] Deployable id rule (`list_deployable_cluster_ids` / `./cluster list` non-policy)
- [x] Empty scan → fail; full params template preserves `TAGS` / `LIMIT` / `EXTRA_VARS`
- [x] Phase 0 gate exists (`tests/test_jenkins_seed_phase0.py`)
- [x] Seed sample scripts (Phase 1)
- [x] Deploy JF `CLUSTER_ID` alignment (Phase 2)
- [x] Operator docs polish (Phase 3)
- [x] List helper + tests (Phase 4)
- [x] Acceptance (Phase 5)

---

## Follow-up: `PHASES` parameter (contract)

> **PHASES follow-up Phase 0–5 done (2026-08-01; Phase 4 = path C unlocked via
> [ADR 010](adr/010-jenkins-phases-active-choices.md)).**
> Normative rules for deploy-job `PHASES` relative to seeded `CLUSTER_ID`.
> Does **not** reopen CLUSTER_ID Phase 0–5. Operator overview:
> [jenkins.md](jenkins.md) (Parameters / Stages).

### Goal

Make **empty `PHASES` ⇒ plan/run without `--phases` (plan SoT)** an explicit
contract, and relate phase lists to the selected `CLUSTER_ID` without breaking
UI SoT = seed.

**Delivered:** empty = plan SoT; optional ADR 008 selector; YAML map
(`cluster-phases.json`) + **Active Choices cascade** (path C / ADR 010) so
Build-with-Parameters shows checkboxes for the selected `CLUSTER_ID`.

### Decision (normative)

| Topic | Lock |
|-------|------|
| **Empty `PHASES`** | Deploy **omits** `--phases` on `plan` / `run` → **plan SoT** (effective stages for that leaf). Default operator path. May **omit** YAML phases skipped by inventory `when:` (or other plan-time filters) |
| **Non-empty `PHASES`** | Same selector as CLI: `NAME` \| `start..end` \| `a,b,c` ([ADR 008](adr/008-phases-cli-selector.md)). UI cascade offers checkboxes → `NAME` or CSV `a,b,c` |
| **`TAGS` / `LIMIT`** | **Unchanged** — non-empty `TAGS` or `LIMIT` still require a **single-phase** `PHASES` (clusterctl **ERROR** on multi-phase windows; [ADR 009](adr/009-unify-run-stage-play.md)) |
| **UI shape (locked)** | Seed-owned **Active Choices Reactive** `PHASES` (`CHECKBOX`, referenced `CLUSTER_ID`) per [ADR 010](adr/010-jenkins-phases-active-choices.md). None selected = empty = plan SoT |
| **Cascade / Active Choices** | **In scope** (ADR 010). Changing `CLUSTER_ID` refreshes available phase checkboxes. Requires plugin `uno-choice` + possible Script Approval |
| **Why cascade needs a plugin** | Job DSL runs only on **seed Build**. It cannot alone rewrite param values when the operator later picks another `CLUSTER_ID` — Active Choices evaluates embedded Groovy on the form |
| **Seed phases map (path B + C)** | Offline helper + seed artifact `examples/internal/seed/cluster-phases.json` (`CLUSTER_ID → [short phase names]`) — **YAML `phases:` catalog only** (no `when:`). Seed Pipeline scans **inventory `clusters/` only** (no `--product-clusters-root`). Same JSON is passed to Job DSL as `CLUSTER_PHASES_JSON` and **embedded** into the reactive script. May differ from empty-`PHASES` plan output. Helper: `clusterctl.tools.list_cluster_phases` (`--all --allow-empty`) |
| **`start..end` in UI** | **Not** offered as checkboxes — use empty (plan SoT) or multi CSV; inclusive ranges remain CLI-oriented |
| **UI SoT** | Unchanged — deploy Jenkinsfiles omit Declarative `parameters { }`; seed owns the full template including `PHASES` |

### Map vs empty `PHASES` (normative)

| Source | Meaning |
|--------|---------|
| **`cluster-phases.json` / `list_cluster_phases` (seed)** | Merged YAML `phases:` short names from **inventory** config cascade only. No inventory `when:`. No product-clusters root on the seed job |
| **Deploy empty `PHASES`** | `./cluster … plan` / `run` **without** `--phases` → **plan SoT** (after deploy `repos sync` may also see product baseline) |

The map may list phases that plan skips. Operators use checkboxes (or the archived
map) when selecting a non-empty `PHASES`; they must **not** require map ≡ plan
text / `plan.json` stage list.

**Where the map lives:** Jenkins job `atlas-clusterctl-seed` → last successful
**Build** → **Artifacts** → `examples/internal/seed/cluster-phases.json`, **and**
embedded into deploy-job Active Choices at that seed Build. Re-run seed after
inventory `phases:` changes so checkboxes stay current.

### Seed map root (inventory-only)

Seed samples call:

`python3 -m clusterctl.tools.list_cluster_phases --clusters-root <INVENTORY_DIR>/clusters --all --allow-empty`

They do **not** pass `--product-clusters-root`. The CLI flag exists for offline /
manual use (org-baseline fallback), but wiring a product tree on the seed agent
is **out of this remediation** (no half-broken `PRODUCT_CLUSTERS_ROOT` seed
param without a stable agent path).

**Implication:** if a leaf’s usable `phases:` would only appear after product
baseline merge (deploy `repos sync`), the seed map may omit or under-list that
leaf relative to a later deploy plan. Prefer **inline `phases:` on inventory
leaves** (org practice). Treat seed map ≠ guarantee of post-sync plan catalog.

### Runtime today (already matches empty lock)

Deploy samples ([`Jenkinsfile`](../examples/internal/Jenkinsfile) /
[`.local`](../examples/internal/Jenkinsfile.local)) Plan / Run:

- `PHASES` empty → `./cluster … plan` / `run` **without** `--phases` (plan SoT);
- `PHASES` set → `plan --phases "${PHASES}"` and per-stage `run --phases <phase_ref>`.
- `envParam` joins Active Choices multi-select to ADR 008 CSV.

Phase 0 does **not** change Pipeline plan/run semantics; it locks the meaning
operators and later phases must preserve.

### Out of scope (this follow-up)

- Active Choices for `CLUSTER_ID` (stays Jenkins `choice` from Job DSL).
- Per-`CLUSTER_ID` default string baked into Job DSL without Active Choices
  (stale when the operator switches leaf without re-seeding) — superseded by
  reactive checkboxes for catalog names.
- Changing `TAGS` / `LIMIT` / ADR 008 / ADR 009 semantics.
- Requiring operators to type every phase name when they want plan SoT
  (empty `PHASES` remains valid and preferred).
- Treating `cluster-phases.json` as equal to empty-`PHASES` `./cluster plan`
  output (map is YAML-only; plan may apply `when:`).
- Seed Pipeline passing `--product-clusters-root` / a `PRODUCT_CLUSTERS_ROOT`
  param (inventory-only map lock; optional product root stays CLI-only until a
  later ADR + stable agent layout).
- Checkbox UI for inclusive `start..end` ranges (CLI-oriented; use CSV or empty).

### Implementation plan (`PHASES` follow-up)

| Phase | Work | Done when |
|-------|------|-----------|
| **Phase 0** | This contract + docs links + gate | Semantics locked — **done** |
| **Phase 1** | Path A: DSL + operator docs spell out empty = plan SoT | Param description / jenkins.md crisp — **done** |
| **Phase 2** | Path B: shared phases-list helper + fixture tests | Offline id → phase names — **done** |
| **Phase 3** | Seed writes / archives phases map artifact | Artifact on successful seed Build — **done** |
| **Phase 4** | Path C: Active Choices cascade ([ADR 010](adr/010-jenkins-phases-active-choices.md)) | **Done** — reactive `PHASES` in samples |
| **Phase 5** | Acceptance: empty PHASES = plan SoT path; map matches YAML leaf; cascade wired | Checklist complete — **done** |

### Phase 0 checklist (`PHASES` follow-up)

- [x] Empty `PHASES` ⇒ plan/run without `--phases` (plan SoT; may differ from YAML map)
- [x] Non-empty `PHASES` ⇒ CLI `--phases` selector (ADR 008)
- [x] `TAGS` / `LIMIT` single-phase rule unchanged (ADR 009)
- [x] Path C initially deferred; **unlocked** by [ADR 010](adr/010-jenkins-phases-active-choices.md) (Phase 4)
- [x] Seed phases **map** as reference + cascade embed (path B + C)
- [x] UI SoT = seed unchanged
- [x] Phase 0 gate exists (`tests/test_jenkins_seed_phases_param_phase0.py`)
- [x] Phase 1 — DSL + operator docs empty = all (`tests/test_jenkins_seed_phases_param_phase1.py`)
- [x] Phase 2 — phases-list helper + fixture (`tests/test_jenkins_seed_phases_param_phase2.py`)
- [x] Phase 3 — seed writes / archives `cluster-phases.json` (`tests/test_jenkins_seed_phases_param_phase3.py`)
- [x] Phase 4 — path C unlocked / ADR 010 (`tests/test_jenkins_seed_phases_param_phase4.py`)
- [x] Phase 5 — acceptance (`tests/test_jenkins_seed_phases_param_phase5.py`)

### Phase 1 artifacts (`PHASES` follow-up)

| Path | Role |
|------|------|
| `examples/internal/seed/seed_deploy_jobs.groovy` | `PHASES` description: empty = plan SoT (now on Active Choices param) |
| `docs/jenkins.md` | Parameters + Stages: empty = plan SoT (may differ from YAML map) |
| `examples/internal/README.md` / `seed/README.md` | Operator-facing empty = plan SoT |
| `tests/test_jenkins_seed_phases_param_phase1.py` | Phase 1 gate |

### Phase 2 artifacts (`PHASES` follow-up)

| Path | Role |
|------|------|
| `clusterctl/tools/list_cluster_phases.py` | `collect_phases_for_cluster` / `collect_phases_map` + CLI |
| `tests/fixtures/jenkins_seed_inventory/` | Leaves with inline `phases:` (+ `hosts_only` without) |
| `tests/test_list_cluster_phases.py` | Unit / CLI coverage |
| `tests/test_jenkins_seed_phases_param_phase2.py` | Phase 2 gate |

### Phase 3 artifacts (`PHASES` follow-up)

| Path | Role |
|------|------|
| `examples/internal/seed/Jenkinsfile` | Stage **List cluster phases map** → `cluster-phases.json` from inventory `clusters/` only; `post` archives with `cluster-ids.txt` |
| `clusterctl/tools/list_cluster_phases.py` | `--all --allow-empty` for seed (empty map → `{}`, exit 0); `ids_missing_from_phases_map` |
| `.gitignore` | `/examples/internal/seed/cluster-phases.json` (generated) |
| `examples/internal/seed/seed_deploy_jobs.groovy` | Embeds map into Active Choices (Phase 4 / ADR 010) |
| `tests/test_jenkins_seed_phases_param_phase3.py` | Phase 3 gate |

Seed does **not** fail when the map is empty (hosts-only inventory): Job DSL still
refreshes `CLUSTER_ID`. After writing the map, seed **warns** (stderr, non-fatal)
for deployable ids absent from the map. Unexpected YAML/load errors from the
helper print `error: …` (no traceback) and fail the stages.

### Phase 4 artifacts (`PHASES` follow-up) — path C unlocked (ADR 010)

Phase 4 ships **Active Choices** reactive `PHASES` checkboxes keyed off
`CLUSTER_ID`. The seed Build embeds `CLUSTER_PHASES_JSON` into the Job DSL
reactive Groovy script (same inventory-only catalog as `cluster-phases.json`).

| Path | Role |
|------|------|
| `docs/adr/010-jenkins-phases-active-choices.md` | Unlock ADR |
| `examples/internal/seed/seed_deploy_jobs.groovy` | `activeChoiceReactiveParam('PHASES')` + embedded map |
| `examples/internal/seed/Jenkinsfile` | Passes `CLUSTER_PHASES_JSON` into Job DSL |
| `examples/internal/Jenkinsfile` / `.local` | `envParam` joins multi-select → CSV |
| `docs/jenkins.md` / seed README | Operator: cascade + empty = plan SoT; plugin `uno-choice` |
| `tests/test_jenkins_seed_phases_param_phase4.py` | Phase 4 gate (cascade present) |

<a id="phase-5-acceptance-phases-follow-up"></a>

### Phase 5 acceptance (`PHASES` follow-up)

| Track | Status |
|-------|--------|
| **Offline** | **Done** — locked by `tests/test_jenkins_seed_phases_param_phase5.py` (no controller) |
| **Live controller** | Org checklist below — **not** exercised by this repo’s CI / gates |

#### Offline proof (gate — done)

`tests/test_jenkins_seed_phases_param_phase5.py` simulates acceptance without a
controller:

1. **Phases map** — `list_cluster_phases --all` on the seed fixture matches
   `collect_phases_map` / leaf YAML short names (`hosts_only` omitted).
2. **Add leaf with `phases:`** → map artifact (`cluster-phases.json` shape)
   includes the new id with the expected phase list.
3. **Empty `PHASES` deploy path** — samples omit `--phases` on `plan` / `run`
   when the param is empty (plan SoT; not required equal to YAML map); non-empty
   still passes `--phases`.
4. **UI SoT + cascade** — DSL uses `activeChoiceReactiveParam('PHASES')` with
   `referencedParameter('CLUSTER_ID')`; seed passes `CLUSTER_PHASES_JSON`;
   deploy `envParam` joins collections; seed archives the map.

#### Live controller (operator checklist — org-local)

Org-local sign-off on a real Jenkins (manual Build only). Completing this table
is an **operator** task; the offline gate above does **not** prove live UI.

1. Install **Active Choices** (`uno-choice`) + **Job DSL**; approve scripts if prompted.
2. **Build** seed → confirm archived `cluster-phases.json` under seed job
   **Artifacts** lists expected leaves (YAML short names for inventory leaves
   that have `phases:`; inventory-only — no product root on seed).
3. Open deploy → **Build with Parameters** → change `CLUSTER_ID` → confirm
   `PHASES` checkboxes refresh to that leaf’s YAML short names (ADR 010).
4. Leave `PHASES` unchecked → Plan runs **without** `--phases` (plan SoT). Do
   **not** require plan / `plan.json` to match `cluster-phases.json` (inventory
   `when:` may skip catalog entries; post-`repos sync` product baseline may also
   differ from the seed map).
5. Re-run with one or more checkboxes (and optional `TAGS`/`LIMIT` with a
   **single** NAME) → selective plan/run.
6. After adding a leaf with `phases:` in inventory → push → **Build** seed →
   new id appears in `CLUSTER_ID` choice and in cascade checkboxes / map artifact.

---

## Follow-up: `LIMIT` parameter (contract)

> **LIMIT follow-up Phase 0–5 done (2026-08-01; Phase 4 = operator docs;
> Phase 5 = offline acceptance + live checklist).**
> Normative rules for deploy-job `LIMIT` relative to seeded `CLUSTER_ID`, and how
> host/group catalogs cascade in Build with Parameters.
> Contract ADR: [ADR 011](adr/011-jenkins-limits-active-choices.md).
> Does **not** reopen CLUSTER_ID Phase 0–5, PHASES follow-up, or ADR 009 classify
> rules. Operator overview: [jenkins.md](jenkins.md) (Parameters / Stages).

<a id="follow-up-limits-parameter-contract"></a>

### Goal

Keep **empty `LIMIT` ⇒ omit ansible `--limit`** as the default operator path, and
lock a seed-owned **Active Choices cascade** so operators can pick inventory
**groups and hosts** for the selected `CLUSTER_ID` without memorizing names —
mirroring [ADR 010](adr/010-jenkins-phases-active-choices.md) for `PHASES`.

**Delivered through Phase 5:** semantics + ADR + helper + seed artifact
`examples/internal/seed/cluster-limits.json` + Job DSL `CLUSTER_LIMITS_JSON` +
reactive `LIMIT` checkboxes + operator docs + offline acceptance gate + live
checklist.

### Decision (normative)

| Topic | Lock |
|-------|------|
| **Empty `LIMIT`** | Deploy Run **omits** `--limit` → no host/group restriction. Default operator path |
| **Non-empty `LIMIT`** | Passed as ansible `--limit <pattern>` — checkbox names joined with `,` via `envParam` |
| **`TAGS` / ADR 009** | **Unchanged** — non-empty `LIMIT` (or selective `TAGS`) still requires a **single-phase** `PHASES` window ([ADR 009](adr/009-unify-run-stage-play.md)) |
| **UI shape (Phase 3+)** | Seed-owned **Active Choices Reactive** `LIMIT` (`CHECKBOX`, referenced `CLUSTER_ID`) per [ADR 011](adr/011-jenkins-limits-active-choices.md). None selected = empty = omit `--limit` |
| **Cascade / Active Choices** | **In scope / delivered** via ADR 011 (Phases 2–3: map + reactive UI) |
| **Catalog membership** | **Groups and hosts** from the leaf YAML inventory file. Seed UI: hierarchical **group then its hosts** (sorted); parent-only groups follow. No `g:`/`h:` prefixes. INI / unusable `hosts` → omitted from map. Flat groups-then-hosts = CLI default without `--ui` |
| **Submitted value SoT** | Inventory **group names** / **host keys** (`extract_inventory_groups` / `extract_inventory_hostnames`) — never DNS / checkbox labels (keys are often IPs in org inventory) |
| **Host label (display)** | Host key; optional inventory `hostname:` shown as `(hostname: dns)` in the label only |
| **Group name SoT** | Inventory group names (`extract_inventory_groups` / limit sections) |
| **Seed limits map** | Helper (Phase 1) + artifact / Job DSL binding (Phase 2) + reactive embed (Phase 3): `list_cluster_limits --all --allow-empty --ui` → `cluster-limits.json` / `CLUSTER_LIMITS_JSON` (ordered `[{value,label},…]` per leaf). Inventory `clusters/` only. Seed-time **`switch`** (no form-render `JsonSlurper`) |
| **Advanced patterns** | `&`, `!`, `~`, and other ansible host-pattern operators are **valid CLI `--limit`** but **out of checkbox UI** in v1 |
| **UI SoT** | Unchanged — deploy Jenkinsfiles omit Declarative `parameters { }`; seed owns the full template including `LIMIT` |

### Map vs empty `LIMIT` (normative)

| Source | Meaning |
|--------|---------|
| **`cluster-limits.json` / `list_cluster_limits` (seed)** | Static group + host-key catalog from leaf YAML inventory at seed Build |
| **Deploy empty `LIMIT`** | `./cluster run …` **without** `--limit` |

Operators must **not** require the catalog to equal live post-provision inventory
or dynamic sources. Prefer keeping leaf `hosts` accurate so the seed map matches
what Run will see after inventory checkout.

**Where the map lives:** Jenkins job `atlas-clusterctl-seed` → last successful
**Build** → **Artifacts** → `examples/internal/seed/cluster-limits.json` (and
passed into Job DSL as `CLUSTER_LIMITS_JSON`, embedded into Active Choices).
Re-run seed after inventory host/group changes.

### Seed map root (inventory-only)

Seed samples call:

`python3 -m clusterctl.tools.list_cluster_limits --clusters-root <INVENTORY_DIR>/clusters --all --allow-empty --ui`

Optional `--structured` → per-leaf `{"groups": [...], "hosts": [...]}` (CLI /
offline; mutually exclusive with `--ui`). Seed artifact uses **`--ui`** ordered
`[{value,label},…]` lists (group then nested host labels) for Job DSL Map
embed — not flat string lists.

No `--product-clusters-root`. No live `ansible-inventory` on the controller at
form-render time.

### Runtime (empty lock + CSV join)

Deploy samples ([`Jenkinsfile`](../examples/internal/Jenkinsfile) /
[`.local`](../examples/internal/Jenkinsfile.local)) Run:

- `LIMIT` empty → omit `--limit`;
- `LIMIT` set → `--limit "${LIMIT}"` on the single-phase selective path;
- `envParam` joins Active Choices `Collection` → CSV (same helper as `PHASES`).

Phase 3 does **not** change Pipeline Run code beyond documenting that `LIMIT`
may arrive as a Collection; `envParam` already handled that for ADR 010.

### Out of scope (this follow-up)

- Active Choices for `CLUSTER_ID` or `TAGS` (tags cascade = separate track).
- Checkbox UI for `&` / `!` / `~` host patterns (CLI remains capable).
- True nested checkbox widgets (uno-choice is flat; nesting = label indentation).
- Using `hostname:` / DNS as submitted `--limit` values (labels only).
- Product-clusters root / dynamic inventory on seed.
- Changing ADR 009 single-phase / classify semantics.
- Companion free-form string beside checkboxes (possible later ADR).
- Parsing INI-style `hosts` files (extractors are YAML-only; such leaves are
  omitted from the limits map — still valid `CLUSTER_ID` choices).

### Implementation plan (`LIMIT` follow-up)

| Phase | Work | Done when |
|-------|------|-----------|
| **Phase 0** | This contract + [ADR 011](adr/011-jenkins-limits-active-choices.md) + gate | Semantics locked — **done** |
| **Phase 1** | Helper `list_cluster_limits` + fixture tests | Offline id → groups/hosts catalog — **done** |
| **Phase 2** | Seed writes / archives `cluster-limits.json`; Job DSL binding | Artifact on successful seed Build — **done** |
| **Phase 3** | DSL: `activeChoiceReactiveParam('LIMIT')` + seed-time `switch` | Checkboxes refresh with `CLUSTER_ID` — **done** |
| **Phase 4** | Operator docs / troubleshooting | jenkins.md + seed README crisp — **done** |
| **Phase 5** | Acceptance: empty omit `--limit`; cascade wired | Checklist complete — **done** |

### Phase 0 checklist (`LIMIT` follow-up)

- [x] Empty `LIMIT` ⇒ omit `--limit`
- [x] Non-empty `LIMIT` ⇒ ansible `--limit` (ADR 009 single-phase unchanged)
- [x] Target catalog = groups + hosts; hierarchical UI (values = host/group keys;
  `hostname:` display-only); flat CLI without `--ui`
- [x] Cascade via [ADR 011](adr/011-jenkins-limits-active-choices.md) — Active Choices delivered (Phase 3)
- [x] Form-render embed = switch only (no JsonSlurper)
- [x] Seed map inventory-only; advanced patterns out of checkbox UI
- [x] UI SoT = seed unchanged
- [x] Phase 0 gate exists (`tests/test_jenkins_seed_limits_param_phase0.py`)
- [x] Phase 1 — helper + fixture (`tests/test_jenkins_seed_limits_param_phase1.py`)
- [x] Phase 2 — seed writes / archives `cluster-limits.json` (`tests/test_jenkins_seed_limits_param_phase2.py`)
- [x] Phase 3 — reactive `LIMIT` checkboxes (`tests/test_jenkins_seed_limits_param_phase3.py`)
- [x] Phase 4 — operator docs / troubleshooting (`tests/test_jenkins_seed_limits_param_phase4.py`)
- [x] Phase 5 — acceptance (`tests/test_jenkins_seed_limits_param_phase5.py`)

### Phase 0 artifacts (`LIMIT` follow-up)

| Path | Role |
|------|------|
| `docs/adr/011-jenkins-limits-active-choices.md` | Unlock / shape ADR (Phase 0 accepted) |
| `docs/jenkins-seed.md` | This contract section |
| `docs/jenkins.md` | Operator pointer: empty omit; Active Choices cascade; host-key / re-seed notes (ADR 011) |
| `examples/internal/seed/README.md` | Checklist + pointer |
| `examples/internal/seed/seed_deploy_jobs.groovy` | Historically `stringParam('LIMIT')` until Phase 3; now Active Choices |
| `tests/test_jenkins_seed_limits_param_phase0.py` | Phase 0 gate |

### Phase 1 artifacts (`LIMIT` follow-up)

| Path | Role |
|------|------|
| `clusterctl/tools/list_cluster_limits.py` | `collect_limits_for_cluster` / `collect_limits_parts_for_cluster` / `collect_limits_map` + CLI |
| `tests/fixtures/jenkins_seed_inventory/` | YAML `hosts` on `fixture/postgresql`, `fixture/redis`, `lab/alpha`; `fixture/hosts_only` stays INI (omitted from map) |
| `tests/test_list_cluster_limits.py` | Unit / CLI coverage |
| `tests/test_jenkins_seed_limits_param_phase1.py` | Phase 1 gate |

### Phase 2 artifacts (`LIMIT` follow-up)

| Path | Role |
|------|------|
| `examples/internal/seed/Jenkinsfile` | Stage **List cluster limits map** → `cluster-limits.json`; `post` archives with ids/phases; Job DSL gets `CLUSTER_LIMITS_JSON` |
| `examples/internal/seed/seed_deploy_jobs.groovy` | Parses `CLUSTER_LIMITS_JSON`; builds seed-time LIMIT `switch` (wired in Phase 3) |
| `.gitignore` | `/examples/internal/seed/cluster-limits.json` (generated) |
| `tests/test_jenkins_seed_limits_param_phase2.py` | Phase 2 gate |

Seed does **not** fail when the limits map is empty (INI-only / phaseless-style
inventory leaves): Job DSL still refreshes `CLUSTER_ID` / `PHASES` / `LIMIT`.
After writing the map, seed **warns** (stderr, non-fatal) for deployable ids
absent from the map. Unexpected YAML/load errors from the helper print
`error: …` (no traceback) and fail the stage.

### Phase 3 artifacts (`LIMIT` follow-up)

| Path | Role |
|------|------|
| `examples/internal/seed/seed_deploy_jobs.groovy` | `activeChoiceReactiveParam('LIMIT')` + `choiceType('CHECKBOX')` + `referencedParameter('CLUSTER_ID')`; form-render = embedded `switch` only |
| `examples/internal/Jenkinsfile` / `.local` | `envParam` joins Active Choices `Collection` → CSV (shared with `PHASES`) |
| `tests/test_jenkins_seed_limits_param_phase3.py` | Phase 3 gate |

**Live notes (from ADR 010 lessons):** Job DSL enum is `CHECKBOX` (not
`PT_CHECKBOX`). Form-render scripts must not call `JsonSlurper` (Script Approval
footgun) — parse JSON at seed/Job-DSL time only.

### Phase 4 artifacts (`LIMIT` follow-up) — operator docs

Phase 4 makes the delivered cascade **operable**: crisp day-to-day notes in
[jenkins.md](jenkins.md) and seed README troubleshooting for empty UI, IP host
keys, and when to re-seed.

| Path | Role |
|------|------|
| `docs/jenkins.md` | Workflow: re-seed on `hosts`/groups; LIMIT bullets (host keys / empty UI / advanced patterns); plugins + Script Approval |
| `examples/internal/seed/README.md` | What it does + troubleshooting (IP keys, empty map, cascade stale) |
| `docs/jenkins-seed.md` | This section + operator notes below |
| `tests/test_jenkins_seed_limits_param_phase4.py` | Phase 4 gate |

#### Operator notes (`LIMIT`)

| Topic | Guidance |
|-------|----------|
| **Empty selection** | No boxes checked → omit `--limit` (default / full inventory path) |
| **Empty checkbox list** | Leaf has no usable YAML `hosts` (INI, missing, parse failure) — still valid; seed may warn `without limits catalog` |
| **Host labels look like IPs** | Expected for **values** / primary text — SoT is inventory **host keys**. When inventory sets `hostname:`, the label adds `(hostname: dns)` |
| **Group then nested hosts** | UI order: each group with direct hosts, then its hosts (indented labels); parent-only groups follow. Submitted values stay clean keys (no `▸` / `hostname:` in `--limit`) |
| **Stale after inventory edit** | Push `hosts`/groups, **Build** seed — map is snapshotted / embedded at seed time |
| **Cascade not refreshing / empty checkboxes** | Install `uno-choice`; **In-process Script Approval** for the LIMIT script (empty map `[:]` / silent failure looks like no catalog); re-run seed; hard-refresh form. Marker checkbox `__LIMIT_SCRIPT_BLOCKED_…__` = approval blocked |
| **Advanced patterns** | `and` / `~` / `!` stay CLI (`./cluster run --limit …`) — not in checkbox UI |
| **With `TAGS` / selective Run** | Non-empty `LIMIT` still needs a **single** `PHASES` checkbox ([ADR 009](adr/009-unify-run-stage-play.md)) |
| **Artifact twin** | Seed → Artifacts → `examples/internal/seed/cluster-limits.json` (same catalog as checkboxes) |

<a id="phase-5-acceptance-limits-follow-up"></a>

### Phase 5 acceptance (`LIMIT` follow-up)

| Track | Status |
|-------|--------|
| **Offline** | **Done** — locked by `tests/test_jenkins_seed_limits_param_phase5.py` (no controller) |
| **Live controller** | Org checklist below — **not** exercised by this repo’s CI / gates |

#### Offline proof (gate — done)

`tests/test_jenkins_seed_limits_param_phase5.py` simulates acceptance without a
controller:

1. **Limits map** — `list_cluster_limits --all` (flat) on the seed fixture matches
   `collect_limits_map` / leaf YAML groups-then-hosts (`hosts_only` INI omitted);
   seed path uses `--ui` ordered `{value,label}` entries.
2. **Add leaf with YAML `hosts`** → map artifact (`cluster-limits.json` shape)
   includes the new id with the expected catalog (flat CLI / UI entries).
3. **Empty `LIMIT` deploy path** — samples omit `--limit` on Run when the param
   is empty; non-empty still passes `--limit`.
4. **UI SoT + cascade** — DSL uses `activeChoiceReactiveParam('LIMIT')` with
   `referencedParameter('CLUSTER_ID')`; seed passes `CLUSTER_LIMITS_JSON`;
   deploy `envParam` joins collections; seed archives the map; no Declarative
   `parameters { }` on deploy samples.

#### Live controller (operator checklist — org-local)

Org-local sign-off on a real Jenkins (manual Build only). Completing this table
is an **operator** task; the offline gate above does **not** prove live UI.

1. Install **Active Choices** (`uno-choice`) + **Job DSL**; approve scripts if prompted
   (seed-time `JsonSlurper` / Job DSL — form-render is `switch` only).
2. **Build** seed → confirm archived `cluster-limits.json` under seed job
   **Artifacts** lists expected leaves as ordered `[{value,label},…]` UI entries
   (group then nested hosts; inventory-only — INI / missing `hosts` omitted; seed
   may warn).
3. Open deploy → **Build with Parameters** → change `CLUSTER_ID` → confirm
   `LIMIT` checkboxes refresh: **group** rows then indented **host** rows
   (ADR 011). Host labels may include `(hostname: dns)` when set in inventory;
   submitted values remain host/group keys (often IPs).
4. Leave `LIMIT` unchecked → Run **omits** `--limit`. Do **not** require the
   catalog to equal live post-provision inventory.
5. Check one or more boxes (and a **single** `PHASES` NAME if using selective
   Run / `TAGS`) → `--limit` CSV on Run.
6. After adding/changing leaf `hosts`/groups in inventory → push → **Build**
   seed → cascade / map artifact update. Advanced patterns (`&`/`~`/`!`) stay
   CLI-only.

## References

- [jenkins.md](jenkins.md) — deploy Pipeline samples + operator workflow + `TAGS` / `LIMIT` / `EXTRA_VARS` / `PHASES`
- [local-labs.md](local-labs.md) — private inventory / `clusters.path`
- [ADR 008](adr/008-phases-cli-selector.md) — `--phases` selector
- [ADR 009](adr/009-unify-run-stage-play.md) — `run` + `TAGS` / `LIMIT`
- [ADR 010](adr/010-jenkins-phases-active-choices.md) — `PHASES` Active Choices cascade (path C)
- [ADR 011](adr/011-jenkins-limits-active-choices.md) — `LIMIT` Active Choices cascade (Phase 0–5)
- `clusterctl.paths.list_deployable_cluster_ids` / `clusterctl.cluster_layout`
- `clusterctl.inventory.extract_inventory_groups` / `extract_inventory_hostnames`
- Gates: `tests/test_jenkins_seed_phase0.py`, `tests/test_jenkins_seed_phase1.py`,
  `tests/test_jenkins_seed_phase2.py`, `tests/test_jenkins_seed_phase3.py`,
  `tests/test_jenkins_seed_phase4.py`, `tests/test_jenkins_seed_phase5.py`;
  follow-up `tests/test_jenkins_seed_followup_a.py`,
  `tests/test_jenkins_seed_followup_b.py`,
  `tests/test_jenkins_seed_followup_c.py`;
  `PHASES` follow-up `tests/test_jenkins_seed_phases_param_phase0.py`,
  `tests/test_jenkins_seed_phases_param_phase1.py`,
  `tests/test_jenkins_seed_phases_param_phase2.py`,
  `tests/test_jenkins_seed_phases_param_phase3.py`,
  `tests/test_jenkins_seed_phases_param_phase4.py`,
  `tests/test_jenkins_seed_phases_param_phase5.py`;
  `LIMIT` follow-up `tests/test_jenkins_seed_limits_param_phase0.py`,
  `tests/test_jenkins_seed_limits_param_phase1.py`,
  `tests/test_jenkins_seed_limits_param_phase2.py`,
  `tests/test_jenkins_seed_limits_param_phase3.py`,
  `tests/test_jenkins_seed_limits_param_phase4.py`,
  `tests/test_jenkins_seed_limits_param_phase5.py`
  (+ `tests/test_list_deployable_clusters.py`, `tests/test_list_cluster_phases.py`,
  `tests/test_list_cluster_limits.py`)
