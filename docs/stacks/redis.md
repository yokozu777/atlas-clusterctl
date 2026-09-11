# Redis Cluster HA via clusterctl

`atlas-redis` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases `provision → init → redis`.

Canonical sibling playbook: `playbooks/redis_cluster.yaml`.  
Operational role details (Predixy source/prebuilt, VIP, troubleshooting) live in the sibling README, not here.

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/redis/` | Public SoT HA scaffold (3 masters + 3 replicas + 2 proxy + 2 lb) |

```bash
./cluster init demo/redis --template redis
./cluster use demo/redis
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..redis

# targeted after green LB:
./cluster run --phases redis --tags 204_redis_verify --limit redis_cluster_masters:redis_cluster_replicas
```

Another env:

```bash
./cluster init prod/redis --template redis
# then: hosts, VIP/passwords, mirrors, secrets → validate → run
```

Optional local org labs: [../local-labs.md](../local-labs.md).

## Phase map

```
  provision --> init --> redis
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init` | `atlas-node-foundation/init` | OS bootstrap (+ managed package repos) |
| `redis` | `atlas-redis/cluster` | Redis nodes → cluster → Predixy → LB → verify |

(`templates` stays in the playbooks catalog for emergency rebuilds; default plan starts at `provision`. Factory: `--template pve_templates` — [compute-provision.md](compute-provision.md).)

Leaf `phases:` lists only redis pipeline refs — omit infra/k8s phase refs.

## Tagged invocations (`atlas-redis/cluster`)

Order in `cluster.yaml` (do not skip verify when accepting VIP):

| # | Tags | Limit |
|---|------|--------|
| 1 | `01_validate_vars` | (all relevant) |
| 2 | `200_redis_node` | `redis_cluster_masters:redis_cluster_replicas` |
| 3 | `201_redis_cluster` | `redis_cluster_masters:redis_cluster_replicas` |
| 4 | `202_redis_proxy` | `redis_proxies` |
| 5 | `203_redis_lb` | `redis_lbs` |
| 6 | `204_redis_verify` | `redis_cluster_masters:redis_cluster_replicas` |

The first invocation in each phase is `00_ensure_workspace` (playbook tag, not `always`). Later tagged invocations do not re-run workspace bootstrap. For `init`, the first remote invocation also includes `00_gather_facts` (with `root_ssh`); ensure-only stays localhost. Later init tags reuse `ansible_facts` via `atlas-node-foundation` `fact_caching=jsonfile` (workspace `ANSIBLE_CACHE_PLUGIN_CONNECTION`).

You may rename inventory groups, but then update in sync:

1. `hosts` (group names),
2. `limit:` in `cluster.yaml` invocations,
3. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
4. override `redis_*_hosts` in `atlas-redis.yml` (see below).

## Inventory contract

Validate expects groups:

| Group | Role |
|-------|------|
| `redis` | Parent (no hosts) |
| `redis_cluster_masters` | Redis Cluster masters (≥3) |
| `redis_cluster_replicas` | replicas (`masters × redis_cluster_replicas_per_master`) |
| `redis_proxies` | Predixy (≥2) |
| `redis_lbs` | HAProxy + Keepalived (≥2) |

Sibling playbook targeting uses variables (defaults = names above):

```yaml
# group_vars/all/atlas-redis.yml — explicit in template/leaf
redis_master_hosts: redis_cluster_masters
redis_replica_hosts: redis_cluster_replicas
redis_proxy_hosts: redis_proxies
redis_lb_hosts: redis_lbs
```

`./cluster run --phases … --limit` still uses **inventory group names**, not values of these vars.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init` phase)

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `redis_cluster_masters:redis_cluster_replicas:redis_proxies:redis_lbs` |
| `pkg_repo_base` / `pkg_repos` / `pkg_repos_extra` | typically OS base in env `pkg_repos`; leaf may omit extras |

`atlas-redis` does **not** consume `pkg_repos` itself (Redis/Predixy build on controller); foundation owns node package sources.

### `group_vars/all/atlas-redis.yml` (`redis` phase)

| Knob | Meaning |
|------|---------|
| `redis_*_hosts` | inventory group names for sibling targeting |
| `vip_*`, `predixy_*`, `redis_version` | application SoT |
| `redis_download_mirror_url` / `predixy_download_url` | optional HTTP(S) mirrors (**leaf-only**; sibling defaults empty) |
| `predixy_install_method` | often `source` on older CPUs without BMI2/ADX |

Standalone sibling defaults: public GitHub URLs, `predixy_install_method: prebuilt`.  
`vip_auth_pass` lives in `atlas-redis.secrets.yml` (sibling / leaf; Vault-friendly).  
Org mirrors and VIP address live in clusterctl `atlas-redis.yml`.

### `group_vars/all/atlas-redis.secrets.yml`

| Knob | Meaning |
|------|---------|
| `vip_auth_pass` | Keepalived PASS — **max 8 characters** |
| `redis_requirepass` | optional Redis AUTH (empty = disabled) |

### `group_vars/all/atlas-compute-provision.yml`

`provision_stack: redis` and map inventory → VM templates. Do not mix with k8s provision maps.

## Sibling mount

Typical mount:

```yaml
atlas-redis:
  source: local
  path: atlas-redis
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    cluster:
      file: playbooks/redis_cluster.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export redis`).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/redis/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-redis README** | Standalone quickstart, tags, role behaviour |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags in `_template/redis` `cluster.yaml` match current sibling tags (+ leading `00_ensure_workspace`).  
2. `redis_*_hosts` in `atlas-redis.yml` match group names in `hosts` and `limit:` in `cluster.yaml`.  
3. `node_foundation_init_hosts` covers all four groups.  
4. `./cluster init … --template redis` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_ci_redis_cluster.py`.  
5. Do not move clusterctl-only instructions into sibling README (short Integrations only, no orchestrator CLI).
