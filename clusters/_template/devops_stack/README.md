# Reference DevOps compose stack — self-contained configuration (provision → init → devops).

Orchestration contract (phases, inventory, vars bridge, tagged invocations):

→ **[`docs/stacks/devops-stack.md`](../../../docs/stacks/devops-stack.md)**

Pipeline (no infra / no k8s):

```bash
./cluster run --cluster <your-id> --phases provision..devops
```

Phases: `provision` → `init` → `devops`

The `devops` phase uses tagged invocations (validate → docker → render → compose up).
Role-level troubleshooting: sibling `atlas-devops-stack` README.

Init copy for new clusters:

```bash
./cluster init prod/devops --template devops_stack
```

Edit after init:

1. Leaf DNS in `atlas-*.yml`: `--dns-suffix` for the shared suffix; `cluster_domain`
   prefix (`devops.`) is template-owned — edit overlays to change it
2. `group_vars/all/atlas-compute-provision.yml` (+ `.secrets.yml`) — PVE/DNS credentials
3. `group_vars/all/atlas-devops-stack.yml` — image tags, ports, vhost labels
4. `group_vars/all/atlas-devops-stack.secrets.yml` — admin and database passwords
5. `group_vars/all/atlas-node-foundation.yml` — `pkg_repos` + `node_foundation_init_hosts`
6. `hosts` — nested `devops` → `devops_stack` (exactly one host, 8 CPU / 32 GB, 50 GB OS disk + 200 GB data disk)

Inventory groups:

| Group | Role |
|-------|------|
| `devops` | Parent (no hosts) |
| `devops_stack` | The Compose VM (exactly one) |

nginx publishes 80, 443, and stream 2222/2223. Product containers stay on the Docker network.

Lab mirrors and domains live in clusterctl `atlas-devops-stack.yml` (and other Leaf DNS overlays); sibling product defaults stay org-neutral.

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template devops_stack
```

Does **not** modify other cluster leaves.
