# Local org labs (private inventory)

Live labs (`ci/`, `dev/`, …) should **not** live in the public `atlas-clusterctl`
checkout. Prefer a **private inventory tree**, pointed at via local
`.config/config.yaml` in this clone (or `ATLAS_CLUSTERS_ROOT`).

```text
.config/config.yaml.example   # tracked template
        |
        v  cp …
.config/config.yaml           # local (gitignored) — edit clusters.path / workspace.path
```

Public checkouts only need:

| Path | Role |
|------|------|
| `clusters/_template/*` | Init scaffolds (`./cluster init … --template …`) |
| `clusters/default/` | Org policy stubs (not deployable; used in cascade) |
| `.config/config.yaml.example` | Template for local `.config/config.yaml` |

```
  public controller                 private inventory
  ---------------------             ----------------------------
  clusters/_template/*  --init-->   <inventory>/clusters/<env>/<name>
  clusters/default/         ^       <inventory>/clusters/ci|dev|…
  .config/config.yaml.example
  .config/config.yaml -----+  (clusters.path / workspace.path)
       or ATLAS_CLUSTERS_ROOT / ATLAS_WORKSPACE_ROOT
```

See also [`SECURITY.md`](../SECURITY.md) and [`.config/config.yaml.example`](../.config/config.yaml.example).

## Local `.config/config.yaml` (preferred)

One file under `.config/` in the controller clone (gitignored):

```bash
cp .config/config.yaml.example .config/config.yaml
# edit clusters.path → your inventory clusters/ directory
# optionally set workspace.path → runtime parent
```

Minimal contents:

```yaml
clusters:
  path: ../atlas-inventory/clusters

workspace:
  # optional — default is $ATLAS_CLUSTER_ROOT/workspace
  # path: ../atlas-runtime/workspace
```

- **Relative** paths are resolved against `ATLAS_CLUSTER_ROOT` (this checkout), not against `.config/`.
- **Absolute** paths are used as-is.

Override the config file location with `ATLAS_CLUSTERCTL_CONFIG=/path/to/config.yaml`
(useful in tests / CI).

```bash
./cluster list
# expect: deployable env/name ids from your inventory (./cluster list)
```

## Environment variables

Same effect without (or overriding) `.config/config.yaml`:

```bash
export ATLAS_CLUSTERS_ROOT=/path/to/atlas-inventory/clusters
export ATLAS_WORKSPACE_ROOT=/path/to/runtime/workspace   # optional
./cluster list
```

Env vars win over `.config/config.yaml` when both are set.

## Resolution order

### Clusters (live inventory)

```
  ATLAS_CLUSTERS_ROOT
         |
         v
  $ATLAS_CLUSTER_ROOT/.config/config.yaml  (clusters.path)
         |
         v
  $ATLAS_CLUSTER_ROOT/clusters
```

### Workspace parent (runtime trees)

```
  ATLAS_WORKSPACE_ROOT
         |
         v
  $ATLAS_CLUSTER_ROOT/.config/config.yaml  (workspace.path)
         |
         v
  $ATLAS_CLUSTER_ROOT/workspace
```

Per-cluster runtime: `<workspace.parent>/<env>/<name>/` (mirrors cluster id) — see [workspace.md](workspace.md).

| Concern | Where |
|---------|--------|
| Live leaves / labs | Inventory (`clusters.path` / `ATLAS_CLUSTERS_ROOT`) |
| Templates (`_template`) | Always controller `clusters/_template` |
| Org stub `default/default` | Controller `clusters/default` (cascade falls back here if inventory omits it) |
| Workspace / logs | `workspace.path` / `ATLAS_WORKSPACE_ROOT` (default: controller `workspace/`) |

## Legacy: labs inside the clone

Older workstations kept labs under `clusters/ci/` and `clusters/dev/` (gitignored).
That still works when no `.config/config.yaml` / `ATLAS_CLUSTERS_ROOT` is set (fallback to
`$ATLAS_CLUSTER_ROOT/clusters`). Prefer a private inventory repo + local config so the
public tree stays clean.

If labs remain in-tree:

```bash
git check-ignore -v clusters/dev/k8s/cluster.yaml   # example path shape
git ls-files clusters/ci clusters/dev
# expect: ignored / nothing tracked
```

## Quick check

```bash
./cluster list
# expect deployable ids from your inventory tree (env/name)

./cluster use "$(./cluster list | head -1)"   # pick any listed lab
./cluster validate --strict     # optional --skip-docker-smoke
```

