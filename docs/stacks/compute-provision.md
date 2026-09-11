# Compute provision via clusterctl

`atlas-compute-provision` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + `group_vars/all/atlas-compute-provision.yml` + phases
`templates` / `provision` (then `init` / stack phases per leaf).

Canonical sibling playbooks:

| Entry | File |
|-------|------|
| `templates` | `playbooks/build_templates.yaml` |
| `provision` | `playbooks/provision_nodes.yaml` |

Operational details (PVE templates, Terraform stacks, `provision_mode`, rename maps,
troubleshooting) live in the sibling README, not here.

Do not confuse with data-plane docs ([postgresql.md](postgresql.md), [redis.md](redis.md), …) —
those cover **after** provision. Here: VM templates + Terraform VMs + wait SSH only.

## Golden templates vs stack leaves

**Build once, clone many.**

| Leaf kind | Default `phases:` | `provision_pve_templates` |
|-----------|-------------------|---------------------------|
| `_template/pve_templates` (factory) | `templates` only | **Required** — `ubuntu-base` / `oracle-base` / `debian-base` with **`id` + `image_url`** |
| Stack scaffolds (`k8s_full`, `postgresql`, …) | start at **`provision`** | **Omit** — Terraform clones `hosts.provision.clone` by PVE template name |

Reserved golden VMIDs: **400100–400102**. Stack leaves only set `hosts.provision.clone`
to a golden name that already exists on the target hypervisor.

```bash
# 1) Build golden templates (once per hypervisor)
./cluster init lab/pve-templates --template pve_templates --dns-suffix example.com
./cluster use lab/pve-templates
# fill secrets + provision_pve_host / target_node; confirm VMIDs free
./cluster run --phases templates

# 2) Stack leaf — clones golden names (no templates phase by default)
./cluster init demo/pgsql --template postgresql --dns-suffix demo.example.com
./cluster use demo/pgsql
# ensure hosts.provision.clone matches a golden template name on the PVE node
./cluster run --phases provision..postgresql
```

Rebuild images only on the factory leaf (`./cluster run --phases templates` under
`pve_templates` / org `lab/pve-templates`). Do not put a build catalog on stack
leaves; `./cluster run --phases templates` on a stack fails when `templates` is not in
`phases:` (entry may still exist for advanced remount).

Sibling contract: `build_templates.yaml` requires catalog `id` + `image_url`;
`00_validate_provision` treats `provision_pve_templates` as optional (soft
allowlist when set). See sibling `examples/provision_catalog_clone_only.example.yml`.
## Template and scaffold

Public SoT tags/invocations: **`clusters/_template/*`**.

| Path | Role |
|------|------|
| `clusters/_template/pve_templates/` | Golden image factory (`./cluster init … --template pve_templates`) |
| `clusters/_template/k8s_full/` | Full k8s without embedded infra (`./cluster init … --template k8s_full`) |
| `clusters/_template/infra_edge/` | Infra platform only (`./cluster init … --template infra_edge`) |
| `clusters/_template/{jenkins_agent,gitlab_runner,postgresql,redis,kafka}/` | Stack scaffolds (same provision tag list; templates entry kept for emergency) |

```bash
./cluster init demo/k8s --template k8s_full
./cluster use demo/k8s
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..k8s-addons

# targeted:
./cluster run --phases provision --tags 00_validate_provision
./cluster run --phases provision --tags 10_tf_apply
./cluster run --phases provision --tags provision_wait_ssh

# emergency image rebuild (needs image_url on catalog):
./cluster run --phases templates --tags 00_check_pve_templates,01_prepare_system
```

Another env:

```bash
./cluster init prod/k8s --template k8s_full
# then: hosts, atlas-compute-provision.yml / secrets → validate → run
```

Stack leaves differ by `provision_stack` and maps in `atlas-compute-provision.yml`, not by tag list.

Edit public SoT directly in `_template/`. Promote a lab only via
`export_template` ([ADR 004](../adr/004-universal-export-template.md)); scrub hostnames/secrets — [../local-labs.md](../local-labs.md).

## Phase map

