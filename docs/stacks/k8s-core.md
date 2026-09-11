# Kubernetes control-plane bootstrap via clusterctl

`atlas-k8s-core` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases
`provision → init → k8s-core → k8s-addons`.

Infra (DNS/CA/registry) is a **separate** leaf — [infra-edge.md](infra-edge.md) (`--template infra_edge`).
Point this cluster’s `dns_server_ip` / NTP at that node after it is up.

Canonical sibling playbook: `playbooks/cluster_core.yaml`.  
Operational role details (VIP, kubeadm init/join, troubleshooting) live in the sibling README, not here.

CNI / Helm platform charts — sibling **atlas-k8s-addons** (`k8s-addons` phase), see [k8s-addons.md](k8s-addons.md).

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/k8s_full/` | Public SoT (`./cluster init … --template k8s_full`) |

```bash
./cluster init demo/k8s --template k8s_full
./cluster use demo/k8s
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..k8s-core

# after core — CNI/Helm:
./cluster run --phases k8s-core..k8s-addons

# targeted (example):
./cluster run --phases k8s-core --tags 10_lb --limit k8s_lbs
./cluster run --phases k8s-core --tags 29_fetch_kubeconfig
```

Another env:

```bash
./cluster init prod/k8s --template k8s_full
# then: hosts, VIP/DNS/CA, atlas-*.secrets.yml (Vault) → validate → run
```

Edit public SoT directly in `_template/k8s_full`. Promote a lab only via
`export_template` ([ADR 004](../adr/004-universal-export-template.md)); scrub hostnames/secrets — [../local-labs.md](../local-labs.md).

## Phase map

```
  provision --> init --> k8s-core --> k8s-addons
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init` | `atlas-node-foundation/init` | OS bootstrap k8s nodes |
| `k8s-core` | `atlas-k8s-core/cluster` | LB → hosts → kubeadm → kubeconfig |
| `k8s-addons` | `atlas-k8s-addons/addons` | Helm + Calico + platform charts |

(`templates` stays in the playbooks catalog for emergency rebuilds; default plan starts at `provision`. Factory: `--template pve_templates` — [compute-provision.md](compute-provision.md).)

Public `k8s_full` `phases:` includes k8s-core + k8s-addons and omits infra refs
(infra is a separate `infra_edge` leaf). To skip platform phases on another leaf,
omit those refs from `phases:` — do not use YAML `stacks:`.

## Tagged invocations (`atlas-k8s-core/cluster`)

Order in `cluster.yaml` matches playbook (do not run `29_fetch_kubeconfig` before join token).

Lifecycle gates (`21` / `22` / `23` / `24` / `25` / `26`) **co-tag** `04_cluster_state` in the
**same** `ansible-playbook` process. Tag-split invocations are separate processes: in-memory
`set_fact` from a prior stage (including a standalone `04`) is not visible to the next. Do not
rely on `fact_caching` for `k8s_needs_*` — re-probe instead.

| # | Tags | Limit |
|---|------|--------|
| 1 | `00_controller_tooling` | (localhost) |
| 2 | `01_validate_vars` | (localhost) |
| 3 | `02_gather_facts` | `k8s_lbs:k8s_masters:k8s_workers` |
| 4 | `03_sync_time` | `k8s_lbs:k8s_masters:k8s_workers` |
| 5 | `09_lb_vip_dns` | (localhost; no-op unless `k8s_lb_dns_tf_manage_a_record`) |
| 6 | `10_lb` | `k8s_lbs` |
| 7 | `11_k8s_hosts` | `k8s_masters:k8s_workers` |
| 8 | `04_cluster_state,21_kubeadm_init` | `k8s_masters` |
| 9 | `04_cluster_state,22_cluster_join_token` | (no limit — probe masters/workers + token on localhost) |
| 10 | `29_fetch_kubeconfig` | (localhost) |
| 11 | `04_cluster_state,23_join_masters` | `k8s_masters` |
| 12 | `04_cluster_state,24_join_workers,12_workers_kernel_rbd` | `k8s_workers` |
| 13 | `04_cluster_state,25_kubeadm_upgrade_control_plane` | `k8s_masters` |
| 14 | `04_cluster_state,26_kubeadm_upgrade_workers` | `k8s_workers` |

The first invocation in each phase is `00_ensure_workspace` (playbook tag, not `always`). Later tagged invocations do not re-run workspace bootstrap. For `init`, the first remote invocation also includes `00_gather_facts` (with `root_ssh`); ensure-only stays localhost. Later init tags reuse `ansible_facts` via `atlas-node-foundation` `fact_caching=jsonfile` (workspace `ANSIBLE_CACHE_PLUGIN_CONNECTION`).

Upgrade roles (`25`/`26`) are no-op while `k8s_needs_upgrade` is false.

You may rename inventory groups, but then update in sync:

1. `hosts` (group names),
2. `limit:` in `cluster.yaml` invocations,
3. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
4. override `k8s_*_hosts` in `atlas-k8s-core.yml` (see below),
5. `when.inventory_groups_any` on playbook entries.

## Inventory contract

Validate expects groups:

| Group | Role | Sizing |
|-------|------|--------|
| `k8s` | Parent (no hosts) | — |
| `k8s_lbs` | Keepalived + Nginx stream VIP | ≥ 1 (template: 2) |
| `k8s_masters` | control plane | ≥ 1 (template: 3) |
| `k8s_workers` | workers | group must exist (may be empty) |

Sibling playbook targeting uses variables (defaults = names above):

```yaml
# group_vars/all/atlas-k8s-core.yml — explicit in template/leaf
k8s_lb_hosts: k8s_lbs
k8s_master_hosts: k8s_masters
k8s_worker_hosts: k8s_workers
```

`./cluster run --phases … --limit` still uses **inventory group names**, not values of these vars.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init` phase)

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `k8s_lbs:k8s_masters:k8s_workers` |
| `pkg_repos` / `pkg_repos_extra` | **Required non-empty combined** guest set when `cleanup_repositories: true` (OS base often in env `pkg_repos`; k8s/containerd/Docker/UEK extras in leaf `pkg_repos_extra`). See catalog `foundation_dev/k8s` / `foundation_k8s_full`. Role combines to `_pkg_repos_effective`. k8s-core only fallbacks k8s/containerd if foundation drop-ins are absent — not a substitute for base OS repos. |
| CA / NTP / SSH | leaf identity |

