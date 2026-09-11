# Workspace

Runtime artifacts are **not in git**. Cluster config lives under `clusters/<env>/<name>/`
([clusters.md](clusters.md)). Per-cluster runtime trees **mirror that hierarchy** under the
workspace parent. Durable Terraform state is **not** scratch under `workspace/` — either a
second clone (`tfstate-repo/`, mode A) or the inventory checkout itself (Phase 6 mode B).

## Three trees (ADR 001 — variant A)

Accepted in sibling **atlas-compute-provision** `docs/adr/001-tfstate-repo-prefix.md`
(operator guide: sibling `docs/tfstate.md`):

| Tree | Path | Role |
|------|------|------|
| Config | `clusters/<cluster_id>/` | leaf inventory (git) |
| Runtime | `workspace/<cluster_id>/` | repos, logs, **`tf_workspace/` scratch** |
| Durable TF | see modes below | SoT blob (+ git when push) |

**In the state remote** (often the same atlas-inventory git repo) objects are stored as
`tfstate/<cluster_id>/…` — never bare `ci/infra/` at the remote root.

### Controller durable modes

| Mode | Durable on disk | Notes |
|------|-----------------|-------|
| **A (default)** | `$ATLAS_CLUSTER_ROOT/tfstate-repo/tfstate/<cluster_id>/` | Second clone of `provision_tf_state_repo` (Phases 1–5) |
| **B (Phase 6 contract)** | `<inventory-root>/tfstate/<cluster_id>/` | Same checkout as `clusters.path` parent; no second clone |

`tfstate-repo/` under `$ATLAS_CLUSTER_ROOT` is gitignored and **deprecated for
inventory-backed labs** (mxhash/ci). After Stage 4 migrate, rename leftovers:

```bash
mv tfstate-repo tfstate-repo.legacy.bak   # when inventory/tfstate/ is SoT
```

Mode B leaves set `provision_tf_state_local_dir: "{{ atlas_inventory_root }}"`.
Docker runs as **host uid:gid**; no post-run `chown`. Files under
**`workspace/<cluster_id>/`**, inventory `tfstate/` + `.git/` stay runner-owned.
Do not edit `tfstate-repo/clusters/…`.

CI (Stage 5 / P1): inventory checkout **is** mode-B `local_dir`
(`examples/internal/ci/prepare_inventory_checkout.sh`). Refresh is ff-only;
deploy uses `INV_FETCH_MODE=full`; seed+deploy share
`resource_group: atlas-clusterctl-inventory`. See [gitlab-ci.md](gitlab-ci.md) /
[jenkins.md](jenkins.md).

| Layer | Mode A (`ci/infra`) | Mode B (`ci/infra`, inventory-backed) |
|-------|---------------------|----------------------------------------|
| Durable on disk | `$ATLAS_CLUSTER_ROOT/tfstate-repo/tfstate/ci/infra/terraform.tfstate` | `<inventory-root>/tfstate/ci/infra/terraform.tfstate` |
| Path inside git remote | `tfstate/ci/infra/terraform.tfstate` | same |
| Scratch (not SoT) | `workspace/ci/infra/tf_workspace/terraform.tfstate` | same |

```
  clusters/<env>/<name>/     workspace/<env>/<name>/     durable tfstate (A or B)
        |                            |                          |
        +-- cluster.yaml             +-- repos/                 +-- terraform.tfstate
        +-- hosts                    +-- logs/                    under tfstate/<id>/
        +-- group_vars/              +-- tf_workspace/
                                     +-- playbooks.lock
```

| Cluster id | Config | Runtime | Durable TF (mode B) | Durable TF (mode A) |
|------------|--------|---------|---------------------|---------------------|
| `ci/redis` | `clusters/ci/redis/` | `workspace/ci/redis/` | `<inv>/tfstate/ci/redis/` | `tfstate-repo/tfstate/ci/redis/` |
| `dev/k8s` | `clusters/dev/k8s/` | `workspace/dev/k8s/` | `<inv>/tfstate/dev/k8s/` | `tfstate-repo/tfstate/dev/k8s/` |
| `lab` (flat) | `clusters/lab/` | `workspace/lab/` | (usually mode A / `git_push: false`) | `tfstate-repo/tfstate/lab/` |

`cluster_workspace_id` (often from `cluster_domain`, e.g. `k8s.example.com`) remains a
**logical** id for Ansible/env. The **filesystem** path for workspace and durable TF
always follows `cluster_id` (`dev/k8s`, not the domain).

## Workspace parent path

Priority:

```
ATLAS_WORKSPACE_ROOT
  → workspace.path in $ATLAS_CLUSTER_ROOT/.config/config.yaml
  → $ATLAS_CLUSTER_ROOT/workspace
```

