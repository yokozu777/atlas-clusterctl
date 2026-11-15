# DevOps compose stack via clusterctl

`atlas-devops-stack` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases `provision → init → devops`.

Canonical sibling playbook: `playbooks/devops_stack.yaml`.
Operational role details (Docker, nginx stream, Compose services) live in the sibling README, not here.

## Layout

| Path | Role |
|------|------|
| `clusters/_template/devops_stack/` | Public SoT scaffold (one VM, 8 CPU / 32 GB, 50 GB OS + 200 GB data) |

```bash
./cluster init demo/devops --template devops_stack
./cluster use demo/devops
# fill atlas-devops-stack.secrets.yml, then:
./cluster run --phases provision..devops
./cluster run --phases devops --tags 220_nexus --limit devops_stack
```

```bash
./cluster init prod/devops --template devops_stack
```

## Secrets before the first real run

| File | What to fill |
|------|----------------|
| `atlas-devops-stack.secrets.yml` | Admin and database passwords (required by `01_validate_vars`) |
| `atlas-compute-provision.secrets.yml` | Proxmox / DNS tokens |
| `atlas-node-foundation.secrets.yml` | OS bootstrap passwords |

Empty product passwords fail validation. OpenBao's unseal key is generated on the VM, not stored in this overlay.

## Phases (order)

```
  provision --> init --> devops
```

| Phase | Playbook ref | What runs |
|-------|----------------|-----------|
| `provision` | `atlas-compute-provision/provision` | Terraform VM |
| `init` | `atlas-node-foundation/init` | OS bootstrap, including `11_certificates` |
| `devops` | `atlas-devops-stack/stack` | Docker, render, nginx, then one role per product |

Leaf `phases:` lists only this pipeline — omit infra/k8s phase refs.

## Tagged invocations (`atlas-devops-stack/stack`)

| # | Tag | Limit |
|---|-----|-------|
| 1 | `00_ensure_workspace` | localhost |
| 2 | `01_validate_vars` | localhost |
| 3 | `200_docker` | `devops_stack` |
| 4 | `210_compose_render` | `devops_stack` |
| 5 | `211_nginx` | `devops_stack` |
| 6 | `220_nexus` | `devops_stack` |
| 7 | `221_gitlab` | `devops_stack` |
| 8 | `222_jenkins` | `devops_stack` |
| 9 | `223_gitea` | `devops_stack` |
| 10 | `224_sonarqube` | `devops_stack` |
| 11 | `225_defectdojo` | `devops_stack` |
| 12 | `226_openbao` | `devops_stack` |
| 13 | `227_wiki` | `devops_stack` |
| 14 | `228_harbor` | `devops_stack` |
| 15 | `229_portainer` | `devops_stack` |
| 16 | `230_heimdall` | `devops_stack` |
| 17 | `231_cloudbeaver` | `devops_stack` |
| 18 | `232_kafbat` | `devops_stack` |
| 19 | `233_redisinsight` | `devops_stack` |

## Inventory

One host. Parent `devops` nests `devops_stack`.

```yaml
# group_vars/all/atlas-devops-stack.yml
devops_stack_hosts: devops_stack
```

The host needs `hostname` (prefer FQDN) and `devops_data_disk` pointing at the slot 1 disk. Template sizing is 8 CPU, 32 GB RAM, a 50 GB OS disk, and a 200 GB XFS data disk. Docker data-root and the Compose project are mounted on that disk.

Init tag `11_certificates` installs the step-ca root into the host trust store. A server leaf placed at `devops_tls_cert_file` / `devops_tls_key_file` is used by nginx. If those files are absent, the product role writes a self-signed certificate for the vhost names.

### `group_vars/all/atlas-node-foundation.yml` (`init`)

| Var | Template value |
|-----|----------------|
| `node_foundation_init_hosts` | `devops_stack` |

### `group_vars/all/atlas-devops-stack.yml` (`devops` phase)

| Var | Role |
|-----|------|
| `devops_stack_hosts` | inventory group name for sibling targeting |
| `devops_vhost_labels` | names under `cluster_domain` |
| `devops_http_port` / `devops_https_port` / SSH stream ports | nginx listeners |
| `devops_image_*` | pinned community/OSS tags |
| `devops_tls_cert_file` / `devops_tls_key_file` | optional step-ca leaf |

Standalone sibling defaults use `devops.example.com`. Org DNS identity lives **only** in the clusterctl overlays.

## Provision

`provision_stack: devops` and map inventory → the VM module. Do not mix with k8s provision maps.

```yaml
atlas-devops-stack:
  source: git
  path: atlas-devops-stack
  path_relative_to: sibling
  entries:
    stack:
      file: playbooks/devops_stack.yaml
```

## Where to read more

| Doc | What it owns |
|-----|----------------|
| **This file** + `_template/devops_stack/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-devops-stack README** | Standalone quickstart, tags, nginx, images |

## Keeping the template honest

1. Invocations/tags in `_template/devops_stack` `cluster.yaml` match current sibling tags (+ leading `00_ensure_workspace`).
2. `devops_stack_hosts` in `atlas-devops-stack.yml` matches the group in `hosts` and `limit:` in `cluster.yaml`.
3. `node_foundation_init_hosts` covers `devops_stack`.
4. `./cluster init … --template devops_stack` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)).
