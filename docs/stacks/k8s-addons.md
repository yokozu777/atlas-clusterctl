# Kubernetes platform addons via clusterctl

`atlas-k8s-addons` is a **standalone** sibling repository (its own README, `./run.sh`, inventory).  
`atlas-clusterctl` only orchestrates: inventory + group_vars + phases
`provision → init → k8s-core → k8s-addons`.

Canonical sibling playbook: `playbooks/cluster_addons.yaml`.  
Operational role details (Helm, Calico, charts, troubleshooting) live in the sibling README, not here.

Control-plane bootstrap — sibling **atlas-k8s-core** (`k8s-core` phase), see [k8s-core.md](k8s-core.md).  
Infra platform (DNS/CA/registry) — separate leaf **atlas-infra-edge** (`--template infra_edge`), see [infra-edge.md](infra-edge.md).  
Templates / Terraform VMs — [compute-provision.md](compute-provision.md).  
This phase assumes a live API and kubeconfig (or SSH to first master).

## Template and scaffold

| Path | Role |
|------|------|
| `clusters/_template/k8s_full/` | Public SoT (`./cluster init … --template k8s_full`) |

```bash
./cluster init demo/k8s --template k8s_full
./cluster use demo/k8s
./cluster validate --strict
# after successful k8s-core:
./cluster run --phases k8s-core..k8s-addons

# targeted (examples):
./cluster run --phases k8s-addons --tags 130_validate_vars
./cluster run --phases k8s-addons --tags 210_helm_bootstrap,220_calico
./cluster run --phases k8s-addons --tags 520_envoy_gateway
./cluster run --phases k8s-addons --tags 930_keycloak_realm,940_apiserver_oidc,941_k8s_oidc
./cluster run --phases k8s-addons --tags 996_cluster_report
./cluster run --phases k8s-addons --tags 999_debug_tooling --limit k8s_masters:k8s_workers
```

Full greenfield through addons:

```bash
./cluster run --phases provision..k8s-core
./cluster run --phases k8s-core..k8s-addons
```

Edit public SoT directly in `_template/k8s_full`. Promote a lab only via
`export_template` ([ADR 004](../adr/004-universal-export-template.md)); scrub hostnames/secrets — [../local-labs.md](../local-labs.md).

## Phase map

```
  k8s-core --> k8s-addons
```

| Alias | Phase ref | Sibling entry |
|-------|-----------|---------------|
| `k8s-core` | `atlas-k8s-core/cluster` | LB → hosts → kubeadm → kubeconfig |
| `k8s-addons` | `atlas-k8s-addons/addons` | Helm + Calico + platform charts |

Public `k8s_full` includes `k8s-core` + `k8s-addons` in `phases:`. Other leaves
omit those refs when they are not a k8s cluster.

## Tagged invocations (`atlas-k8s-addons/addons`)

Order in `cluster.yaml` matches `playbooks/cluster_addons.yaml`
(do not run Helm roles before tooling / validate / kubeconfig fetch):

