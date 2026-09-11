# ADR 006 — Redundant `playbooks_enabled: true` (infer from `playbooks:`)

- **Status:** Accepted (Phase 5 complete — offline `./tests/run_ci.sh` + sample
  validate/plan green; no live labs)
- **Date:** 2026-07-28
- **Deciders:** atlas-clusterctl maintainers
- **Related:** [cluster-config-v2.md](../cluster-config-v2.md), ADR 005

## Context

Deployable leaves already carry a full `playbooks:` catalog (+ `phases:`).
Templates and labs also repeat:

```yaml
playbooks_enabled: true
```

That flag is largely noise: `ClusterConfigV2.effective_playbooks_enabled()` already
treats a missing key as **enabled when `playbooks.repos` is non-empty**.

Operators still need an explicit **off** switch (`playbooks_enabled: false`) for
cascade / temporary disable without deleting the catalog.

## Decision

### Semantics (SoT)

| YAML | Effective runner / sync |
|------|-------------------------|
| omit `playbooks_enabled` + non-empty `playbooks:` | **enabled** (infer) |
| omit `playbooks_enabled` + no `playbooks` repos | **disabled** |
| `playbooks_enabled: true` | enabled (redundant when `playbooks:` present) |
| `playbooks_enabled: false` | **disabled** (override; key **kept**) |

Plan SoT remains **`phases:`** (ADR 005). This ADR only clarifies the enable flag.

### Target end state

- Public `_template/*/cluster.yaml` and org baseline omit redundant `true` — **done (Phase 2)**.
- Inventory labs omit redundant `true` — **done (Phase 3)**.
- Docs / error hints say: define `playbooks:` (+ `phases:`); use `false` to disable — **done (Phase 1 / 4)**.
- Unittest fixtures omit redundant `"playbooks_enabled": True` when they already
  carry a `playbooks:` catalog — **done (Phase 4)**.
- Offline CI + sample validate/plan confirm infer path — **done (Phase 5)**.
- Key `playbooks_enabled` remains in schema for **`false`** and explicit override.
- Out of scope: deleting the key from dataclasses / cascade merge API.

### Out of scope (this ADR)

- Removing `playbooks_enabled` from the schema entirely.
- Changing `phases:` / playbook repo layout.
- Live lab deploys.

## Current runtime (Phase 5)

- Infer: `ClusterConfigV2.effective_playbooks_enabled()` and
  `playbooks_feature_enabled(raw)` (same omit→infer rule).
- Resolve path: `resolve_playbooks_enabled(leaf, config_v2=…)` — leaf explicit wins,
  else merged v2 effective flag.
- User-facing errors / hints: **define `playbooks:`** (+ optional `false`).
- `cluster_config_v2_to_yaml_dict`: emits `playbooks_enabled` only when **explicit**.
- Public `_template/**` + `clusters/default/default`: **no** redundant `true`.
- Sibling `atlas-inventory` deployable labs (`ci/*`, `dev/mxhash`, …): **no** redundant
  `true` (stubs without `playbooks:` correctly stay disabled).
- Operator docs controller contract: presence of `playbooks:` (not mandatory `true`).
- Unittest fixtures: redundant `"playbooks_enabled": True` removed where the same
  fixture already defines `playbooks:`. Remaining `True` / `False` literals are
  intentional (infer matrix, schema cleanup, enable-without-catalog stubs, gates).
- Verification: `./tests/run_ci.sh` green; sample validate + execution plan on a leaf
  that **omits** `playbooks_enabled` (infer-enabled) — no live labs.

## Touchpoint inventory (grep map)

### Engine

| Path | Role |
|------|------|
| `playbooks_config.py` | parse / merge / `effective_playbooks_enabled` / `playbooks_feature_enabled` / resolve |
| `cluster_config.py` | load → `resolve_playbooks_enabled` |
| `cluster_config_loader.py` | dump emits explicit true/false only |
| `context.py` | `ctx.playbooks_enabled` |
| `playbooks_sync.py` / `playbooks_cmd.py` / `playbooks_repos.py` | gates on effective flag |
| `role_repos.py` | deprecated re-export shim (Phase 5) |
| `validate.py` / `docker_validate.py` / `repo_conventions.py` | hints → define `playbooks:` |

### Public YAML

| Path | Notes |
|------|-------|
| `clusters/_template/**/cluster.yaml` | **no redundant `true`** (Phase 2) |
| `clusters/default/default/cluster.yaml` | **no redundant `true`** (Phase 2) |

### Inventory (sibling `atlas-inventory`)

| Path | Notes |
|------|-------|
| `clusters/**/cluster.yaml` | **no redundant `true`** (Phase 3) |

### Docs / tests

| Path | Notes |
|------|-------|
| `docs/cluster-config-v2.md` | callout + controller contract + example without mandatory `true` |
| `tests/test_playbooks_enabled_infer.py` | infer / cascade matrix (keeps explicit `True`/`False`) |
| `tests/test_adr_006_*` | phase gates 0–5 |
| unittest fixtures | Phase 4 hygiene: omit redundant `True` when `playbooks:` present |
| `./tests/run_ci.sh` | Phase 5 offline verification (no live labs) |

## Consequences

### Positive

- Less YAML noise; presence of `playbooks:` is the enable signal.
- `false` remains an explicit kill switch.
- Public SoT, inventory labs, fixtures, and CI match infer contract.

### Negative / follow-up

- A small allowlist of fixtures still passes explicit `True`/`False` on purpose
  (infer matrix, kill-switch, enable-without-catalog stubs).

## Implementation plan

| Phase | Work | Done when |
|-------|------|-----------|
| Phase 0 | This ADR + schema doc callout + infer/cascade test matrix | Contract locked; **no YAML deletion** |
| Phase 1 | Align helpers / rewrite user-facing hints | No mandatory `true` in errors |
| Phase 2 | Drop `true` from public templates + org baseline | Public tree clean |
| Phase 3 | Drop `true` from inventory labs | Inventory clean |
| Phase 4 | Docs polish + fixture hygiene | Docs SoT + fixtures |
| **Phase 5** | Offline `./tests/run_ci.sh` (+ sample validate/plan) | Green; no live labs |

## Breaking changes checklist

- [x] Public templates omit redundant `playbooks_enabled: true`
- [x] Org baseline omits redundant `true`
- [x] Inventory labs omit redundant `true`
- [x] Docs example omits redundant `true`; documents infer + `false`
- [x] User-facing errors do not require setting `true`
- [x] Infer / cascade / `false` override covered by tests (Phase 0)
- [x] `playbooks_feature_enabled` omit→infer aligned (Phase 1)
- [x] `playbooks_enabled: false` still disables sync/run (covered by tests)
- [x] Docs controller contract + unittest fixture hygiene (Phase 4)
- [x] Offline `./tests/run_ci.sh` (+ sample validate/plan) green (Phase 5)

## References

- `clusterctl/playbooks_config.py` — `effective_playbooks_enabled` / `playbooks_feature_enabled` / resolve
- [cluster-config-v2.md](../cluster-config-v2.md)
- ADR 005 — `phases:` plan SoT (orthogonal)
- `./tests/run_ci.sh` — public-track offline CI
