# ADR 009 — Unify `run` / `stage` / `play` into one execute verb

- **Status:** Accepted (Phase 5 complete + **alias hard-removal Phase 1–5 done** —
  CLI ``stage``/``play`` removed; docs/siblings teach ``run --phases``;
  ``./tests/run_ci.sh`` green after hard remove; see
  [Alias removal](#alias-removal-follow-up); product Phase 5 unittest gate
  does **not** subprocess ``run_ci`` — acceptance-time / CI workflow; see
  Current runtime)
- **Date:** 2026-07-31
- **Deciders:** atlas-clusterctl maintainers
- **Related:** [clusterctl.md](../clusterctl.md), [jenkins.md](../jenkins.md),
  ADR 007 (inline aliases), ADR 008 (`--phases` selector)

## Context

> **Historical problem statement (pre–Phase 1).** Current policy:
> [Decision](#decision) / [Current runtime (Phase 5)](#current-runtime-phase-5--alias-removal-phase-15).

Before Phase 1, operators and Jenkins faced three execute commands:

| Command | Granularity | Overrides (`--tags` / `--limit` / `-e`) |
|---------|-------------|------------------------------------------|
| `run` | 1..N phases from leaf plan | none |
| `stage` | exactly one phase | none (catalog invocations as in YAML) |
| `play` | one phase | yes — and **collapses** the phase to a single ansible invocation |

That split was hard to explain and blocked Jenkins `EXTRA_VARS` (e.g.
`provision_mode=destroy`): Pipeline Run called `stage`, but only `play` accepted
`-e`. Adding a Jenkins text field without a unified execute path could not work.

## Decision

### Target CLI — one verb

```bash
./cluster run                                    # full plan
./cluster run --phases provision..redis          # ADR 008 selector
./cluster run --phases atlas-redis/cluster       # former stage
./cluster run --phases redis --tags 204_… -e x=y # former play
./cluster run --phases provision -e provision_mode=destroy
./cluster run --dry-run
```

Canonical execute command: **`run`**. Phase window stays ADR 008
(`--phases` / `-p`).

### Override policy (normative)

Classifier: `clusterctl.run_overrides.classify_run_overrides` (Phase 0 helper;
wired into argparse in Phase 1).

| Inputs | `phase_count` | Mode | Behavior |
|--------|---------------|------|----------|
| no `--tags` (or `all`), no `--limit`, no `-e`, no `--root-ssh` | ≥1 | **`catalog`** | Run each selected phase with YAML invocations unchanged |
| only `-e` / `--extra-vars` (one or more) | ≥1 | **`merge_e`** | **Append** each `-e` to every catalog invocation; **do not** collapse |
| `--tags` ≠ `all` and/or `--limit` and/or `--root-ssh` | **1** | **`collapse`** | One ansible invocation per selected phase (former `play`) |
| `--tags` / `--limit` / `--root-ssh` | **>1** | **`error`** | Reject before ansible — selective overrides need a single phase |
| `--git-ssh` alone | any | *(flag only)* | Does **not** change mode (parity with today's `play`: flips git-ssh on stage) |

Notes:

1. **`merge_e` is the Jenkins `EXTRA_VARS` path** — full provision phase keeps
   tag-split invocations; `provision_mode=destroy` is visible on each.
2. **`collapse` + `-e`** — when selective overrides force collapse, `-e` values
   attach to that **single** invocation (former `play`).
3. Empty / whitespace-only `--tags` treats as `all`.
4. `phase_count == 0` is a plan-resolve error (ADR 008), not this classifier.
5. **Env `LIMIT`** (post-cleanup A1): equivalent to CLI `--limit` for classify /
   apply on **all** execute verbs (`run` / `stage` / `play`). Resolved by
   `resolve_run_limit` (CLI wins). Multi-phase + `LIMIT` → ERROR like `--limit`.

### Legacy command mapping

| Legacy | Target |
|--------|--------|
| `./cluster run …` | unchanged shape; gains override flags in Phase 1 |
| `./cluster stage NAME` | `./cluster run --phases NAME` |
| `./cluster play NAME --tags T -e E` | `./cluster run --phases NAME --tags T -e E` |

### Aliases (later phases)

- Phases **2–5**: `stage` / `play` were thin deprecated aliases of `run`
  (stderr warning).
- **Alias-removal Phase 1:** CLI ``stage`` / ``play`` **hard-removed** (unknown
  subcommands). Mapping table above remains historical.

### Jenkins contract (Phase 3)

- Parameter `EXTRA_VARS` (string, default empty): space-separated `key=value`
  tokens (no leading `-e` required).
- Parameters `TAGS` / `LIMIT` (string, default empty): optional `--tags` /
  `--limit` on each Run phase (empty/`all` tags → omit; selective → single-phase
  `PHASES` only, else clusterctl ERROR).
- Pipeline builds argv `-e key=value` **without** `eval` / shell interpolation of
  the raw string as a command.
- Run loop: `./cluster run --phases "$PHASE_REF"` + optional `--tags` / `--limit`
  + those `-e` args.
- Dedicated `PROVISION_MODE` choice is **out of scope** — `EXTRA_VARS` covers it.

## Current runtime (Phase 5 + alias removal Phase 1–5)

> **Scope note:** product Phase 5 `./tests/run_ci.sh` green is
> **acceptance-time proof** (no live labs). The Phase 5 unittest gate
> **does not subprocess** `run_ci.sh` (too heavy / fragile for every
> unittest discover). Ongoing green is enforced by
> [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) (`./tests/run_ci.sh`)
> and local maintainer re-runs before publish. Tree drift after acceptance is
> tracked by ongoing gates, not this ADR status line alone.

- ``./cluster run`` — sole execute verb (ADR 009); **alias-removal Phase 1–5 done**
  (CLI removed; docs/siblings migrated — no live teach of aliases;
  ``./tests/run_ci.sh`` green 2026-08-01).
- Operator docs teach ``run --phases`` (Phase 4); ``stage``/``play`` **removed**.
- Maintainer notes §4.9/§4.10 **Removed** cards (alias-removal Phase 3).
- External callers (inventory READMEs + compute-provision ADR) **migrated**
  (alias-removal Phase 4).
- Jenkins samples: ``EXTRA_VARS`` + ``run --phases`` (Phase 3).
- Offline ``./tests/run_ci.sh`` green at acceptance; sample dry-run coverage in
  Phase 5 gate (`tests/test_adr_009_unify_run_stage_play_phase5.py`) for
  ``run --phases … -e …`` (``merge_e``).
- ``./cluster stages`` list helper retained (unrelated).

### Phase 0–4 deliverables (retained)

- Contract + ``classify_run_overrides`` / ``apply_run_cli_overrides``.
- ``run`` override flags (former ``stage``/``play`` aliases removed in
  alias-removal Phase 1).
- Jenkins ``EXTRA_VARS`` + Pipeline ``run --phases``.
- Operator docs canonical ``run``.

## Target end state

- One execute verb: `run` with ADR 008 `--phases` + override flags.
- `-e` alone never collapses multi-invocation phases.
- Jenkins `EXTRA_VARS` works on the same path as CLI.
- Offline gates green; no live labs required for acceptance.

## Out of scope

- Changing leaf YAML `phases:` / invocations / ADR 007–008 selector grammar.
- Rewriting `plan` / `plan --json` (Jenkins stage loop stays).
- Dedicated Jenkins `PROVISION_MODE` choice (use `EXTRA_VARS`).
- Live lab deploys as acceptance proof.
- Removing `stages` (list helper) — unrelated inventory of phase names.

## Implementation plan

| Phase | Work | Done when |
|-------|------|-----------|
| **Phase 0** | This ADR + policy helper + contract matrix + docs callout + changelog | Contract locked; **no argparse wiring** — **done** |
| **Phase 1** | `run` accepts `--tags` / `--limit` / `-e` / `--root-ssh` / `--git-ssh`; apply `classify_run_overrides`; merge_e vs collapse | CLI `run … -e` works; multi-phase+tags errors — **done** |
| **Phase 2** | `stage` / `play` → deprecated aliases of `run`; help text | Aliases warn; behavior matches table — **done** |
| **Phase 3** | Jenkinsfile(+`.local`) `EXTRA_VARS`; `docs/jenkins.md`; Jenkinsfile contract test | UI → `-e` on Run — **done** |
| **Phase 4** | Operator docs (`clusterctl.md` examples) teach `run` as canonical | Docs SoT — **done** |
| **Phase 5** | Offline `./tests/run_ci.sh` (+ sample dry-run); optional alias cleanup PR | Green; no live labs — **done** (aliases were retained at product Phase 5; hard-removed in [Alias removal](#alias-removal-follow-up) Phase 1) |

## Breaking changes checklist

- [x] Target CLI + override policy table locked (Phase 0)
- [x] `merge_e` vs `collapse` vs multi-phase selective ERROR decided (Phase 0)
- [x] Legacy `stage` / `play` mapping + Jenkins `EXTRA_VARS` shape decided (Phase 0)
- [x] Contract matrix tests exist (Phase 0)
- [x] **No argparse wiring** yet (Phase 0)
- [x] `run` override flags + policy wiring (Phase 1)
- [x] `stage` / `play` deprecated aliases (Phase 2)
- [x] Jenkins `EXTRA_VARS` + docs (Phase 3)
- [x] Operator docs canonical `run` (Phase 4)
- [x] Offline `./tests/run_ci.sh` green (Phase 5)

## Consequences

### Positive

- One mental model for execute; Jenkins and CLI share `-e`.
- Destroy/recreate via `provision_mode=…` without editing inventory or collapsing
  tag-split provision phases.

### Negative / follow-up

- Operator examples teach ``run`` (Phase 4 done); legacy mapping remains in this ADR
  only.
- **Done (alias removal Phase 1):** CLI ``stage`` / ``play`` hard-removed
  (argparse unknown; ``stages`` kept).
- **Done (alias removal Phase 2):** ADR 009 / cutover gates no longer require
  aliases retained (`tests/test_adr_009_alias_removal_phase2.py`).
- **Done (alias removal Phase 3):** in-repo docs / notes / CHANGELOG Breaking —
  no live teach of aliases (`tests/test_adr_009_alias_removal_phase3.py`).
- **Done (alias removal Phase 4):** external inventory READMEs +
  ``atlas-compute-provision`` ADR migrated; sibling scan clean
  (`tests/test_adr_009_alias_removal_phase4.py`).
- **Done (alias removal Phase 5):** ``./tests/run_ci.sh`` green after hard remove
  (`tests/test_adr_009_alias_removal_phase5.py`); renamed
  ``_merge_extra_into_phase_plan`` (avoid ADR 008 retired-dest grep false
  positive on the former helper name).
- **Done (alias removal Phase 0):** hard remove locked; external caller inventory
  recorded.
- **Done (post-cleanup A1):** env ``LIMIT`` unified — no longer ``play``-only for
  classify; ``resolve_run_limit`` + shared ``_cmd_run_execute``.
- **Done (post-cleanup A2):** SoT docs / README / stack phase maps match public
  scaffolds (**4** phases for ``k8s_full`` / ``infra_edge``, start at ``provision``).
  Audit Phase 1: Typical order + Unicode gate; stack ``fact_caching`` dedupe.
- **Done (post-cleanup A3):** runtime validate hints use ``run`` (no ``./cluster
  play`` / ``stage`` in ``repo_conventions``).
- **Done (post-cleanup A4):** Jenkins plan example uses ``provision`` as typical
  ``[1/4]`` phase (not ``templates``).
- **Done (post-cleanup A5):** ``run -e`` / former ``play -e`` merge_e E2E; ADR
  clarifies Phase 5 gate does not subprocess ``run_ci`` (CI workflow does).
- **Done (post-cleanup B):** ``apply_play_cli_overrides`` docstring (tests-only /
  collapse-on-``-e``); ``notes/report_clusterctl.md`` teaches ``run --phases``.
- **Done (audit Phase 3):** notes §4.9 / §4.10 compressed to short cards (later
  retargeted to **Removed** in alias-removal Phase 3; SoT →
  ``docs/clusterctl.md`` + this ADR).
- **Done (audit Phase 2):** Status line aligned with A5 ``run_ci`` scope
  (acceptance-time / CI workflow; unittest gate does not subprocess); Context
  table marked historical pre–Phase 1.

## Alias removal (follow-up)

> **Phase 0 locked (2026-08-01); Phase 1–5 done.** Alias hard-removal complete:
> CLI ``stage`` / ``play`` unknown; docs/siblings teach ``run --phases``;
> ``./tests/run_ci.sh`` green (2026-08-01).

### Decision (normative)

| Topic | Lock |
|-------|------|
| Mechanism | **Hard remove** — ``stage`` / ``play`` are unknown subcommands (argparse). **No** silent shim; **no** Variant S stub release |
| Accidental call | Standard argparse “invalid choice” / usage; migration one-liner in CHANGELOG Breaking |
| Keep | ``./cluster stages`` (list helper); internal ``PhaseStagePlan`` / ``run_phase_stage``; historical ``apply_play_cli_overrides`` (tests-only) |
| External docs | Migrated to ``run --phases`` (alias-removal Phase 4) — inventory READMEs + compute-provision ADR; gate scans siblings when present |

### External callers inventory (Phase 0 scan → Phase 4 migrated)

Live ``./cluster stage`` / ``./cluster play`` outside ``atlas-clusterctl`` internals
(2026-08-01 workspace scan; **migrated 2026-08-01**). Jenkins samples in this
repo already use ``run --phases``. Sibling playbook repos: **no** CLI hits.

| Repo | Path | Was | Status |
|------|------|-----|--------|
| `atlas-inventory` | `clusters/ci/infra/README.md` | `play` | **migrated** → `run --phases` |
| `atlas-inventory` | `clusters/ci/jenkins/README.md` | `play` | **migrated** → `run --phases` |
| `atlas-inventory` | `clusters/ci/kafka/README.md` | `play` | **migrated** → `run --phases` |
| `atlas-inventory` | `clusters/ci/postgresql/README.md` | `play`, `stage` | **migrated** → `run --phases` |
| `atlas-inventory` | `clusters/ci/redis/README.md` | `play`, `stage` | **migrated** → `run --phases` |
| `atlas-inventory` | `clusters/lab/pve-templates/README.md` | `play` | **migrated** → `run --phases` |
| `atlas-compute-provision` | `docs/adr/001-tfstate-repo-prefix.md` | `play` | **migrated** → `run --phases` |

Migration shape: ``./cluster play NAME --tags T`` →
``./cluster run --phases NAME --tags T``;
``./cluster stage NAME`` → ``./cluster run --phases NAME``.

### Removal plan

| Phase | Work | Done when |
|-------|------|-----------|
| **Phase 0** | This lock + inventory + gate | Contract locked — **done** |
| **Phase 1** | Remove argparse / dispatch / ``SUBCOMMANDS`` entries | ``stage``/``play`` unknown; ``run`` OK — **done** |
| **Phase 2** | Rewrite ADR 009 gates / cutover tests that require aliases | Suite green without “aliases retained” — **done** (`tests/test_adr_009_alias_removal_phase2.py`) |
| **Phase 3** | Operator docs / notes / CHANGELOG Breaking | No live teach of aliases — **done** (`tests/test_adr_009_alias_removal_phase3.py`) |
| **Phase 4** | Migrate external callers in table above | Scan clean — **done** (`tests/test_adr_009_alias_removal_phase4.py`) |
| **Phase 5** | ``./tests/run_ci.sh`` acceptance | Green — **done** (`tests/test_adr_009_alias_removal_phase5.py`) |

### Alias-removal checklist

- [x] Hard remove vs Variant S decided (Phase 0) — **hard remove**
- [x] External caller inventory recorded (Phase 0)
- [x] Keep ``stages`` / historical helper called out (Phase 0)
- [x] Phase 0 gate exists (`tests/test_adr_009_alias_removal_phase0.py`)
- [x] Argparse / ``cli_args`` remove (Phase 1) — gate
  `tests/test_adr_009_alias_removal_phase1.py`
- [x] Gates no longer require aliases retained (Phase 2) —
  `tests/test_adr_009_alias_removal_phase2.py`
- [x] Docs / notes / Breaking changelog (Phase 3) —
  `tests/test_adr_009_alias_removal_phase3.py`
- [x] External READMEs / sibling ADR migrated (Phase 4) —
  `tests/test_adr_009_alias_removal_phase4.py`
- [x] Offline ``run_ci`` green after removal (Phase 5) —
  `tests/test_adr_009_alias_removal_phase5.py`

## References

- `clusterctl/run_overrides.py` — `classify_run_overrides` + `apply_run_cli_overrides`
  + `resolve_run_limit` (env `LIMIT` / CLI `--limit`)
- `clusterctl/phase_plan.py` — `apply_play_cli_overrides` (historical test helper;
  CLI execute uses ADR 009 ``apply_run_cli_overrides``; ``play`` alias removed)
- ADR 008 — `--phases` selector (unchanged)
- `examples/internal/Jenkinsfile` / `Jenkinsfile.local` — Phase 3 consumers
- Gates: `tests/test_adr_009_unify_run_stage_play_phase0.py`,
  `tests/test_adr_009_unify_run_stage_play_phase1.py`,
  `tests/test_adr_009_unify_run_stage_play_phase2.py`,
  `tests/test_adr_009_unify_run_stage_play_phase3.py`,
  `tests/test_adr_009_unify_run_stage_play_phase4.py`,
  `tests/test_adr_009_unify_run_stage_play_phase5.py`,
  `tests/test_adr_009_limit_unify_a1.py`,
  `tests/test_adr_009_sot_phase_counts_a2.py`,
  `tests/test_adr_009_hints_a3.py`,
  `tests/test_adr_009_jenkins_plan_example_a4.py`,
  `tests/test_adr_009_coverage_a5.py`,
  `tests/test_adr_009_notes_helper_b.py`,
  `tests/test_adr_009_alias_removal_phase0.py`,
  `tests/test_adr_009_alias_removal_phase1.py`,
  `tests/test_adr_009_alias_removal_phase2.py`,
  `tests/test_adr_009_alias_removal_phase3.py`,
  `tests/test_adr_009_alias_removal_phase4.py`,
  `tests/test_adr_009_alias_removal_phase5.py`,
  `tests/test_run_overrides_contract.py`,
  `tests/test_phase6_e2e_signoff.py` (Jenkinsfile matrix)
