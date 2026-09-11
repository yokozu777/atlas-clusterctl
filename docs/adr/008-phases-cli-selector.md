# ADR 008 — Unified `--phases` CLI selector (replace `--from` / `--to`)

- **Status:** Accepted (Phase 5 — offline `./tests/run_ci.sh` green at product
  acceptance; ADR complete). Cleanup **Variant B** complete (Phases 0–3 — dual
  docs anti-regression gate purged).
- **Date:** 2026-07-28
- **Deciders:** atlas-clusterctl maintainers
- **Related:** [clusterctl.md](../clusterctl.md), ADR 007 (inline aliases), ADR 005

> **Scope split:** product Phase 5 `run_ci` green is **acceptance-time proof**, not
> a claim about the current tree after later work. Variant B offline proof is the
> ADR 008 unittest suite + argparse/dest-name hygiene; full `./tests/run_ci.sh`
> debt (if any) is **out of scope** for Variant B — see Cleanup Phase 3 evidence.

## Context

`plan` / `run` historically took a phase window as two flags:

```bash
./cluster plan --from provision --to k8s-addons
./cluster run --from init --to k8s-addons
```

That is a range over ordered leaf `phases:` (inclusive), not an arbitrary set.
Two flags are harder to remember and read than one selector.

## Decision

### Target CLI

| Form | Meaning |
|------|---------|
| `--phases init` | single phase |
| `--phases provision..k8s-addons` | inclusive range; order from leaf `phases:` |
| `--phases provision,k8s-addons` | explicit comma list / CSV set; **order = leaf `phases:`**, not CSV |
| `-p` | short alias for `--phases` |

Boundaries / list items are phase **aliases** or full `repo/entry` refs (ADR 007).

### Legacy `plan` / `run` flags

`--from` / `--to` on `plan` / `run` are **removed** (Phase 4). Use `--phases`
(`NAME` | `start..end` | `a,b,c`). During Phases 1–3 they were dual-read and
**deprecated** in help; mixing with `--phases` was an ERROR.

`init --from` and `export_template --from` are **out of scope** (different meaning).

### Sibling inventory

Private **`atlas-inventory`** lab READMEs / `group_vars` comments must teach
`--phases` (not CLI-like `cluster plan|run …` with retired phase-window flags).

**Cleanup Variant B:** the dual docs anti-regression gate is **purged**.
Cleanup Phase 1 removed Python `tests/adr_008_legacy_cli.py` from clusterctl;
Cleanup Phase 2 deleted inventory `scripts/check-no-legacy-phase-window.sh`.
Permanent enforcement is argparse + `from_stage`/`to_stage` dest-name hygiene
under `clusterctl/` (no docs twin SoT).

### Selector grammar

| Input | Result |
|-------|--------|
| `init` | range `from=init`, `to=init` |
| `provision..k8s-addons` | inclusive range |
| `provision,k8s-addons` | explicit set (≥2 names); leaf order |
| `provision .. k8s-addons` | OK — trim whitespace around `..` |
| empty / whitespace | ERROR |
| `..` / `a..` / `..b` | ERROR |
| more than one `..` | ERROR |
| mix `..` and `,` | ERROR |
| empty CSV item / duplicate CSV name | ERROR |
| single CSV item (`init,` / lone comma form) | ERROR — use `NAME` without commas |
| Unicode `…` / `‥` / `⋯` lookalikes for `..` | ERROR — use ASCII `..` |
| Unicode en/em dash (`–` / `—`) | ERROR — use ASCII `-` in names or `..` for ranges |
| unknown name / not in plan | ERROR at plan resolve |
| `start` after `end` in range | ERROR at plan resolve |

### Out of scope

- Changing YAML `phases:` / inline aliases.
- Rewiring `stage` / `play` positional args (**superseded target:** [ADR 009](009-unify-run-stage-play.md)
  unify into `run`; Phase 0 contract only as of that ADR).
- Live lab deploys.
- Renaming `init --from` / `export_template --from`.

## Current runtime (Phase 5)

Phase 4/5 product runtime, plus **Cleanup Variant B complete** (Phases 0–3).

Do **not** conflate:

