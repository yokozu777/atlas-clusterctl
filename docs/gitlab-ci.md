# GitLab CI

Sample pipeline: [`examples/internal/.gitlab-ci.yml`](../examples/internal/.gitlab-ci.yml)
(+ jobs body [`gitlab-ci.jobs.yml`](../examples/internal/gitlab-ci.jobs.yml)).

Sibling to the Jenkins deploy samples under [`examples/internal/`](../examples/internal/)
([`jenkins.md`](jenkins.md), [`jenkins-seed.md`](jenkins-seed.md)). Like Jenkins
deploy: optional `ci_preflight --skip-tests` (input `run_ci_preflight`), not the
full `./tests/run_ci.sh` suite (that stays on [GitHub Actions](../.github/workflows/ci.yml)).

## Wire the sample (required for Inputs UI)

Pipeline **`spec:inputs`** (the Run-pipeline form) only apply when this file is the
project’s **main** CI config. Set:

**Settings → CI/CD → CI/CD configuration file** → `examples/internal/.gitlab-ci.yml`

Needs GitLab **16.11+** (inputs / `options` / `rules` as supported by your instance).

### Project job timeout (required for long deploy)

Full leaf runs (`provision` → `init` → `k8s-core` → `addons`, upgrades, …) often
exceed GitLab’s default job timeout. When the job hits the limit, GitLab cancels
it and **`CI_JOB_TOKEN` expires** (UI may show *“The CI job token has expired.
The job may have exceeded the maximum time limit.”*).

Set under **Settings → CI/CD → General pipelines → Timeout**:

| Setting | Value |
|---------|--------|
| **Timeout** | `5h` (or `18000` seconds) |

Jobs fail if they run longer than this. Input is seconds by default; human-readable
values are accepted (e.g. `1 hour`, `5h`). Raise further only if a leaf routinely
needs more; prefer splitting phases over unbounded timeouts.

Also ensure the **runner** `maximum timeout` (if set in runner config) is **≥**
this project timeout — the lower of the two wins.

## Jobs

| Job | When | What |
|-----|------|------|
| `seed` | **manual** (web/api/pipeline) | Inventory scan → regenerate dropdowns (Jenkins seed analog) |
| `deploy` | **manual** (web/api/pipeline) | Jenkinsfile.local-style `./cluster` flow (optional `ci_preflight --skip-tests`). `needs: []` so it does **not** wait on seed. |

## Seed (Jenkins analog)

GitLab cannot do Active Choices at form-render time. Dropdowns are **static**
`options` / `rules` inside `.gitlab-ci.yml`. Job **`seed`** refreshes them:

1. **Run pipeline** → play **`seed`** (inventory from CI/CD Variables; see below).
2. Seed runs the same scanners as Jenkins seed:
   `list_deployable_clusters`, `list_cluster_phases`, `list_cluster_limits --ui`.
3. `examples/internal/seed/generate_gitlab_ci.py` rewrites
   `examples/internal/.gitlab-ci.yml` (`cluster_id` options; `phases` / `limit`
   cascaded string `rules` per cluster).
4. If `GITLAB_PUSH_TOKEN` (or push-enabled `CI_JOB_TOKEN`) is set, seed commits
   with `[skip ci]` and pushes to the pipeline branch. Otherwise download the
   artifact and commit manually.

Hand-maintained job scripts stay in `gitlab-ci.jobs.yml` (not overwritten).

Optional seed input: `prefer_cluster_id` — list that id first when present.

### CI/CD variables (seed inventory + push / SSH)

Set under **Settings → CI/CD → Variables** — **not** Run-pipeline Inputs.
Seed ignores inventory Inputs; only these Variables feed the inventory clone.

