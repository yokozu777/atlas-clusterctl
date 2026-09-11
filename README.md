# atlas-clusterctl

Ansible **controller** for provisioning and operating Atlas clusters on Proxmox
(Kubernetes full stack and data-plane labs: Redis, PostgreSQL, Kafka, Jenkins agents).

This repository is the **orchestrator only**: CLI, cluster layout, validate/plan/run,
and playbook-repo sync. Playbook **roles live in sibling git repos** — they are not
vendored here.

| | |
|--|--|
| **CLI** | `./cluster` → `python3 -m clusterctl` (schema v2: `playbooks` + `phases`) |
| **License** | Apache-2.0 — [`LICENSE`](LICENSE) |
| **Security** | [`SECURITY.md`](SECURITY.md) |
| **Version** | `clusterctl.__version__` / `pyproject.toml` (`0.1.0`) |

## Compatibility

Controller host (where you run `./cluster`):

- Linux, Python **3.11+**
- `PyYAML` (`pip install -r requirements.txt` or `pip install -e .`)
- For live runs: Ansible **2.14+**, SSH client; optional Docker executor ([`yokozu/krang:336`](https://hub.docker.com/r/yokozu/krang) — [build](https://github.com/yokozu777/infrastructure-automation-toolkit))
- Writable `workspace/` under the controller root (gitignored)

Playbook execution targets (guests / Proxmox) are defined by sibling repos — see
[Sibling playbook repos](#sibling-playbook-repos).

## How it fits together

```
  Operator
     |
     v
  ./cluster  ------->  atlas-clusterctl (orchestrator)
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
     clusters/<env>/<name>   workspace/<id>/   sibling playbook repos
     (inventory+group_vars)  (logs, tf, repos) (roles live here)
                                                  |
                                                  v
                                            Proxmox / guests
```

Operator flow:

```
  init --template  -->  use  -->  repos sync  -->  validate  -->  plan  -->  run / play
```

## Quick start

Public path (no local labs required):

```bash
git clone <this-repo> atlas-clusterctl
cd atlas-clusterctl

# deps (use a venv on PEP 668 / externally-managed Python)
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt   # or: pip install -e .

./cluster list
./cluster init demo/k8s --template k8s_full --dns-suffix demo.example.com
./cluster use demo/k8s
# fill atlas-<repo>.secrets.yml (prefer Ansible Vault); edit hosts
./cluster validate --cluster demo/k8s
./cluster plan -v
# ./cluster run --phases provision..k8s-addons   # after golden templates + secrets + siblings
```

Other scaffolds: `--template infra_edge` | `jenkins_agent` | `gitlab_runner` | `postgresql` | `redis` | `kafka` | `pve_templates`.

Preferred entrypoint from a clone is **`./cluster`** (sets `ATLAS_CLUSTER_ROOT` to the
repo root). Equivalent: `ATLAS_CLUSTER_ROOT=$PWD python3 -m clusterctl …`.
After `pip install -e .`, the `cluster` console script works the same when
`ATLAS_CLUSTER_ROOT` points at this tree (or you `cd` here).

## Sibling playbook repos

**Contract:** `atlas-clusterctl` does **not** ship Ansible roles. Materialize playbook
trees next to this clone (`source: local`, `path_relative_to: sibling`) or via
`./cluster repos sync` / `./cluster playbooks sync` (`source: git`).

```
  atlas-clusterctl
       |
       |  cluster.yaml phases + ./cluster run|play
       |
       +-----> atlas-compute-provision     (templates, provision)
       +-----> atlas-node-foundation       (init-infra, init)
       +-----> atlas-infra-edge            (infra)
       +-----> atlas-k8s-core              (k8s-core)
       +-----> atlas-k8s-addons            (k8s-addons)
       +-----> atlas-postgresql / redis / kafka / jenkins-agent / gitlab-runner
```

| Sibling (directory name) | Typical phases |
|--------------------------|----------------|
| `atlas-compute-provision` | templates, provision |
| `atlas-node-foundation` | init-infra, init |
| `atlas-infra-edge` | infra |
| `atlas-k8s-core` | k8s-core |
| `atlas-k8s-addons` | k8s-addons |
| `atlas-jenkins-agent` | jenkins-agent |
| `atlas-gitlab-runner` | gitlab-runner |
| `atlas-postgresql` / `atlas-redis` / `atlas-kafka` | data-plane stacks |

Galaxy collections are installed from each sibling’s `requirements.yml` (bootstrap),
not from this controller package.

See [`docs/playbooks.md`](docs/playbooks.md). Public full k8s phase order (`k8s_full`;
golden PVE images are a separate `--template pve_templates` leaf):

```
  provision --> init --> k8s-core --> k8s-addons
```

Infra platform is a separate template (`infra_edge`):

```
  provision --> init-infra --> infra --> init-infra-post
```

Data-plane / agent scaffolds are shorter (also start at `provision`):

```
  provision --> init --> <stack>
```

## Local labs vs public tree

| Path | Published? | Role |
|------|------------|------|
| `clusters/_template/*` | yes | Init scaffolds |
| `clusters/default/` | yes | Org policy stubs |
| Private inventory (`clusters.path` / `ATLAS_CLUSTERS_ROOT`) | **no** (separate repo) | Live labs (`ci/`, `dev/`, …) |
| `clusters/ci/`, `clusters/dev/` in this clone | **no** (gitignored) | Legacy in-tree labs |

Preferred: local `.config/config.yaml` in this clone pointing at a private inventory tree.
Template: [`.config/config.yaml.example`](.config/config.yaml.example) (runtime file is gitignored):

```bash
cp .config/config.yaml.example .config/config.yaml
# set clusters.path → e.g. ../atlas-inventory/clusters
# optional: workspace.path → runtime parent
```

```
  public controller                  private inventory
  -----------------                  -----------------------
  clusters/_template/*  --init-->    <inventory>/clusters/<env>/<name>
  clusters/default/         ^
  .config/config.yaml.example
  .config/config.yaml -----+
```

Details: [`docs/local-labs.md`](docs/local-labs.md), [`docs/workspace.md`](docs/workspace.md).

Keep labs on disk for day-to-day ops; they must not be pushed to a public remote.
Verify with `./cluster list` (see [`docs/local-labs.md`](docs/local-labs.md), [`SECURITY.md`](SECURITY.md)).

## Optional operator UI

Sibling **atlas-ui** (checkout next to this repo, typically `../atlas-ui`): Next.js + shadcn
console that spawns this CLI (`./cluster`). Loopback only — same trust as a shell on
the controller. Not part of `phases:`.

## Jenkins Pipeline

Samples: [`examples/internal/`](examples/internal/) — deploy (`Jenkinsfile` /
`Jenkinsfile.local`) plus optional **seed** job for the `CLUSTER_ID` dropdown.

| Doc | Content |
|-----|---------|
| [`docs/jenkins.md`](docs/jenkins.md) | Operator workflow, plugins, agent software, params |
| [`docs/jenkins-seed.md`](docs/jenkins-seed.md) | Seed contract (manual Build only; UI SoT = seed) |
| [`examples/internal/README.md`](examples/internal/README.md) | Short internal how-to |

**Bootstrap:** build `atlas-clusterctl-seed` once before **Build with Parameters** on
the deploy job. Deploy Jenkinsfiles omit `parameters {}` — seed owns the UI.
Re-run seed after inventory leaf add/rename/remove.

Agent must already provide tools (python3, PyYAML, git, ssh/sshpass, …) — samples do
not `pip install` on the agent. Prefer a labeled Atlas agent over the controller.

## Documentation

Full index: **[docs/README.md](docs/README.md)**

| Topic | Doc |
|-------|-----|
| Schema v2 | [docs/cluster-config-v2.md](docs/cluster-config-v2.md) |
| CLI | [docs/clusterctl.md](docs/clusterctl.md) |
| Cluster layout | [docs/clusters.md](docs/clusters.md) |
| Playbooks sync | [docs/playbooks.md](docs/playbooks.md) |
| **Stack orchestration** | **[docs/stacks/README.md](docs/stacks/README.md)** — provision, k8s, data-plane, Jenkins agents |
| Validate / smoke | [docs/validate.md](docs/validate.md) |
| Local labs | [docs/local-labs.md](docs/local-labs.md) |
| Jenkins Pipeline | [docs/jenkins.md](docs/jenkins.md) · [jenkins-seed.md](docs/jenkins-seed.md) |
| Pre-publish | [docs/pre-publish.md](docs/pre-publish.md) |

Per-stack guides (phases, inventory, vars bridge): [compute-provision](docs/stacks/compute-provision.md),
[infra-edge](docs/stacks/infra-edge.md), [k8s-core](docs/stacks/k8s-core.md),
[k8s-addons](docs/stacks/k8s-addons.md), [jenkins-agent](docs/stacks/jenkins-agent.md), [gitlab-runner](docs/stacks/gitlab-runner.md),
[postgresql](docs/stacks/postgresql.md), [redis](docs/stacks/redis.md), [kafka](docs/stacks/kafka.md).

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
# or editable: python3 -m pip install -e .
# (optional alias) python3 -m pip install -e ".[dev]"  # same deps; see pyproject.toml

# Same gates as GitHub Actions (preferred before a PR)
./tests/run_ci.sh

# Unittest only
python3 -m unittest discover -s tests
```

`./tests/run_ci.sh` runs packaging smoke, unittest, `ci_preflight --skip-tests`,
public template YAML parse, and a publish-hygiene fingerprint scan. Dual-track tests:
public CI does **not** require `clusters/ci` / `clusters/dev`; optional labs are skipped
via `tests/lab_support.py` when absent. Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

Packaging metadata: [`pyproject.toml`](pyproject.toml). Runtime pin:
[`requirements.txt`](requirements.txt).

## Layout

```
clusters/            # per-cluster inventory + cluster.yaml
  _template/         # public scaffolds (./cluster init --template …)
  default/           # org policy stubs (published)
  ci/  dev/          # local labs only (gitignored)
clusterctl/          # Python engine
docs/                # operator documentation (see docs/stacks/ for per-stack guides)
examples/internal/   # org-coupled samples (not product path)
tests/               # unittest + run_ci.sh / hygiene helpers
.github/workflows/   # public CI (no labs required)
workspace/           # runtime (gitignored): logs, tf state, cloned repos
./cluster            # recommended CLI wrapper
```

## Security

Do not commit live secrets, production inventories, or private labs into tracked paths.
Reporting and history notes: [`SECURITY.md`](SECURITY.md).

## Contributing

1. Keep product paths free of org fingerprints (`example.com` / `CHANGEME` in templates).
2. Prefer `_template/*` as public SoT; put live overlays only under gitignored labs.
3. Run `./tests/run_ci.sh` before proposing changes.
4. Do not vendor sibling playbook roles into this tree.
5. Do not add a repo-root `scripts/` directory (layout convention — use `./cluster` / `tests/`).
6. Before a public remote, follow [`docs/pre-publish.md`](docs/pre-publish.md)
   (history rewrite is separate and operator-owned).

Breaking-change history: [`CHANGELOG.md`](CHANGELOG.md).
