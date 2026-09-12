# Playbook repositories

Ansible playbooks and roles live in **sibling git repositories**. clusterctl describes them in `cluster.yaml` → `playbooks:` and materializes them under `workspace/<id>/repos/` (or mounts `local` siblings).

```
  cluster.yaml playbooks:
       |
       +-- source: local  -->  ../sibling-repo  (mount, sync: never)
       |
       +-- source: git    -->  ./cluster repos sync  -->  workspace/<id>/repos/<repo>/
```

## Sibling repos (typical set)

| Repo | Used by |
|------|---------|
| `atlas-compute-provision` | templates + provision (all scaffolds) — [compute-provision.md](stacks/compute-provision.md) (`_template/*`) |
| `atlas-node-foundation` | OS init |
| `atlas-infra-edge` | DNS/CA/registry — [infra-edge.md](stacks/infra-edge.md) (`_template/infra_edge`) |
| `atlas-k8s-core` | kubeadm / control plane — [k8s-core.md](stacks/k8s-core.md) |
| `atlas-k8s-addons` | Helm / Calico / platform charts — [k8s-addons.md](stacks/k8s-addons.md) |
| `atlas-redis` | `_template/redis` ([redis.md](stacks/redis.md)) |
| `atlas-postgresql` | `_template/postgresql` ([postgresql.md](stacks/postgresql.md)) |
| `atlas-kafka` | `_template/kafka` ([kafka.md](stacks/kafka.md)) |
| `atlas-jenkins-agent` | Jenkins agents — [jenkins-agent.md](stacks/jenkins-agent.md) (`_template/jenkins_agent`) |
| `atlas-gitlab-runner` | GitLab runners — [gitlab-runner.md](stacks/gitlab-runner.md) (`_template/gitlab_runner`) |

The list for a given cluster = keys under `playbooks:` in its `cluster.yaml`.

Sibling playbook repos (postgresql, redis, …) remain **standalone products**: their own README / entrypoint. clusterctl supplies inventory, group_vars, and phases; do not duplicate orchestrator CLI docs in sibling READMEs.

## Local siblings (dev / CI)

```yaml
playbooks:
  atlas-redis:
    source: local
    path: atlas-redis
    path_relative_to: sibling
    layout: roles/
    sync: never
    ref: main
    entries:
      cluster:
        file: playbooks/redis_cluster.yaml
        invocations:
          - tags: 01_validate_vars
          # …
```

`path_relative_to: sibling` — repo next to `atlas-clusterctl` (e.g. `../atlas-redis`).

## Git sync

```yaml
playbooks:
  atlas-k8s-core:
    source: git
    url: git@github.com:yokozu777/atlas-k8s-core.git
    ref: main          # prefer pin SHA/tag for prod
    layout: roles/
    shallow: true
    sync: always       # always | if_missing | never
```

```bash
./cluster repos sync
./cluster repos sync --repo atlas-k8s-core
./cluster repos sync --phase k8s-addons
./cluster repos status
./cluster repos show
```

Equivalent: `./cluster playbooks sync|status|show`.

Env overrides (one-off pin):

| Env | Effect |
|-----|--------|
| `PLAYBOOKS_<REPO>_REF` | override `ref` |
| `PLAYBOOKS_<REPO>_PATH` | override local path |
| `PLAYBOOKS_<REPO>_SOURCE` | `git` / `local` |

`<REPO>` name is upper snake from repo name (`atlas-k8s-core` → `ATLAS_K8S_CORE`).

## playbooks.lock

After a successful `./cluster repos sync` (not dry-run), clusterctl writes:

`workspace/<workspace_id>/playbooks.lock`

Validate can check SHA drift (`--strict` → ERROR). For `source: local` + `sync: never`, lock is often absent — expected in sibling-dev mode.

## Workspace layout

```
workspace/<workspace_id>/
  repos/
    atlas-node-foundation/
    atlas-k8s-addons/
    …
  playbooks.lock
```

Do not clone playbook repos into the `atlas-clusterctl/` root — `validate` catches legacy layout.

## Python API (engine)

| Prefer | Avoid (deprecated shim) |
|--------|-------------------------|
| `clusterctl.playbooks_repos` (`ResolvedPlaybookRepo`, `ctx.playbook_repos`) | `clusterctl.role_repos` (`RoleRepoSpec`, `ctx.role_repos`) |
| `build_resolved_playbooks_repos` | `build_role_repos_config` |
| `playbooks_paths.workspace_repos_root` | importing path helpers via `role_repos` |

YAML key `role_repos:` in `cluster.yaml` remains a hard load error (use `playbooks:`).

## Galaxy collections

Ansible collection dependencies are declared in sibling `requirements.yml`, not in clusterctl. Sync/CI installs them via playbook-repo discovery.

See [workspace.md](workspace.md), [cluster-config-v2.md](cluster-config-v2.md). Optional local labs: [local-labs.md](local-labs.md).
