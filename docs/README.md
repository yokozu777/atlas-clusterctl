# clusterctl documentation

Operator documentation for `atlas-clusterctl`. Runtime is **schema v2 only** (`playbooks` + `phases`).

```
  Start here  -->  Operations  -->  Stacks
```

Public SoT layout: `clusters/_template/*` and `clusters/default/`.  
Private labs / inventory (`.config/config.yaml` or `ATLAS_CLUSTERS_ROOT`) — [local-labs.md](local-labs.md).

## Start here

| Doc | Audience | Contents |
|-----|----------|----------|
| [clusterctl.md](clusterctl.md) | Operators | CLI: commands, examples, env |
| [cluster-config-v2.md](cluster-config-v2.md) | Authors of `cluster.yaml` | `playbooks`, `phases` (inline aliases — ADR 007); YAML `stacks:` removed — ADR 005 |
| [clusters.md](clusters.md) | Cluster operators | layout, templates, group_vars, init, [leaf contract](clusters.md#leaf-filesystem-contract) |
| [adr/](adr/README.md) | Maintainers | accepted ADRs (003 optional `cluster.yml`; 004 universal `export_template`; 005 remove YAML `stacks`; 006 redundant `playbooks_enabled: true`; 007 inline phase aliases; 008 `--phases` CLI selector; 009 unify `run`/`stage`/`play`) |
| [local-labs.md](local-labs.md) | Maintainers with private labs | `.config/config.yaml` / `ATLAS_CLUSTERS_ROOT` |
| [pre-publish.md](pre-publish.md) | Maintainers before public remote | checklist, push dry-run, history rewrite |
| [workspace.md](workspace.md) | Everyone | runtime paths, logs, repos, durable TF (inventory `tfstate/` / legacy `tfstate-repo/`) |
| [validate.md](validate.md) | CI / pre-flight | `validate`, `smoke`, inventory gates, `./tests/run_ci.sh` |

## Operations

| Doc | Contents |
|-----|----------|
| [execution.md](execution.md) | `local` vs `docker` executor ([`yokozu/krang:336`](https://hub.docker.com/r/yokozu/krang)) |
| [ansible.md](ansible.md) | `ansible.cfg`, phase env, materialized vars |
| [jenkins.md](jenkins.md) | Jenkins Pipeline samples + operator workflow (`examples/internal/`) |
| [jenkins-seed.md](jenkins-seed.md) | Manual seed job — `CLUSTER_ID` choice (UI SoT) |
| [gitlab-ci.md](gitlab-ci.md) | GitLab CI sample (`examples/internal/.gitlab-ci.yml`) |
| [playbooks.md](playbooks.md) | Sibling repo sync (`repos` / `playbooks`) |

## Stacks

Per-stack orchestration (phases, inventory, vars bridge): **[stacks/README.md](stacks/README.md)**.

| Doc | Contents |
|-----|----------|
| [compute-provision.md](stacks/compute-provision.md) | PVE templates + Terraform VMs (`atlas-compute-provision`) |
| [infra-edge.md](stacks/infra-edge.md) | DNS / CA / registry (`atlas-infra-edge`) |
| [k8s-core.md](stacks/k8s-core.md) | Kubernetes control-plane (`atlas-k8s-core`) |
| [k8s-addons.md](stacks/k8s-addons.md) | Platform addons / Helm (`atlas-k8s-addons`) |
| [jenkins-agent.md](stacks/jenkins-agent.md) | Jenkins agents (`atlas-jenkins-agent`) |
| [gitlab-runner.md](stacks/gitlab-runner.md) | GitLab runners (`atlas-gitlab-runner`) |
| [postgresql.md](stacks/postgresql.md) | PostgreSQL HA (`atlas-postgresql`) |
| [redis.md](stacks/redis.md) | Redis Cluster HA (`atlas-redis`) |
| [kafka.md](stacks/kafka.md) | Kafka KRaft HA (`atlas-kafka`) |

## Quick start

```bash
./cluster list
./cluster init demo/k8s --template k8s_full --dns-suffix demo.example.com
./cluster use demo/k8s
# fill atlas-<repo>.secrets.yml (prefer Ansible Vault); edit hosts
./cluster validate --cluster demo/k8s
./cluster plan -v
# ./cluster run --phases provision..k8s-addons   # after golden templates + siblings + secrets
# # slices: provision | provision..k8s-core | k8s-core..k8s-addons
```

Data-plane / agent scaffolds:

```bash
# Redis (see stacks/redis.md)
./cluster init demo/redis --template redis
./cluster use demo/redis
./cluster validate && ./cluster plan -v
# ./cluster run && ./cluster run --phases redis --tags 204_redis_verify

# PostgreSQL HA (see stacks/postgresql.md)
./cluster init demo/pgsql --template postgresql
./cluster use demo/pgsql
# ./cluster run --phases provision..postgresql
# ./cluster run --phases postgresql --tags 202_pgsql_patroni_verify --limit pgsql_cluster

# Kafka KRaft (see stacks/kafka.md)
./cluster init demo/kafka --template kafka
./cluster use demo/kafka
# ./cluster run --phases provision..kafka
# ./cluster run --phases kafka --tags 203_kafka_verify --limit kafka_brokers

# Jenkins agents (see stacks/jenkins-agent.md)
./cluster init demo/jenkins --template jenkins_agent

# GitLab runners (see stacks/gitlab-runner.md)
./cluster init demo/gitlab --template gitlab_runner
./cluster use demo/jenkins
# ./cluster run --phases provision..jenkins-agent
# ./cluster run --phases jenkins-agent --tags 03_install_jslave --limit jslave

# Infra platform only (see stacks/infra-edge.md)
# Window: provision → init-infra → infra → init-infra-post
# (golden templates: --template pve_templates)
./cluster init demo/infra --template infra_edge
./cluster use demo/infra
# ./cluster run --phases provision..init-infra-post
# ./cluster run --phases infra --tags 01_validate_vars

# Full k8s (see stacks/compute-provision.md, k8s-core.md, k8s-addons.md)
# Phases: provision → init → k8s-core → k8s-addons
# DNS/CA/registry: separate leaf (--template infra_edge) — stacks/infra-edge.md
./cluster init demo/k8s --template k8s_full
./cluster use demo/k8s
./cluster validate
# ./cluster run --phases provision
# ./cluster run --phases provision --tags 00_validate_provision
# ./cluster run --phases provision..k8s-core
# ./cluster run --phases k8s-core..k8s-addons
# # or full leaf window:
# ./cluster run --phases provision..k8s-addons
```

Local org labs (if present on disk): [local-labs.md](local-labs.md).

## Repo map

| Path | Role |
|------|------|
| `clusterctl/` | Python engine |
| `clusters/_template/*/` | Public scaffolds for `./cluster init --template …` |
| `clusters/default/default/` | Org policy stub (not deployable; customize if needed) |
| `clusters/ci/`, `clusters/dev/` | Local org labs only — [local-labs.md](local-labs.md) (gitignored) |
| `workspace/` | Runtime (gitignored): logs, tf state, cloned repos |
| `examples/internal/` | Org-coupled samples (not product path) |

Breaking-change history: [CHANGELOG.md](../CHANGELOG.md).
