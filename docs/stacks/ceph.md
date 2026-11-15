# Ceph cephadm HA via clusterctl

`atlas-ceph` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases `provision → init → ceph`.

Canonical sibling playbook: `playbooks/ceph_cluster.yaml`.  
Operational role details (cephadm bootstrap, OSD devices, RGW troubleshooting) live in the sibling README, not here.

Colocated topology: MON + MGR + OSD + RGW on each of ≥ 3 hosts. **Not Rook** (Rook remains on k8s leaves).

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/ceph/` | Public SoT HA scaffold (3 colocated nodes + OSD data disks) |

```bash
./cluster init demo/ceph --template ceph
./cluster use demo/ceph
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..ceph

# targeted after green cluster:
./cluster run --phases ceph --tags 206_ceph_verify --limit ceph_nodes
```

Another env:

```bash
./cluster init prod/ceph --template ceph
# then: hosts + S3 keys, mirrors, atlas-*.secrets.yml → validate → run
```

Optional local org labs: [../local-labs.md](../local-labs.md).

## Secrets

| File | Notes |
|------|--------|
| `atlas-ceph.secrets.yml` | `ceph_s3_access_key` / `ceph_s3_secret_key` (required for 205_ceph_s3) |
| `atlas-compute-provision.secrets.yml` / `atlas-node-foundation.secrets.yml` | PVE/DNS / bootstrap |

Prefer Ansible Vault on product `*.secrets.yml` (not gitignore).

## Phase map

```
  provision --> init --> ceph
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init` | `atlas-node-foundation/init` | OS bootstrap (+ managed package repos) |
| `ceph` | `atlas-ceph/cluster` | prereqs → bootstrap → hosts → osds → rgw → s3 → verify |

(`templates` stays in the playbooks catalog for emergency rebuilds; default plan starts at `provision`. Factory: `--template pve_templates` — [compute-provision.md](compute-provision.md).)

Leaf `phases:` lists only ceph pipeline refs — omit infra/k8s phase refs.

## Tagged invocations (`atlas-ceph/cluster`)

Order in `cluster.yaml` (do not skip verify on acceptance):

| # | Tags | Limit |
|---|------|--------|
| 1 | `01_validate_vars` | (all relevant) |
| 2 | `200_ceph_prereqs` | `ceph_nodes` |
| 3 | `201_cephadm_bootstrap` | `ceph_nodes` (run_once on first) |
| 4 | `202_cephadm_hosts` | `ceph_nodes` |
| 5 | `203_ceph_osds` | `ceph_nodes` |
| 6 | `204_ceph_rgw` | `ceph_nodes` |
| 7 | `205_ceph_s3` | `ceph_nodes` |
| 8 | `206_ceph_verify` | `ceph_nodes` |

The first invocation in each phase is `00_ensure_workspace` (playbook tag, not `always`). Later tagged invocations do not re-run workspace bootstrap. For `init`, the first remote invocation also includes `00_gather_facts` (with `root_ssh`); ensure-only stays localhost. Later init tags reuse `ansible_facts` via `atlas-node-foundation` `fact_caching=jsonfile` (workspace `ANSIBLE_CACHE_PLUGIN_CONNECTION`).

You may rename inventory groups, but then update in sync:

1. `hosts` (group names),
2. `limit:` in `cluster.yaml` invocations,
3. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
4. override `ceph_*_hosts` in `atlas-ceph.yml` (see below),
5. `provision_inventory_group_map_ceph` keys in `atlas-compute-provision.yml`.

## Inventory contract

Validate expects groups:

| Group | Role | Sizing |
|-------|------|--------|
| `ceph` | Parent (no hosts) | — |
| `ceph_nodes` | Colocated mon/mgr/osd/rgw | ≥ 3 |

Sibling playbook targeting uses variables (defaults = names above):

```yaml
# group_vars/all/atlas-ceph.yml — explicit in template/leaf
ceph_node_hosts: ceph_nodes
ceph_mon_hosts: ceph_nodes
ceph_osd_hosts: ceph_nodes
ceph_rgw_hosts: ceph_nodes
```

`./cluster run --phases … --limit` still uses **inventory group names**, not values of these vars.

Each host should set **`hostname`** (prefer FQDN). Slot `1` is the OSD disk: `wwn` / `serial` on `provision.disks`, and `ceph_osd_devices` set to `/dev/disk/by-id/wwn-<wwn>`. Init tag `23_init_data_disk` wipes that disk raw. `ceph_osd_all_available_devices` is false, so role 203 adds only that path.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init` phase)

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `ceph_nodes` |
| `pkg_repo_base` / `pkg_repos` / `pkg_repos_extra` | typically OS base in env `pkg_repos`; leaf may omit extras |

### `group_vars/all/atlas-ceph.yml` (`ceph` phase)

| Knob | Meaning |
|------|---------|
| `ceph_*_hosts` | inventory group names for sibling targeting |
| `ceph_release` / `ceph_rgw_port` / dashboard / OSD policy | application SoT |
| `ceph_repo_mirror_url` / `ceph_cephadm_url` | optional HTTP(S) mirrors (**leaf-only**; sibling defaults empty) |
| `ceph_s3_user` / `ceph_s3_bucket` | S3 identity (keys in secrets) |

Standalone sibling defaults: Tentacle release, image `quay.io/ceph/ceph:v20.2.5`, RGW `7480`, neutral `ceph.example.com` workspace.  
Org mirrors and Leaf DNS identity live **only** in clusterctl `atlas-ceph.yml`.

### `group_vars/all/atlas-compute-provision.yml`

`provision_stack: ceph` and map inventory → VM templates. Do not mix with k8s provision maps.

## Sibling mount

Typical mount:

```yaml
atlas-ceph:
  source: local
  path: atlas-ceph
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    cluster:
      file: playbooks/ceph_cluster.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export ceph`).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/ceph/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-ceph README** | Standalone quickstart, tags, role behaviour |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags in `_template/ceph` `cluster.yaml` match current sibling tags (+ leading `00_ensure_workspace`).  
2. `ceph_*_hosts` in `atlas-ceph.yml` match group names in `hosts` and `limit:` in `cluster.yaml`.  
3. `node_foundation_init_hosts` covers `ceph_nodes`.  
4. `./cluster init … --template ceph` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_ci_ceph_cluster.py`.  
5. Do not move clusterctl-only instructions into sibling README (short Integrations only, no orchestrator CLI).