| # | Tags | Limit |
|---|------|--------|
| 1 | `110_workspace` | (localhost) |
| 2 | `120_controller_tooling` | (localhost) |
| 3 | `130_validate_vars` | (localhost) |
| 4 | `140_fetch_kubeconfig` | (localhost) |
| 5 | `210_helm_bootstrap` | (localhost) |
| 6 | `220_calico` | (localhost) |
| 7–10 | `310_prometheus` … `340_calico_metrics` | (localhost) |
| 11–15 | `410_snapshotter` … `440_rook_csi_drivers`, `450_thanos` | (localhost; Thanos after Rook RGW / CSI) |
| 16–21 | `510_metallb` … `560_apply_ingress` | (localhost) |
| 22–26 | `610_elasticsearch_prepare` … `650_fluentbit` | (localhost) |
| 27–30 | `710_istio`, `720_external_dns_istio`, `730_tracing`, `740_kiali` | (localhost; Istio NS before Kiali CR). `710_istio` applies `Telemetry/mesh-default` (`otel-tracing`, sampling); empty Jaeger without sidecars is expected; inject app namespaces separately. |
| 31–35 | `800_chaos_mesh`, `810_falco`, `820_kyverno`, `830_policy_reporter`, `840_trivy` | (localhost; Kyverno engine, then Policy Reporter UI, then Trivy Operator; HTTPRoute OIDC after 961) |
| 36–38 | `910_cloudnative_pg` … `930_keycloak_realm` | (localhost) |
| 39–41 | `940_apiserver_oidc`, `941_k8s_oidc`, `942_pinniped` | (localhost except `940_apiserver_oidc` → `k8s_masters`; `940` after `930`, then `941`, then `942`). Live OIDC: `--tags 930_keycloak_realm,940_apiserver_oidc,941_k8s_oidc` (do not add `--limit` / `LIMIT`). |
| 42–46 | `950_mailu`, `954_opencost`, `960_oauth2_proxy`, `961_apply_oidc_ingress`, `962_headlamp` | (localhost; OIDC HTTPRoute in 961 after 960; Headlamp after 961) |
| 46–47 | `973_openbao`, `972_external_secrets` | (localhost). Template sets `consul_chart_state` and `vault_chart_state` to `skip` and does not invoke `970_consul` / `971_vault`. `973_openbao` SSHes to `k8s_masters` for unseal-key SoT — no `limit` in `cluster.yaml`. |
| 49 | `980_argocd` | (localhost; after external-secrets — heavy CRDs) |
| 50 | `982_argocd_rollouts` | (localhost; after argocd) |
| 51–54 | `990_rook_ceph_dashboard`, `992_kibana_dashboards`, `994_sentry`, `996_cluster_report` | (localhost) |
| 55 | `999_debug_tooling` | `k8s_masters:k8s_workers` |

The **k8s-addons** phase starts with `110_workspace` (playbook tag, not `always`). Other stacks still start with `00_ensure_workspace`. Later tagged invocations do not re-run workspace bootstrap.

Most roles are **localhost** Helm/kubectl against `controller_kubeconfig`.  
`940_apiserver_oidc` — SSH to `k8s_masters` (`limit: k8s_masters`); installs lab CA and merges kube-apiserver OIDC extraArgs after Keycloak. Leaf overlay sets only `kube_apiserver_oidc_enabled: true` (issuer is `oidc_issuer_url`; client_id/ca_file from role 940 defaults). Sibling catalog default `false`.  
`941_k8s_oidc` — localhost CRB + `kubeconfig.oidc` after 940 (API already has OIDC flags). Do not `--limit k8s_masters` with `--tags 930_keycloak_realm,940_apiserver_oidc,941_k8s_oidc`: selective `--tags` collapse to one playbook, and that limit would skip 930/941 (localhost). Play 940 still targets `k8s_masters` without a CLI limit.  
`973_openbao` — localhost helm/unseal plus SSH plays on `k8s_masters` for `/root/openbao-init-keys.txt` (no invocation `limit`). HA storage is integrated Raft, not Consul. Do not `--limit localhost` or `--limit k8s_masters` with `--tags 973_openbao`. Helm 4 `upgrade --install` uses `--take-ownership --force-conflicts` (SSA vs the injector webhook `caBundle`); do not delete the injector MutatingWebhookConfiguration. `970_consul` and `971_vault` stay in the playbook; the k8s_full template leaves both chart states at `skip`.  
`999_debug_tooling` — break-glass CLI on nodes.

You may rename inventory groups, but then update in sync:

1. `hosts` (group names),
2. `limit:` on `999_debug_tooling` in `cluster.yaml`,
3. `when.inventory_groups_any` on playbook entry (`k8s_masters` by default),
4. override `k8s_master_hosts` / `k8s_worker_hosts` in `atlas-k8s-core.yml`,
5. children key in `provision_hosts_file` for Rook (see sibling README).

## Inventory contract

| Group | Role for addons | Sizing |
|-------|-----------------|--------|
| `k8s_masters` | Validate (≥1), kubeconfig SSH fetch, debug tooling | ≥ 1 |
| `k8s_workers` | Debug tooling; Rook OSD list via provision inventory | group must exist (may be empty for chart-only) |

Sibling targeting uses variables (defaults = names above):

