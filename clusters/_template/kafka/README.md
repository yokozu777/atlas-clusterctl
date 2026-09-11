# Reference Kafka KRaft HA — self-contained configuration (provision → init → kafka).

Orchestration contract (phases, inventory, vars bridge, tagged invocations):

→ **[`docs/stacks/kafka.md`](../../../docs/stacks/kafka.md)**

Pipeline (no infra / no k8s):

```bash
./cluster run --cluster <your-id> --phases provision..kafka
```

Phases: `provision` → `init` → `kafka`

The `kafka` phase uses five tagged invocations (validate → node → controllers → brokers → verify). Role-level troubleshooting: sibling `atlas-kafka` README.

Init copy for new clusters:

```bash
./cluster init prod/kafka --template kafka
```

Edit after init:

1. Leaf DNS in `atlas-*.yml`: `--dns-suffix` for the shared suffix; `cluster_domain`
   prefix (`kafka.`) is template-owned — edit overlays to change it
2. `group_vars/all/atlas-compute-provision.yml` (+ `.secrets.yml`) — PVE/DNS credentials, VM templates
3. `group_vars/all/atlas-kafka.yml` — version/ports, `kafka_*_hosts`, optional HTTP mirrors
4. `group_vars/all/atlas-kafka.secrets.yml` — future SASL/TLS (empty for plaintext lab)
5. `group_vars/all/atlas-node-foundation.yml` — `pkg_repos` + `node_foundation_init_hosts`
6. `hosts` — nested `kafka` → controllers/brokers + stable `kafka_node_id`

Inventory groups:

| Group | Role |
|-------|------|
| `kafka` | Parent (no hosts) |
| `kafka_controllers` | KRaft controllers (odd ≥ 3) |
| `kafka_brokers` | Brokers (≥ 3) |

Lab mirrors and domains live in clusterctl `atlas-kafka.yml` (and other Leaf DNS overlays); sibling product defaults stay org-neutral.

Regenerate this scaffold from a lab (maintainer; scrub hostnames/secrets after):

```bash
python3 -m clusterctl.tools.export_template --from <lab-id> --template kafka
```

Does **not** modify other cluster leaves.
