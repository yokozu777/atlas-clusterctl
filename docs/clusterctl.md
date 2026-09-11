# clusterctl guide

`clusterctl` is the CLI lifecycle tool for Atlas clusters in the `atlas-clusterctl` repository.

```bash
./cluster <command> [options]
# equivalent:
python3 -m clusterctl <command> [options]
```

`./cluster` sets `ATLAS_CLUSTER_ROOT` and runs the module.

Public SoT layout: `clusters/_template/*`. Local org labs / private inventory: [local-labs.md](local-labs.md)
(`.config/config.yaml` or `ATLAS_CLUSTERS_ROOT`).

> **CLI phase window (ADR 008 Phase 5):** `--phases` / `-p` on `plan` / `run`:
> - single phase: `NAME` (no commas)
> - inclusive range: `start..end` (ASCII `..` only — not `…`)
> - names: ASCII `-` only (not en/em dash `–`/`—`)
> - explicit CSV: `a,b,c` (**≥2** names; order follows leaf `phases:`, not CSV —
>   skip-middle; a single name must be `NAME` without commas)
>
> Legacy `plan`/`run` `--from`/`--to` are **removed**
> ([adr/008-phases-cli-selector.md](adr/008-phases-cli-selector.md)).
> (`init --from` / `export_template --from` are unrelated.)
> Cleanup **Variant B** complete (Cleanup Phases 0–3): dual docs anti-regression
> gate purged. Permanent hygiene is argparse + retired plan/run dest-name guards.
>
> **Execute verb unify (ADR 009):** canonical ``./cluster run`` with
> ``--phases`` + ``--tags`` / ``--limit`` / ``-e`` / ``--root-ssh`` / ``--git-ssh``
> (policy ``catalog`` / ``merge_e`` / ``collapse`` —
> [adr/009-unify-run-stage-play.md](adr/009-unify-run-stage-play.md)).
> Deprecated ``stage`` / ``play`` aliases are **removed** (alias-removal Phase 1–5);
> use ``run --phases`` (see mapping in the ADR).

---

## Quick start

### Full k8s (from template)

```bash
./cluster list
./cluster init demo/k8s --template k8s_full --dns-suffix demo.example.com
./cluster use demo/k8s
# fill atlas-<repo>.secrets.yml (prefer Ansible Vault); edit hosts
./cluster validate
./cluster plan -v
./cluster repos sync
# ./cluster run
# ./cluster run --phases provision..k8s-addons
# ./cluster run --phases k8s-addons
# ./cluster run --phases k8s-addons --tags 520_envoy_gateway
```

### Data-plane / agent (from template)

```bash
./cluster init demo/redis --template redis
./cluster use demo/redis
./cluster validate --strict
./cluster plan -v
# ./cluster run
# ./cluster run --phases redis --tags 204_redis_verify
```

Other scaffolds: `--template infra_edge` / `postgresql` / `kafka` / `jenkins_agent` / `gitlab_runner` → `prod/…` or `demo/…`.

`./cluster` and `python3 -m clusterctl.ansible_env` **auto-remove** legacy
repo-root `.ansible` / `.ansible_facts_cache` under `ATLAS_CLUSTER_ROOT` at
startup (runtime belongs under `workspace/<id>/`). Manual cleanup only if purge
cannot delete (permissions):

```bash
rm -rf .ansible .ansible_facts_cache
```

---

## Global flags

Available before or after subcommand:

| Flag | Description |
|------|-------------|
| `--cluster ID` | Cluster ID (`demo/k8s`, `prod/redis`, …) |
| `--executor MODE` | `local` or `docker` |
| `--version` | clusterctl version |

```bash
./cluster --cluster demo/kafka validate
./cluster validate --cluster demo/kafka
./cluster --executor local run --phases init..kafka
```

---

## Cluster selection

Priority:

```
  --cluster (CLI)
         |
         v  (else)
  CLUSTER_ID (env)
         |
         v  (else)
  .cluster-active
         |
         v  (else)
  default
```

| Mechanism | Description |
|----------|----------|
| `./cluster use <id>` | Writes canonical id to `.cluster-active` |
| `CLUSTER_ID` | Override for CI/shell |
| `.cluster-active` | File at repo root |
| `cluster_id_aliases` | Optional aliases in leaf `cluster.yaml` |