| Proof | Meaning |
|-------|---------|
| **Product Phase 5** checklist | Offline `./tests/run_ci.sh` was green at ADR acceptance (historical; no live labs). |
| **Variant B** offline proof | ADR 008 unittest suite + permanent argparse/dest-name hygiene. Full `run_ci` may stay red for unrelated pre-existing public-track debt — **out of scope** for Variant B (Cleanup Phase 3 evidence). |

- Phase 5 gate: `tests/test_adr_008_phases_cli_selector_phase5.py`.
- **No** `tests/adr_008_legacy_cli.py` / docs CLI-like scanner.
- Permanent hygiene: `plan`/`run` argparse `--phases`/`-p` only; negative
  argparse tests; `git grep` ban on `from_stage`/`to_stage` outside allowlist
  (`tests/test_adr_008_phases_cli_selector_phase4.py`).
- Inventory `check-no-legacy-phase-window.sh` **removed** (Cleanup Phase 2).

### Phase 4 runtime (retained)

- `parse_phases_selector` → `PhaseRangeSelector` | `PhaseListSelector`.
- `resolve_cli_phase_window(phases_selector=…)` only (no legacy dual-read).
- `select_explicit_phase_refs` / `resolve_phase_execution_plan(only_phases=…)`.
- `plan` / `run` argparse: `--phases` / `-p` only (no `from_stage` / `to_stage`).
- Dest-name grep-gate under `clusterctl/` (allowlisted ADR/CHANGELOG/tests).
- Operator docs teach `--phases`; no Python docs twin scanner (Cleanup Phase 1).

## Target end state

- Offline CI green at **product Phase 5** acceptance; no live labs required.
  **Done** (historical). Current-tree `run_ci` debt ≠ Variant B scope.
- Post-complete cleanup **Variant B**: Phases **0–3 complete** (verify + close).

## Post-complete cleanup — Variant B (legacy anti-regression purge)

Phases **0–5** of this ADR delivered `--phases` and **removed** `plan`/`run`
`--from`/`--to` from argparse. What remains is **scaffolding that only exists to
ban teaching / reintroducing those flags** (docs grep twin SoT). That scaffolding
is itself legacy relative to the shipped CLI.

### Decision (Cleanup Phase 0 — locked)

**Variant B — full purge of legacy anti-regression from the repos.**

After cleanup:

| Keep (permanent CLI hygiene) | Delete (legacy anti-regression) |
|------------------------------|----------------------------------|
| `plan`/`run` argparse: only `--phases`/`-p`; unknown `--from`/`--to` → error | `tests/adr_008_legacy_cli.py` (`PLAN_RUN_LEGACY_PHASE_WINDOW_PATTERN`, `find_legacy_phase_window_hits`) |
| Negative tests: `parse_args(["plan", "--from", …])` fails | Inventory `scripts/check-no-legacy-phase-window.sh` |
| Grep / assert: no `dest="from_stage"` / `dest="to_stage"` under `clusterctl/` | Phase-gate asserts that require the `.sh` or Python docs scanner |
| Operator docs teach `--phases` only (manual / normal review) | Twin SoT comment “keep `.sh` PATTERN= in sync with Python” |
| CHANGELOG / ADR history mentioning dual-read / Phase 1–4 removal | Docs that tell operators to run `check-no-legacy-phase-window.sh` |

**Rejected — Variant A:** keep Python docs grep-gate, delete only the inventory
`.sh` duplicate. Rejected because it leaves a permanent “legacy window” product
surface (`adr_008_legacy_cli.py`) after the flags themselves are gone.

### Out of scope (unchanged)

- Renaming or removing `./cluster init --from` (copy-source cluster id).
- Renaming or removing `export_template --from` (source lab id).
- Changing `--phases` grammar or YAML `phases:`.
- Rewriting ADR 008 Phase 0–5 history / checklist checkmarks.
- Live lab redeploys.
- Controller junk (`tfstate-repo/` bak trees, untracked workspace).

### Cleanup implementation plan

