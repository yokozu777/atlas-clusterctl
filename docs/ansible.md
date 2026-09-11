# Ansible env

Single `ansible.cfg` at the `atlas-clusterctl` root. Per-phase env (roles path, strategy, temps) is resolved by clusterctl.

## Materialized vars

```
  org/env/leaf group_vars/all  -->  clusterctl materialize  -->  workspace extra-vars + ansible env
                                              |
                                              v
                                    ./cluster run --phases / ansible-playbook
```

Before a play, clusterctl writes to workspace:

- merged group_vars → playbook extra-vars file
- controller path contract (workspace roots, kubeconfig paths, …)

Edit policy layers and/or the leaf `group_vars/all/*.{yml,yaml}`, not generated files.

### Cascade merge (shallow, later wins)

Layers (same path rules as `cluster.yaml` cascade):

1. `clusters/default/default/group_vars/all/` (org policy, optional)
2. `clusters/<env>/default/group_vars/all/` (env policy, optional)
3. `clusters/<env>/<name>/group_vars/all/` (deployable leaf — required)

Within that:

1. All **non-secrets** `*.yml` / `*.yaml` per layer (alphabetical within each layer)
2. All product `*.secrets.yml` per layer (org → env → leaf; alphabetical within layer)

So: **defaults &lt; leaf**; secrets always after non-secrets; **leaf secrets** have the highest priority. Env/org secrets also override leaf non-secrets for the same key (secrets force-last). Monolithic `secrets.yml` is **not** merged (validate ERROR).

`group_vars/proxmox.yml` and other inventory **group-level** files are leaf-only (not cascaded). `pub_keys/` stays on the leaf.

## Export for ad-hoc

```bash
./cluster init demo/pgsql --template postgresql   # if leaf does not exist yet
./cluster use demo/pgsql
eval "$(python3 -m clusterctl.ansible_env export-workspace)"
eval "$(python3 -m clusterctl.ansible_env export postgresql)"
python3 -m clusterctl.ansible_env show postgresql
```

| Command | Effect |
|---------|--------|
| `export-workspace` | `CLUSTER_WORKSPACE_*`, ansible temp/cache dirs |
| `export <phase>` | + `ANSIBLE_CONFIG`, `ANSIBLE_ROLES_PATH`, forks/strategy |
| `show <phase>` | Human-readable resolved env |

Default phase for parts of the CLI is `k8s-addons`.

## Config show

```bash
./cluster config show k8s-addons
./cluster config show redis --json
./cluster config effective --cluster demo/kafka --json
```

## Interpreter

In `ansible.cfg`: `interpreter_python = auto`, discovery silent — suitable for Ubuntu/Debian/Oracle.

## Fact cache (tag-split siblings)

`ANSIBLE_CONFIG` for a phase points at the **sibling** `ansible.cfg` when present. Tag-split
`ansible-playbook` invocations (separate processes) only share facts if that sibling enables
`fact_caching = jsonfile` and clusterctl’s `ANSIBLE_CACHE_PLUGIN_CONNECTION` (under
`workspace/<id>/.ansible_facts_cache`). Do not set `fact_caching_connection` in sibling cfg
(clusterctl convention). Example: `atlas-node-foundation` after `00_gather_facts` on the first
remote init step.

Lifecycle decisions in `atlas-k8s-core` (`k8s_needs_init` / `k8s_needs_join` / `k8s_needs_upgrade`)
must **not** depend on fact cache: co-tag `04_cluster_state` with each gate in the same
invocation (see [stacks/k8s-core.md](stacks/k8s-core.md)).

## Do not

- Keep root `.ansible/` / `.ansible_facts_cache/` — CLI auto-removes them at
  startup (`./cluster`, `python3 -m clusterctl.ansible_env`); runtime belongs
  only under `workspace/<id>/`
- Run playbooks from sibling repos without export env / `./cluster run` — workspace paths and roles path will break

See [workspace.md](workspace.md), [clusterctl.md](clusterctl.md). Labs: [compute-provision.md](stacks/compute-provision.md), [redis.md](stacks/redis.md), [postgresql.md](stacks/postgresql.md), [kafka.md](stacks/kafka.md), [jenkins-agent.md](stacks/jenkins-agent.md), [gitlab-runner.md](stacks/gitlab-runner.md), [infra-edge.md](stacks/infra-edge.md).
