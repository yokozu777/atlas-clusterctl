# Seed job sample (CLUSTER_ID choice + PHASES / LIMIT cascades)

> Contract: [`docs/jenkins-seed.md`](../../docs/jenkins-seed.md)
> (`CLUSTER_ID` Phase 0–5 + [`PHASES` follow-up](../../docs/jenkins-seed.md#follow-up-phases-parameter-contract)
> + [`LIMIT` follow-up](../../docs/jenkins-seed.md#follow-up-limits-parameter-contract) Phase 0–5).
> Cascades: [`ADR 010`](../../docs/adr/010-jenkins-phases-active-choices.md) (`PHASES`);
> [`ADR 011`](../../docs/adr/011-jenkins-limits-active-choices.md) (`LIMIT`).
> Operator overview: [`docs/jenkins.md`](../../docs/jenkins.md) → **Operator workflow**.

Manual **seed** job. Trigger: **Build** only — no cron, no inventory webhook.

## What it does

1. Checks out inventory (`INVENTORY_GIT_URL`).
2. Lists deployable leaves (`python3 -m clusterctl.tools.list_deployable_clusters`).
3. Writes phases map (`python3 -m clusterctl.tools.list_cluster_phases --all
   --allow-empty` → `cluster-phases.json`). Archived on the seed job **and**
   embedded into deploy-job Active Choices as `CLUSTER_PHASES_JSON`.
4. Writes limits map (`python3 -m clusterctl.tools.list_cluster_limits --all
   --allow-empty --ui` → `cluster-limits.json`). Archived on the seed job **and**
   embedded into deploy-job Active Choices as `CLUSTER_LIMITS_JSON`.
5. Job DSL refreshes deploy job(s): full parameter template + `choice CLUSTER_ID`
   + reactive `PHASES` / `LIMIT` checkboxes (Active Choices / ADR 010 + 011).

Deploy `PHASES` is **Active Choices Reactive** (checkboxes for the selected
`CLUSTER_ID`). None selected → plan/run **without** `--phases` = **plan SoT**.
Changing `CLUSTER_ID` refreshes the checkbox list. Re-run seed after inventory
leaf / `phases:` changes (map is snapshotted at seed Build).

Deploy `LIMIT` is the same pattern ([ADR 011](../../docs/adr/011-jenkins-limits-active-choices.md)):
groups with nested host keys for the selected leaf. None selected → omit `--limit`.
Multi → CSV → ansible `--limit`. Non-empty requires single-phase `PHASES`
([ADR 009](../../docs/adr/009-unify-run-stage-play.md)). Submitted values are
inventory **keys** (often IPs); labels may add `(hostname: dns)` from inventory
`hostname:`. Re-run seed after inventory `hosts` / group changes.

`cluster-phases.json` is a **YAML `phases:` catalog** (no `when:`). It may list
phases that an empty-`PHASES` plan skips. Seed scans **inventory `clusters/`
only** (no product baseline / `--product-clusters-root`); prefer inline
`phases:` on inventory leaves.

`cluster-limits.json` is a **hierarchical UI catalog** (`--ui`: ordered
`[{value,label},…]` — group then nested hosts) from leaf YAML inventory only.
It may list names that are unreachable after provision, and it omits INI /
unusable `hosts` leaves (checkboxes empty; empty `LIMIT` still OK).

Empty inventory scan → seed **fails** (does not wipe existing choices with `[]`).
Empty phases / limits maps → seed **continues** (writes `{}`; Job DSL still runs;
checkboxes empty for missing catalogs).

Scanner API: `collect_deployable_cluster_ids` (CLI module above). Phases helper:
`python3 -m clusterctl.tools.list_cluster_phases --clusters-root … --cluster-id ID`
(or `--all`). Limits helper:
`python3 -m clusterctl.tools.list_cluster_limits --clusters-root … --cluster-id ID`
(or `--all` / `--structured` / `--ui`). Offline fixture
`tests/fixtures/jenkins_seed_inventory/`; units in
`tests/test_list_deployable_clusters.py`, `tests/test_list_cluster_phases.py`,
`tests/test_list_cluster_limits.py`.

| Suggested job | Script path |
|---------------|-------------|
| `atlas-clusterctl-seed` | `examples/internal/seed/Jenkinsfile` |

| Default `DEPLOY_SPECS` (job \| script) | |
|---------------------------------------|---|
| `atlas-clusterctl-local` | `examples/internal/Jenkinsfile.local` |
| `atlas-clusterctl` | `examples/internal/Jenkinsfile` |

## Files

| File | Role |
|------|------|
| [`Jenkinsfile`](Jenkinsfile) | Seed Pipeline |
| [`seed_deploy_jobs.groovy`](seed_deploy_jobs.groovy) | Job DSL template (incl. Active Choices) |
| *(generated)* `cluster-ids.txt` | Archived id list (gitignored) |
| *(generated)* `cluster-phases.json` | Archived id → phases map (gitignored; inventory-only) |
| *(generated)* `cluster-limits.json` | Archived id → LIMIT UI catalog (gitignored; `{value,label}` hierarchy) |

## Setup (once)

1. Install **Job DSL** (`job-dsl`) and **Active Choices** (`uno-choice`) on the
   controller.
2. New Pipeline job `atlas-clusterctl-seed` → SCM = atlas-clusterctl → script path
   `examples/internal/seed/Jenkinsfile`.
3. Set seed parameters (table below) → **Build** (approve Script Security prompts
   if shown).
4. Open deploy job → **Build with Parameters** → pick `CLUSTER_ID` → `PHASES`
   and `LIMIT` checkboxes update.

## When to re-run

| Event | Re-run seed? |
|-------|----------------|
| Add / rename / remove inventory leaf | **Yes** (manual Build) |
| Change leaf `phases:` catalog | **Yes** (cascade embed) |
| Change leaf inventory `hosts` / groups | **Yes** (limits map embed) |
| Ordinary deploy | No |
| Change only deploy Pipeline stages | No (unless you also change `DEPLOY_SPECS` / SCM URL) |

## Side effects

Each seed **Build** rewrites deploy job **parameters** and **SCM** via Job DSL
(`pipelineJob`). Manual UI edits on the deploy job do not survive the next seed.
Prefer editing `seed_deploy_jobs.groovy` / seed params / `DEPLOY_SPECS`.

Parameter template follows `scriptPath`: Docker `Jenkinsfile` includes
`EXECUTION_DOCKER_TAG`; `Jenkinsfile.local` does not. `AGENT` is a choice list
from the last seed Build (inventory jenkins `hostname:` values + controller
computers when readable; `built-in` first).

Deploy SCM checkout uses **full** checkout (`lightweight(false)`) plus
`wipeOutWorkspace` — not lightweight+wipe (unreliable combo).

Inventory checkout: seed/deploy call
`examples/internal/ci/prepare_inventory_checkout.sh` (Phase 6 Stage 5 / P1).
If `INVENTORY_DIR` already has `.git` but `origin` ≠ `INVENTORY_GIT_URL`
(after URL normalization), prepare runs `git remote set-url` then fetch.
Refresh is **ff-only** by default (fail if the runner is ahead/diverged — protects
unpushed TF). Seed sets `INV_RESET_HARD=true` via checkbox **`INVENTORY_RESET_HARD`**
(default on): `git reset --hard origin/<ref>` on ahead/diverged and discard dirty
paths outside `tfstate/`. Deploy leaves `INV_RESET_HARD` unset/false. Seed uses
`INV_FETCH_MODE=shallow` for **fresh** clones; existing non-shallow
checkouts are fetched without `--depth` (no re-shallow after a full deploy).
Deploy uses `full`. Dirty paths outside `tfstate/` fail deploy; seed with reset
on discards them.

Sample defaults use **`ssh://git@host/path`** for both inventory and
atlas-clusterctl. `INVENTORY_GIT_REF` / `CLUSTERCTL_GIT_REF` are **branch names**
(not commit SHAs).

## Seed parameters

| Param | Role |
|-------|------|
| `INVENTORY_GIT_URL` / `_REF` / `_DIR` | Inventory checkout for the scan (`_REF` = branch name) |
| `INVENTORY_RESET_HARD` | Checkbox (default **on**): `git reset --hard` inventory to origin on ahead/diverged / dirty outside `tfstate/` |
| `CLUSTERCTL_GIT_URL` / `_REF` | Embedded into deploy job SCM (`cpsScm`; `_REF` = branch) |
| `DEPLOY_SPECS` | Lines `JOB_NAME\|scriptPath` to create/update |
| `PREFER_CLUSTER_ID` | Pin first in `CLUSTER_ID` choices if present |
| `GIT_SSH_CREDENTIALS_ID` | SSH for inventory + deploy SCM |
| `INVENTORY_GIT_URL_DEFAULT` | Default written into deploy job’s `INVENTORY_GIT_URL` |
| `AGENT` | Agent label for the seed run itself |

## Troubleshooting

| Symptom | Likely fix |
|---------|------------|
| Deploy Prepare: `CLUSTER_ID missing` / seed booleans missing | Build seed once (UI SoT = seed; deploy JF has no `parameters {}`) |
| Deploy UI shows `EXECUTION_DOCKER_TAG` on `.local` job | Re-run seed — DSL omits that param for `Jenkinsfile.local` |
| Seed / Job DSL fails mentioning Active Choices / uno-choice | Install plugin `uno-choice`, re-run seed |
| `PHASES` checkboxes empty / stale after leaf change | Push inventory `phases:`, **Build** seed again (map is embedded at seed time) |
| `PHASES` does not change when picking another `CLUSTER_ID` | Active Choices not installed / Script Approval pending; or seed not re-run with ADR 010 DSL |
| Seed fails: no deployable ids | Inventory URL/ref wrong, or `clusters/` has no deployable leaves |
| Seed fails: dirty outside `tfstate/` | Commit/stash runner edits, remove `INVENTORY_DIR`, or leave **`INVENTORY_RESET_HARD`** checked (default) |
| Seed / deploy fails: local ahead of origin / diverged | Unpushed inventory commits (often `tfstate/`) — push them, or on **seed** leave **`INVENTORY_RESET_HARD`** checked (deploy never auto-resets) |
| Seed archives empty `cluster-phases.json` (`{}`) | Inventory leaves lack `phases:` — Job DSL still OK; empty `PHASES` deploy still uses plan SoT when the leaf has a catalog |
| Seed archives empty `cluster-limits.json` (`{}`) | No usable YAML inventory catalogs — Job DSL still OK; empty `LIMIT` checkboxes / omit `--limit` |
| Seed log: `warning: N deployable id(s) without limits catalog` | Expected for INI / missing `hosts` leaves — checkboxes empty for those ids |
| `LIMIT` checkboxes empty / only description | **Most common:** Script Approval pending for the LIMIT groovy — Manage Jenkins → In-process Script Approval → Approve → re-run seed → hard-refresh Build with Parameters. If you see `__LIMIT_SCRIPT_BLOCKED_APPROVE_IN_JENKINS__` as a fake checkbox, that confirms it. Also try `ci/postgresql` / `ci/jenkins` (known catalogs); `lab/pve-templates` has empty LIMIT by design |

| `LIMIT` does not change when picking another `CLUSTER_ID` | Active Choices not installed / Script Approval pending; or seed not re-run with ADR 011 DSL |
| `LIMIT` shows IPs without DNS | Values / primary text are inventory **host keys** (often IPs). When `hostname:` is set on the host entry, the label shows `(hostname: dns)` after re-seed |
| Need `&` / `~` / `!` host patterns | Out of checkbox UI — use CLI `./cluster run --limit …` |
| Seed fails with `error: …` (no Traceback) on limits map | Broken inventory YAML / load failure — fix `hosts`, re-run seed |
| Plan stage list ≠ checkboxes / `cluster-phases.json` | Expected if inventory `when:` skips YAML phases — map is catalog-only; also if deploy sees product baseline after `repos sync` (seed map is inventory-only) |
| Seed log: `warning: N deployable id(s) without phases` | Expected for hosts-only / phaseless leaves — Job DSL still seeds `CLUSTER_ID`; checkboxes empty for those ids |
| Map missing phases that deploy plan shows | Seed is inventory-only (no product root). Put inline `phases:` on the inventory leaf, or accept map ≠ post-`repos sync` plan |
| Seed fails with `error: …` (no Traceback) on phases map | Broken `cluster.yaml` / load failure under inventory — fix YAML, re-run seed |
| Dropdown stale after new leaf | Push inventory, then **Build** seed again |
| Changed `INVENTORY_GIT_URL` but old repo | Seed updates `origin` via `set-url` when `.git` exists |
| UI tweaks on deploy job vanished | Expected — next seed rewrites params/SCM (see Side effects) |
| Job DSL / Active Choices Script Approval prompt | Approve once on the controller, re-run seed / reload Build with Parameters |
| Job DSL: `String.call()` / `scriptPath` | Fixed locally as `jfScript` — push atlas-clusterctl, re-run seed |

## Phase checklist

- [x] Phase 0 — contract locked
- [x] Phase 1 — seed scripts in this directory
- [x] Phase 2 — deploy Jenkinsfile omits `parameters {}`
- [x] Phase 3 — operator docs polish
- [x] Phase 4 — shared list helper tests (fixture) / hardening
- [x] Phase 5 — acceptance (offline proof + live operator checklist in
  [`docs/jenkins-seed.md`](../../docs/jenkins-seed.md#phase-5-acceptance))
- [x] `PHASES` follow-up Phase 0 — empty = plan SoT without `--phases`
  ([contract](../../docs/jenkins-seed.md#follow-up-phases-parameter-contract))
- [x] `PHASES` follow-up Phase 1 — DSL / docs spell out empty = plan SoT
- [x] `PHASES` follow-up Phase 2 — `list_cluster_phases` helper + fixture
- [x] `PHASES` follow-up Phase 3 — seed writes / archives `cluster-phases.json`
- [x] `PHASES` follow-up Phase 4 — path C unlocked ([ADR 010](../../docs/adr/010-jenkins-phases-active-choices.md))
- [x] `PHASES` follow-up Phase 5 — acceptance (offline gate + live checklist in
  [`docs/jenkins-seed.md`](../../docs/jenkins-seed.md#phase-5-acceptance-phases-follow-up))
- [x] Remediation Phase A — map ≠ empty-`PHASES` plan SoT
- [x] Remediation Phase B — superseded by ADR 010 cascade (map still via Artifacts)
- [x] Remediation Phase C — seed warn ids without phases; CLI clean errors
- [x] Remediation Phase D — seed map inventory-only; Artifacts path documented
- [x] Remediation Phase E — CLI `--allow-empty` footgun; banner/anchor hygiene
- [x] `LIMIT` follow-up Phase 0 — empty omit `--limit`; cascade contracted
  ([ADR 011](../../docs/adr/011-jenkins-limits-active-choices.md) /
  [contract](../../docs/jenkins-seed.md#follow-up-limits-parameter-contract))
- [x] `LIMIT` follow-up Phase 1 — `list_cluster_limits` helper + fixture
  (`tests/test_list_cluster_limits.py`)
- [x] `LIMIT` follow-up Phase 2 — seed `cluster-limits.json` + `CLUSTER_LIMITS_JSON`
- [x] `LIMIT` follow-up Phase 3 — reactive `LIMIT` checkboxes (ADR 011)
- [x] `LIMIT` follow-up Phase 4 — operator docs / troubleshooting
  ([jenkins.md](../../docs/jenkins.md), this README)
- [x] `LIMIT` follow-up Phase 5 — acceptance (offline gate + live checklist in
  [`docs/jenkins-seed.md`](../../docs/jenkins-seed.md#phase-5-acceptance-limits-follow-up))
