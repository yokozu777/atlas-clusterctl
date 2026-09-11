# Kafka KRaft HA via clusterctl

`atlas-kafka` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases `provision → init → kafka`.

Canonical sibling playbook: `playbooks/kafka_cluster.yaml`.  
Operational role details (KRaft format, `kafka_node_id`, troubleshooting) live in the sibling README, not here.

Scheme B: dedicated controllers + brokers. **No ZooKeeper. No L4 VIP** on the Kafka protocol path.

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/kafka/` | Public SoT HA scaffold (3 controllers + 3 brokers) |

```bash
./cluster init demo/kafka --template kafka
./cluster use demo/kafka
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..kafka

# targeted after green brokers:
./cluster run --phases kafka --tags 203_kafka_verify --limit kafka_brokers
```

Another env:

```bash
./cluster init prod/kafka --template kafka
# then: hosts + kafka_node_id, mirrors, atlas-*.secrets.yml → validate → run
```

Optional local org labs: [../local-labs.md](../local-labs.md).

## Secrets

| File | Notes |
|------|--------|
| `atlas-kafka.secrets.yml` | Stub for plaintext lab; SASL/TLS keys when `kafka_security_mode != plaintext` |
| `atlas-compute-provision.secrets.yml` / `atlas-node-foundation.secrets.yml` | PVE/DNS / bootstrap |

Prefer Ansible Vault on product `*.secrets.yml` (not gitignore).

## Phase map

```
  provision --> init --> kafka
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init` | `atlas-node-foundation/init` | OS bootstrap (+ managed package repos) |
| `kafka` | `atlas-kafka/cluster` | install → controllers → brokers → verify |

(`templates` stays in the playbooks catalog for emergency rebuilds; default plan starts at `provision`. Factory: `--template pve_templates` — [compute-provision.md](compute-provision.md).)

Leaf `phases:` lists only kafka pipeline refs — omit infra/k8s phase refs.

## Tagged invocations (`atlas-kafka/cluster`)

Order in `cluster.yaml` (do not skip verify on acceptance):

| # | Tags | Limit |
|---|------|--------|
| 1 | `01_validate_vars` | (all relevant) |
| 2 | `200_kafka_node` | `kafka_controllers:kafka_brokers` |
| 3 | `201_kafka_controllers` | `kafka_controllers` |
| 4 | `202_kafka_brokers` | `kafka_brokers` |
| 5 | `203_kafka_verify` | `kafka_brokers` |

The first invocation in each phase is `00_ensure_workspace` (playbook tag, not `always`). Later tagged invocations do not re-run workspace bootstrap. For `init`, the first remote invocation also includes `00_gather_facts` (with `root_ssh`); ensure-only stays localhost. Later init tags reuse `ansible_facts` via `atlas-node-foundation` `fact_caching=jsonfile` (workspace `ANSIBLE_CACHE_PLUGIN_CONNECTION`).

You may rename inventory groups, but then update in sync:

1. `hosts` (group names),
2. `limit:` in `cluster.yaml` invocations,
3. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
4. override `kafka_*_hosts` in `atlas-kafka.yml` (see below).

## Inventory contract

Validate expects groups:

| Group | Role | Sizing |
|-------|------|--------|
| `kafka` | Parent (no hosts) | — |
| `kafka_controllers` | KRaft controllers | odd ≥ 3 |
| `kafka_brokers` | Brokers | ≥ 3 |

Each host must set a stable unique **`kafka_node_id`** (controllers `1..99`, brokers `≥100` per sibling defaults). Controllers and brokers do not overlap on hosts.

Sibling playbook targeting uses variables (defaults = names above):

```yaml
# group_vars/all/atlas-kafka.yml — explicit in template/leaf
kafka_controller_hosts: kafka_controllers
kafka_broker_hosts: kafka_brokers
```

`./cluster run --phases … --limit` still uses **inventory group names**, not values of these vars.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init` phase)

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `kafka_controllers:kafka_brokers` |
| `pkg_repo_base` / `pkg_repos` / `pkg_repos_extra` | typically OS base in env `pkg_repos`; leaf may omit extras |

`atlas-kafka` does **not** consume `pkg_repos` itself (binary downloads on controller); foundation owns node package sources.

### `group_vars/all/atlas-kafka.yml` (`kafka` phase)

| Knob | Meaning |
|------|---------|
| `kafka_controller_hosts` / `kafka_broker_hosts` | inventory group names for sibling targeting |
| `kafka_version` / `kafka_scala_version` / ports / `kafka_security_mode` | application SoT |
| `kafka_download_mirror_url` / `kafka_download_url` | optional HTTP(S) mirrors (**leaf-only**; sibling defaults empty) |
| `kafka_heap_opts` | JVM heap (often `1G`) |

Standalone sibling defaults: Apache downloads, `kafka_security_mode: plaintext`, neutral `kafka.example.com` workspace.  
Org mirrors and Leaf DNS identity live **only** in clusterctl `atlas-kafka.yml` (and sibling product overlays that declare the Leaf DNS block).

### `group_vars/all/atlas-compute-provision.yml`

`provision_stack: kafka` and map inventory → VM templates. Do not mix with k8s provision maps.

## Sibling mount

Typical mount:

```yaml
atlas-kafka:
  source: local
  path: atlas-kafka
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    cluster:
      file: playbooks/kafka_cluster.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export kafka`).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/kafka/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-kafka README** | Standalone quickstart, tags, role behaviour |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags in `_template/kafka` `cluster.yaml` match current sibling tags (+ leading `00_ensure_workspace`).  
2. `kafka_*_hosts` in `atlas-kafka.yml` match group names in `hosts` and `limit:` in `cluster.yaml`.  
3. `node_foundation_init_hosts` covers controllers + brokers.  
4. `./cluster init … --template kafka` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_ci_kafka_cluster.py`.  
5. Do not move clusterctl-only instructions into sibling README (short Integrations only, no orchestrator CLI).