```bash
./cluster use demo/k8s
./cluster use prod/redis
```

---

## Commands

## Typical operator flow (visual)

```
  init --template / lab
         |
         v
       use <id>
         |
         v
     repos sync
         |
         v
  validate --strict
         |
         v
      plan -v
         |
         v
   run --phases …
```

### `list`

```bash
./cluster list
./cluster list --json
```

Labels: `← active`, `[policy]` (not deployable). `--json` emits an array of
`{ id, display_name, active, kind, error? }` (`kind`: `deployable` | `policy` | `broken`).

### `use`

```bash
./cluster use demo/pgsql
```

### `validate`

```bash
./cluster validate
./cluster validate --cluster demo/redis --strict
./cluster validate --all --strict
./cluster validate --repo
./cluster validate --json
./cluster validate --skip-docker-smoke
```

| Flag | Meaning |
|------|---------|
| `--repo` | Repo-level checks only |
| `--all` | All deployable + repo |
| `--strict` | Warnings → errors |
| `--skip-docker-smoke` | Skip docker pull / in-container smoke |
| `--json` | JSON report |

Details: [validate.md](validate.md).

### `smoke`

```bash
./cluster smoke --all
./cluster smoke --cluster demo/jenkins
```

Validate + plan smoke per cluster.

### `plan`

```bash
./cluster plan -v
./cluster plan --phases provision..k8s-addons
./cluster plan -p init
./cluster plan --phases provision,k8s-addons
./cluster plan --json
```

### `run`

```bash
./cluster run
./cluster run --phases provision..k8s-addons
./cluster run --phases provision,k8s-addons
./cluster run --phases provision -e provision_mode=destroy
./cluster run --phases redis --tags 204_redis_verify
./cluster run --dry-run
```

| Flag | Meaning |
|------|---------|
| `--phases` / `-p` | `NAME` \| `start..end` \| `a,b,c` (≥2; ADR 008; CSV order = leaf `phases:`) |
| `-e` / `--extra-vars` | ansible extra-vars (repeatable). **Alone:** merge into every catalog invocation (`merge_e`, no collapse). With `--tags`/`--limit`/`--root-ssh`: on collapsed invocation (ADR 009) |
| `--tags` | ansible `--tags` (default `all`); with other selective flags → single-phase **collapse** |
| `--limit` | ansible `--limit`; selective → single-phase collapse. Fallback: env ``LIMIT`` (CLI wins) |
| `--root-ssh` | root SSH extra-vars (init); selective → single-phase collapse |
| `--git-ssh` | git-over-SSH for roles; does **not** collapse |
| `--dry-run` | Plan summary without ansible |

Multi-phase + `--tags` / `--limit` / `--root-ssh` → ERROR (narrow with `--phases NAME`).

### `stages`

```bash
./cluster stages
./cluster stages --json
./cluster stages --baseline    # reference phases helper (fixture / full-k8s baseline)
./cluster stages --baseline --json
```

### `stage` / `play` (removed)

**Removed** (ADR 009 alias-removal Phase 1–5). Use:

```bash
./cluster run --phases provision
./cluster run --phases redis --tags 204_redis_verify
./cluster run --phases provision -e provision_mode=destroy
```

Historical mapping: [ADR 009](adr/009-unify-run-stage-play.md). List helper
``./cluster stages`` is unrelated and remains.

### `init`

```bash
./cluster init prod/k8s --template k8s_full
./cluster init prod/redis --template redis
./cluster init lab/x --from demo/kafka
./cluster init lab/x --template redis --dns-suffix lab.example.com
./cluster init lab/x --template k8s_full --force
```

| Flag | Effect |
|------|--------|
| `--dns-suffix DOMAIN` | rewrite `dns_domain_suffix` in every Leaf DNS `atlas-*.yml` overlay; errors if no overlay can receive it |
| *(no prefix flag)* | `cluster_domain` stack prefixes stay template-owned — pick `--template` (`redis` → `redis.…`) or edit YAML |

