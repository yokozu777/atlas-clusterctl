# Clusters layout

Cluster configuration lives under `clusters/<env>/<name>/`. Runtime artifacts live in `workspace/` ([workspace.md](workspace.md)).

Public SoT: **`clusters/_template/*`** + **`clusters/default/`**.  
Live labs / private inventory: [local-labs.md](local-labs.md)
(`.config/config.yaml` or `ATLAS_CLUSTERS_ROOT`; `./cluster list` reads that tree).

## Leaf filesystem contract

Canonical decision: [ADR 003 — Optional `cluster.yml`](adr/003-optional-cluster-yml.md)
(Phases 0–4 complete).

### Required vs omitted

| Required | Optional / forbidden as SoT |
|----------|-----------------------------|
| `cluster.yaml` (schema v2) | `group_vars/all/cluster.yml` — **omit**; `FAIL [cluster_yml_legacy]` if present |
| `hosts` | path / workspace / `cluster_id` authored in YAML — **forbidden** (inject only) |
| `group_vars/all/` with ≥1 mergeable `*.yml` | monolithic `secrets.yml` — **forbidden** (`FAIL [secrets_legacy_monolith]`) |

| Concern | Where it lives |
|---------|----------------|
| Phases / playbooks / execution | `cluster.yaml` (+ cascade) |
| Shared knobs (env/org) | `default/default` and `<env>/default` `group_vars/all/` (optional; lower priority) |
| DNS identity (`dns_domain_suffix`, `cluster_domain`, …) | leaf `atlas-*.yml` (may inherit suffix from env default if duplicated carefully) |
| Secrets | `atlas-<repo>.secrets.yml` (Vault preferred; leaf secrets win) |
| `provision_stack` + TF maps | leaf `atlas-compute-provision.yml` only |
| Absolute paths / workspace id | clusterctl inject (`controller_extra_vars.yaml`) |

### group_vars cascade

Materialize merges `group_vars/all` from **org → env → leaf** (see [ansible.md](ansible.md)). Policy dirs may omit `group_vars`; the deployable leaf still needs ≥1 mergeable overlay. Put repeated knobs in `<env>/default/group_vars/all/`; keep site identity, maps, and secrets on the leaf.

### Current runtime (Phase 4)

clusterctl **does not require** `group_vars/all/cluster.yml`. Public `_template/*`,
`clusters/default`, and inventory labs **omit** the file. A deployable leaf needs
`cluster.yaml`, `hosts`, and ≥1 mergeable `group_vars/all/*.yml` (normally
`atlas-*.yml`).

If a custom leaf still has `cluster.yml`, `./cluster validate` emits
`FAIL [cluster_yml_legacy]`. Move DNS into `atlas-*.yml`, delete the file, and
update any scripts that `test -f …/cluster.yml`.

### Leaf DNS identity

Declared under `# Leaf DNS identity` in each product `atlas-*.yml` (duplicated per
consumer; see `clusterctl/leaf_dns.py`). Same `dns_domain_suffix` across overlays
in one leaf; stack-specific prefix lives in `cluster_domain`.

| Key | Ownership | How to set |
|-----|-----------|------------|
| `dns_domain_suffix` | shared leaf suffix (e.g. `lab.example.com`) | `./cluster init … --dns-suffix` (errors if no overlay has the key) or edit YAML |
| `cluster_domain` | template/stack prefix + suffix Jinja (e.g. `redis.{{ dns_domain_suffix }}`) | edit `atlas-*.yml` / choose the right `--template` |
| `k8s_cluster_domain` | usually `"{{ cluster_domain }}"` | leave as Jinja; do not invent a second FQDN |

Init never creates `cluster.yml` and never rewrites `cluster_domain` prefixes.

## Tree

```
clusters/
  default/default/          # org policy stub (NOT deployable)
  <env>/default/            # env policy stub (NOT deployable) — often local-only
  <env>/<name>/             # deployable leaf (from init --template or local lab)
    cluster.yaml            # schema v2 (usually self-contained)
    hosts                   # ansible inventory
    group_vars/all/
      atlas-<repo>.yml      # product catalog (copy from sibling) — includes leaf DNS when used
      atlas-<repo>.secrets.yml  # product secrets (Vault-friendly examples OK)
      *.yml / *.yaml        # any extra overlays still merge
  _template/                # public scaffolds for ./cluster init --template
  # Live leaves may live here OR in a private inventory (see local-labs.md)
  ci/  dev/                 # optional in-tree labs (gitignored) — prefer .config/config.yaml inventory
```