## Stack ↔ public template map

Lab **paths are inventory-local** (discovered at runtime). Tests resolve them via
`tests/lab_support.py` (`lab_id_for(<stack>)`, `list_deployable_cluster_ids`,
product overlays on deployable leaves) — not a fixed `ci/*` / `dev/*` whitelist.

| Stack marker | Public scaffold | Orchestration doc |
|--------------|-----------------|-------------------|
| `k8s` (`atlas-k8s-core`) | `_template/k8s_full` (DNS/CA/registry often from a full `infra` leaf) | [k8s-core.md](stacks/k8s-core.md), [k8s-addons.md](stacks/k8s-addons.md), [compute-provision.md](stacks/compute-provision.md); infra: [infra-edge.md](stacks/infra-edge.md) |
| `infra` (full `atlas-infra-edge`) | `_template/infra_edge` | [infra-edge.md](stacks/infra-edge.md) |
| `jenkins` | `_template/jenkins_agent` | [jenkins-agent.md](stacks/jenkins-agent.md) |
| `gitlab` | `_template/gitlab_runner` | [gitlab-runner.md](stacks/gitlab-runner.md) |
| `redis` | `_template/redis` | [redis.md](stacks/redis.md) |
| `postgresql` | `_template/postgresql` | [postgresql.md](stacks/postgresql.md) |
| `kafka` | `_template/kafka` | [kafka.md](stacks/kafka.md) |
| `pve_templates` | `_template/pve_templates` | [compute-provision.md](stacks/compute-provision.md) |

Dual-track unit tests: public CI uses templates/fixtures; optional lab assertions
`skip_unless_stack(...)` when no matching leaf exists. CI forces an empty
`ATLAS_CLUSTERCTL_CONFIG` so a local `.config/config.yaml` cannot break public gates.

## Day-to-day workflow

```bash
./cluster use <lab-id>                 # id from ./cluster list
./cluster repos sync                   # if using git-sourced playbooks
./cluster validate --strict
./cluster plan -v
# ./cluster run --phases <phase>..<phase>
```
Phase window is **`--phases` / `-p` only** ([ADR 008](adr/008-phases-cli-selector.md) Phase 5).
Retired `plan`/`run` `--from`/`--to` flags are removed — keep inventory lab
READMEs/comments on `--phases`.

**Cleanup Variant B:** complete (Cleanup Phases 0–3) — dual docs anti-regression
gate for retired `plan`/`run` phase-window flags is purged. Labs must still teach
`--phases` only; permanent hygiene is argparse + dest-name guards
(see [ADR 008](adr/008-phases-cli-selector.md)).

Typical greenfield order: build golden templates once (`lab/pve-templates` or
`--template pve_templates`), then data-plane labs
`provision` → `init` → stack phase (`redis` / postgresql / `kafka` / `jenkins-agent`).
Infra-only: `provision` → `init-infra` → `infra` → `init-infra-post` (full infra leaf).
Full k8s (`k8s_full`): point DNS/NTP at the infra leaf, then
`provision` → `init` → `k8s-core` → `k8s-addons`.

## Durable Terraform state (inventory as remote)

When a leaf sets `provision_tf_state_git_push: true` and
`provision_tf_state_repo` to the inventory git remote, durable blobs are committed as
`tfstate/<cluster_id>/` inside that remote (ADR 001 Phase 3) — not bare `ci/infra/` at the
inventory root, and not under `workspace/`.

**Controller layout (two modes — ADR 001 Phase 6):**

| Mode | On-disk durable root | Status |
|------|----------------------|--------|
| **A (product default)** | `$ATLAS_CLUSTER_ROOT/tfstate-repo/tfstate/<cluster_id>/` | Standalone / dedicated state remotes |
| **B (unified lab)** | `<inventory-repo-root>/tfstate/<cluster_id>/` | Inventory leaves with `git_push: true` (Stage 2) |

`clusters.path` / `ATLAS_CLUSTERS_ROOT` select leaf config. Lab leaves that push
state into this inventory set `provision_tf_state_local_dir: "{{ atlas_inventory_root }}"`
(controller inject). Roles reuse that checkout — no required second clone under
clusterctl. Docker runs as **host uid:gid** (`--user`); post-run chown is not
used. New files under **`workspace/<cluster_id>/`** and inventory `tfstate/` /
`.git/` belong to the runner. Legacy root-owned trees need a one-time host
`chown`.

