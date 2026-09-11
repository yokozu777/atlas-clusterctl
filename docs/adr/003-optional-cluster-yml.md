# ADR 003 — Optional `group_vars/all/cluster.yml`

- **Status:** Accepted (Phase 4 complete — soft-compat follow-up: `FAIL [cluster_yml_legacy]`)
- **Date:** 2026-07-27
- **Deciders:** atlas-clusterctl maintainers
- **Supersedes:** informal rule that `PRIMARY_CLUSTER_VAR = cluster.yml` is mandatory forever
- **Related:** [clusters.md](../clusters.md), per-product `atlas-*.yml` / `*.secrets.yml` layout

## Context

Orchestrated leaves historically required `group_vars/all/cluster.yml` as the
identity SoT (`cluster_id`, workspace Jinja, DNS). That collided with:

1. **Controller inject** — path / workspace / `cluster_id` are already injected by
   clusterctl (`controller_extra_vars.yaml`) and must not be authored in leaf YAML.
2. **Product overlays** — DNS and stack knobs are consumed by `atlas-*.yml`
   (compute, foundation, stack product, k8s-core/addons, …).
3. **Operator UX** — a comment-only stub `cluster.yml` existed only because
   older loaders hard-failed without it.

DNS identity (`dns_domain_suffix`, `cluster_domain`, optional `k8s_cluster_domain` /
`dns_server_ip`) lives in the product overlays that use those keys.
`provision_stack` lives only in `atlas-compute-provision.yml`.

## Decision

### Leaf filesystem contract (current)

A deployable leaf **MUST** have:

| Artifact | Requirement |
|----------|-------------|
| `cluster.yaml` | schema v2 playbooks/phases (or cascade-complete policy) |
| `hosts` | Ansible inventory |
| `group_vars/all/` | ≥ 1 mergeable `*.yml` / `*.yaml` (normally `atlas-*.yml` pairs) |

A deployable leaf **MUST NOT** require:

| Artifact | Notes |
|----------|-------|
| `group_vars/all/cluster.yml` | Omitted from public templates and inventory labs; if present, `./cluster validate` emits `FAIL [cluster_yml_legacy]` |

### Semantics

| Concern | SoT |
|---------|-----|
| Orchestration (phases, playbooks, execution) | `cluster.yaml` (+ cascade) |
| DNS / leaf FQDN identity | `atlas-*.yml` overlays that use the keys (duplicated per consumer file until a later thin-identity track) |
| Secrets | `atlas-<repo>.secrets.yml` (Vault preferred) |
| Provision TF stack selector | `atlas-compute-provision.yml` → `provision_stack` |
| Absolute paths / workspace / `cluster_id` | clusterctl inject only |

### `ClusterContext.cluster_var_file`

| Phase 0 | Phase 1+ (current) |
|---------|-------------------|
| Always `group_vars/all/cluster.yml` (required file) | `Path \| None` — set only if the file exists; callers must not assume identity lives there |

### `./cluster init`

| Phase 0–1 | Phase 2+ (current) |
|-----|--------|
| Patched `dns_domain_suffix` / `cluster_domain` only in `cluster.yml` | Patches **`dns_domain_suffix`** (and legacy `cluster_id` if present) in every overlay with a `# Leaf DNS identity` block — typically `atlas-*.yml`. Does **not** rewrite `cluster_domain` stack prefixes (`redis.` / `kafka.` / …) and does **not** create `cluster.yml` |

## Consequences

### Positive

- One less fake “config” file for operators.
- Identity sits next to the roles that expand it.
- Aligns filesystem layout with Ansible group_vars discovery (any `*.yml` merges).

### Negative / follow-up work

- **Breaking** for anything that assumes `cluster.yml` always exists (scripts, older docs, `ClusterContext.cluster_var_file` type).
- Org baseline / empty stubs without product catalogs need at least one `atlas-*.yml` (or stay non-deployable).
- Future: stop merging `cluster.yml` entirely (still merged if present; validate ERROR).

