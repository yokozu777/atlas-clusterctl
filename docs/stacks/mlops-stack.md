# MLOps compose stack via clusterctl

`atlas-mlops-stack` is a standalone sibling repository.
`atlas-clusterctl` orchestrates inventory, group_vars, and phases `provision → init → mlops`.

Canonical sibling playbook: `playbooks/mlops_stack.yaml`.

## Layout

| Path | Role |
|------|------|
| `clusters/_template/mlops_stack/` | Public scaffold (one VM, 8 CPU / 32 GB, 50 GB OS + 200 GB data) |

```bash
./cluster init demo/mlops --template mlops_stack
./cluster use demo/mlops
./cluster run --phases provision..mlops
```

## Secrets before the first real run

| File | What to fill |
|------|----------------|
| `atlas-mlops-stack.secrets.yml` | Admin and database passwords |
| `atlas-compute-provision.secrets.yml` | Proxmox / DNS tokens |
| `atlas-node-foundation.secrets.yml` | OS bootstrap passwords |

The JupyterHub crypt key and the Airflow Fernet key are generated on the VM.

## Phases (order)

```
  provision --> init --> mlops
```

| Phase | Playbook ref | What runs |
|-------|----------------|-----------|
| `provision` | `atlas-compute-provision/provision` | Terraform VM |
| `init` | `atlas-node-foundation/init` | OS bootstrap, including `11_certificates` |
| `mlops` | `atlas-mlops-stack/stack` | Docker, render, nginx, then one role per product |

## Tagged invocations (`atlas-mlops-stack/stack`)

| # | Tag | Limit |
|---|-----|-------|
| 1 | `00_ensure_workspace` | localhost |
| 2 | `01_validate_vars` | localhost |
| 3 | `200_docker` | `mlops_stack` |
| 4 | `210_compose_render` | `mlops_stack` |
| 5 | `211_nginx` | `mlops_stack` |
| 6 | `220_jupyterhub` | `mlops_stack` |
| 7 | `221_mlflow` | `mlops_stack` |
| 8 | `222_airflow` | `mlops_stack` |
| 9 | `223_superset` | `mlops_stack` |
| 10 | `224_portainer` | `mlops_stack` |
| 11 | `225_heimdall` | `mlops_stack` |
| 12 | `226_evidently` | `mlops_stack` |

## Inventory

One host. Parent `mlops` nests `mlops_stack`. `mlops_data_disk` is a host variable.
