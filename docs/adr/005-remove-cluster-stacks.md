# ADR 005 — Remove `cluster.yaml` `stacks:` (phases are SoT)

- **Status:** Accepted (Phase 4 complete — `stacks.py` deleted; `stacks:` hard-rejected; cleanup A–E verified offline)
- **Date:** 2026-07-28
- **Deciders:** atlas-clusterctl maintainers
- **Supersedes:** schema v2 `stacks` / `skip_phase_refs` as a second plan DSL
- **Related:** [cluster-config-v2.md](../cluster-config-v2.md), [validate.md](../validate.md),
  docs under [stacks/](../stacks/) (product runbooks — **kept**), ADR 003 / 004

## Context

Deployable leaves already declare the executable plan explicitly:

```yaml
phases:
  - atlas-compute-provision/templates
  - atlas-compute-provision/provision
  - atlas-node-foundation/init
  - atlas-jenkins-agent/agent
```

A parallel `stacks:` block was added historically so a thick cascade/`phases`
list could be coarsely filtered via flags:

```yaml
stacks:
  infra:
    enabled: false
    skip_phase_refs:
      - atlas-node-foundation/init-infra
      - atlas-infra-edge/infra
  k8s:
    enabled: false
    skip_phase_refs:
      - atlas-k8s-core/cluster
      - atlas-k8s-addons/addons
```

In the current product shape that second DSL was redundant:

1. **Public templates and labs already ship a short `phases:`** that matches the
   leaf (jenkins / redis / kafka / postgresql / infra_edge / k8s_full). There was
   no thick org `phases` that leaves only toggled via `stacks`.
2. **`skip_phase_refs` only removed refs that were already in `phases:`.** On
   jenkins/redis/… the listed infra/k8s refs were absent → skip was a no-op.
3. **`enabled` largely duplicated `provision_stack`** in
   `atlas-compute-provision.yml`. Historically the engine also derived coarse
   intent from that selector; **today** inventory intent comes from `phases:`
   (`phase_intent.py`), while `provision_stack` remains only the provision/TF
   selector (and mysql until a phase ref exists).
4. Operators already decide presence and order by editing `phases:` /
   `phase_aliases`. A silent filter on top of that list was surprising.

Org baseline (`clusters/default/default/cluster.yaml`) historically had `stacks` as a
**commented** example — removed in Phase 3.

## Decision

### Source of truth

| Concern | SoT after this ADR |
|---------|---------------------|
| Which phases run / order | **`phases:` only** |
| Short CLI names | **inline in `phases:`** (ADR 007; top-level `phase_aliases:` removed) |
| Controller runtime | **`execution`** |
| Provision/TF product selector | **`provision_stack`** in group_vars (unchanged; not YAML `stacks:`) |
| Product how-to docs | **`docs/stacks/*.md`** (folder name stays; not the YAML key) |

To disable a stack on a leaf: **omit its phase refs from `phases:`** (and drop
unused aliases). Do not use `stacks.*.enabled` / `skip_phase_refs`.

### Target end state (Phase 4 — achieved)

- No `stacks:` key in public templates, org baseline, or inventory labs.
- No plan-time filter (`apply_stacks_filter` / `stacks_skipped`).
- `clusterctl/stacks.py` **deleted**; intent lives in `clusterctl/phase_intent.py`.
- Validate inventory checks derive intent from **`phases:`** (and may still read
  `provision_stack` where useful) — not from YAML `stacks.enabled`.
- Present `stacks:` in cascade → **`StacksRemovedError`** / validate ERROR
  (`stacks_removed`), not silent ignore.
- Inventory validate codes use `phase_intent_*` / `inventory_*_phases_omitted`
  (no legacy `stacks_*_no_inventory` / `*_stack_disabled`).

### Replacement map

| Today (`stacks`) | After |
|------------------|-------|
| `stacks.<name>.enabled: false` + `skip_phase_refs` | Those phase refs are simply **not** in `phases:` |
| `stacks.<name>.enabled: true` | Phase refs **are** in `phases:` |
| Plan line `Stack filter skipped: …` | Gone — plan == `phases:` slice |
| Validate flags from YAML `stacks` + `provision_stack` | `PhaseIntent` from `phases:` (+ `provision_stack` for mysql) |
| Docs “`stacks.infra` / `stacks.k8s` disabled” | “Leaf `phases:` omit infra/k8s refs” |
| Validate codes `stacks_*_no_inventory` | `phase_intent_*_no_inventory` / `inventory_*_phases_omitted` |

