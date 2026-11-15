# Reference Ceph cephadm HA — self-contained configuration (provision → init → ceph).

Orchestration contract (phases, inventory, vars bridge, tagged invocations):

→ **[`docs/stacks/ceph.md`](../../../docs/stacks/ceph.md)**

Pipeline (no infra / no k8s / no Rook):

```bash
./cluster run --cluster <your-id> --phases provision..ceph
```

Phases: `provision` → `init` → `ceph`

The `ceph` phase uses tagged invocations (validate → prereqs → bootstrap → hosts →
osds → rgw → s3 → verify). Role-level troubleshooting: sibling `atlas-ceph` README.

Init copy for new clusters:

```bash
./cluster init prod/ceph --template ceph
```

Edit after init:

1. Leaf DNS in `atlas-*.yml`: `--dns-suffix` for the shared suffix; `cluster_domain`
   prefix (`ceph.`) is template-owned — edit overlays to change it
2. `group_vars/all/atlas-compute-provision.yml` (+ `.secrets.yml`) — PVE/DNS credentials, VM templates
3. `group_vars/all/atlas-ceph.yml` — release, RGW port, targeting vars, optional mirrors
4. `group_vars/all/atlas-ceph.secrets.yml` — S3 access/secret keys
5. `group_vars/all/atlas-node-foundation.yml` — `pkg_repos` + `node_foundation_init_hosts`
6. `hosts` — nested `ceph` → `ceph_nodes` (≥ 3) with OS + OSD disks

Inventory groups:

| Group | Role |
|-------|------|
| `ceph` | Parent (no hosts) |
| `ceph_nodes` | Colocated mon/mgr/osd/rgw (≥ 3) |

Lab mirrors and domains live in clusterctl `atlas-ceph.yml` (and other Leaf DNS overlays); sibling product defaults stay org-neutral.

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template ceph
```

Does **not** modify other cluster leaves.
