# Infra edge via clusterctl

`atlas-infra-edge` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases
`provision → init-infra → infra → init-infra-post`.

Canonical sibling playbook: `playbooks/infra_hosts.yaml`.  
Operational role details (BIND, step-ca, registry/nginx caches, cache sync) live in the sibling README, not here.

This stack does **not** include k8s phases. After the infra node is up, operators configure
DNS/CA/registry/pkg/helm client vars in a **separate** k8s cluster leaf by hand.

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/infra_edge/` | Public SoT (`./cluster init … --template infra_edge`) |
| Private inventory `ci/infra` | Optional org lab — [../local-labs.md](../local-labs.md) |

```bash
./cluster init demo/infra --template infra_edge
./cluster use demo/infra
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..init-infra-post

# org lab (when inventory is configured):
./cluster use ci/infra
./cluster run --phases provision..init-infra-post

# targeted (phase tags — preferred):
./cluster run --phases infra --tags 01_validate_vars
./cluster run --phases infra --tags compose_render --limit infra_platform
./cluster run --phases infra --tags compose_start_core --limit infra_platform
./cluster run --phases infra --tags compose_start_registry --limit infra_platform

# targeted (legacy single-stack ops — explicit only):
./cluster run --phases infra --tags 03_deploy_bind_compose --limit infra_platform
```

Another env:

```bash
./cluster init prod/infra --template infra_edge
# then: hosts, atlas-infra-edge.yml / secrets → validate → run
```

Optional local org labs: [../local-labs.md](../local-labs.md).

## Phase map

```
  provision --> init-infra --> infra --> init-infra-post
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init-infra` | `atlas-node-foundation/init-infra` | Short OS bootstrap on `infra_platform` (no DNS/apt/CA yet) |
| `infra` | `atlas-infra-edge/infra` | Docker + BIND / NTP / step-ca / registry / caches |
| `init-infra-post` | `atlas-node-foundation/init-infra-post` | After BIND/CA: DNS→infra, apt cleanup, trust CA, repos, timezone, reboot |

(`templates` / `playbooks/build_templates.yaml` stays in the playbooks catalog for
emergency rebuilds; default plan starts at `provision`. Factory leaf:
`--template pve_templates` — [compute-provision.md](compute-provision.md).)

Why split: `init-infra` must not rewrite DNS to this host or download `ca.<apex>` before BIND/step-ca exist.
`init-infra-post` runs those tags only after `infra`.

`phases:` on this leaf includes infra refs only — omit `atlas-k8s-core/cluster` /
`atlas-k8s-addons/addons` (k8s is a separate `k8s_full` leaf).

## Tagged invocations (`atlas-infra-edge/infra`)

Order in `cluster.yaml` matches `playbooks/infra_hosts.yaml`
(validate before Docker/compose; Phase 3–4 compose phases; do not reorder without syncing):

| # | Tags | Limit |
|---|------|--------|
| 1 | `00_ensure_workspace` | (localhost) |
| 2 | `01_validate_vars` | (localhost) |
| 3 | `00_bootstrap_infra_repos,01_install_docker_engine,02_configure_docker_daemon` | `infra_platform` |
| 4 | `compose_render` | `infra_platform` |
| 5 | `compose_pull` | `infra_platform` |
| 6 | `compose_start_core` | `infra_platform` |
| 7 | `11_sync_infra_cache_pull,14_infra_cache_seed_load` | `infra_platform` |
| 8 | `compose_start_registry` | `infra_platform` |
| 9 | `compose_reconcile` | `infra_platform` |
| 10 | `11_sync_infra_cache_push` | `infra_platform` |

Cold path: render → pull → start **core** (BIND/NTP/step-ca) → cache fill (rsync pull **xor** OCI seed load) → start **registry**
(nginxes + warm) → slim reconcile → cache push. Registry is not started before cache fill.
Optional OCI seed **publish** is not a catalog slot. Standalone `./run.sh` /
untagged / `--tags all` **do** push when `publish_enabled=true`; `./cluster run`
catalog does not unless `--tags 14_infra_cache_seed_publish`. Seed load skip
matches a remote **sha256** (no layer pull; not the `name@digest` string) plus
dest trees that contain regular files, not the tag alone. After pull, stamp is
re-checked against local RepoDigests. Hold clears only when held compose
projects have running containers.

Phase 6 merges docker baseline into **one** ansible-playbook invocation (comma-union tags;
bootstrap stays gated in-role). `compose_pull` defaults to parallel `docker pull`; phase
durations log as `atlas_infra_edge_timing` when `compose_timing_enabled` is true.

Legacy per-role tags (`03_deploy_bind_compose`, …) remain for single-stack **render**
ops (Phase 5 thin `main.yaml`); they do not run on a full untagged play and do not
pull/start by themselves. Follow with `compose_pull` / `compose_start_*` /
`compose_reconcile` as needed. The **default clusterctl plan** uses only the phase
tags above (10 infra invocations; full leaf plan = 38).

## Adding a compose stack

New gated compose stacks are added in **`atlas-infra-edge` only** — **without editing `cluster.yaml`** invocations:

1. Deploy role under `roles/` with `tasks/render.yaml` (+ optional `pre_start` / `post_start` / `warm`).
2. Append an entry to `infra_compose_stacks` in
   `roles/06-enable-compose-systemd/defaults/main.yml` (`start_group`, `after`, gates).
3. Wire legacy single-tag include in sibling `playbooks/infra_hosts.yaml` if operators still
   need `--tags 0X_deploy_*` for one-stack ops.
4. Update sibling layout / catalog tests + README.

clusterctl / inventory already run `compose_render` → … → `compose_reconcile`; a new stack
picked up by the catalog rides those tags automatically.

The first invocation in each phase is `00_ensure_workspace` (playbook tag, not `always`). Later tagged invocations do not re-run workspace bootstrap.
For `init-infra` / `init-infra-post`, the first remote invocation also includes `00_gather_facts` (with `root_ssh`) so facts run under root SSH; ensure-only stays localhost.
Later init tags reuse `ansible_facts` via `atlas-node-foundation` `fact_caching=jsonfile` (clusterctl sets `ANSIBLE_CACHE_PLUGIN_CONNECTION` under the workspace).

Play-level tag unions are **not** used on remote plays (task-scoped tags only); see sibling
`playbooks/infra_hosts.yaml`. Cacheable facts (`pkg_repo_cache_warm_pending`, …) need jsonfile
fact caching (clusterctl ansible.cfg / sibling `./run.sh`).

You may rename the inventory group, but then update in sync:

1. `hosts` (group name),
2. `limit:` on `init-infra` and remote infra tags in `cluster.yaml`,
3. `when.inventory_groups_any` on playbook entries,
4. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
5. override `infra_platform_hosts` in `atlas-infra-edge.yml`,
6. `provision_inventory_group_map_infra` / provision maps when renaming the group.

## Inventory contract

| Group | Role for infra-edge | Sizing |
|-------|---------------------|--------|
| `infra_platform` | Validate (≥1), Docker + compose stacks, init-infra OS bootstrap | ≥ 1 |

Sibling targeting uses a variable (default = name above):

```yaml
# group_vars/all/atlas-infra-edge.yml — explicit in template/leaf
infra_platform_hosts: infra_platform
```

`./cluster run --phases … --limit` uses **inventory group names**, not the value of `infra_platform_hosts`.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init-infra` + `init-infra-post`)