### Intent inference matrix (Phase 1+)

| Intent flag | True when `phases:` contains any of |
|-------------|-------------------------------------|
| `k8s` | `atlas-k8s-core/cluster`, `atlas-k8s-addons/addons` |
| `infra` | `atlas-infra-edge/infra`, `atlas-node-foundation/init-infra`, `atlas-node-foundation/init-infra-post` |
| `postgresql` | `atlas-postgresql/cluster` (canonical pg phase ref) |
| `redis` | `atlas-redis/cluster` |
| `kafka` | `atlas-kafka/cluster` |
| `jenkins` / agents | presence of `atlas-jenkins-agent/agent` (validate groups via inventory, not a YAML stack flag) |

Exact refs must match live `_template/*/cluster.yaml` at implementation time.
`provision_stack` remains the provision/TF selector and may corroborate intent
(`mysql` still uses `provision_stack == "mysql"` until a phase ref exists).

### Out of scope

- Renaming or deleting the **`docs/stacks/`** documentation tree.
- Removing or renaming **`provision_stack`** in compute-provision overlays.
- Changing playbook repos or phase alias names.
- Merging infra into k8s leaves (separate leaf `infra_edge` stays).

## Current runtime (Phase 4 + post-cleanup)

- Intent flags: `infer_phase_intent` / `PHASE_INTENT_REFS` /
  `PhaseIntent` in `clusterctl/phase_intent.py`
- Plan: `phases:` slice + inventory `when` only
- Public templates, org baseline, inventory labs: **no** `stacks:` key
- Present `stacks:` in any cascade fragment → **`StacksRemovedError`**
  (validate issue code **`stacks_removed`**, not `cluster_load_failed`)
- Inventory mismatch codes: `phase_intent_*_no_inventory` /
  `inventory_*_phases_omitted` (no legacy `stacks_*` validate codes)
- `clusterctl/stacks.py` **deleted** (no migration helper left)
- Product docs folder `docs/stacks/` **kept** (runbooks, not YAML key)

### Post-Phase-4 cleanup (contract / naming / docs)

| Step | Result |
|------|--------|
| A | Typed `StacksRemovedError`; validate/smoke report `stacks_removed` |
| B | Removed dead `load_phase_intent`; renamed legacy validate codes |
| C | ADR/docs wording matched runtime (`PhaseIntent`; hard delete of `stacks.py`; no soft-delete prose) |
| D | Strengthened grep-gate: legacy validate codes + retired APIs hard-banned in `clusterctl/`; repo allowlist = CHANGELOG + ADR + phase gates + negative tests |
| E | Offline full verification: `./tests/run_ci.sh` (no live labs) |

## Touchpoint inventory (grep map)

### Engine (`clusterctl/`)

| Path | Role |
|------|------|
| ~~`stacks.py`~~ | **deleted (Phase 4)** |
| `phase_intent.py` | Intent from `phases:` for inventory validate |
| `phase_plan.py` | plan from `phases:` (+ `when`); filter API removed Phase 2 |
| `validate.py` | `infer_phase_intent` ↔ inventory groups |
| `cluster_config.py` / `playbooks_config.py` | **`StacksRemovedError`** at load |
| `exceptions.py` | `StacksRemovedError` (`code=stacks_removed`) |
| `validate.py` / `smoke.py` | map load → issue `stacks_removed` |
| `phase_filter.py` | inventory `when` filter only |

### Public YAML (`clusters/`)

