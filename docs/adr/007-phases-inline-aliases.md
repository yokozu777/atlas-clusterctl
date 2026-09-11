# ADR 007 — Inline phase aliases in `phases:` (remove `phase_aliases:`)

- **Status:** Accepted (Phase 5 complete — offline `./tests/run_ci.sh` + sample
  plan/stage resolve green; no live labs)
- **Date:** 2026-07-28
- **Deciders:** atlas-clusterctl maintainers
- **Supersedes (partial):** ADR 005 SoT row «Short CLI names = `phase_aliases`»
- **Related:** [cluster-config-v2.md](../cluster-config-v2.md), ADR 005, ADR 006

## Context

Deployable leaves historically carried two related blocks:

```yaml
phases:
  - atlas-compute-provision/templates
  - atlas-compute-provision/provision
  - atlas-node-foundation/init
phase_aliases:
  templates: atlas-compute-provision/templates
  provision: atlas-compute-provision/provision
  init: atlas-node-foundation/init
```

`phases:` is plan SoT (order + refs). `phase_aliases:` was a second dictionary for
CLI short names — always 1:1 with the same refs, a common drift source.

## Decision

### Target YAML (single SoT)

```yaml
phases:
  - templates: atlas-compute-provision/templates
  - provision: atlas-compute-provision/provision
  - init: atlas-node-foundation/init
  - k8s-core: atlas-k8s-core/cluster
  - k8s-addons: atlas-k8s-addons/addons
```

| Form | Meaning |
|------|---------|
| single-key map `{alias: repo/entry}` | ordered phase + CLI alias |
| bare string `repo/entry` | ordered phase **without** short alias |
| top-level `phase_aliases:` | **removed** — hard-reject at load |

### Semantics

| Case | Result |
|------|--------|
| `{alias: ref}` | append `ref` to plan; register `alias → ref` |
| bare `repo/entry` | append ref; **no** alias for that item |
| duplicate alias | ERROR |
| duplicate phase ref | ERROR |
| multi-key map / empty map / non-string value | ERROR |
| alias empty or contains `/` | ERROR |
| alias value not `repo/entry` | ERROR |
| top-level `phase_aliases:` present | ERROR (`PhaseAliasesRemovedError` / `phase_aliases_removed`) |
| CLI `stage <alias>` / `plan --phases` | resolve from **derived** alias map of effective `phases:` |

### Runtime model

- `PhasesConfig.phases` — ordered refs (plan SoT).
- `PhasesConfig.phase_aliases` — **derived** from inline maps (dataclass field kept).
- Cascade: `phases` list **replace**; aliases recomputed from winning list.
  Omit inherits; explicit `phases: []` replaces with empty (does not inherit).
- Dump / `config show`: emit only inline `phases:` (no top-level `phase_aliases:`);
  inconsistent `PhasesConfig` (dup refs / drifted aliases) errors on dump.
- Duplicate phase refs / aliases rejected at **parse** (not only validate).
- **No dual-read** of legacy `phase_aliases:`.

### Bare refs

Allowed. Phases without an alias are only addressable by full `repo/entry` in CLI.

## Current runtime (Phase 5)

- Engine parses inline maps + bare strings; rejects top-level `phase_aliases:`.
- Typed error: `PhaseAliasesRemovedError` (`phase_aliases_removed`).
- Public `_template/**` + org baseline: inline (Phase 1–2).
- Sibling `atlas-inventory` labs: inline (Phase 3).
- Operator docs (`cluster-config-v2`, `validate`, docs index): inline form only;
  top-level key mentioned only as rejected / removed (Phase 4).
- Unittest fixtures: no redundant YAML `"phase_aliases":` writers outside
  intentional negative tests (reject matrix / ADR gates). `PhasesConfig(phase_aliases=…)`
  kwargs remain valid (derived field).
- Verification: `./tests/run_ci.sh` green; sample validate + execution plan with
  `--phases` short aliases on a leaf that uses **only** inline `phases:`
  (no top-level `phase_aliases:`) — no live labs.