| Cleanup phase | Work | Done when |
|---------------|------|-----------|
| **0** | Lock Variant B + out-of-scope in this ADR; gate test; CHANGELOG | **This section + gate green** |
| **1** | `atlas-clusterctl`: remove Python docs scanner + phase-gate deps; update ADR/docs/local-labs; keep argparse + dest-name guards | **Done** — no `adr_008_legacy_cli`; ADR 008 suite / hygiene green (full `run_ci` not required) |
| **2** | `atlas-inventory`: delete `scripts/check-no-legacy-phase-window.sh` | **Done** — file gone from HEAD |
| **3** | Verify: script basename absent outside ADR/CHANGELOG/cleanup gates; ADR 008 suite + hygiene green; inventory `.sh` gone; `run_ci` executed (note unrelated pre-existing fails) | **Done** — cleanup complete |

**PR order:** clusterctl Cleanup Phase 1 **before** inventory Phase 2 (otherwise
sibling tests fail when the script disappears).

### Cleanup Phase 0 acceptance

1. Status line records Variant B Phase 0 locked.
2. This section names Variant B, rejects A, lists keep/delete tables, out-of-scope,
   and Cleanup Phases 0–3.
3. Gate: `tests/test_adr_008_legacy_window_cleanup_phase0.py`.
4. ADR index + CHANGELOG mention cleanup Variant B Phase 0.
5. **No** deletion of `.sh` / `adr_008_legacy_cli.py` in Phase 0 (code purge = 1–2).

### Cleanup Phase 0 (done)

Locked 2026-07-28: Variant **B**; dual docs-gate scheduled for removal; permanent
hygiene = argparse + `from_stage`/`to_stage` dest ban under `clusterctl/`.

### Cleanup Phase 1 acceptance

*(Historical Phase 1 DoD snapshot. Items 4 and 6 describe mid-cleanup state —
**superseded by Cleanup Phase 2/3 Done**.)*

1. `tests/adr_008_legacy_cli.py` and `tests/test_adr_008_legacy_cli.py` deleted.
2. Phase 2 / Phase 4 gates no longer import the docs scanner or run the inventory
   `.sh`.
3. Permanent hygiene retained: argparse reject `plan`/`run --from/--to`;
   `dest="from_stage"` / `to_stage` absent under `clusterctl/`; dest-name
   allowlist grep in Phase 4 gate.
4. *(Historical)* Operator docs (`clusterctl.md`, `local-labs.md`) no longer
   require running the inventory script; they pointed at Cleanup Phase 2 for
   `.sh` deletion.
5. Gate: `tests/test_adr_008_legacy_window_cleanup_phase1.py`.
6. *(Historical)* Inventory `.sh` may still exist on disk at Phase 1 exit
   (deleted in Cleanup Phase 2).

### Cleanup Phase 1 (done)

Verified 2026-07-28: Python docs twin SoT removed from atlas-clusterctl; Phase 4
gate keeps argparse + dest-name hygiene only.

### Cleanup Phase 2 acceptance

1. `atlas-inventory/scripts/check-no-legacy-phase-window.sh` deleted from inventory
   HEAD (sibling checkout when present).
2. No operator doc instructs running that script (`local-labs.md`, `clusterctl.md`).
3. Clusterctl gates do not reference or invoke the script.
4. Gate: `tests/test_adr_008_legacy_window_cleanup_phase2.py`.
5. ADR index + CHANGELOG record Cleanup Phase 2.
6. Historical mentions remain allowed in ADR/CHANGELOG only.

### Cleanup Phase 2 (done)

Verified 2026-07-28: inventory twin `.sh` removed; dual docs-gate fully gone.

### Cleanup Phase 3 acceptance

1. Basename `check-no-legacy-phase-window` appears only in ADR / CHANGELOG /
   `tests/test_adr_008_legacy_window_cleanup_*` (operator docs scrubbed).
2. No `./scripts/check-no-legacy-phase-window.sh` run instructions anywhere in
   tracked operator docs.
3. Sibling inventory (when present): script file absent and not git-tracked;
   durable `tfstate/` still present.
4. Permanent hygiene still green: argparse reject + dest-name allowlist grep
   (Phase 4 gate).