### Deployable vs policy

```
  _template/*  --init-->  clusters/<env>/<name>  (deployable leaf)
  default/default        (policy stub, not deployable)
  <env>/default          (policy stub)
  ci/  dev/              (local labs, gitignored)
```

| Kind | Examples | `./cluster list` | `run` / `validate --all` |
|------|----------|------------------|---------------------------|
| Deployable | `prod/k8s`, `demo/redis`, … | normal row | yes |
| Policy / stub | `default/default`, `<env>/default` | `[policy]` | skip (`cluster_policy_skipped`) |
| Template | `_template/*` | not a cluster id | copied via `init` |

Deployable id = `env/name` (e.g. `prod/kafka`). Optional `cluster_id_aliases` in leaf `cluster.yaml` resolve on `use` / `--cluster`.

## Public scaffolds

| Template | Stack | Orchestration docs |
|----------|-------|--------------------|
| `k8s_full` | full k8s (no embedded infra) | [compute-provision.md](stacks/compute-provision.md), [k8s-core.md](stacks/k8s-core.md), [k8s-addons.md](stacks/k8s-addons.md) |
| `infra_edge` | infra platform only | [infra-edge.md](stacks/infra-edge.md), [compute-provision.md](stacks/compute-provision.md) |
| `redis` | Redis Cluster + Predixy + VIP | [redis.md](stacks/redis.md) |
| `postgresql` | etcd + Patroni + LB | [postgresql.md](stacks/postgresql.md) |
| `kafka` | KRaft controllers + brokers | [kafka.md](stacks/kafka.md) |
| `jenkins_agent` | Jenkins agents | [jenkins-agent.md](stacks/jenkins-agent.md) |
| `gitlab_runner` | GitLab runners | [gitlab-runner.md](stacks/gitlab-runner.md) |

Orchestration (phases / tags / vars bridge): docs above. Init index: [`clusters/_template/README.md`](../clusters/_template/README.md).

## Templates (`./cluster init`)

| Template | Command |
|----------|---------|
| minimal | `./cluster init lab/empty --template` |
| full k8s | `./cluster init prod/k8s --template k8s_full` |
| infra | `./cluster init prod/infra --template infra_edge` |
| jenkins | `./cluster init prod/jenkins --template jenkins_agent` |
| gitlab | `./cluster init prod/gitlab --template gitlab_runner` |
| postgresql | `./cluster init prod/pgsql --template postgresql` |
| redis | `./cluster init prod/redis --template redis` |
| kafka | `./cluster init prod/kafka --template kafka` |
| PVE images | `./cluster init lab/pve-templates --template pve_templates` |
| env policy | `./cluster init lab/policy --template default` |

Copy from an existing leaf (if present locally):

```bash
./cluster init lab/copy --from prod/k8s
```

After init:

1. Verify `id` / `display_name` in `cluster.yaml` (init patches them).
2. Edit `hosts`, VIP, versions in `group_vars`.
3. Fill `atlas-<repo>.secrets.yml` (example values in templates; prefer Ansible Vault).
4. `./cluster repos sync && ./cluster validate` (when using `source: git` / lock).

## group_vars merge order

clusterctl discovers **all** `group_vars/all/*.{yml,yaml}` (same set Ansible loads from
inventory), merges them for validate / phase intent / materialized `cluster_playbook_vars.yaml`
(`ansible-playbook -e @`).

```
  non-secrets *.yml (alphabetical)
       -->  *.secrets.yml (alphabetical, force-last)
```

Rules:

- Include every regular `*.yml` / `*.yaml` under `group_vars/all/`.
- Skip `*.example`, hidden files (`.…`), and non-YAML (e.g. `README.md`).
- Sort catalogs by filename (Ansible-style alphabetical order).
- Force secrets overlays last so credentials override catalogs:
  - **canonical:** `atlas-redis.secrets.yml` next to `atlas-redis.yml` (Vault-encrypt in place; not gitignored)
  - **forbidden:** monolithic `secrets.yml` / `secrets.yaml` (not merged; validate ERROR — delete and use product overlays)
