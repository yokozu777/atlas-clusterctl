# Jenkins agents via clusterctl

`atlas-jenkins-agent` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases
`provision → init → jenkins-agent`.

Canonical sibling playbook: `playbooks/jenkins_agent.yaml`.  
Operational role details (Docker CE, JNLP registration, troubleshooting) live in the sibling README, not here.

Do not confuse with [../jenkins.md](../jenkins.md) — that document covers the **Jenkinsfile / CI pipeline for clusterctl itself**, not sibling `atlas-jenkins-agent`.

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/jenkins_agent/` | Public SoT (`./cluster init … --template jenkins_agent`) |

```bash
./cluster init demo/jenkins --template jenkins_agent
./cluster use demo/jenkins
./cluster validate --strict
./cluster plan -v
./cluster run --phases provision..jenkins-agent

# targeted:
./cluster run --phases jenkins-agent --tags 01_validate_vars
./cluster run --phases jenkins-agent --tags 03_install_jslave --limit jslave
```

Another env:

```bash
./cluster init prod/jenkins --template jenkins_agent
# then: hosts, jenkins_url/credentials, secrets → validate → run
```

Optional local org labs: [../local-labs.md](../local-labs.md).

## Phase map

```
  provision --> init --> jenkins-agent
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `provision` | `atlas-compute-provision/provision` | Terraform VMs + wait SSH — [compute-provision.md](compute-provision.md) |
| `init` | `atlas-node-foundation/init` | OS bootstrap (+ CA + managed package repos) |
| `jenkins-agent` | `atlas-jenkins-agent/agent` | Docker + agent jars + Jenkins CLI register |

(`templates` stays in the playbooks catalog for emergency rebuilds; default plan starts at `provision`. Factory: `--template pve_templates` — [compute-provision.md](compute-provision.md).)

Leaf `phases:` lists only jenkins pipeline refs — omit infra/k8s phase refs
(infra is a separate `infra_edge` leaf).

## Tagged invocations (`atlas-jenkins-agent/agent`)

Order in `cluster.yaml` matches `playbooks/jenkins_agent.yaml`
(do not run install before validate):

| # | Tags | Limit |
|---|------|--------|
| 1 | `01_validate_vars` | (localhost) |
| 2 | `03_install_jslave` | `jslave` |

The first invocation in each phase is `00_ensure_workspace` (playbook tag, not `always`). Later tagged invocations do not re-run workspace bootstrap. For `init`, the first remote invocation also includes `00_gather_facts` (with `root_ssh`); ensure-only stays localhost. Later init tags reuse `ansible_facts` via `atlas-node-foundation` `fact_caching=jsonfile` (workspace `ANSIBLE_CACHE_PLUGIN_CONNECTION`).

You may rename the inventory group, but then update in sync:

1. `hosts` (group name),
2. `limit:` on `init` and `03_install_jslave` in `cluster.yaml`,
3. `when.inventory_groups_any` on playbook entries,
4. `node_foundation_init_hosts` in `atlas-node-foundation.yml`,
5. override `jenkins_agent_hosts` in `atlas-jenkins-agent.yml`,
6. `provision_inventory_group_map_jenkins` / provision maps when renaming the group.

## Inventory contract

| Group | Role for jenkins-agent | Sizing |
|-------|------------------------|--------|
| `jslave` | Validate (≥1), install/register, init OS bootstrap | ≥ 1 |

Sibling targeting uses a variable (default = name above):

```yaml
# group_vars/all/atlas-jenkins-agent.yml — explicit in template/leaf
jenkins_agent_hosts: jslave
```

`./cluster run --phases … --limit` uses **inventory group names**, not the value of `jenkins_agent_hosts`.

## Vars bridge (clusterctl → sibling)

### `group_vars/all/atlas-node-foundation.yml` (`init` phase)

| Knob | Lab expectation |
|------|-----------------|
| `node_foundation_init_hosts` | `jslave` (or renamed group) |
| `pki_ca_url` | CA bootstrap (string or list of root PEM URLs) → system trust + `jenkins_ca_cert_path` |
| `pkg_repo_base` / `pkg_repos` / `pkg_repos_extra` | OS base (+ env default) + containerd/Docker extras on leaf `pkg_repos_extra` |

### `group_vars/all/atlas-jenkins-agent.yml` (`jenkins-agent` phase)

| Knob | Meaning |
|------|---------|
| `jenkins_agent_hosts` | inventory group name for sibling targeting |
| `jenkins_url` / `jenkins_admin_*` | controller + CLI/JNLP credentials |
| `jenkins_ca_cert_path` | CA file on agent (usually from init `11_certificates`) |
| `jenkins_agent_num_executors` / `jenkins_docker_registry_mirrors` | agent behaviour |
| `pkg_repo_base` / `pkg_repo_nginx_ingress_domain` | Docker CE URI bake when foundation drop-ins are absent (`base` → domain → public) |
| `jenkins_agent_debian_packages_extra` | Ubuntu/Debian extras: `certbot`, `python3-yaml` (PyYAML), `ansible-core` (`ansible-galaxy`) |
| `jenkins_agent_oracle_packages_extra` | OL extras: `certbot`, `python3-pyyaml`, `ansible-core` (EPEL) |

Standalone sibling defaults: `example.com`, `CHANGEME`, empty `pkg_repo_base` / domain (public Docker CE).  
Org mirrors, URLs, and passwords live **only** in clusterctl overlays / `atlas-*.secrets.yml`.

### `group_vars/all/atlas-compute-provision.yml`

`provision_stack: jenkins` and map inventory → VM templates. Do not mix with k8s provision maps.

### Secrets

`group_vars/all/atlas-jenkins-agent.secrets.yml` (+ compute/foundation secrets overlays):

- `jenkins_admin_password`
- provision/DNS tokens in `atlas-compute-provision.secrets.yml`

Do not commit live passwords in `atlas-jenkins-agent.yml`.

## Sibling mount

Typical mount:

```yaml
atlas-jenkins-agent:
  source: local
  path: atlas-jenkins-agent
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    agent:
      file: playbooks/jenkins_agent.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export jenkins-agent` / phase env).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/jenkins_agent/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-jenkins-agent README** | Standalone quickstart, tags, role behaviour |
| [../jenkins.md](../jenkins.md) | clusterctl Jenkinsfile / CI pipeline |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags/limits in `_template/jenkins_agent` match playbook order (+ leading `00_ensure_workspace`).  
2. `01_validate_vars` before `03_install_jslave`; install has `limit:` on agent group.  
3. `jenkins_agent_hosts` in `atlas-jenkins-agent.yml` matches group name in `hosts` and `limit:` / `when`.  
4. `node_foundation_init_hosts` covers the same group.  
5. Credentials — in `atlas-*.secrets.yml` (Vault), not plaintext in tracked `atlas-jenkins-agent.yml`.  
6. `./cluster init … --template jenkins_agent` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_jenkins_agent_orchestration.py`.  
7. Do not move clusterctl-only instructions into sibling README (short Integrations only).