Example local config snippet ([`.config/config.yaml.example`](../.config/config.yaml.example)):

```yaml
workspace:
  path: ../atlas-runtime/workspace
```

Relative paths resolve against `ATLAS_CLUSTER_ROOT`. Full tree:
`<workspace.parent>/<env>/<name>/`.

## Terraform state path

Ansible vars (provision phase) — ADR 001:

| Var | Mode A (default) | Mode B (Phase 6 contract) |
|-----|------------------|---------------------------|
| `provision_tf_state_local_dir` | `$ATLAS_CLUSTER_ROOT/tfstate-repo` | inventory repository root |
| `provision_tf_state_repo_prefix` | `tfstate` | same |
| `provision_tf_state_cluster_path` | `tfstate/{{ cluster_id }}` | same |
| `provision_tf_state_repo_file` | `…/tfstate-repo/tfstate/<id>/terraform.tfstate` | `…/inventory/tfstate/<id>/terraform.tfstate` |

Working copy used by `terraform apply` stays under the workspace:
`workspace/<id>/tf_workspace/` (**scratch only**). Roles `07_tf_state_pull` /
`11_tf_state_push` sync to/from `tfstate/<cluster_id>/` **inside** `local_dir`.

When `provision_tf_state_git_push: true`, `local_dir` is either a dedicated clone
(mode A) or the live inventory checkout (mode B / Phase 6). CI checkouts use the
same mode-B tree (Stage 5 / P1 — never a second `tfstate-repo/` under clusterctl;
ff-only refresh; deploy `INV_FETCH_MODE=full`). Commits use `tfstate/{{ cluster_id }}`
only (never bare `{{ cluster_id }}` at the remote root, never `git add` of
`clusters/` by default).

Leaf overlays set **repo URL / branch / push / git identity**. Inventory-backed
labs also set:

```yaml
provision_tf_state_local_dir: "{{ atlas_inventory_root }}"
```

(`atlas_inventory_root` = parent of `clusters.path`, injected by clusterctl.)
Do not set `local_dir=…/tfstate` together with `cluster_path=tfstate/…` (double prefix).

## Logical workspace id

Priority (Ansible `cluster_workspace_id` / `CLUSTER_WORKSPACE_ID`):

```
CLUSTER_WORKSPACE_ID
  → cluster.yaml workspace_id
  → cluster_domain (from group_vars, after Jinja)
  → ERROR
```

```bash
./cluster workspace id
./cluster workspace show
```

## Tree

```
<workspace.parent>/<env>/<name>/
├── controller-state/       # kubeconfig, reports, venv, …
├── .ansible/               # ANSIBLE_LOCAL_TEMP
├── .ansible_facts_cache/
├── repos/                  # ./cluster repos sync
├── playbooks.lock
├── tf_workspace/           # terraform apply working copy
├── build/
├── generated/
└── logs/
    ├── latest → <timestamp>/
    └── <timestamp>/
        ├── meta.json
        ├── run.log
        └── stages/
```

```
# Mode A (standalone / leftover)
<$ATLAS_CLUSTER_ROOT>/tfstate-repo/tfstate/<env>/<name>/
├── terraform.tfstate
└── .terraform.lock.hcl     # optional, synced from apply workdir

# Mode B (inventory-backed labs / CI) — preferred for mxhash/ci
<inventory-root>/tfstate/<env>/<name>/
├── terraform.tfstate
└── .terraform.lock.hcl
```

Do not create at repo root: `logs/`, `.ansible/`, `.ansible_facts_cache/`.
`./cluster` and `python3 -m clusterctl.ansible_env` auto-remove the ansible
legacy dirs at startup; validate ERROR only if they reappear or purge cannot
delete them (permissions). Runtime belongs under `workspace/<id>/`.

## Bootstrap

`./cluster` creates ansible runtime dirs before playbooks. First play usually includes role `00_ensure_workspace` on `localhost`.

Ad-hoc:

```bash
./cluster use demo/k8s
eval "$(python3 -m clusterctl.ansible_env export-workspace)"
eval "$(python3 -m clusterctl.ansible_env export k8s-addons)"
```

## Reset

```bash
./cluster workspace reset --yes
```

Deletes `workspace/<env>/<name>/` for the active cluster (logs, repos checkout, apply workdir).
Does **not** delete durable inventory `tfstate/<env>/<name>/`, legacy
`tfstate-repo/tfstate/<env>/<name>/`, or config under `clusters/`.
(Legacy local `$ATLAS_CLUSTER_ROOT/tfstate/<id>/` clones from before ADR 001 may still exist
on disk — remove/rename manually after migrating remotes.)

See [playbooks.md](playbooks.md), [ansible.md](ansible.md), [local-labs.md](local-labs.md).