- `cluster.yml`: **omit** (ADR 003 Phase 4). Public templates and inventory labs
  do not ship it. If present, `./cluster validate` errors `cluster_yml_legacy`.
  Still merged so values remain visible while deleting; prefer `atlas-*.yml`
  Leaf DNS blocks.

Conventional leaf files (templates; not an exclusive list) — sibling repo basenames:

`atlas-<repo>.yml` + `atlas-<repo>.secrets.yml` for each product
(`compute-provision`, `infra-edge`, `jenkins-agent`, `k8s-addons`, `k8s-core`,
`kafka`, `node-foundation`, `postgresql`, `redis`).
Any extra `*.yml` / `*.yaml` under `group_vars/all/` still merges. Prefer the
conventional repo-named pair above in templates and inventory leaves.

Copy product catalogs from the sibling repo (`atlas-redis/group_vars/all/…`) into
`_template` or your leaf. Prefer Ansible Vault on `*.secrets.yml` (not gitignore).

## Catalog / secrets parity (Phase 5)

CI gate: `tests/test_catalog_secrets_parity_phase5.py` (helpers in
`tests/catalog_parity.py`).

| Check | Rule |
|-------|------|
| Sibling ↔ `_template` | Same operational keys after excluding identity/controller inject and other-stack compute maps |
| Secrets placement | Password/token/TSIG keys live in `atlas-*.secrets.yml`, not in catalogs |
| Inventory labs | Product pairs present; Phase 0/4 must-add keys present; no legacy `secrets.yml` |
| k8s lab thin infra | Thin `atlas-infra-edge` bridge only (not full infra SoT; TSIG in k8s-addons secrets) |

## Operator secrets (Phase 6)

Canonical path: `group_vars/all/atlas-<repo>.secrets.yml` next to each product catalog.
Vault-encrypt in place (file stays trackable — **not** gitignored).

Forbidden: monolithic `group_vars/all/secrets.yml` (not merged; validate ERROR —
delete and split into `atlas-*.secrets.yml`). Public scaffolds no longer ship
`secrets.yml.example`.

Identity DNS (`dns_domain_suffix`, `cluster_domain`, optional `k8s_cluster_domain` /
`dns_server_ip`) is declared in every `atlas-*.yml` overlay that uses it (and the
stack product catalog). See [Leaf DNS identity](#leaf-dns-identity) and
[ADR 003](adr/003-optional-cluster-yml.md). Path/workspace keys are injected by
clusterctl. `provision_stack` lives only in `atlas-compute-provision.yml`. Sibling
standalone catalogs may still declare identity keys for `./run.sh`.

## Inventory groups (validate contract)

| Stack | Groups |
|-------|--------|
| k8s | `k8s_lbs`, `k8s_masters`, `k8s_workers` |
| infra | `infra_platform` |
| postgresql | `pgsql_etcd_cluster`, `pgsql_cluster`, `pgsql_lbs` |
| redis | `redis_cluster_masters`, `redis_cluster_replicas`, `redis_proxies`, `redis_lbs` |
| kafka | `kafka_controllers`, `kafka_brokers` |
| jenkins | `jslave` |

Groups must align with leaf `phases:` intent and `provision_stack` / host layout
(see [adr/005-remove-cluster-stacks.md](adr/005-remove-cluster-stacks.md)).

## Typical operator flow

```bash
./cluster list
./cluster init demo/redis --template redis
./cluster use demo/redis
./cluster repos sync
./cluster validate --strict
./cluster plan -v
# ./cluster run
# ./cluster run --phases redis --tags 204_redis_verify
```

Full k8s:

```bash
./cluster init demo/k8s --template k8s_full
./cluster use demo/k8s
# ./cluster run --phases provision..k8s-addons
# or a range:
# ./cluster run --phases k8s-core..k8s-addons
```

See [clusterctl.md](clusterctl.md), [cluster-config-v2.md](cluster-config-v2.md), [local-labs.md](local-labs.md).
