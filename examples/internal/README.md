# INTERNAL samples

## Jenkinsfiles

Two Declarative Pipeline samples for `./cluster` (schema v2). Full guide:
[`docs/jenkins.md`](../../docs/jenkins.md) (start with **Operator workflow**).

| File | Jenkins agent | Leaf `execution.mode` |
|------|---------------|------------------------|
| [`Jenkinsfile`](Jenkinsfile) | Docker Pipeline (`harbor.mxhash.com/library/krang` + `docker.sock`) | **`docker`** |
| [`Jenkinsfile.local`](Jenkinsfile.local) | Normal agent (label / VM) | from leaf `cluster.yaml` |
| [`seed/Jenkinsfile`](seed/Jenkinsfile) | Any agent (python3 + git) | *(seed — UI params)* |

## GitLab CI

Sample: [`.gitlab-ci.yml`](.gitlab-ci.yml) (+ [`gitlab-ci.jobs.yml`](gitlab-ci.jobs.yml)) —
operator doc: [`docs/gitlab-ci.md`](../../docs/gitlab-ci.md).

| Job | When | What |
|-----|------|------|
| `seed` | manual | Inventory scan → regenerate `cluster_id` / `phases` / `limit` dropdowns (Jenkins seed analog) |
| `deploy` | manual | Jenkinsfile.local-style `./cluster` flow (optional `ci_preflight --skip-tests`) |

Point **CI/CD configuration file** at `examples/internal/.gitlab-ci.yml`. Shell
runner needs `python3` + `python3-venv` (jobs use a project `.venv`, not system
pip). Set project CI/CD Variable **`INVENTORY_GIT_URL`**, then **Run pipeline** →
play **`seed`** (needs `GITLAB_PUSH_TOKEN` or manual commit of the artifact).
Then deploy with dropdowns.

### Seed (`CLUSTER_ID` choice)

UI SoT = seed Job DSL. Deploy samples **omit** `parameters {}`.

- Contract: [`docs/jenkins-seed.md`](../../docs/jenkins-seed.md)
- How-to: [`seed/README.md`](seed/)
- Overview workflow: [`docs/jenkins.md`](../../docs/jenkins.md)

**Manual Build only** for seed (no cron / webhook). Re-run seed after inventory
leaf add/rename/remove.

Do **not** mix: `execution.mode: local` inside the Docker Pipeline agent often hits
Ansible `Local RPC server did not start`. Use `Jenkinsfile.local` on a real VM/host
agent instead.

Samples assume plugins and agent software are **already installed** — no OS bootstrap
or `pip install` in the Pipeline.

### Required Jenkins plugins

Install on the controller before the first build:

| Plugin | ID | Why |
|--------|----|-----|
| Pipeline | `workflow-aggregator` | Declarative pipeline |
| Pipeline: Declarative | `pipeline-model-definition` | Stages / options |
| Git | `git` | SCM checkout |
| Credentials Binding | `credentials-binding` | `withCredentials` |
| SSH Credentials | `ssh-credentials` | `sshUserPrivateKey` |
| Pipeline Utility Steps | `pipeline-utility-steps` | `readJSON` (`plan.json` → Run stages) |
| AnsiColor | `ansicolor` | `ansiColor('xterm')` |
| Timestamper | `timestamper` | `timestamps()` |
| Workspace Cleanup | `ws-cleanup` | `cleanWs()` |
| Docker Pipeline | `docker-workflow` | `agent { docker { } }` — **`Jenkinsfile` only** |
| Job DSL | `job-dsl` | Seed job — [`docs/jenkins-seed.md`](../../docs/jenkins-seed.md) |

Also: Script Approval may be needed the first time the **seed** Job DSL runs.

### Agent software

**Common** (host agent or `krang` container that runs `./cluster`):

- `python3`, **PyYAML**, `git`, `openssh-client` (`ssh`), `sshpass`
- writable `/tmp/clusterctl`

**`Jenkinsfile` (Docker Pipeline)** — leaf `execution.mode: docker`:

| Layer | Needs |
|-------|--------|
| Jenkins **node** | Docker Engine, usable `/var/run/docker.sock`, Harbor pull |
| Agent **image** (`krang`) | Common tools + **Docker CLI** |
| Nested **executor** (`execution.image:tag`) | Ansible (+ collections); often same `krang` |

**`Jenkinsfile.local`** — leaf `execution.mode: local`:

| Layer | Needs |
|-------|--------|
| Jenkins **node** | Common tools + **ansible** / `ansible-playbook` (+ galaxy collections as used by synced repos) |

Prefer an Atlas jenkins-agent node — not the Jenkins controller container.

**Credentials:** SSH private-key id matching `GIT_SSH_CREDENTIALS_ID` (sample default
`ssh_git`) for private inventory / playbook remotes.

### How to use

**Bootstrap**

1. Install plugins + agent software (tables above).
2. Create/build `atlas-clusterctl-seed` (`examples/internal/seed/Jenkinsfile`).
3. Open deploy job from seed (`atlas-clusterctl` / `-local`) — or point a Pipeline
   job at `Jenkinsfile` / `.local` and re-run seed so params exist.
4. Match leaf `execution.mode` to the Jenkinsfile.

**Deploy (day-to-day)**

1. **Build with Parameters**: pick `CLUSTER_ID` and `AGENT` (node list), optional
   `INVENTORY_GIT_URL` / `PHASES` (Active Choices checkboxes; none = plan SoT without `--phases`) / `TAGS` / `LIMIT` /
   `EXTRA_VARS`, … — see [`docs/jenkins-seed.md`](../../docs/jenkins-seed.md#follow-up-phases-parameter-contract).
   Seed `cluster-phases.json` is a YAML lookup only (may differ from plan if `when:` applies).
2. Re-run **seed** only when inventory leaves change (add/rename/remove).

Optional `INVENTORY_GIT_URL` checkouts a private inventory repo and wires
`.config/config.yaml` `clusters.path` (see [`docs/local-labs.md`](../../docs/local-labs.md)).
Phase 6 Stage 5 / P1: checkout uses
[`ci/prepare_inventory_checkout.sh`](ci/prepare_inventory_checkout.sh) (inventory =
mode-B TF `local_dir`; no controller `tfstate-repo/`; dirty outside `tfstate/`
fails; working-tree dirt under `tfstate/` discarded; ff-only refresh — fail if
ahead/diverged; seed `INV_FETCH_MODE=shallow`, deploy `full`; GitLab
`resource_group: atlas-clusterctl-inventory`). Run defaults
`provision_tf_state_git_discard_local=true` (`TFSTATE_GIT_DISCARD_LOCAL=false` to
opt out).

Local labs stay out of the public tree — private inventory + `.config/config.yaml`,
or in-tree `clusters/ci/` / `clusters/dev/` (gitignored). Public scaffolds:
`clusters/_template/`, `clusters/default/`.