Shared vars for both foundation entries. DNS/`pki_ca_url` matter for **post**
(after BIND/step-ca); short `init-infra` does not apply network/certs yet.

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `infra_platform` (or renamed group) |
| `pki_ca_url` | CA bootstrap (string or list; may switch to local step-ca later) |
| `pkg_repo_nginx_domain` / `pkg_repos` / `pkg_repos_extra` | nginx URIs via `pkg_repo_nginx_uri`; OS base + docker/containerd extras; role combines to `_pkg_repos_effective` |
| `cleanup_repositories` | `true` only with non-empty combined `pkg_repos` + `pkg_repos_extra` |

### `group_vars/all/atlas-infra-edge.yml` (`infra` phase)

| Knob | Meaning |
|------|---------|
| `infra_platform_hosts` | inventory group name for sibling targeting |
| `setup_bind` / `setup_ntp` / `setup_stepca` / `setup_compose_systemd` | compose feature gates |
| `bind_zones` | nested dict of authoritative zones (`apex` / `k8s` / `istio` / custom); each entry has `name`, `tsig_*`, `update_mode`, optional `inventory_a_records` |
| `use_internal_*` / nginx ingress domains | pull-through modes |
| `nginx_cache_sync_*` | optional peer cache mirror (off in public scaffold) |
| `infra_cache_seed_*` | optional OCI seed publish/load (off in public scaffold; XOR with rsync load) |