- Follow-up hardening: duplicate refs rejected at parse; dump refuses drifted
  alias maps; empty `phases: []` is replace (not inherit).

## Target end state

- Public / inventory / docs / fixtures on inline form — **done through Phase 4**.
- Offline `./tests/run_ci.sh` + sample plan/stage resolve — **done (Phase 5)**.
- Live lab deploys — out of scope.

## Out of scope

- Renaming existing aliases (`k8s-core`, …).
- Changing phase order / playbooks catalog / git sync.
- Dual-read / soft migration window for `phase_aliases:`.
- Live lab deploys.
- Removing short CLI names entirely.

## Touchpoint inventory (grep map)

### Engine

| Path | Role |
|------|------|
| `exceptions.py` | `PhaseAliasesRemovedError` |
| `cluster_config.py` | `reject_removed_phase_aliases_key` |
| `playbooks_config.py` | parse / dump / merge `phases`; reject key |
| `phase_plan.py` | unknown-alias hint; `--phases` via derived aliases |
| `validate.py` / `__main__.py` | `phase_aliases_removed` report |

### Public YAML / inventory

| Path | Notes |
|------|-------|
| `clusters/_template/**/cluster.yaml` | inline (Phase 2) |
| `clusters/default/default/cluster.yaml` | forbid-comments (Phase 2) |
| `atlas-inventory/clusters/**/cluster.yaml` | inline (Phase 3) |

### Docs / tests

| Path | Notes |
|------|-------|
| `docs/cluster-config-v2.md` / `validate.md` / `docs/README.md` | Phase 4 polish |
| `tests/test_phases_inline_aliases_contract.py` | parse/dump/reject matrix |
| `tests/test_adr_007_*` | phase gates 0–5 |
| `./tests/run_ci.sh` | Phase 5 offline verification (no live labs) |

## Consequences

### Positive

- One list is plan + CLI naming SoT across public tree, inventory, and docs.
- Negative tests still prove hard-reject of the legacy key.
- Offline CI + sample plan/stage confirm derived aliases end-to-end.

### Negative / follow-up

- None for this ADR; live lab deploys remain operator-owned.

## Implementation plan

| Phase | Work | Done when |
|-------|------|-----------|
| Phase 0 | ADR + schema callout + contract matrix | Contract locked; **no YAML deletion**; **no parse change** |
| Phase 1 | Parse/dump/merge/validate/hints; hard-reject; public SoT rewrite | Engine + public tree |
| Phase 2 | Verify-clean public tree + gate | Public tree clean |
| Phase 3 | Inventory labs rewrite | Inventory clean |
| Phase 4 | Docs polish + fixture hygiene | Docs SoT |
| **Phase 5** | Offline `./tests/run_ci.sh` (+ sample plan/stage) | Green; no live labs |

## Breaking changes checklist

- [x] Target YAML + semantics table locked (Phase 0)
- [x] Bare-ref + hard-reject `phase_aliases:` + no dual-read decided (Phase 0)
- [x] Contract matrix tests exist (Phase 0)
- [x] Engine parse/dump/merge rejects top-level `phase_aliases:` (Phase 1)
- [x] User-facing errors/hints point at inline `phases:` (Phase 1)
- [x] Public templates omit `phase_aliases:` (Phase 1 / Phase 2)
- [x] Public tree verify-clean gate (Phase 2)
- [x] Inventory labs omit `phase_aliases:` (Phase 3)
- [x] Docs examples use inline form only (Phase 4)
- [x] Offline `./tests/run_ci.sh` (+ sample plan/stage) green (Phase 5)

## References

- [cluster-config-v2.md](../cluster-config-v2.md)
- ADR 005 — `phases:` plan SoT (short-name SoT superseded here)
- `clusterctl/playbooks_config.py` — `PhasesConfig` / `parse_phases_config`
- `clusterctl/exceptions.py` — `PhaseAliasesRemovedError`
- `./tests/run_ci.sh` — public-track offline CI
