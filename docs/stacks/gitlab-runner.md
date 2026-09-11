# GitLab runners via clusterctl

`atlas-gitlab-runner` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases
`provision → init → gitlab-runner`.

Canonical sibling playbook: `playbooks/gitlab_runner.yaml`.  
Operational role details (Docker CE, shell|docker executor, config.toml) live in the sibling README, not here.

Do not confuse with [../gitlab-ci.md](../gitlab-ci.md) — that document covers the **GitLab CI pipeline for clusterctl itself**, not sibling `atlas-gitlab-runner`.

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/gitlab_runner/` | Public SoT (`./cluster init … --template gitlab_runner`) |

```bash
./cluster init demo/gitlab --template gitlab_runner
./cluster use demo/gitlab
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..gitlab-runner

# targeted:
./cluster run --phases gitlab-runner --tags 01_validate_vars
./cluster run --phases gitlab-runner --tags 03_install_runner --limit gitlab_runners
```

Another env:

```bash
./cluster init prod/gitlab --template gitlab_runner
# then: hosts, gitlab_url/token, secrets → validate → run
```

Optional local org labs: [../local-labs.md](../local-labs.md).

## Phase map

```
  provision --> init --> gitlab-runner
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init` | `atlas-node-foundation/init` | OS bootstrap (+ CA + managed package repos) |
| `gitlab-runner` | `atlas-gitlab-runner/runner` | Docker + gitlab-runner package + managed config.toml (no CLI register) |

(`templates` stays in the playbooks catalog for emergency rebuilds; default plan starts at `provision`. Factory: `--template pve_templates` — [compute-provision.md](compute-provision.md).)

Leaf `phases:` lists only gitlab-runner pipeline refs — omit infra/k8s phase refs
(infra is a separate `infra_edge` leaf).

## Tagged invocations (`atlas-gitlab-runner/runner`)

Order in `cluster.yaml` matches `playbooks/gitlab_runner.yaml`
(do not run install before validate):

| # | Tags | Limit |
|---|------|--------|
| 1 | `01_validate_vars` | (localhost) |
| 2 | `02_ensure_runner_token` | (localhost; PAT preflight when auto-create) |
| 3 | `03_install_runner` | `gitlab_runners` |

The first invocation in each phase is `00_ensure_workspace` (playbook tag, not `always`). Later tagged invocations do not re-run workspace bootstrap. For `init`, the first remote invocation also includes `00_gather_facts` (with `root_ssh`); ensure-only stays localhost. Later init tags reuse `ansible_facts` via `atlas-node-foundation` `fact_caching=jsonfile` (workspace `ANSIBLE_CACHE_PLUGIN_CONNECTION`).

You may rename the inventory group, but then update in sync:

1. `hosts` (group name),
2. `limit:` on `init` and `03_install_runner` in `cluster.yaml`,
3. `when.inventory_groups_any` on playbook entries,
4. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
5. override `gitlab_runner_hosts` in `atlas-gitlab-runner.yml`,
6. `provision_inventory_group_map_gitlab_runner` / provision maps when renaming the group.

## Inventory contract

| Group | Role for gitlab-runner | Sizing |
|-------|------------------------|--------|
| `gitlab_runners` | Validate (≥1), install + managed config.toml, init OS bootstrap | ≥ 1 |

Sibling targeting uses a variable (default = name above):

```yaml
# group_vars/all/atlas-gitlab-runner.yml — explicit in template/leaf
gitlab_runner_hosts: gitlab_runners
```

`./cluster run --phases … --limit` uses **inventory group names**, not the value of `gitlab_runner_hosts`.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init` phase)

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `gitlab_runners` (or renamed group) |
| `pki_ca_url` | CA bootstrap (string or list of root PEM URLs) → system trust + `gitlab_runner_ca_cert_path` |
| `pkg_repo_base` / `pkg_repos` / `pkg_repos_extra` | OS base (+ env default `pkg_repos`) + stack extras (`pkg_repos_extra`); role combines to `_pkg_repos_effective` |

### `group_vars/all/atlas-gitlab-runner.yml` (`gitlab-runner` phase)

| Knob | Meaning |
|------|---------|
| `gitlab_runner_hosts` | inventory group name for sibling targeting |
| `gitlab_url` / `gitlab_runner_authentication_token` | GitLab + modern runner auth token (secrets; or auto-create) |
| `gitlab_runner_token_auto_create` | when true, role `03` resolves per-host `glrt-…` (secrets → host `config.toml`+verify → API create/reset); role `02` is PAT preflight only |
| `gitlab_runner_api_private_token` | PAT for auto-create (`create_runner` + `read_api`; `manage_runner` for reset) |
| `gitlab_runner_api_description` | optional override; default `atlas:{{ cluster_domain }}:{{ hostname }}` (one GitLab instance runner per host) |
| (durable token) | secrets and/or `/etc/gitlab-runner/config.toml` on each runner host — **not** workspace cache (`CHANGEME` in secrets is fine; live value is `_gitlab_runner_auth_token` because clusterctl `-e` cannot be overridden by `set_fact`) |
| `gitlab_runner_executor` | `shell` (default) or `docker` |
| `gitlab_runner_ca_cert_path` | basename hint for `tls-ca-file`; role resolves into distro trust dir (same as foundation `11_certificates`) |
| `pki_ca_url` / `gitlab_runner_ca_cert_download_url` | foundation-style PEM fetch (`get_url` → ca-certificates / OL anchors) |
| `gitlab_runner_docker_*` / `gitlab_docker_registry_mirrors` | docker executor + dockerd mirrors |
| `pkg_repo_base` / `pkg_repo_nginx_ingress_domain` | Docker CE / gitlab-runner URI bake when foundation drop-ins are absent |
| `gitlab_runner_debian_packages_extra` | Ubuntu/Debian extras: `certbot`, `python3-yaml`, `ansible-core` |
| `gitlab_runner_oracle_packages_extra` | OL extras: `certbot`, `python3-pyyaml`, `ansible-core` |

Standalone sibling defaults: `example.com`, `CHANGEME`, empty `pkg_repo_base` / domain (public packages).  
Org mirrors, URLs, and tokens live **only** in clusterctl overlays / `atlas-*.secrets.yml`.

**Migration (shared → per-host):** if an older leaf used a single shared description
(e.g. `atlas:gitlab-runner.example.com`), delete that runner in GitLab Admin after
cutover. New descriptions are `atlas:<cluster_domain>:<hostname>` (N instance runners).

### `group_vars/all/atlas-compute-provision.yml`

`provision_stack: gitlab_runner` and map inventory → VM templates. Do not mix with k8s provision maps.

## Related

- Sibling README: `atlas-gitlab-runner`
- Compute maps: [compute-provision.md](compute-provision.md)
- clusterctl GitLab CI jobs (consumer of runners): [gitlab-ci.md](../gitlab-ci.md)