Do **not** set `k8s_cluster_domain` on an infra leaf just for BIND — child zone FQDNs belong in `bind_zones.*.name` (avoids workspace-id assert clashes with compute-provision).

Standalone sibling defaults: `example.com`, `CHANGEME`, conservative gates.  
Org domains, TSIG, step-ca password, and peer sync live **only** in clusterctl
overlays / `atlas-*.secrets.yml` (prefer Vault).

### `group_vars/all/atlas-compute-provision.yml`

`provision_stack: infra` with `provision_*_map_infra` (`infra_platform` → `proxmox_infra_node`).  
Inventory lists **only** `infra_platform`. Site PVE/DNS/secrets in the leaf; stable
provision knobs come from sibling `playbooks/group_vars/all/provision_defaults.yml`.

### Secrets

`group_vars/all/atlas-infra-edge.secrets.yml` (+ `atlas-compute-provision.secrets.yml` /
`atlas-node-foundation.secrets.yml`):

- `stepca_init_password`
- `external_dns_tsig_secret` / `external_dns_istio_tsig_secret` (and optional `bind_*_tsig_secret`)
- `nginx_cache_sync_ssh_password` when peer sync uses password auth
- `infra_cache_seed_*_registry_user` / `_password` when OCI seed publish or load is enabled
- provision/Proxmox tokens in `atlas-compute-provision.secrets.yml`

Do not commit live passwords in tracked `atlas-infra-edge.yml`.

## Sibling mount

Typical mount:

```yaml
atlas-infra-edge:
  source: local
  path: atlas-infra-edge
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    infra:
      file: playbooks/infra_hosts.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export infra` / phase env).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/infra_edge/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-infra-edge README** | Standalone quickstart, tags, role behaviour |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags/limits in `_template/infra_edge` match playbook order (+ leading `00_ensure_workspace`).  
2. Default plan uses phase tags only (`compose_*` / `11_sync_*` / `14_infra_cache_seed_load`) — no legacy `03_deploy_*` /
   `helm_repo_cache_warm` in `cluster.yaml` invocations.  
3. `01_validate_vars` before Docker/compose tags; ensure/validate **without** `limit:`; remote tags have `limit: infra_platform`.  
4. `infra_platform_hosts` in `atlas-infra-edge.yml` matches group name in `hosts` and `limit:` / `when`.  
5. `node_foundation_init_hosts` covers the same group.  
6. Secrets — in `atlas-*.secrets.yml` (Vault), not plaintext in tracked `atlas-infra-edge.yml`.  
7. `./cluster init … --template infra_edge` → `validate --strict`; `./cluster plan -v` shows
   phase order (optional local lab — [../local-labs.md](../local-labs.md)); unit
   `tests/test_infra_edge_orchestration.py`.  
8. Do not move clusterctl-only instructions into sibling README (short Integrations only).
9. Private `ci/infra` invocations must stay in lockstep with `_template/infra_edge`.
