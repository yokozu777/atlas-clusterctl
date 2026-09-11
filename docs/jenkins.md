# Jenkins

Portable Pipeline samples under [`examples/internal/`](../examples/internal/):

| Script path | Jenkins agent | Leaf `execution.mode` |
|-------------|---------------|------------------------|
| [`examples/internal/Jenkinsfile`](../examples/internal/Jenkinsfile) | Docker Pipeline (`krang` + `docker.sock`) | **`docker`** |
| [`examples/internal/Jenkinsfile.local`](../examples/internal/Jenkinsfile.local) | Normal agent (label / VM) | from leaf `cluster.yaml` (no env override) |
| [`examples/internal/seed/Jenkinsfile`](../examples/internal/seed/Jenkinsfile) | Any agent with python3 + git | *(seed — refreshes deploy job params)* |

GitLab CI sample (same folder): [`gitlab-ci.md`](gitlab-ci.md) /
[`examples/internal/.gitlab-ci.yml`](../examples/internal/.gitlab-ci.yml).

Mixing `local` execute inside the Docker Pipeline agent often fails with Ansible
`Local RPC server did not start` — use `Jenkinsfile.local` on a real VM/host agent.

Install plugins and agent software **before** the first run — samples do not
bootstrap packages or `pip install` on the agent.

## Operator workflow

Trigger is **manual only** (no cron, no inventory webhook). Details / contract:
[`jenkins-seed.md`](jenkins-seed.md).

### First time (bootstrap)

1. Install plugins (table below) + agent software.
2. Create Pipeline job **`atlas-clusterctl-seed`** → SCM = this repo → script path
   `examples/internal/seed/Jenkinsfile`.
3. **Build** the seed job once (sets inventory URL / credentials as needed).
4. Open the deploy job seed created/updated (`atlas-clusterctl` and/or
   `atlas-clusterctl-local`) → **Build with Parameters**.
5. Pick `CLUSTER_ID` and `AGENT` (node list); run.

### Day-to-day deploy

1. **Build with Parameters** on the deploy job → choose `CLUSTER_ID`, optional
   `PHASES` / `TAGS` / `LIMIT` / `EXTRA_VARS`, …
2. Match leaf `execution.mode` to the Jenkinsfile (Docker vs `.local`).

### When to re-run seed

**Build** `atlas-clusterctl-seed` again after inventory leaf **add / rename /
remove** (so the `CLUSTER_ID` dropdown stays accurate), after leaf **`phases:`**
changes (`PHASES` checkboxes), or after leaf inventory **`hosts` / groups**
change (`LIMIT` checkboxes). Deploy runs do **not** refresh choices and do
**not** reset them (deploy JF omits `parameters { }`).

