# Reference Redis Cluster HA — self-contained configuration (provision → init → redis).

Orchestration contract (phases, inventory, vars bridge, tagged invocations):

→ **[`docs/stacks/redis.md`](../../../docs/stacks/redis.md)**

Pipeline (no infra / no k8s):

```bash
./cluster run --cluster <your-id> --phases provision..redis
```

Phases: `provision` → `init` → `redis`

The `redis` phase uses six tagged invocations (validate → nodes → cluster → proxy → LB → verify). Role-level troubleshooting: sibling `atlas-redis` README.

Init copy for new clusters:

```bash
./cluster init prod/redis --template redis
```

Edit after init:

1. Leaf DNS in `atlas-*.yml`: `--dns-suffix` for the shared suffix; `cluster_domain`
   prefix (`redis.`) is template-owned — edit overlays to change it
2. `group_vars/all/atlas-compute-provision.yml` — PVE/DNS credentials, VM templates
3. `group_vars/all/atlas-redis.yml` — VIP address/interface, Redis/Predixy version, `redis_*_hosts`, optional HTTP mirrors
4. `group_vars/all/atlas-redis.secrets.yml` — `vip_auth_pass` (prefer Ansible Vault; max 8 chars)
5. `group_vars/all/atlas-node-foundation.yml` — `pkg_repos` + `node_foundation_init_hosts`
6. `hosts` — nested `redis` → `redis_*` VM layout

Inventory groups:

| Group | Role |
|-------|------|
| `redis` | Parent (no hosts) |
| `redis_cluster_masters` | Redis Cluster masters (>=3) |
| `redis_cluster_replicas` | Redis Cluster replicas (masters × replicas_per_master) |
| `redis_proxies` | Predixy cluster proxy (>=2) |
| `redis_lbs` | HAProxy + Keepalived VIP (>=2) |

Lab mirrors and VIP address live in clusterctl `atlas-redis.yml`; Keepalived pass in
`atlas-redis.secrets.yml`. Sibling product defaults stay org-neutral (`CHANGEME` / empty mirrors).

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template redis
```

Does **not** modify other cluster leaves.