```
  [pve_templates leaf]  templates
  [stack leaf]          provision  (+ then init/stack)
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `templates` | `atlas-compute-provision/templates` | PVE cloud images → templates (factory / emergency) |
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH |

Next per leaf (not part of sibling compute-provision):

| Alias | Typical next |
|-------|--------------|
| `init` / `init-infra` | `atlas-node-foundation` |
| `infra` | [infra-edge.md](infra-edge.md) |
| `k8s-core` / `k8s-addons` | [k8s-core.md](k8s-core.md), [k8s-addons.md](k8s-addons.md) |
| `jenkins-agent` / `postgresql` / … | corresponding orchestration docs |

## Tagged invocations

Order in `cluster.yaml` matches sibling playbooks
(do not run apply before validate / generate; do not reorder without syncing all templates).

### `atlas-compute-provision/templates`

| # | Tags | Notes |
|---|------|--------|
| 1 | `00_check_pve_templates,01_prepare_system` | combined first step |
| 2 | `02_download_images` | |
| 3 | `03_customize_images` | |
| 4 | `04_upload_images` | |
| 5 | `05_create_pve_templates` | |

### `atlas-compute-provision/provision`

| # | Tags | Notes |
|---|------|--------|
| 1 | `00_validate_provision` | maps/secrets contract (**not** `01_validate_vars`) |
| 2 | `06_configure_git` | git identity only; no-op if `provision_tf_state_git_push: false` |
| 3 | `07_tf_state_pull` | |
| 4 | `08_generate_tf_vars` | |
| 5 | `09a_tf_destroy_dns` | gated by `provision_mode` |
| 6 | `09_hypervisor_cleaner` | gated by `provision_mode` |
| 7 | `10_tf_apply` | gated by `provision_mode` |
| 8 | `provision_wait_ssh` | `root_ssh: true` in SoT |
| 9 | `11_tf_state_push` | |

The `provision` entry in SoT also has `git_ssh: true` (needed for optional remote TF state git).
That flag makes clusterctl export `GIT_SSH_COMMAND` with `-i` (preserving the
docker mount at `/tmp/atlas-ssh/id_rsa`, or `TFSTATE_SSH_KEY` / `SSH_KEY`) so
`11_tf_state_push` bare `git pull`/`push` can auth — not only `07`’s `key_file`.
Under `execution.mode: docker`, that container path is bind-mounted from a
**per-run** host copy via `tempfile.mkdtemp(prefix="atlas-ssh-")` under
`workspace/<cluster_id>/.atlas-ssh/` — not controller `.cache/`, not legacy
`.cache/docker-identity`, and not host `/tmp` (Docker Desktop / snap often
deny `/tmp` mounts). Details: [execution.md](../execution.md).

The first invocation in each compute phase is `00_ensure_workspace` (explicit tag, not `always`).

You may rename inventory groups, but then update in sync:

1. `hosts` (group names),
2. keys `provision_inventory_group_map_<stack>` / `provision_wait_hosts`,
3. `limit:` / `when.inventory_groups_any` on **subsequent** phases (`init`, stack playbooks),
4. targeting vars on neighboring siblings (`jenkins_agent_hosts`, `gitlab_runner_hosts`, `infra_platform_hosts`, …),
5. **do not** change TF module key values without syncing `stacks/<stack>/` in the sibling.

## Inventory contract

Depends on `provision_stack` and overlays. Reference k8s (`k8s_full`):

| Group | Role for provision | Sizing |
|-------|--------------------|--------|
| `k8s_lbs` / `k8s_masters` / `k8s_workers` | map → TF module vars | ≥ 1 each (template SoT) |
| `infra_platform` | `provision_stack: infra` maps (`provision_*_map_infra`) | ≥ 1 |

Jenkins template: group `jslave` → `provision_inventory_group_map_jenkins`.  
PostgreSQL / Redis / Kafka — own groups + maps in their `atlas-compute-provision.yml`.

Targeting inside the sibling uses `provision_stack` + maps, not a single `*_hosts` var.
SoT does **not** set `./cluster run --phases … --limit` for templates/provision (localhost + dynamic PVE host).

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-compute-provision.yml`

Leaf overlay (site-specific). Stable knobs live in sibling
`playbooks/group_vars/all/provision_defaults.yml` (and role defaults).

| Knob | Meaning |
|------|---------|
| `provision_stack` | `k8s` / `infra` / `jenkins` / `postgresql` / `redis` / `kafka` / … (omit on `pve_templates`) |
| `provision_mode` | `apply` / `recreate` / `destroy` (see sibling README) |
| `provision_inventory_group_map_<stack>` | inventory group → TF variable name |
| `provision_tf_module_map_<stack>` | TF variable → module name in stack |
| `provision_hosts_file` | usually `cluster_inventory` / leaf `hosts` |
| `provision_gateway` / `provision_pve_host` / secrets | site hypervisor + network |
| `provision_pve_templates` | **factory only** — `id` + `image_url` per key; omit on stack leaves (clone via `hosts.provision.clone`) |
| `provision_dns_*` secrets / server | RFC2136 (algorithm/TTL defaults in sibling) |
| `provision_tf_state_repo` / `provision_tf_state_git_push` | opt-in remote state git (leaf) |
| lab VM overrides | e.g. `provision_vm_cloudinit_storage: ramdisk` |

