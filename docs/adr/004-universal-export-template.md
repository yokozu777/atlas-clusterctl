# ADR 004 — Universal `export_template`

- **Status:** Accepted (Phase 4 complete — shim deleted; grep-gate green)
- **Date:** 2026-07-28
- **Deciders:** atlas-clusterctl maintainers
- **Supersedes:** informal k8s-only exporter hardcoding `dev/mxhash` → `_template/k8s_full`
  (module name retired; see CHANGELOG history)
- **Related:** [local-labs.md](../local-labs.md), [clusters/_template/README.md](../../clusters/_template/README.md), ADR 003 Leaf DNS scrub

## Context

clusterctl is a **universal** orchestrator. Public scaffolds live under
`clusters/_template/<name>/` and are consumed by:

```bash
./cluster init <env>/<name> --template <name>
```

A separate **maintainer** helper historically regenerated only the full-k8s
scaffold from one private lab (`dev/mxhash` → `_template/k8s_full`). That path
was not universal: other stacks (`redis`, `kafka`, `postgresql`, `infra_edge`,
`jenkins_agent`) had no exporter. Docs already prefer editing `_template/*`
directly; export is an optional promote path.

## Decision

### Audience

| Audience | Tool | Direction |
|----------|------|-----------|
| Operators | `./cluster init --template <name>` | `_template/<name>` → deployable leaf |
| Maintainers | `python3 -m clusterctl.tools.export_template` | deployable/lab leaf → `_template/<name>` |

`export_template` is **maintainer-only**. It must not become a required step for
`./cluster run` / validate / publish CI.

### CLI

```bash
python3 -m clusterctl.tools.export_template \
  --from <env>/<name> \
  --template <name> \
  [--source-root DIR] [--target-root DIR]
```

| Flag | Meaning |
|------|---------|
| `--from` | Source cluster id under inventory/product `clusters/` (e.g. `ci/redis`, `dev/k8s`) |
| `--template` | Destination scaffold name under `clusters/_template/<name>/` |
| `--source-root` | Optional override for inventory `clusters/` |
| `--target-root` | Optional override for product `clusters/` (receives `_template/`) |

Use the same path for both `--source-root` and `--target-root` when promoting
inside a single tree. There is no `--clusters-root` alias (removed in Phase 4).

### Copy + scrub contract (same for every template)

1. Require source `cluster.yaml`.
2. Copy the **full leaf tree** (not only `hosts` / `group_vars` / `pub_keys`).
   Keep an existing non-empty public `README.md`. Optional `--flatten-cascade`
   merges org→env→leaf `group_vars/all` by top-level YAML blocks (comments travel
   with the winning block). Public stack scaffolds omit flatten: env knobs stay
   on `_template/default`, leaves stay thin like `clusters/dev/*`.
3. Write `cluster.yaml` as source text plus a header (`id: ""`, `display_name: null`,
   drop `deployable`; playbook `url:` → `git@github.com:yokozu777/<repo>.git`;
   neutralize execution image). Parent
   `_template/` (nameless `--template`) is out of scope for export.
4. Leaf DNS scrub via `scrub_leaf_dns_suffix_for_public_template`:
   - `dns_domain_suffix` → `example.com`
   - literal `cluster_domain` FQDNs → `"<prefix>.{{ dns_domain_suffix }}"`
5. Secrets scrub via `scrub_secrets_overlays_for_public_template`:
   - keep keys / structure in `*.secrets.yml` and legacy `secrets.yml`
   - replace every leaf scalar value with `""` (Ansible Vault payloads → empty stub)
6. Delete legacy `group_vars/all/cluster.yml` when present.
7. Org FQDN / leftover lab-token scrub (`example.com`); do not overwrite a
   non-empty public README.

Manual scrub of live hostnames / images remains an operator checklist item
([local-labs.md](../local-labs.md)).

### Known public templates (inventory)

| `--template` | Typical `--from` (example lab) | Notes |
|--------------|--------------------------------|-------|
| `k8s_full` | `dev/k8s` | full k8s without embedded infra |
| `infra_edge` | `dev/infra` | infra platform leaf |
| `jenkins_agent` | `dev/jenkins` | Jenkins agents |
| `gitlab_runner` | `dev/gitlab` | GitLab runners |
| `postgresql` | `dev/postgresql` | PostgreSQL HA |
| `redis` | `dev/redis` | Redis Cluster HA |
| `kafka` | `dev/kafka` | Kafka KRaft HA |
| `pve_templates` | `dev/pve-templates` | golden PVE templates (build-only) |
| `default` | `dev/default` | env-policy overlay (not a stack) |

Empty parent `_template/` (minimal scaffold for `--template` with no name) is
**out of scope** for export (not a named stack scaffold). Named `_template/default`
is the env-policy fragment, distinct from `clusters/default/default/` (org baseline).

There is **no** auto-mapping `ci/redis` → `redis`: both `--from` and `--template`
are always explicit.

### Current runtime (Phase 4)

- Maintainer path: `python3 -m clusterctl.tools.export_template --from <id> --template <name>`
- Coverage: `tests/test_export_template.py` (all known stacks + scrub + CLI)
- Docs / inventory SoT recommend **only** `export_template`
- Secrets overlays copied with keys preserved and values emptied
- Legacy k8s-only module and `--clusters-root` alias: **deleted**
- Operators unchanged: edit `_template/*` or `./cluster init --template …`

### Legacy hardcodes removed

| Hardcode (historical) | Resolution |
|-----------------------|------------|
| Sole source `dev/mxhash` | `--from` |
| Sole target `k8s_full` | `--template` |
| Lab-specific README rewrites | never carried into `export_template` |
| Docs / inventory naming only the old module | Phase 3 SoT → `export_template` |
| Shim module + `--clusters-root` | Phase 4 delete |

## Consequences

### Positive

- One maintainer tool for every stack template.
- Aligns with universal clusterctl (no k8s-only backdoor).
- Makes inventory↔product promote path explicit and testable.

### Negative / follow-up

- Bookmarks to the retired k8s-only module break (use `export_template`).
- DNS scrub only — hosts/images still need human review before commit.

### Out of scope (later)

- `./cluster export` operator subcommand.
- Full hostname/image/password scrub automation.
- Inferring `--template` from `--from`.

## Implementation plan (Phases 0–4)

| Phase | Work | Done when |
|-------|------|-----------|
| Phase 0 | This ADR + known-template inventory + gate | Contract accepted; no behavior change |
| Phase 1 | Implement `export_template`; old module = thin shim | `--from` + `--template` work; shim calls universal |
| Phase 2 | Tests for multi-stack export + scrub | Unit/gates green |
| Phase 3 | Docs / inventory / CHANGELOG point at new tool | No SoT docs recommend old module |
| Phase 4 | Delete shim + legacy flags; grep-gate | Retired name only in CHANGELOG (+ ADR history / phase gates) |

## Breaking changes checklist

- [x] `python3 -m clusterctl.tools.export_template --from … --template …` exists
- [x] Old k8s-only exporter removed (shim deleted)
- [x] Docs/local-labs + inventory READMEs updated
- [x] Tests no longer import the retired module as SoT API
- [x] Public CI does not require labs to run export
- [x] `--clusters-root` alias removed

## References

- `clusterctl/tools/export_template.py` — universal maintainer export
- `clusterctl/leaf_dns.py` — `scrub_leaf_dns_suffix_for_public_template`, `remove_legacy_cluster_yml`
- `clusters/_template/*/cluster.yaml` — public scaffolds
- `CHANGELOG.md` — historical mentions of the retired module name
