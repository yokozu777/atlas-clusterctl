# PostgreSQL HA via clusterctl

`atlas-postgresql` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases `provision → init → postgresql`.

Canonical sibling playbook: `playbooks/postgresql_cluster.yaml`.  
Operational role details (Patroni reinit, VIP, troubleshooting) live in the sibling README, not here.

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/postgresql/` | Public SoT HA scaffold (3 etcd + 3 pg + 3 lb) |

```bash
./cluster init demo/pgsql --template postgresql
./cluster use demo/pgsql
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..postgresql

# targeted after green init:
./cluster run --phases postgresql --tags 202_pgsql_patroni_verify --limit pgsql_cluster
```

Another env:

```bash
./cluster init prod/pgsql --template postgresql
# then: hosts, VIP, atlas-*.secrets.yml (Vault) → validate → run
```

Optional local org labs: [../local-labs.md](../local-labs.md).

## Secrets

| File | Keys |
|------|------|
| `atlas-postgresql.secrets.yml` | `vip_auth_pass`, `pgsql_postgres_password`, `pgsql_replicator_password` |
| `atlas-compute-provision.secrets.yml` | PVE / DNS / VM cipassword |
| `atlas-node-foundation.secrets.yml` | bootstrap passwords |

Prefer Ansible Vault on those files (not gitignore). Catalogs stay non-secret.

## Phase map

```
  provision --> init --> postgresql
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init` | `atlas-node-foundation/init` | OS bootstrap + managed PGDG repos |
| `postgresql` | `atlas-postgresql/cluster` | etcd → Patroni stack → LB → verify |

(`templates` stays in the playbooks catalog for emergency rebuilds; default plan starts at `provision`. Factory: `--template pve_templates` — [compute-provision.md](compute-provision.md).)

Leaf `phases:` lists only postgresql pipeline refs — omit infra/k8s phase refs.

## Tagged invocations (`atlas-postgresql/cluster`)

Order in `cluster.yaml` (do not skip verify when accepting VIP):

| # | Tags | Limit |
|---|------|--------|
| 1 | `01_validate_vars` | (all relevant) |
| 2 | `200_pgsql_etcd` | `pgsql_etcd_cluster` |
| 3 | `201_pgsql_cluster,202_pgsql_patroni,203_pgsql_bouncer` | `pgsql_cluster` |
| 4 | `204_pgsql_lb` | `pgsql_lbs` |
| 5 | `202_pgsql_patroni_verify` | `pgsql_cluster` |

You may rename inventory groups, but then update in sync:

1. `hosts` (group names),
2. `limit:` in `cluster.yaml` invocations,
3. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
4. override `pgsql_*_hosts` in `atlas-postgresql.yml` (see below).

## Inventory contract

Validate expects groups:

| Group | Role |
|-------|------|
| `postgresql` | Parent (no hosts) |
| `pgsql_etcd_cluster` | etcd for Patroni DCS |
| `pgsql_cluster` | PostgreSQL + Patroni + PgBouncer |
| `pgsql_lbs` | HAProxy + Keepalived |

Sibling playbook targeting uses variables (defaults = names above):

```yaml
# group_vars/all/atlas-postgresql.yml — explicit in template/leaf
pgsql_etcd_hosts: pgsql_etcd_cluster
pgsql_cluster_hosts: pgsql_cluster
pgsql_lb_hosts: pgsql_lbs
```

`./cluster run --phases … --limit` still uses **inventory group names**, not values of these vars.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init` phase)

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `pgsql_etcd_cluster:pgsql_cluster:pgsql_lbs` |
| `pkg_repo_base` | Nexus repository root (ci/lab templates) |
| `pkg_repos` / `pkg_repos_extra` | OS base (env `pkg_repos`) + `pgdg-apt` / `pgdg-yum` (often leaf `pkg_repos_extra`); role → `_pkg_repos_effective` |

Init lays down catalog PGDG drop-ins: `pgdg-apt.sources` / `pgdg-yum.repo` from the combined list.

### `group_vars/all/atlas-node-foundation.yml` (managed repos / PGDG)

For multi-OS leaves include `pgdg-apt` and `pgdg-yum` in `pkg_repos` or `pkg_repos_extra` with full `uri` values (see template / inventory `atlas-node-foundation.yml`).

### `group_vars/all/atlas-postgresql.yml` (`postgresql` phase)

| Knob | Meaning |
|------|---------|
| `pgsql_pgdg_repo_from_init: true` | Roles do **not** install PGDG themselves; verify catalog drop-ins `pgdg-apt.sources` / `pgdg-yum.repo` |
| `vip_*`, passwords, `pgsql_version`, etcd/Patroni tunables | application SoT |

Standalone sibling default: `pgsql_pgdg_repo_from_init: false`.  
Under clusterctl + foundation init keep **`true`**.

### `group_vars/all/atlas-compute-provision.yml`

`provision_stack: postgresql` and map inventory → VM templates (`ubuntu-base` / …). Do not mix with k8s provision maps.

## Sibling mount

Typical mount:

```yaml
atlas-postgresql:
  source: local
  path: atlas-postgresql
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    cluster:
      file: playbooks/postgresql_cluster.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export postgresql`).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/postgresql/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-postgresql README** | Standalone quickstart, tags, role behaviour |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags in `_template/postgresql` `cluster.yaml` match current sibling tags.  
2. Catalog PGDG paths (`pgdg-apt.sources` / `pgdg-yum.repo`) match what foundation writes.  
3. `pgsql_pgdg_repo_from_init: true` when using foundation PGDG.  
4. `./cluster init … --template postgresql` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_ci_postgresql_cluster.py`.  
5. Do not move clusterctl-only instructions into sibling README (short Integrations only, no orchestrator CLI).