### Durable TF paths (ADR 001)

Sibling SoT: `docs/adr/001-tfstate-repo-prefix.md`, operator guide `docs/tfstate.md`.
Also [../workspace.md](../workspace.md) (Phase 6 contract: two controller modes).

| Layer | Path |
|-------|------|
| Controller (mode A, default) | `$ATLAS_CLUSTER_ROOT/tfstate-repo/tfstate/<cluster_id>/` |
| Controller (mode B, Phase 6) | `<inventory-root>/tfstate/<cluster_id>/` (same checkout as `clusters.path` parent) |
| Inside state git remote | `tfstate/<cluster_id>/` (never bare `<cluster_id>/` at remote root) |
| Scratch | `workspace/<cluster_id>/tf_workspace/` (not SoT) |
| CI (Stage 5 / P1) | mode B via inventory checkout; ff-only prepare; deploy `INV_FETCH_MODE=full` |

Leaf `atlas-compute-provision.yml` normally sets `provision_tf_state_repo`,
`_branch`, `_git_push`, and `git_user_*` / `gitea_host`. Inventory-backed labs
also set `provision_tf_state_local_dir: "{{ atlas_inventory_root }}"` (controller
inject). Do not invent a second prefix (`local_dir=…/tfstate` + `cluster_path=tfstate/…`).
CI samples: [gitlab-ci.md](../gitlab-ci.md) / [jenkins.md](../jenkins.md).

Defaults in sibling (override only when needed): provider versions, plugin dirs,
wait-SSH timeouts, rook helpers, `provision_dns_tf_manage_a_records`, build_* paths.

Standalone sibling: `example.com`, `CHANGEME`, `provision_stack: jenkins`.  
Org URLs, tokens, and passwords live **only** in clusterctl overlays / `atlas-*.secrets.yml`.

### Secrets

`group_vars/all/atlas-compute-provision.secrets.yml`:

- `provision_pve_ssh_password` / `provision_proxmox_token_id` / `provision_proxmox_token_secret` / `provision_dns_key_secret` / `provision_vm_cipassword`
- optional git identity for TF state push stays in the catalog when non-secret

Do not commit live tokens in tracked `atlas-compute-provision.yml` (prefer Vault on `*.secrets.yml`).

## Sibling mount

Typical template / leaf:

```yaml
atlas-compute-provision:
  source: local
  path: atlas-compute-provision
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    templates:
      file: playbooks/build_templates.yaml
    provision:
      file: playbooks/provision_nodes.yaml
```

`pve_templates` mounts only the `templates` entry. See [../playbooks.md](../playbooks.md).
Public scaffolds default to `source: local` (sibling-dev). Org inventory leaves that
track remotes use `source: git` / `sync: always` after the product is published
(`./cluster repos sync`).

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export templates` /
`export provision` / phase env).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/*/README.md` | Orchestration, SoT tags, `./cluster` flow |
| **atlas-compute-provision README** | Standalone quickstart, stacks, modes, role behaviour |
| Stack docs ([jenkins-agent.md](jenkins-agent.md), …) | phases **after** provision |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags in `_template/k8s_full` (and stack templates) match playbook order (+ leading `00_ensure_workspace`).  
2. Same templates/provision tag list across all stack templates (unit test); factory leaf has templates only.  
3. `00_validate_provision` before TF generate/apply; wait SSH after `10_tf_apply`.  
4. `provision_stack` + maps in `atlas-compute-provision.yml` align with `hosts` and downstream limits.  
5. Credentials — in `atlas-compute-provision.secrets.yml` / Vault.  
6. `./cluster init … --template …` → `validate --strict` on your leaf (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_compute_provision_orchestration.py`.  
7. Do not move clusterctl-only instructions into sibling README (short Integrations only).  
8. Public SoT = `_template/`; promote only via `export_template` ([ADR 004](../adr/004-universal-export-template.md)) with scrub ([../local-labs.md](../local-labs.md)).  
9. Stack leaves omit `provision_pve_templates`; build catalog lives only in `pve_templates`.