### Out of scope (later)

- Deduplicating DNS keys into a single overlay (thin identity).
- Moving DNS into `cluster.yaml` + materialize.

## Implementation plan (Phases 0–4 — complete)

| Phase | Work | Done when |
|-------|------|-----------|
| Phase 0 | This ADR + operator contract in `docs/clusters.md` | Accepted; CI asserts ADR presence |
| Phase 1 | Soft-require in loader/context/layout; no hard fail on missing `cluster.yml` | Leaf with only `atlas-*.yml` loads |
| Phase 2 | Init / CLI / export patch overlays, not `cluster.yml` | `init --dns-suffix` updates overlays |
| Phase 3 | Delete stubs from `_template`, `default`, inventory labs | No required stub files |
| Phase 4 | Docs cleanup; then soft-compat follow-up `FAIL [cluster_yml_legacy]` | CHANGELOG + stacks docs + validate gate |

## Current runtime (Phase 4)

clusterctl **does not require** `group_vars/all/cluster.yml`. Public `_template/*`,
`clusters/default`, and inventory labs **omit** the file. A leaf loads with
`cluster.yaml`, `hosts`, and ≥1 mergeable `group_vars/all/*.yml` (typically
`atlas-*.yml`).

`./cluster init --dns-suffix` rewrites `dns_domain_suffix` in matching Leaf DNS
overlays (`clusterctl/leaf_dns.py`); `cluster_domain` stack prefixes are not
rewritten (edit the overlay YAML to change `redis.` / `k8s.` / …).
`python3 -m clusterctl.tools.export_template` (ADR 004) scrubs live suffixes in
overlays to `example.com`, rewrites literal `cluster_domain` FQDNs to
`"<prefix>.{{ dns_domain_suffix }}"`, and **deletes** any copied `cluster.yml`.

If a leaf still ships `group_vars/all/cluster.yml`, `./cluster validate` reports:

```text
FAIL [cluster_yml_legacy] legacy group_vars/all/cluster.yml is not allowed — omit this file
```

**Operator notice:** update external scripts that `test -f …/group_vars/all/cluster.yml`
(or similar). Check for `atlas-*.yml` / `group_vars/all/*.yml` instead.

Soft-compat Phase 4 (2026-07-28): severity escalated WARN → ERROR; file is still
merged if present so operators see the values while fixing, but validate fails.

## Breaking changes checklist

- [x] Missing `group_vars/all/cluster.yml` is no longer an error if other group_vars exist
- [x] `ClusterContext.cluster_var_file` may be `None`
- [x] `primary_cluster_var_file()` deprecated alias of `optional_cluster_var_file`
  (DeprecationWarning — packaging Phase 6)
- [x] `config_dir_is_usable` does not key off `cluster.yml` alone
- [x] `./cluster init` no longer writes/requires `cluster.yml`
- [x] Templates/inventory may omit `cluster.yml`
- [x] External scripts that `test -f …/cluster.yml` must be updated (operator notice + validate `FAIL [cluster_yml_legacy]`)

## Alternatives considered

1. **Keep forever stub** — rejected; perpetual confusion.
2. **Rename to `identity.yml`** — rejected; still a fourth place for DNS vs product overlays.
3. **DNS only in `cluster.yaml`** — deferred; needs materialize redesign.

## References

- `clusterctl/leaf_dns.py` — discover / patch / export scrub + remove
- `clusterctl/tools/export_template.py` — maintainer promote lab → `_template/<name>` (ADR 004)
- `clusterctl/validate.py` — `FAIL [cluster_yml_legacy]`
- `clusterctl/cluster_vars_loader.py` — `PRIMARY_CLUSTER_VAR`, `optional_cluster_var_file` / `primary_cluster_var_file`
- `clusterctl/context.py` — `cluster_var_file`
- `clusterctl/controller_extra_vars.py` — inject contract keys
