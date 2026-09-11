# Cluster config schema v2

The only clusterctl configuration model: `playbooks` + `phases` (+ optional `execution`).

## Overview

| Key | Purpose |
|-----|---------|
| `playbooks` | Sibling repo catalog (sync, layout) + runnable `entries` |
| `phases` | Ordered list — plan SoT **and** short CLI names (inline aliases) |
| `execution` | `local` / `docker` + image:tag |
| `playbooks_enabled` | Optional kill switch — see callout below |

> **Inline phase aliases (ADR 007):** short CLI names live in `phases:` as
> single-key maps (`- templates: atlas-compute-provision/templates`). Bare
> `repo/entry` strings are allowed (no short name). Top-level `phase_aliases:`
> is **hard-rejected** (`PhaseAliasesRemovedError` / validate
> `phase_aliases_removed`). Public `_template/**`, org baseline, sibling
> `atlas-inventory` labs, and operator docs use the inline form only
> (Phases 1–4). Offline CI + sample plan/`--phases` alias resolve green
> (Phase 5); no live labs
> ([adr/007-phases-inline-aliases.md](adr/007-phases-inline-aliases.md)).

> **`playbooks_enabled` (ADR 006):** omit the key when `playbooks:` is present —
> the runner **infers enabled** from a non-empty catalog
> (`effective_playbooks_enabled`). Explicit `playbooks_enabled: true` is
> redundant. Keep **`playbooks_enabled: false`** to disable sync/run without
> deleting `playbooks:`. Public templates omit redundant `true` (Phase 2+);
> inventory labs likewise (Phase 3+); unittest fixtures follow the same
> omit-when-catalog pattern (Phase 4+)
> ([adr/006-redundant-playbooks-enabled.md](adr/006-redundant-playbooks-enabled.md)).

> **Removed (ADR 005 Phase 4):** YAML `stacks:` is **hard-rejected** at load as
> `StacksRemovedError` (validate code **`stacks_removed`**). Omit unwanted
> phases from `phases:` instead
> ([adr/005-remove-cluster-stacks.md](adr/005-remove-cluster-stacks.md)).
> Product runbooks remain under [stacks/](stacks/).

Engine is generic: repo names and aliases come from cluster YAML, not Python hardcoding.

## Where SoT lives

Deployable clusters are **self-contained**: full `playbooks` / `phases` (with
inline aliases) live in the leaf.

| Path | Role |
|------|------|
| `clusters/_template/k8s_full/` | Public SoT full k8s (**4 phases**, starts at `provision`) for `./cluster init --template k8s_full` |
| `clusters/_template/infra_edge/` | Infra platform only (**4 phases**, starts at `provision`) for `./cluster init --template infra_edge` |
| `clusters/_template/pve_templates/` | Golden PVE factory (**1 phase**: `templates`) — build-once / clone-many |
| `clusters/_template/{redis,postgresql,kafka,jenkins_agent,gitlab_runner}/` | Stack scaffolds (**3 phases**, start at `provision`) |
| `clusters/default/default/cluster.yaml` | Org policy **stub** (not deployable) |
| `clusters/<env>/default/` | Env policy stub (not deployable) |

Public SoT = templates. Optional local org labs (`ci/` / `dev/`): [local-labs.md](local-labs.md).

For tests/helpers, "org baseline" in code may point at a local full-k8s leaf or fixture (`clusterctl/pipeline_fixture.py`), not stub contents.

### Cascade merge (when policy layers are populated)

1. `clusters/default/default/cluster.yaml`
2. `clusters/<env>/default/cluster.yaml`
3. `clusters/<env>/<name>/cluster.yaml`

| Field | Merge |
|-------|--------|
| `playbooks.<repo>` / `entries` | deep merge |
| `phases` | **replace** (child wins; aliases derived from winning list). Omit inherits; explicit `phases: []` replaces with empty (fails later validate — list must be non-empty when runner enabled) |
| `execution` | deep merge |
| `playbooks_enabled` | child explicit wins; omit inherits; infer from merged `playbooks` when still unset |

## Cascade merge (visual)

```
  clusters/default/default/cluster.yaml
              |
              v  (deep merge / phases replace)
  clusters/<env>/default/cluster.yaml
              |
              v
  clusters/<env>/<name>/cluster.yaml   (leaf wins)
              |
              v
       effective cluster config
```

In practice, leaves currently carry full config; stubs can be filled with org-wide defaults later.

## Minimal example

```yaml
schema_version: 2
id: lab/rare
inventory: hosts

playbooks:
  rare-stack:
    source: local
    path: rare-stack
    path_relative_to: sibling
    layout: roles/
    sync: never
    entries:
      install:
        file: playbooks/install.yaml
        invocations:
          - tags: all

phases:
  - install: rare-stack/install

execution:
  mode: docker
  image: yokozu/krang
  tag: "336"
```

(`playbooks_enabled: true` omitted — inferred from `playbooks:`; use
`playbooks_enabled: false` only to disable.)

## Full k8s phases (`_template/k8s_full`)

