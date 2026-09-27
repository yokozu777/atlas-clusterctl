# `infra_edge` — infra platform node template

Self-contained scaffold for the edge platform host (DNS / CA / registry / pkg+helm caches).
No k8s phases — operators configure k8s clients against this node later in a separate cluster leaf.

Orchestration: [docs/stacks/infra-edge.md](../../../docs/stacks/infra-edge.md).

Product pair (copy/align with sibling `atlas-infra-edge`):

- `group_vars/all/atlas-infra-edge.yml`
- `group_vars/all/atlas-infra-edge.secrets.yml` (Vault-friendly; TSIG / step-ca / sync)

## Init new cluster

```bash
./cluster init prod/infra --template infra_edge
./cluster init prod/infra --template infra_edge --dns-suffix prod.example.com
```

Then edit `hosts`, fill `atlas-infra-edge.secrets.yml` (compute-provision secrets
live on ``<env>/default``), and tune `atlas-infra-edge.yml` gates.

Leaf DNS: `--dns-suffix` sets the shared suffix; `cluster_domain` keeps the
`infra.` template prefix unless you edit `atlas-*.yml`.

## Phases

`templates` → `provision` → `init-infra` → `infra` → `init-infra-post`

`infra` compose cold path (clusterctl invocations — do not reorder without syncing sibling playbook):

```
compose_render → compose_pull → compose_start_core
  → 11_sync_infra_cache_pull / 14_infra_cache_seed_load → compose_start_registry → compose_reconcile
  → 11_sync_infra_cache_push
```

```bash
./cluster plan -v
./cluster run --phases provision..init-infra-post
./cluster run --phases infra --tags compose_render --limit infra_platform
./cluster run --phases infra --tags compose_start_registry --limit infra_platform
```

## Reference

After init: `./cluster use <your-id>` (optional local org labs — [docs/local-labs.md](../../../docs/local-labs.md))  
Sibling product docs: `atlas-infra-edge` README (standalone `./run.sh`).

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template infra_edge
```
