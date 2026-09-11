# Reference PostgreSQL HA cluster — self-contained configuration (provision → init → postgresql).

Orchestration contract (phases, inventory, vars bridge, tagged invocations):

→ **[`docs/stacks/postgresql.md`](../../../docs/stacks/postgresql.md)**

Pipeline (no infra / no k8s):

```bash
./cluster run --cluster <your-id> --phases provision..postgresql
```

Phases: `provision` → `init` → `postgresql`

The `postgresql` phase uses five tagged invocations (validate → etcd → PG stack → LB → verify). Role-level troubleshooting: sibling `atlas-postgresql` README.

Init copy for new clusters:

```bash
./cluster init prod/pgsql --template postgresql
```

Edit after init:

1. Leaf DNS in `atlas-*.yml`: `--dns-suffix` for the shared suffix; `cluster_domain`
   prefix (`pgsql.`) is template-owned — edit overlays to change it
2. `group_vars/all/atlas-compute-provision.yml` (+ `.secrets.yml`) — PVE/DNS / `ubuntu-base`
3. `group_vars/all/atlas-postgresql.yml` — VIP, version, `pgsql_*_hosts`, `pgsql_pgdg_repo_from_init`
4. `group_vars/all/atlas-postgresql.secrets.yml` — `vip_auth_pass`, DB passwords (Vault)
5. `group_vars/all/atlas-node-foundation.yml` — `pkg_repos` including `pgdg-apt` / `pgdg-yum`
6. `group_vars/all/atlas-node-foundation.yml` — `node_foundation_init_hosts`
7. `hosts` — nested `postgresql` → `pgsql_*` VM layout

Inventory groups:

| Group | Role |
|-------|------|
| `postgresql` | Parent (no hosts) |
| `pgsql_etcd_cluster` | etcd for Patroni |
| `pgsql_cluster` | PostgreSQL + Patroni + PgBouncer |
| `pgsql_lbs` | HAProxy + Keepalived |

`pgsql_pgdg_repo_from_init: true` — expect catalog drop-ins `pgdg-apt.sources` / `pgdg-yum.repo` from foundation init (standalone sibling default is `false`).

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template postgresql
```

Does **not** modify other cluster leaves.