See [clusters.md — Leaf DNS identity](clusters.md#leaf-dns-identity).

### `repos` / `playbooks`

```bash
./cluster repos sync
./cluster repos sync --dry-run
./cluster repos sync --repo atlas-kafka
./cluster repos sync --phase redis
./cluster repos status
./cluster repos status --json
./cluster repos show
```

`playbooks` is the same API. See [playbooks.md](playbooks.md).

### `config`

```bash
./cluster config show
./cluster config show k8s-addons
./cluster config show --json
./cluster config effective
./cluster config effective --cluster demo/redis --json
```

Default phase for `config show` is `k8s-addons`.

### `workspace`

```bash
./cluster workspace show
./cluster workspace show --json
./cluster workspace id
./cluster workspace reset          # deletes workspace/<id>/ (with confirm)
./cluster workspace reset --yes
```

See [workspace.md](workspace.md).

---

## Phase aliases (full k8s / `k8s_full`)

| Alias | Ref |
|-------|-----|
| `templates` | `atlas-compute-provision/templates` |
| `provision` | `atlas-compute-provision/provision` |
| `init` | `atlas-node-foundation/init` |
| `k8s-core` | `atlas-k8s-core/cluster` |
| `k8s-addons` | `atlas-k8s-addons/addons` |

Infra platform aliases (`infra_edge` template): `init-infra`, `infra`, `init-infra-post` — see [infra-edge.md](stacks/infra-edge.md).

Stack aliases (in respective `cluster.yaml`): `redis`, `postgresql`, `kafka`, `jenkins-agent`.

Templates / provision: [compute-provision.md](stacks/compute-provision.md).  
Full k8s orchestration: [k8s-core.md](stacks/k8s-core.md), [k8s-addons.md](stacks/k8s-addons.md).  
Infra leaf: [infra-edge.md](stacks/infra-edge.md).  
Jenkins agents: [jenkins-agent.md](stacks/jenkins-agent.md). GitLab runners: [gitlab-runner.md](stacks/gitlab-runner.md). (Jenkinsfile sample: [jenkins.md](jenkins.md).)

---

## Env vars (commonly used)

| Var | Purpose |
|-----|---------|
| `CLUSTER_ID` | Active cluster override |
| `CLUSTER_EXECUTOR` | `local` / `docker` |
| `LIMIT` | Fallback ansible `--limit` for ``run``. Same as CLI ``--limit`` for ADR 009 classify (`collapse` / multi-phase ERROR). CLI ``--limit`` wins when both set |
| `CLUSTER_WORKSPACE_ID` | Workspace dir override |
| `EXECUTION_DOCKER_IMAGE` / `EXECUTION_DOCKER_TAG` | Docker image override |
| `PLAYBOOKS_*_REF` / `_PATH` / `_SOURCE` | Per-repo sync override |
| `ATLAS_CLUSTER_ROOT` | Controller checkout root (usually set by `./cluster`) |
| `ATLAS_CLUSTERS_ROOT` | Live inventory tree (overrides `.config/config.yaml` `clusters.path`) |
| `ATLAS_WORKSPACE_ROOT` | Workspace parent (overrides `.config/config.yaml` `workspace.path`) |
| `ATLAS_CLUSTERCTL_CONFIG` | Alternate path to local config YAML |

Private inventory / workspace wiring: [local-labs.md](local-labs.md), sample [`.config/config.yaml.example`](../.config/config.yaml.example).

---

## Ad-hoc ansible env

```bash
./cluster use demo/k8s
eval "$(python3 -m clusterctl.ansible_env export-workspace)"
eval "$(python3 -m clusterctl.ansible_env export k8s-addons)"
```

See [ansible.md](ansible.md).

---

## Related docs

| Doc | Topic |
|-----|-------|
| [cluster-config-v2.md](cluster-config-v2.md) | schema |
| [clusters.md](clusters.md) | layout / templates |
| [local-labs.md](local-labs.md) | optional private inventory (`.config/config.yaml` / `ATLAS_CLUSTERS_ROOT`) |
| [execution.md](execution.md) | docker/local |
| [validate.md](validate.md) | gates |
| [jenkins.md](jenkins.md) | CI pipeline sample |