Leaf DNS identity and path/workspace contract: see product overlays below
([ADR 003](../adr/003-optional-cluster-yml.md) — no `cluster.yml`).
`provision_stack` lives in `atlas-compute-provision.yml` only.

### `group_vars/all/atlas-k8s-core.yml` (`k8s-core` phase)

Includes leaf DNS identity (`dns_domain_suffix`, `cluster_domain`, `k8s_cluster_domain`,
`dns_server_ip`) plus Keepalived/nginx, kube versions, containerd mirrors, kubeadm networking,
and controller targeting (`k8s_*_hosts`, `controller_*`, control-plane SSH).  
Org mirrors / passwords live **only** in the leaf (not in sibling defaults).

| Knob | Meaning |
|------|---------|
| `dns_domain_suffix` / `cluster_domain` / `k8s_cluster_domain` | leaf DNS identity |
| `dns_server_ip` | shared BIND/NTP target |
| `k8s_lb_hosts` / `k8s_master_hosts` / `k8s_worker_hosts` | inventory group names for sibling targeting |
| `k8s_control_plane_master_host` | first master (`groups[k8s_master_hosts]`) for SSH fetch |
| `controller_*` | controller layout under injected `cluster_workspace_root` |
| `k8s_lb_dns_tf_manage_a_record` | `true` → role `09_lb_vip_dns` creates `{{ k8s_lb_hostname }}` → `vip_address` via Terraform RFC2136 (reuses `provision_dns_*`); `false` (default) → BIND / manual DNS. Do not dual-own with BIND when enabled. |
| `pkg_repo_base` / `pkg_repo_nginx_ingress_domain` | package URI bake when foundation drop-ins are absent (`base` → domain → public) |

Standalone sibling defaults: `example.com`, empty package URI knobs (public pkgs.k8s.io), `use_internal_docker_registry: none`.

Addon charts / Helm catalog live in `atlas-k8s-addons.yml` — see [k8s-addons.md](k8s-addons.md).

### Secrets

| File | Keys (examples) |
|------|-----------------|
| `atlas-k8s-core.secrets.yml` | `vip_auth_pass` (Keepalived); optional `k8s_lb_dns_key_secret` |
| `atlas-compute-provision.secrets.yml` / `atlas-node-foundation.secrets.yml` | PVE/DNS / bootstrap |
| `atlas-k8s-addons.secrets.yml` | addon passwords / TSIG / oauth (see [k8s-addons.md](k8s-addons.md)) |

Prefer Ansible Vault on `*.secrets.yml` (not gitignore). Keep aggregate `k8s_secrets:` Jinja map in the catalog.

## Sibling mount

Typical mount:

```yaml
atlas-k8s-core:
  source: local
  path: atlas-k8s-core
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    cluster:
      file: playbooks/cluster_core.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export k8s` / phase env).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/k8s_full/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-k8s-core README** | Standalone quickstart, tags, role behaviour |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags/limits in `_template/k8s_full` match playbook order (+ leading `00_ensure_workspace`).  
2. `k8s_*_hosts` in `atlas-k8s-core.yml` match group names in `hosts` and `limit:` in `cluster.yaml`.  
3. `node_foundation_init_hosts` covers lbs + masters + workers.  
4. `./cluster init … --template k8s_full` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_k8s_core_orchestration.py`.  
5. Do not move clusterctl-only instructions into sibling README (short Integrations only, no orchestrator CLI).  
6. Public SoT = `_template/k8s_full`; promote only via `export_template` ([ADR 004](../adr/004-universal-export-template.md)) with scrub ([../local-labs.md](../local-labs.md)).