Do **not** edit `tfstate-repo/clusters/…` (legacy duplicate). Edit leaves under
`clusters.path` only. Durable blobs are tracked under inventory `tfstate/`;
`/workspace/` stays gitignored.

**Stage 4 migrate (lab controllers):** after Stages 1–3 are published, compare
serials (inventory should be SoT), then
`mv $ATLAS_CLUSTER_ROOT/tfstate-repo $ATLAS_CLUSTER_ROOT/tfstate-repo.legacy.bak`
and smoke `07_tf_state_pull` on postgresql + redis labs. Log must show
`tf state local dir: <inventory-root>` and
`Fetch and fast-forward existing matching checkout`.

**Stage 5 / P1 (CI):** inventory checkout is mode-B `local_dir`
([`prepare_inventory_checkout.sh`](../examples/internal/ci/prepare_inventory_checkout.sh)).
ff-only refresh (fail if ahead/diverged); seed `INV_FETCH_MODE=shallow`, deploy
`full`; GitLab `resource_group: atlas-clusterctl-inventory`. Dirty outside
`tfstate/` fails seed and deploy. See [gitlab-ci.md](gitlab-ci.md) /
[jenkins.md](jenkins.md).

Operator guide: sibling `atlas-compute-provision` `docs/tfstate.md`; orchestrator
[workspace.md](workspace.md). Inventory marker: `tfstate/README.md`.

**Publish gate:** a full infra leaf uses `source: git` + `sync: always` for
`atlas-compute-provision`. ADR 001 path defaults must be on that remote `main`
before a normal `./cluster repos sync` / `./cluster run` — otherwise sync
restores pre-ADR `…/tfstate/<cluster_id>` defaults. Until published, mount the
local sibling (or rsync into `workspace/…/repos/`) for verify runs.

## Syncing templates and labs

Canonical decision: [ADR 004 — Universal `export_template`](adr/004-universal-export-template.md)
(Phase 4 complete — shim deleted; SoT is `export_template`).

Prefer editing public `_template/*` directly. To **promote** a private lab into a
scaffold (maintainer-only):

```bash
# examples — <lab-id> from ./cluster list (stack markers in lab_support)
python3 -m clusterctl.tools.export_template --from <lab-id> --template redis
python3 -m clusterctl.tools.export_template --from <lab-id> --template k8s_full
# overrides: --source-root / --target-root (inventory clusters/ → product clusters/)
```

| Change | Where first | Then |
|--------|-------------|------|
| Phase / tag / playbook layout | **`clusters/_template/*/cluster.yaml`** | Sync matching lab leaf if you keep one |
| Secrets / FQDN / PVE / live hosts | Inventory only (`atlas-*.secrets.yml` + Vault, `hosts`) | Never copy live values into `_template/` |
| Promote lab → public scaffold | `python3 -m clusterctl.tools.export_template --from <lab-id> --template <name>` | DNS scrub automatic; `*.secrets.yml` keys kept, **values emptied**; still **scrub** hostnames / images before commit |

**Known `--template` names:** `k8s_full`, `infra_edge`, `jenkins_agent`, `gitlab_runner`, `postgresql`, `redis`, `kafka`, `pve_templates`, `default` (env-policy overlay, not a stack).

**Audience:** `export_template` is maintainer-only. Operators use
`./cluster init … --template <name>` (opposite direction).

Public SoT is always the scrubbed template tree, not the raw lab.

## Do not

- Commit live labs / plaintext credentials / local `.config/config.yaml` to a **public** remote
- Re-export a private lab into `_template/` without scrubbing hostnames and secrets
- Put live passwords in tracked `group_vars` under `_template/` or `default/`
- Rely on labs being present for GitHub Actions / `./tests/run_ci.sh` (public track must pass without them)

## Related

- [clusters.md](clusters.md) — layout model
- [clusterctl.md](clusterctl.md) — CLI + env vars
- [workspace.md](workspace.md) — runtime trees + `workspace.path`
- [validate.md](validate.md) — gates + `./tests/run_ci.sh`
- [`.config/config.yaml.example`](../.config/config.yaml.example) — local config template
- [examples/internal/README.md](../examples/internal/README.md) — org Jenkins sample (not product path)
- [jenkins.md](jenkins.md) / [jenkins-seed.md](jenkins-seed.md) — Pipeline + seed (`CLUSTER_ID` choice)