5. Offline ADR 008 suite green (`python3 -m unittest discover -p 'test_adr_008*.py'`).
6. `./tests/run_ci.sh` executed; any remaining failures must be **unrelated**
   pre-existing public-track debt (not introduced by Variant B) — recorded below.
   Variant B does **not** require a green full `run_ci` (product Phase 5 ≠
   Variant B verify).
7. Gate: `tests/test_adr_008_legacy_window_cleanup_phase3.py`.
8. ADR status records Variant B **complete**; checklist Phase 3 checked.

### Cleanup Phase 3 (done)

Verified 2026-07-28: Variant B closed — dual docs anti-regression gate purged;
permanent hygiene = argparse + `from_stage`/`to_stage` dest ban.

Verify evidence:

| Check | Result |
|-------|--------|
| Script basename outside ADR/CHANGELOG/cleanup gates | 0 |
| Inventory `.sh` file + git index | absent |
| Durable `tfstate/{ci/infra,dev/mxhash}` | present |
| `test_adr_008*.py` | 66 OK |
| Phase 4 argparse + dest-name hygiene | OK |
| `./tests/run_ci.sh` | executed; **pre-existing** failures remain (docker validate mocks, packaging report sync, Phase 7 report wording) — **not** caused by Variant B; **out of scope** for Variant B close |

## Touchpoint inventory

| Path | Role |
|------|------|
| `clusterctl/phase_selector.py` | parse + CLI window |
| `clusterctl/phase_plan.py` | range slice + explicit set |
| `clusterctl/__main__.py` | argparse / `_resolve_plan` |
| `docs/clusterctl.md` | operator examples |
| `tests/test_phases_selector_contract.py` | matrix |
| `tests/test_adr_008_*` | phase gates (dest-name + argparse; no docs scanner) |
| `tests/test_adr_008_legacy_window_cleanup_phase0.py` | Cleanup Phase 0 gate |
| `tests/test_adr_008_legacy_window_cleanup_phase1.py` | Cleanup Phase 1 gate |
| `tests/test_adr_008_legacy_window_cleanup_phase2.py` | Cleanup Phase 2 gate |
| `tests/test_adr_008_legacy_window_cleanup_phase3.py` | Cleanup Phase 3 gate |

## Implementation plan

| Phase | Work | Done when |
|-------|------|-----------|
| Phase 0 | ADR + selector helper + contract; **no argparse** | Contract locked |
| Phase 1 | Wire `--phases`/`-p`; dual-read from/to; conflict ERROR | Equivalent windows |
| Phase 2 | Docs happy-path; deprecate from/to in help | Docs SoT |
| Phase 3 | CSV explicit set (leaf order) | Skip-middle works |
| **Phase 4** | Remove `--from`/`--to`; grep-gate | Legacy flags gone |
| Phase 5 | Offline `./tests/run_ci.sh` | Green; no live labs |
| Cleanup 0–3 | Variant B anti-regression purge | See Post-complete cleanup |

## Breaking changes checklist

- [x] Target selector grammar locked (Phase 0)
- [x] Single + `start..end` decided; CSV deferred with hard ERROR **at Phase 0** (lifted in Phase 3)
- [x] Contract matrix tests exist (Phase 0)
- [x] **No argparse wiring** yet (Phase 0)
- [x] `--phases` on `plan`/`run` (+ conflict with from/to) (Phase 1)
- [x] Docs happy-path (Phase 2)
- [x] CSV explicit set (Phase 3)
- [x] Remove `--from`/`--to` (Phase 4)
- [x] Offline `./tests/run_ci.sh` green (Phase 5)
- [x] Cleanup Variant B Phase 0 locked (decision + gate; no code purge yet)
- [x] Cleanup Phase 1 — remove Python docs scanner / script deps (clusterctl)
- [x] Cleanup Phase 2 — delete inventory `check-no-legacy-phase-window.sh`
- [x] Cleanup Phase 3 — verify + close (Variant B complete)

## References

- [clusterctl.md](../clusterctl.md)
- ADR 007 — inline phase aliases
- `clusterctl/phase_plan.py` — `resolve_phase_execution_plan` / `select_explicit_phase_refs`
- `clusterctl/phase_selector.py` — `parse_phases_selector` / `resolve_cli_phase_window`