| Variable | Role |
|----------|------|
| `INVENTORY_GIT_URL` | Inventory git URL for **seed** and **deploy** (Inputs empty → this var). If unset, both fall back to Jenkins default `ssh://git@gitea.mxhash.com/root/atlas-inventory.git`. Without a checkout, deploy fails with `cluster config not found`. |
| `INVENTORY_GIT_REF` | Inventory branch (default `main`) |
| `INVENTORY_DIR` | Checkout directory (default `atlas-inventory`) |
| `GIT_SSH_PRIV_KEY` | File or Variable (PEM) for private inventory / sibling remotes **and** (on deploy) host Ansible via `SSH_KEY`. Type **File** preferred. |
| `SSH_KEY` | Optional absolute path to the private key for `./cluster` validate/run (Jenkins parity). If unset and `GIT_SSH_PRIV_KEY` is set, deploy exports `SSH_KEY` to the prepared key file. Default otherwise: `~/.ssh/id_rsa`. |
| `GITLAB_PUSH_TOKEN` | Personal/project access token (`glpat-…`) with `write_repository`. Seed pushes as HTTPS user **`oauth2`** (not `gitlab-ci-token`). Token owner must be allowed to push the pipeline branch (often protected `main`). |

**Flags for secrets** (`GIT_SSH_PRIV_KEY`, `GITLAB_PUSH_TOKEN`):

| Flag | Recommendation |
|------|----------------|
| **Masked** | On for `GITLAB_PUSH_TOKEN` (File vars cannot be Masked) |
| **Protect variable** | On **only if** seed/deploy run on a **protected** branch/tag (e.g. `main`). On a non-protected branch the var is empty → clone/push fails |
| **Expand variable reference** | **Off** for secrets |

Seed/deploy always set `GIT_SSH_COMMAND` with `StrictHostKeyChecking=no` (and
clusterctl docker also uses `UserKnownHostsFile=/dev/null`). Empty runner
`known_hosts` is fine — host-key checking is disabled via that env, not via
`06_configure_git` (that role only sets git `user.name` / `user.email`). Without
`GIT_SSH_PRIV_KEY`, git uses the runner user default key — that key must be
allowed to read `INVENTORY_GIT_URL`.

Inside docker, after preflight, clusterctl copies the host key into a unique
per-run dir via `tempfile.mkdtemp(prefix="atlas-ssh-")` under
`workspace/<cluster_id>/.atlas-ssh/` (mode `0700`/`0600` — **not** host `/tmp`,
**not** controller `.cache/` / legacy `.cache/docker-identity`), mounts it at
container `/tmp/atlas-ssh/id_rsa`,
and sets `GIT_SSH_COMMAND` with `-i`. Staging is removed after the run. Phases
with `git_ssh: true` **keep** that identity
(or rebuild from `TFSTATE_SSH_KEY` / `SSH_KEY`) so bare `git pull`/`push` in
roles such as `11_tf_state_push` still authenticate — they must not collapse to
host-check-only `ssh`.

**Push auth:** prefer `GITLAB_PUSH_TOKEN`. Fallback `CI_JOB_TOKEN` needs
**Settings → CI/CD → Job token permissions** (and protected-branch rules) that
allow push to this project. If push fails, job fails; artifact still has the
generated `.gitlab-ci.yml` for a manual commit.

## Operator workflow

### First time (admin / bootstrap)