Acceptance (**CLUSTER_ID** Phase 0–5): **offline done** (gate) + **live = org checklist** in
[jenkins-seed.md — Phase 5 acceptance](jenkins-seed.md#phase-5-acceptance).
`PHASES` follow-up acceptance (empty = plan SoT without `--phases`; YAML map ≠ plan;
Active Choices cascade — [ADR 010](adr/010-jenkins-phases-active-choices.md)):
[PHASES Phase 5](jenkins-seed.md#phase-5-acceptance-phases-follow-up).
`LIMIT` follow-up (empty omit `--limit`; groups+hosts cascade —
[ADR 011](adr/011-jenkins-limits-active-choices.md)):
[LIMIT Phase 5](jenkins-seed.md#phase-5-acceptance-limits-follow-up)
(**offline done**; live = org checklist).
Changing `CLUSTER_ID` refreshes `PHASES` **and** `LIMIT` checkboxes
(seed-embedded inventory maps). Seed maps = **inventory `clusters/` only**
(no product baseline on seed). Re-run seed after inventory `phases:` or
`hosts`/group changes.

Seed **rewrites** deploy job params/SCM on every seed Build — see
[jenkins-seed.md — Seed side effects](jenkins-seed.md#seed-side-effects-deploy-job-rewrite).

### Seed job (`CLUSTER_ID` dropdown)

**UI SoT:** seed Job DSL owns the full deploy-job parameter template (incl.
`choice CLUSTER_ID`). Deploy samples omit Declarative `parameters { }`. Contract
(**CLUSTER_ID** Phase 0–5 done): [`jenkins-seed.md`](jenkins-seed.md). Sample directory:
[`examples/internal/seed/`](../examples/internal/seed/).

If Prepare fails with `CLUSTER_ID missing` → seed was never run (or job has no
params). Re-run seed.

## Required Jenkins plugins

Install on the **controller** (Manage Jenkins → Plugins). Short names are Plugin Manager IDs.

| Plugin | ID | Used by samples |
|--------|----|-----------------|
| **Pipeline** | `workflow-aggregator` | Declarative `pipeline { }` |
| **Pipeline: Declarative** | `pipeline-model-definition` | Stages / `options` (deploy samples omit `parameters`) |
| **Git** | `git` | SCM checkout of atlas-clusterctl |
| **Credentials Binding** | `credentials-binding` | `withCredentials` |
| **SSH Credentials** | `ssh-credentials` | `sshUserPrivateKey` (`GIT_SSH_CREDENTIALS_ID`) |
| **Pipeline Utility Steps** | `pipeline-utility-steps` | `readJSON` on `plan.json` (dynamic Run) |
| **AnsiColor** | `ansicolor` | `ansiColor('xterm')` console colors |
| **Timestamper** | `timestamper` | `timestamps()` |
| **Workspace Cleanup** | `ws-cleanup` | `cleanWs()` in `post` |
| **Docker Pipeline** | `docker-workflow` | `agent { docker { … } }` — **`Jenkinsfile` only** |
| **Job DSL** | `job-dsl` | **Seed job only** (refresh deploy `CLUSTER_ID` + embed `PHASES` / `LIMIT` maps) — see [jenkins-seed.md](jenkins-seed.md) |
| **Active Choices** | `uno-choice` | **Seed / deploy UI** — reactive `PHASES` / `LIMIT` checkboxes off `CLUSTER_ID` ([ADR 010](adr/010-jenkins-phases-active-choices.md), [ADR 011](adr/011-jenkins-limits-active-choices.md)) |

Usually already present with a modern Jenkins: **Script Security** (`script-security`).
Deploy ``envParam`` must not call ``Class.isArray()`` (sandbox rejects
``TypeDescriptor$OfField.isArray`` on modern JDKs) — samples use
``instanceof Collection`` / ``instanceof Object[]``.

Seed / Job DSL / Active Choices may need Script Approval the first time
(Job DSL itself; seed-time `JsonSlurper` when embedding maps — **not** at
Build-with-Parameters form-render, which uses sandbox-friendly `switch` only).

Without **AnsiColor**, Ansible still emits ANSI (`ANSIBLE_FORCE_COLOR=true`) but the
console shows raw escapes (`[0;32m…`) instead of colors.

Without **Pipeline Utility Steps**, the Run stage fails on `readJSON`.

## Agent software

Two layers matter for the Docker sample: the **Jenkins node** (host) and the
**Pipeline agent image** (`krang`). For the local sample there is only the node.

### Common (both Jenkinsfiles)

On whatever runs `./cluster` (host agent or `krang` container):

| Software | Why |
|----------|-----|
| **python3** | `./cluster` / `python3 -m clusterctl…` |
| **PyYAML** (`pip install PyYAML` / `requirements.txt`) | config + inventory YAML |
| **git** | inventory checkout, `repos sync` |
| **openssh-client** (`ssh`) | git over SSH, Ansible SSH |
| **sshpass** | Ansible password auth when leaf uses it |
| writable **`/tmp/clusterctl`** | Ansible controller temp root (`mkdir` in Prepare) |

Optional but typical: network reachability to Git (Gitea) and registry (Harbor).

### Docker Pipeline (`Jenkinsfile`) + leaf `execution.mode: docker`

| Where | Software |
|-------|----------|
| **Jenkins node (host)** | Docker Engine; agent user in `docker` group (or equivalent); `/var/run/docker.sock` usable; pull access to Harbor (`harbor.mxhash.com/library/krang` and leaf `execution.image:tag`) |
| **Pipeline agent image** (default `harbor.mxhash.com/library/krang`) | python3, PyYAML, git, sshpass, **Docker CLI** (talks to host via sock) |
| **Nested executor image** (`execution.image` / `execution.tag` in leaf) | Ansible + collections (often the same `krang`); used for `ansible-playbook` |

Do **not** set leaf `execution.mode: local` with this Jenkinsfile — nested-container
Ansible RPC often fails.

### Local agent (`Jenkinsfile.local`) + leaf `execution.mode: local`

| Where | Software |
|-------|----------|
| **Jenkins node (VM/host)** | Everything in **Common**, plus **ansible** / `ansible-playbook` and galaxy collections (pipeline may run `bootstrap` / `ansible-galaxy` into the cluster workspace). Prefer an Atlas jenkins-agent label — not the controller container. |

No Docker CLI required on the agent for pure `local` execute.

### Local agent (`Jenkinsfile.local`) + leaf `execution.mode: docker`

Same Jenkinsfile; mode comes from the leaf (e.g. `ci/kafka`). Agent needs **Docker CLI**
and pull access to the leaf `execution.image:tag` (typically `krang`).

### Credentials (controller)

| Item | Notes |
|------|--------|
| SSH private key credential | Id must match `GIT_SSH_CREDENTIALS_ID` (sample default `ssh_git`) for private inventory / playbook remotes |
| Job SCM credential | Separate from the above if the Multibranch/Pipeline job clones atlas-clusterctl via SSH |

## Agents (summary)

### Docker Pipeline (`Jenkinsfile`)

Prepared image + host Docker as in the tables above. Leaf `execution.image` / `tag`
control the **Ansible** executor container (may match `krang`).

### Local agent (`Jenkinsfile.local`)

Real Jenkins agent (label / VM). Leaf `execution.mode` / `image` / `tag` from
`cluster.yaml` — sample does **not** set `CLUSTER_EXECUTOR`.

## Model

| Then | Now |
|------|-----|
| Clone playbooks into job root | `./cluster repos sync` → `workspace/<env>/<name>/repos/` |
| Profile / v1 pipeline | schema v2 `phases` + `playbooks` |
| Ansible executor | `execution.mode` + optional `execution.image:tag` in leaf `cluster.yaml` |

## Parameters

Parameter definitions live on the **job config** from seed Job DSL
([jenkins-seed.md](jenkins-seed.md)) — not in the deploy Jenkinsfile.

| Param | Default (seed template) | Meaning |
|-------|-------------------------|---------|
| `AGENT` | `built-in` | Agent node name (choice from last seed: inventory jenkins `hostname:` + computers; Pipeline label) |
| `CLUSTER_ID` | (seeded choices) | Deployable leaf — **choice** from inventory scan |
| `INVENTORY_GIT_URL` | org sample / empty | Optional private inventory git URL (`ssh://git@host/path` preferred; checkout skipped if empty) |
| `INVENTORY_GIT_REF` | `main` | Inventory **branch name** only (not a commit SHA; shallow `--branch` clone) |
| `INVENTORY_DIR` | `atlas-inventory` | Checkout directory (expects `clusters/` inside) |
| `PHASES` | none checked | Active Choices checkboxes for selected `CLUSTER_ID` ([ADR 010](adr/010-jenkins-phases-active-choices.md)). **None selected** → plan/run **without** `--phases` (**plan SoT**; may skip YAML phases via inventory `when:`). One or more checks → `NAME` or CSV `a,b,c` (ADR 008). With `TAGS`/`LIMIT` use a **single** NAME. `start..end` not in UI. Map = inventory `phases:` embedded at last seed (≠ empty-`PHASES` plan / post-sync product baseline). Artifact twin: seed → Artifacts → `examples/internal/seed/cluster-phases.json` |
| `TAGS` | empty | Optional ansible `--tags` for **Run** ([ADR 009](adr/009-unify-run-stage-play.md)). Empty or `all` = catalog. Non-empty → single-phase `PHASES` only |
| `LIMIT` | none checked | Active Choices checkboxes for selected `CLUSTER_ID` ([ADR 011](adr/011-jenkins-limits-active-choices.md)): inventory **groups with nested host keys** (labels may show `hostname:`). **None selected** → omit `--limit`. Multi → CSV `a,b` → ansible `--limit`. Non-empty → single-phase `PHASES` only ([ADR 009](adr/009-unify-run-stage-play.md)). Advanced patterns (`&`/`~`/`!`) not in UI — use CLI. Map embedded at last seed (≠ live post-provision inventory). Artifact twin: seed → Artifacts → `examples/internal/seed/cluster-limits.json`. Contract: [jenkins-seed.md — LIMIT follow-up](jenkins-seed.md#follow-up-limits-parameter-contract) |
| `EXTRA_VARS` | empty | Optional ansible extra-vars for **Run** ([ADR 009](adr/009-unify-run-stage-play.md)): space-separated `key=value` tokens (e.g. `provision_mode=destroy`). No leading `-e`. Values must not contain spaces. |
| `EXECUTION_DOCKER_TAG` | empty | Override `execution.tag` — seeded **only** for Docker `Jenkinsfile` (omitted from `.local` UI) |
| `GIT_SSH_CREDENTIALS_ID` | empty / `ssh_git` | Optional Jenkins SSH key for git sync / inventory |
| `VALIDATE_STRICT` | `off` | Choice: `--strict` (warnings → fail) or `off` |
| `RUN_SMOKE` | true | `./cluster smoke` before deploy |
| `SKIP_DEPLOY` | false | Stop after validate/smoke/plan |
| `RUN_CI_PREFLIGHT` | true | Offline `ci_preflight --skip-tests` |

When `INVENTORY_GIT_URL` is set, the pipeline clones the inventory repo and writes
`.config/config.yaml` with `clusters.path` pointing at `<INVENTORY_DIR>/clusters`
([local-labs.md](local-labs.md)). Parent of that path is mode-B
`atlas_inventory_root` / `provision_tf_state_local_dir` (Phase 6). Checkout uses
[`examples/internal/ci/prepare_inventory_checkout.sh`](../examples/internal/ci/prepare_inventory_checkout.sh)
(**Stage 5 / P1**):

- fail if dirty outside `tfstate/` (deploy; seed may `INV_RESET_HARD`);
- discard **working-tree** dirt under `tfstate/` only (not commits);
- `fetch` + named branch + **`merge --ff-only`** (fail if ahead/diverged —
  unpushed TF must be pushed or resolved by hand);
- seed checkbox **`INVENTORY_RESET_HARD`** (default true) sets `INV_RESET_HARD`
  → `git reset --hard origin/<ref>` on ahead/diverged (and cleans dirty outside
  `tfstate/`); deploy must not enable this;
- deploy sets `INV_FETCH_MODE=full`; seed uses `shallow` for **fresh** clones
  only — existing non-shallow checkouts are fetched without `--depth` (no
  re-shallow after a full deploy);
- never create controller `tfstate-repo/`.

Run injects `-e provision_tf_state_git_discard_local=true` by default (working
tree under `tfstate/` only; not a substitute for push). Opt out with
`TFSTATE_GIT_DISCARD_LOCAL=false` or an `EXTRA_VARS` token for that var.

Avoid concurrent deploys on the same agent workspace while inventory is mode-B
SoT (GitLab samples use shared `resource_group: atlas-clusterctl-inventory`).

## Stages

```
  Prepare --> Inventory? --> CI preflight --> repos sync --> validate --> smoke --> plan --> run*
                                                                      |
                                                              archive workspace/**/logs/**
```

`*` **Run** is dynamic: `plan --json` → one Jenkins stage per **phase**
(`[1/4] atlas-compute-provision/provision`, … on typical stack / `k8s_full`
leaves; factory `pve_templates` may show `…/templates`) via
`./cluster run --phases …` plus optional `TAGS` / `LIMIT` / `EXTRA_VARS`
([ADR 009](adr/009-unify-run-stage-play.md)) — same numbering as `./cluster plan` text.

1. `chmod +x ./cluster` + `/tmp/clusterctl` (tools come from the agent / image)
2. Optional inventory git checkout + `.config/config.yaml` `clusters.path`
3. Optional offline `ci_preflight --skip-tests`
4. `repos sync` for `CLUSTER_ID`
5. `validate` (+ optional `--strict`) / optional `smoke`
6. `plan` (text + `plan.json`): **empty `PHASES`** → no `--phases` (**plan SoT**;
   may differ from seed YAML map when `when:` applies); non-empty → `--phases`
   selector ([PHASES follow-up](jenkins-seed.md#follow-up-phases-parameter-contract))
7. Dynamic `Run`: one stage per plan phase (`[i/n] phase_ref` →
   `./cluster run --phases` + optional `TAGS` / `LIMIT` / `EXTRA_VARS`)
8. Archive logs, then `cleanWs`

## Local analogue

```bash
export CLUSTER_ID=demo/k8s
./cluster use "$CLUSTER_ID"
python3 -m pip install -r requirements.txt   # or use the same prepared image / agent tools
python3 -m clusterctl.tools.ci_preflight --skip-tests
./cluster repos sync
./cluster validate --strict
./cluster smoke --cluster "$CLUSTER_ID"
./cluster run
# same as Jenkins EXTRA_VARS=provision_mode=destroy on a single phase:
# ./cluster run --phases provision -e provision_mode=destroy
# selective (TAGS + LIMIT — single phase only):
# ./cluster run --phases infra --tags 11_sync_infra_cache_push --limit infra_platform \
#   -e nginx_cache_sync_direction=push
```

### `TAGS` / `LIMIT` / `EXTRA_VARS` (ADR 009)

Job parameters → each Run phase:

```text
PHASES=infra
TAGS=11_sync_infra_cache_push
LIMIT=infra_platform
EXTRA_VARS=nginx_cache_sync_direction=push
→ ./cluster run --phases infra --tags 11_sync_infra_cache_push --limit infra_platform \
     -e nginx_cache_sync_direction=push
```

- `TAGS` empty or `all` → omit `--tags` (catalog invocations).
- `LIMIT` empty → omit `--limit`. Non-empty value is an ansible host pattern
  (group, host key, or comma-list from Active Choices). Cascade of group/host
  checkboxes off `CLUSTER_ID`: [ADR 011](adr/011-jenkins-limits-active-choices.md)
  (**Phase 0–5 delivered** — UI + operator docs + acceptance).
  - Checkbox **values** are inventory **host keys** / group names (often IPs).
    Labels nest hosts under groups; optional inventory `hostname:` appears as
    `(hostname: dns)` in the label only — not in `--limit`.
  - Empty checkbox list for a leaf → usual when `hosts` is INI / missing / unusable
    YAML; empty selection still omits `--limit` (valid).
  - Stale / empty after inventory edit → **Build** seed again (map is embedded at
    seed time). Artifact twin: seed → Artifacts →
    `examples/internal/seed/cluster-limits.json`.
  - Advanced patterns (`&`, `!`, `~`) stay CLI-only — not in checkbox UI.
- `EXTRA_VARS`: space-separated `key=value` → repeated `-e` (no leading `-e` in the
  parameter; values must not contain whitespace; argv array, no `eval`).
- Non-empty `TAGS` / `LIMIT` with a multi-phase `PHASES` window → **ERROR** from
  clusterctl (selective overrides need one phase).

See [validate.md](validate.md), [execution.md](execution.md),
[examples/internal/README.md](../examples/internal/README.md),
[ADR 009](adr/009-unify-run-stage-play.md),
[LIMIT follow-up](jenkins-seed.md#follow-up-limits-parameter-contract),
[LIMIT Phase 5 acceptance](jenkins-seed.md#phase-5-acceptance-limits-follow-up).