```yaml
# group_vars/all/atlas-k8s-core.yml — explicit in template/leaf
k8s_master_hosts: k8s_masters
k8s_worker_hosts: k8s_workers
```

`./cluster run --phases … --limit` uses **inventory group names**, not values of these vars.

## Vars bridge (clusterctl → sibling)

Leaf DNS identity and product knobs live in `atlas-*.yml` overlays
([ADR 003](../adr/003-optional-cluster-yml.md) — no `cluster.yml`).

Path / workspace / `cluster_id` are injected by clusterctl. Controller targeting
(`k8s_*_hosts`, `controller_*`, control-plane SSH) lives in `atlas-k8s-core.yml`
— see [k8s-core.md](k8s-core.md).

### `group_vars/all/atlas-k8s-addons.yml` (`k8s-addons` phase)

SoT for Helm catalog, namespaces, ingress hosts, chart versions/states, `k8s_secrets` aggregates.  
Org mirrors (`use_internal_helm_repo: nginx|nexus`), passwords, MetalLB/ingress IPs live **only** here
(not in sibling defaults — there `example.com` / `CHANGEME` / `use_internal_helm_repo: none`).

`*_chart_state` is `present` (install/upgrade), `skip` (not in BOM: no-op, do not uninstall), or `absent` (intentional teardown). clusterctl still invokes every addons tag; the role decides. Template/lab Sentry is `skip`. Ingress entries set `chart_state_var` so skipped charts do not get HTTPRoutes.

Core LB/kubeadm knobs live in `atlas-k8s-core.yml` — see [k8s-core.md](k8s-core.md).

### `group_vars/all/atlas-compute-provision.yml`

| Knob | Meaning |
|------|---------|
| `provision_hosts_file` | SoT for Rook storage nodes (`430_rook_cluster`) |
| `provision_rook_*` | OSD disk index / WWN path prefix |

Standalone sibling: `examples/provision_hosts.example.yml`.

### Secrets

| File | Notes |
|------|--------|
| `atlas-k8s-addons.secrets.yml` | grafana/keycloak/oauth2/envoy-gateway OIDC/vault OIDC/argocd OIDC/elastic (incl. `elastic_jaeger_password`)/kibana/argocd/ceph/sentry/graylog/`vault_admin_password` + external-dns TSIG |
| Catalog `k8s_secrets:` | Jinja refs → keys above (keep in `atlas-k8s-addons.yml`) |

Prefer Ansible Vault on `atlas-k8s-addons.secrets.yml` (not gitignore).

## Sibling mount

Typical mount:

```yaml
atlas-k8s-addons:
  source: local
  path: atlas-k8s-addons
  path_relative_to: sibling
  layout: roles/
  sync: never
  entries:
    addons:
      file: playbooks/cluster_addons.yaml
```

See [../playbooks.md](../playbooks.md). For git mode — `source: git` + `./cluster repos sync`.

Ad-hoc Ansible with the same workspace env: [../ansible.md](../ansible.md) (`export k8s-addons` / phase env).

## Documentation split

| Where to write | What |
|----------------|------|
| **This file** + `_template/k8s_full/README.md` | Orchestration, topology, `./cluster` flow |
| **atlas-k8s-addons README** | Standalone quickstart, tags, role behaviour |
| Sibling must not require `./cluster` knowledge | Product path = `./run.sh` + inventory |

## Checklist after sibling changes

1. Invocations/tags/limits in `_template/k8s_full` match playbook order (+ leading `110_workspace`).  
2. `130_validate_vars` runs after tooling and before fetch/Helm.  
3. `994_sentry` before `996_cluster_report` (as in playbook).  
4. `k8s_*_hosts` in `atlas-k8s-core.yml` match group names in `hosts` and `limit:` on debug tooling.  
5. `./cluster init … --template k8s_full` → `validate --strict` (optional local lab — [../local-labs.md](../local-labs.md)) and unit `tests/test_k8s_addons_orchestration.py`.  
6. Do not move clusterctl-only instructions into sibling README (short Integrations only).  
7. Public SoT = `_template/k8s_full`; promote only via `export_template` ([ADR 004](../adr/004-universal-export-template.md)) with scrub ([../local-labs.md](../local-labs.md)).
