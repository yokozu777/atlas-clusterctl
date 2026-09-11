# `k8s_full` — full Kubernetes stack template

Self-contained **public** scaffold for `./cluster init <id> --template k8s_full`.
Uses neutral `example.com` / `CHANGEME` placeholders — fill secrets and inventory before live apply.

Phases: `provision → init → k8s-core → k8s-addons`.

**Infra (DNS / CA / registry) is not included.** Bring it up with a separate leaf:

```bash
./cluster init lab/infra --template infra_edge
```

Then point this cluster’s `dns_server_ip`, `ntp_servers`, and `dns_servers` at that node
(see `atlas-k8s-core.yml` / `atlas-node-foundation.yml` Leaf DNS and related knobs).

Orchestration: [docs/stacks/compute-provision.md](../../../docs/stacks/compute-provision.md),
[docs/stacks/k8s-core.md](../../../docs/stacks/k8s-core.md), [docs/stacks/k8s-addons.md](../../../docs/stacks/k8s-addons.md).
Infra platform: [docs/stacks/infra-edge.md](../../../docs/stacks/infra-edge.md).

Prefer this over `init --from default` for a full k8s leaf.

## Init new cluster

```bash
./cluster init prod/k8s --template k8s_full
./cluster init prod/k8s --template k8s_full --dns-suffix prod.example.com
./cluster init prod/k8s --template k8s_full --display-name "Prod k8s"
```

Then:

1. Edit `hosts` (IPs / hostnames).
2. Confirm Leaf DNS: `--dns-suffix` sets the shared suffix; `cluster_domain` keeps the
   `k8s.` template prefix unless you edit `atlas-*.yml`.
3. Fill product secrets overlays (Vault recommended):
   `atlas-compute-provision.secrets.yml`, `atlas-node-foundation.secrets.yml`,
   `atlas-k8s-core.secrets.yml`, `atlas-k8s-addons.secrets.yml`.
4. Set `dns_server_ip` / NTP / DNS to your infra_edge (or lab) BIND.
5. Set `execution.image` / `execution.tag` if needed (default: [`yokozu/krang:336`](https://hub.docker.com/r/yokozu/krang) — build from [infrastructure-automation-toolkit](https://github.com/yokozu777/infrastructure-automation-toolkit)).
6. Point playbook `url:` entries at your remotes (or keep `source: local` siblings).

## Runtime cascade

Even with a flattened `cluster.yaml`, **`default/default` org baseline still merges at runtime**
unless the leaf replaces sections explicitly.

## Local labs

Org reference labs under `clusters/ci/` and `clusters/dev/` are **local-only** (gitignored).
Some labs may still embed infra in one leaf for convenience; the public template does not.
Do not re-export a private lab into this public template without scrubbing hostnames and secrets.
See [`SECURITY.md`](../../../SECURITY.md) and [ADR 004](../../../docs/adr/004-universal-export-template.md).

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template k8s_full
```

Sibling product docs: `atlas-k8s-core` / `atlas-k8s-addons` README (standalone `./run.sh`).