```
  provision --> init --> k8s-core --> k8s-addons
```

| Alias | Phase ref | Playbook (sibling repo) |
|-------|-----------|-------------------------|
| `provision` | `atlas-compute-provision/provision` | `playbooks/provision_nodes.yaml` |
| `init` | `atlas-node-foundation/init` | `playbooks/init_nodes.yaml` |
| `k8s-core` | `atlas-k8s-core/cluster` | `playbooks/cluster_core.yaml` |
| `k8s-addons` | `atlas-k8s-addons/addons` | `playbooks/cluster_addons.yaml` |

(`templates` / `playbooks/build_templates.yaml` remains a playbooks catalog entry for
emergency rebuilds; default plan starts at `provision`. Factory leaf:
`--template pve_templates`.)

Orchestration: [compute-provision.md](stacks/compute-provision.md), [k8s-core.md](stacks/k8s-core.md), [k8s-addons.md](stacks/k8s-addons.md).

Infra (DNS/CA/registry) is a **separate** template — see [infra-edge.md](stacks/infra-edge.md) (`infra_edge`).

Public full-k8s template: **4 phases** (starts at ``provision``; golden PVE
templates are ``--template pve_templates``), on the order of **95** ansible
invocations (count changes with YAML — do not hardcode in CI forever).

## Data-plane / agent / infra scaffolds

```
  provision --> init --> <stack>          # stack leaves (golden templates built separately)
  templates --> provision --> …           # pve_templates factory only
  provision --> init-infra --> infra --> init-infra-post   # infra_edge
```

| Template | Stack alias | Phase ref |
|----------|-------------|-----------|
| `infra_edge` | `infra` / `init-infra` / `init-infra-post` | `atlas-infra-edge/infra` |
| `redis` | `redis` | `atlas-redis/cluster` |
| `postgresql` | `postgresql` | `atlas-postgresql/cluster` |
| `kafka` | `kafka` | `atlas-kafka/cluster` |
| `jenkins_agent` | `jenkins-agent` | `atlas-jenkins-agent/agent` |
| `gitlab_runner` | `gitlab-runner` | `atlas-gitlab-runner/runner` |

Typical order matches the diagram above: stack leaves start at `provision`
(not `templates`); `infra_edge` is `provision` → `init-infra` → `infra` →
`init-infra-post`; golden PVE factory is `--template pve_templates` only.

Example: `./cluster init demo/redis --template redis`.

## `playbooks.<repo>` fields

| Field | Required | Description |
|-------|----------|-------------|
| `source` | yes | `git` or `local` |
| `url` / `ref` | git | Remote + branch/tag/SHA |
| `path` / `path_relative_to` | local | `sibling`, `repo_root`, or `absolute` |
| `layout` | no | Subdir for `ANSIBLE_ROLES_PATH` (`roles/` or `""`) |
| `shallow` | no | Shallow clone (default `true`) |
| `sync` | no | `always`, `if_missing`, `never` |
| `readiness_markers` | no | Dir names under layout; any present ⇒ ready |
| `entries` | yes* | Runnable units (*if repo is in `phases`) |

### `entries.<id>`

| Field | Description |
|-------|-------------|
| `file` | Playbook path inside repo |
| `invocations` | List of `{tags, limit, when, …}` |
| `ansible` | Optional: strategy, forks, extra env hints |

## Phase aliases (inline in `phases:`)

Short CLI names are **not** a separate YAML key. Put them on the phase list item
(ADR 007). Python does **not** maintain a parallel alias table.

```yaml
phases:
  - provision: atlas-compute-provision/provision
  - k8s-addons: atlas-k8s-addons/addons
  - redis: atlas-redis/cluster
```

Bare refs without a short name are allowed:

```yaml
phases:
  - atlas-compute-provision/templates
  - provision: atlas-compute-provision/provision
```

Top-level `phase_aliases:` is rejected at load. Usage:
`./cluster run --phases provision..k8s-addons`, `./cluster run --phases redis`,
`./cluster run --phases redis --tags …`.

## `execution`

```yaml
execution:
  mode: docker          # local | docker
  image: yokozu/krang
  tag: "336"
```

Default image: [`yokozu/krang:336`](https://hub.docker.com/r/yokozu/krang). Build your own from [infrastructure-automation-toolkit](https://github.com/yokozu777/infrastructure-automation-toolkit).

Details: [execution.md](execution.md).

## Controller contract

Leaf must have:

- `schema_version: 2`
- `id: <env>/<name>` (matches path)
- `inventory` (usually `hosts`)
- when `playbooks:` is present — consistent `playbooks` + `phases` (omit
  redundant `playbooks_enabled: true`; use `false` to disable — ADR 006)


Validate checks phases ↔ playbooks entries, phase intent ↔ inventory groups,
readiness markers after sync. Present `stacks:` → `stacks_removed` at load.

See also: [clusters.md](clusters.md), [playbooks.md](playbooks.md), [validate.md](validate.md), [local-labs.md](local-labs.md).
