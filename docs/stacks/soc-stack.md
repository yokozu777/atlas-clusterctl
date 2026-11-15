# SOC compose stack via clusterctl

`atlas-soc-stack` is a standalone sibling repository.
`atlas-clusterctl` orchestrates inventory, group_vars, and phases `provision → init → soc`.

Canonical sibling playbook: `playbooks/soc_stack.yaml`.

## Layout

| Path | Role |
|------|------|
| `clusters/_template/soc_stack/` | Public scaffold (one VM, 16 CPU / 64 GB, 50 GB OS + 500 GB data) |

```bash
./cluster init demo/soc --template soc_stack
./cluster use demo/soc
./cluster run --phases provision..soc
```

## Secrets before the first real run

| File | What to fill |
|------|----------------|
| `atlas-soc-stack.secrets.yml` | Admin and database passwords |
| `atlas-compute-provision.secrets.yml` | Proxmox / DNS tokens |
| `atlas-node-foundation.secrets.yml` | OS bootstrap passwords |

Wazuh certificates and indexer password hashes are generated on the VM.

## Phases (order)

```
  provision --> init --> soc
```

| Phase | Playbook ref | What runs |
|-------|----------------|-----------|
| `provision` | `atlas-compute-provision/provision` | Terraform VM |
| `init` | `atlas-node-foundation/init` | OS bootstrap, including `11_certificates` |
| `soc` | `atlas-soc-stack/stack` | Docker, render, nginx, then one role per product |

## Tagged invocations (`atlas-soc-stack/stack`)

| # | Tag | Limit |
|---|-----|-------|
| 1 | `00_ensure_workspace` | localhost |
| 2 | `01_validate_vars` | localhost |
| 3 | `200_docker` | `soc_stack` |
| 4 | `210_compose_render` | `soc_stack` |
| 5 | `211_nginx` | `soc_stack` |
| 6 | `220_iris` | `soc_stack` |
| 7 | `221_wazuh` | `soc_stack` |
| 8 | `222_cortex` | `soc_stack` |
| 9 | `223_misp` | `soc_stack` |
| 10 | `224_greenbone` | `soc_stack` |
| 11 | `225_shuffle` | `soc_stack` |
| 12 | `226_portainer` | `soc_stack` |
| 13 | `227_heimdall` | `soc_stack` |

## Inventory

One host. Parent `soc` nests `soc_stack`. `soc_data_disk` is a host variable.
Wazuh also publishes agent ports 1514 and 1515. Each product keeps its own database.
