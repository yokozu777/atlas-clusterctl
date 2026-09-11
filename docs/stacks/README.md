# Stack orchestration guides

Per-stack docs for `./cluster` phases: inventory groups, vars bridge, tags, and sibling repo contracts.

```
  Golden images:  templates                         (pve_templates leaf)
  Full k8s:       provision --> init --> k8s-core --> k8s-addons
  Infra-only:     provision --> init-infra --> infra --> init-infra-post
  Data-plane:     provision --> init --> postgresql|redis|kafka
  Agents:         provision --> init --> jenkins-agent
```

Build golden PVE templates once (`--template pve_templates`), then clone
`ubuntu-base` / `oracle-base` / `debian-base` via `hosts.provision.clone` on stack
leaves (no `provision_pve_templates` catalog on stacks).
Infra is a **separate** leaf (`infra_edge`), not part of public `k8s_full`.
Point k8s `dns_server_ip` / NTP at that node after it is up.

| Doc | Sibling repo | Typical template |
|-----|--------------|------------------|
| [compute-provision.md](compute-provision.md) | `atlas-compute-provision` | `pve_templates` + all stacks (`templates` / `provision`) |
| [infra-edge.md](infra-edge.md) | `atlas-infra-edge` | `infra_edge` |
| [k8s-core.md](k8s-core.md) | `atlas-k8s-core` | `k8s_full` |
| [k8s-addons.md](k8s-addons.md) | `atlas-k8s-addons` | `k8s_full` |
| [jenkins-agent.md](jenkins-agent.md) | `atlas-jenkins-agent` | `jenkins_agent` |
| [gitlab-runner.md](gitlab-runner.md) | `atlas-gitlab-runner` | `gitlab_runner` |
| [postgresql.md](postgresql.md) | `atlas-postgresql` | `postgresql` |
| [redis.md](redis.md) | `atlas-redis` | `redis` |
| [kafka.md](kafka.md) | `atlas-kafka` | `kafka` |

Leaf DNS identity (`dns_domain_suffix` / `cluster_domain`) lives in each stack’s
`atlas-*.yml` overlays — see [ADR 003](../adr/003-optional-cluster-yml.md)
(no `group_vars/all/cluster.yml`).

- Shared suffix: `./cluster init … --dns-suffix lab.example.com` (or edit YAML).
- Stack prefix (`redis.` / `kafka.` / `pgsql.` / `k8s.` / …): choose the matching
  `--template`, or edit `cluster_domain` in the overlays — init does not rewrite it.

Back to [docs index](../README.md).