1. **Settings → CI/CD → CI/CD configuration file** → `examples/internal/.gitlab-ci.yml`.
2. **Settings → CI/CD → General pipelines → Timeout** → `5h` (see
   [Project job timeout](#project-job-timeout-required-for-long-deploy)).
3. Register a **shell** runner tagged/available to the project (`python3`,
   `python3-venv`, `git`, `openssh-client`; for deploy also ansible/sshpass/docker
   as required by the leaf).
4. **Variables** (see table above):
   - `INVENTORY_GIT_URL` (if not using the baked-in Gitea default),
   - `GIT_SSH_PRIV_KEY` (if inventory is private SSH),
   - `GITLAB_PUSH_TOKEN` (so seed can push dropdown refresh to `main`).
5. Ensure the token can push **protected** `main` (Maintainer / Allowed to push,
   or unprotected branch for smoke tests).
6. **Build → Pipelines → Run pipeline** (defaults OK) → play job **`seed`**.
7. Confirm log: inventory clone → `N deployable id(s)` →
   `push auth=oauth2` → `pushed … → main`.
8. **Run pipeline** again — `cluster_id` / `phases` / `limit` dropdowns should
   match inventory.

### Day-to-day (operator)

**Deploy a leaf**

1. **Run pipeline**.
2. Pick **`cluster_id`**; optionally **`phases`** / **`limit`** (cascade after
   cluster; `__none__` = plan SoT / no `--limit`).
3. Set other inputs if needed (`tags`, `extra_vars`, `skip_deploy`, …).
4. Play job **`deploy`** (leave **`seed`** unplayed).
5. Match leaf `execution.mode` to what the shell runner can run (`local` vs
   docker tooling on the host).

**Refresh dropdowns** (same triggers as Jenkins seed)

Re-run **`seed`** after inventory leaf add/rename/remove, `phases:` changes, or
`hosts` / group changes that affect LIMIT keys. No need before every deploy.

## Run pipeline inputs

| Input | Type | Role |
|-------|------|------|
| `cluster_id` | string **options** (seeded) | Leaf id — like Jenkins `CLUSTER_ID` |
| `phases` | string **rules** (seeded; `__none__` = plan SoT) | One phase or CSV-of-all option |
| `limit` | string **rules** (seeded; `__none__` = omit `--limit`) | One key or CSV-of-all option |
| `tags` | string | Ansible `--tags` |
| `extra_vars` | string | `key=value` tokens |
| `inventory_git_url` / `_ref` / `_dir` | string | **Deploy only** optional override (empty → CI/CD Variables) |
| `prefer_cluster_id` | string | Seed ordering hint |
| `validate_strict` | options `off` / `--strict` | Validate |
| `run_smoke` / `skip_deploy` / `run_ci_preflight` | boolean | Flags |

GitLab cannot combine `type: array` with `rules`: rules require `default` to be
an exact scalar member of `options`, while array inputs require `default` to be
an array. We use `type: string` with cascaded options; when a leaf has 2+
phases/limits, options also include a CSV of all values. Sentinel `__none__` is
stripped at deploy (plan SoT / omit `--limit`). Arbitrary multi-subsets are not
in the dropdown (unlike Jenkins multi-select).

Labels like Jenkins hierarchical LIMIT UI are not shown (GitLab options are
values only). Keys match inventory `--limit` values.

Automatic pipelines (MR / push) use input **defaults** — they do not prompt.

## Runner software (shell executor — Option A)

Jobs assume a **shell** GitLab Runner (no Docker `image:`). Host needs:

```bash
sudo apt-get install -y python3 python3-venv python3-pip git openssh-client
# deploy also: ansible / sshpass / docker as required by the leaf
```

Install/register runners with sibling **`atlas-gitlab-runner`**
([stacks/gitlab-runner.md](stacks/gitlab-runner.md)): shell default, docker
executor via `gitlab_runner_executor`, and `gitlab-runner` in the `docker` group
for `unix:///var/run/docker.sock`.

`seed` creates a project **`.venv`**, install `requirements-dev.txt`
there (PEP 668-safe), and put `.venv/bin` on `PATH`. Do not `pip install` into
the system Python.

**`deploy`:** uses the runner environment (ansible / Docker CLI as needed by the
leaf). Optional inventory checkout still needs git + SSH. When
`run_ci_preflight` is true (default), runs
`python3 -m clusterctl.tools.ci_preflight --skip-tests` before repos sync
(Jenkins `RUN_CI_PREFLIGHT` parity).

For leaves with `execution.mode: docker` (e.g. `ci/redis`), the runner user must
reach `unix:///var/run/docker.sock` (`usermod -aG docker gitlab-runner` + restart
runner). The Docker executor runs as the **host uid:gid** (`--user`), stages the
SSH key per-run under `workspace/<cluster_id>/.atlas-ssh/atlas-ssh-*`
(`tempfile.mkdtemp`, mode `0700`/`0600`; not host `/tmp`, not controller
`.cache/` / legacy `.cache/docker-identity`),
mounts it at
container `/tmp/atlas-ssh/id_rsa`, sets `safe.directory=*`, and does **not**
post-run `chown` (bind-mount writes already match the runner). SSH staging is
deleted in `finally`. Phase 6 mode B
durable state is `<INVENTORY_DIR>/tfstate/<cluster_id>/` — jobs do **not**
require a controller `tfstate-repo/` checkout. If a leftover `tfstate-repo/`
exists beside clusterctl, it is safe to remove after a green deploy. Older
clusterctl wrote `.cache/docker-identity/id_rsa`; that path is
**no longer created**. Safe cleanup on the runner/controller checkout:

```bash
rm -rf .cache/docker-identity
```

Keep `/.cache/` in `.gitignore` (pip/other CI cache may remain). If a
**previous** root-image run left root-owned trees under
`workspace/<cluster_id>/` / `INV_DIR/tfstate` / `INV_DIR/.git`, one-time cleanup
may still be needed (`sudo chown -R gitlab-runner …`).

### Phase 6 Stage 5 / P1 — inventory as TF local_dir

Seed and deploy both call
[`examples/internal/ci/prepare_inventory_checkout.sh`](../examples/internal/ci/prepare_inventory_checkout.sh).
Both jobs share GitLab **`resource_group: atlas-clusterctl-inventory`** so only one
writer touches persistent `INVENTORY_DIR` + `tfstate/` at a time (do not run two
deploys against the same runner workspace in parallel).

1. Checkout inventory → `clusters.path` parent is mode-B
   `provision_tf_state_local_dir` (`atlas_inventory_root`).
2. **Never** create `tfstate-repo/` under the clusterctl checkout.
3. Dirty paths **outside** `tfstate/` → job fails (deploy), or seed with
   `INV_RESET_HARD=true` (default) discards them. No silent whole-repo reset on
   deploy.
4. Dirty **working tree** under `tfstate/` → discarded before refresh (not
   commits). This mirrors role `provision_tf_state_git_discard_local`; it is
   **not** a substitute for a successful `11` push.
5. Refresh = `fetch` + checkout named branch + **`merge --ff-only`**. Never
   `checkout -B FETCH_HEAD`. If the runner is **ahead** or **diverged** from
   `origin` (e.g. unpushed TF commits after a failed push) → **fail** on deploy.
   Seed defaults `INV_RESET_HARD=true` → `git reset --hard origin/<ref>`.
6. **`INV_FETCH_MODE`:** seed = `shallow` (fresh clone may be `--depth 1`);
   deploy = `full` (unshallow/deepen when needed — inventory is the TF SoT).
   On an **existing non-shallow** checkout, seed never uses `fetch --depth 1`
   (avoids re-shallowing after a full deploy on persistent runners).

On **run**, deploy injects `-e provision_tf_state_git_discard_local=true` by
default (roles discard **working tree** under `tfstate/` only; never
`clusters/`, never `reset --hard` of unpushed commits). Opt out with CI/CD
variable `TFSTATE_GIT_DISCARD_LOCAL=false`, or set the token explicitly in
`extra_vars` (e.g. `provision_tf_state_git_discard_local=false`).

## Stages (deploy)

Same order as [`Jenkinsfile.local`](../examples/internal/Jenkinsfile.local):
inventory → preflight → repos sync → validate → smoke → plan → run.

## Related

- Jenkins seed contract: [`jenkins-seed.md`](jenkins-seed.md)
- Example README: [`examples/internal/README.md`](../examples/internal/README.md)
- Generator: [`examples/internal/seed/generate_gitlab_ci.py`](../examples/internal/seed/generate_gitlab_ci.py)
