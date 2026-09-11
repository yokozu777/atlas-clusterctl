# Cluster scaffold templates

Public init sources for `./cluster init … --template <name>`.
Neutral placeholders (`example.com`, `CHANGEME`) — not live org labs.

## Templates

| Path | Purpose |
|------|---------|
| `_template/` | Minimal empty scaffold (`--template`) |
| `_template/k8s_full/` | Full k8s stack without infra (`--template k8s_full`) |
| `_template/infra_edge/` | Infra platform only (`--template infra_edge`) — [docs/stacks/infra-edge.md](../../docs/stacks/infra-edge.md) |
| `_template/jenkins_agent/` | Jenkins CI agents (`--template jenkins_agent`) |
| `_template/gitlab_runner/` | GitLab CI runners (`--template gitlab_runner`) |
| `_template/postgresql/` | PostgreSQL HA (`--template postgresql`) — [docs/stacks/postgresql.md](../../docs/stacks/postgresql.md) |
| `_template/redis/` | Redis Cluster HA (`--template redis`) — [docs/stacks/redis.md](../../docs/stacks/redis.md) |
| `_template/kafka/` | Kafka KRaft HA (`--template kafka`) — [docs/stacks/kafka.md](../../docs/stacks/kafka.md) |
| `_template/pve_templates/` | Golden PVE templates build-only (`--template pve_templates`) — [docs/stacks/compute-provision.md](../../docs/stacks/compute-provision.md) |

Stack leaves set `hosts.provision.clone` to golden names (`ubuntu-base` /
`oracle-base` / `debian-base`); they do **not** carry `provision_pve_templates`.
Build images with `pve_templates` first; default stack `phases:` start at `provision`.

Maintainer promote (lab → template):
`python3 -m clusterctl.tools.export_template --from <lab-id> --template <name>`
([ADR 004](../../docs/adr/004-universal-export-template.md)).

```bash
./cluster init lab --from default                    # legacy copy-source (minimal)
./cluster init prod/k8s --template k8s_full --dns-suffix prod.example.com
./cluster init prod/infra --template infra_edge --dns-suffix prod.example.com
./cluster init prod/jenkins --template jenkins_agent --dns-suffix prod.example.com
./cluster init prod/pgsql --template postgresql --dns-suffix prod.example.com
./cluster init prod/redis --template redis --dns-suffix prod.example.com
./cluster init prod/kafka --template kafka --dns-suffix prod.example.com
./cluster init lab/pve-templates --template pve_templates --dns-suffix prod.example.com
./cluster init lab --template                        # minimal empty scaffold
```

## Schema v2

- Templates ship **self-contained** `playbooks` / `phases` (inline aliases — ADR 007)
  in the leaf `cluster.yaml`.
- `clusters/default/default/` is an optional org policy stub (not deployable).
- Local org labs (`clusters/ci/`, `clusters/dev/`) are gitignored — see
  [`docs/local-labs.md`](../../docs/local-labs.md) and [`SECURITY.md`](../../SECURITY.md).

After init:

1. Confirm `id` / `display_name` in `cluster.yaml` (patched by `init`).
2. Confirm Leaf DNS in `group_vars/all/atlas-*.yml`:
   - `dns_domain_suffix` — pass `--dns-suffix` at init, or edit YAML
   - `cluster_domain` — stack prefix is template-owned (`redis.` / `kafka.` / …);
     change it only by editing overlays (or picking another `--template`)
3. Fill product secrets: `group_vars/all/atlas-<repo>.secrets.yml` next to each
   `atlas-<repo>.yml` (Vault-encrypt in place). Prefer copying the sibling pair.
4. Edit `hosts` and stack-specific overlays; replace `CHANGEME` before live apply.

See [docs/clusters.md — Leaf DNS identity](../../docs/clusters.md#leaf-dns-identity),
[docs/playbooks.md](../../docs/playbooks.md).