| Path | Notes |
|------|-------|
| `_template/k8s_full/cluster.yaml` | **no `stacks:`** (Phase 3) |
| `_template/infra_edge/cluster.yaml` | **no `stacks:`** (Phase 3) |
| `_template/jenkins_agent/cluster.yaml` | **no `stacks:`** (Phase 3) |
| `_template/redis/cluster.yaml` | **no `stacks:`** (Phase 3) |
| `_template/kafka/cluster.yaml` | **no `stacks:`** (Phase 3) |
| `_template/postgresql/cluster.yaml` | **no `stacks:`** (Phase 3) |
| `_template/cluster.yaml` | parent scaffold — **no `stacks:`** |
| `default/default/cluster.yaml` | **no `stacks:`** example (Phase 3) |

### Docs

| Path | Notes |
|------|-------|
| `docs/cluster-config-v2.md` | no `stacks` schema key; hard-reject + `stacks_removed` callout |
| `docs/validate.md` | `stacks_removed` + `phase_intent_*` / `inventory_*_phases_omitted` |
| `docs/clusters.md` | groups align with phase intent |
| `docs/stacks/*.md` | product runbooks — reworded off YAML `stacks.*` (files **kept**) |

### Tests (primary)

| Path | Notes |
|------|-------|
| `tests/test_phase_intent.py` | Phase 4 SoT: intent inference + load reject |
| `tests/test_phase_plan.py`, `test_phase_aliases_g2.py` | fixtures without `stacks` |
| `tests/test_*_orchestration.py`, `test_ci_*_cluster.py` | phases-only templates |
| `tests/test_validate_all_gates.py`, `test_smoke_validate_v2.py`, … | fixtures without `stacks` |

### Inventory (sibling `atlas-inventory`, Phase 3)

| Path | Notes |
|------|-------|
| `clusters/ci/**`, `clusters/dev/**`, `clusters/lab/**` | **`stacks:` removed** |

## Consequences

### Positive

- One plan DSL: what you list in `phases:` is what can run.
- Less surprise (no silent skip).
- Smaller schema surface for publish/templates.

### Negative / follow-up

- Leaves that relied on thick `phases` + `stacks` toggles must slim `phases:`
  (none in public templates today).
- Breaking: existing private `cluster.yaml` with `stacks:` fail at load with
  `stacks_removed` until the key is removed.
- Grep-gate (Phase D) keeps legacy validate codes / retired stack APIs out of
  `clusterctl/` and out of the tree outside history allowlists.

## Implementation plan (Phases 0–4)

| Phase | Work | Done when |
|-------|------|-----------|
| Phase 0 | This ADR + touchpoint inventory + gate | Contract accepted; **no behavior change** |
| Phase 1 | Infer intent from `phases:`; warn on redundant/conflicting `stacks:`
  (`stacks_legacy`); stop applying `skip_phase_refs` | Validate green; plan no longer silently filters |
| Phase 2 | Remove plan filter + `stacks_skipped` UX; rewrite/delete `test_stacks_g5` | Plan == phases slice |
| Phase 3 | Delete `stacks:` from templates, baseline, inventory; reword docs | Grep clean outside CHANGELOG/ADR |
| Phase 4 | Delete `stacks.py` API; reject `stacks:` key; grep-gate | Key only in history |

## Breaking changes checklist

- [x] Plan does not apply `skip_phase_refs`
- [x] Validate intent inferred from `phases:` (not YAML `stacks.enabled`)
- [x] Plan filter / `stacks_skipped` UX removed
- [x] Public `_template/*/cluster.yaml` omit `stacks:`
- [x] Org baseline omits `stacks:` example (or documents removal)
- [x] Inventory labs omit `stacks:`
- [x] `clusterctl/stacks.py` removed / non-SoT
- [x] Present `stacks:` → hard error (`StacksRemovedError` / `stacks_removed`)
- [x] Docs (`cluster-config-v2`, validate, product stacks prose) updated
- [x] Grep-gate: retired YAML key / skip API / legacy validate codes only in
  CHANGELOG + ADR history (+ phase gates / negative tests)

## References

- `clusterctl/stacks.py` — **deleted (Phase 4)**; intent in `phase_intent.py`
- `clusterctl/phase_plan.py` — plan from `phases:` (+ `when`); filter API removed Phase 2
- `docs/cluster-config-v2.md` — schema SoT (no `stacks:` key)
- `provision_stack` in `atlas-compute-provision.yml` — **kept**
- `docs/stacks/` — product runbooks — **kept**
