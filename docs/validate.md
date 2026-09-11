# Validate and smoke

Pre-flight checks before `run`.

## Commands

```bash
./cluster validate
./cluster validate --cluster demo/redis --strict
./cluster validate --all --strict
./cluster validate --repo
./cluster validate --json
./cluster validate --skip-docker-smoke

./cluster smoke --all
./cluster smoke --cluster demo/jenkins --json
```

A leaf is required first (`./cluster init … --template …` or a local lab — [local-labs.md](local-labs.md)).

Exit non-zero on ERROR (and on WARNING when `--strict`).

## What is checked

```
  ./cluster validate
         |
         +-- repo-level checks (--repo / --all)
         |
         +-- per deployable cluster
         |      +-- load cluster.yaml (stacks: → stacks_removed)
         |      +-- playbooks <-> phases + readiness
         |      +-- phases intent <-> inventory groups
         |      +-- execution image/tag (docker)
         |
         v
  report: ERROR / WARNING / OK
```

### Repo-level (`--repo` or part of `--all`)

| Check | Severity |
|-------|----------|
| Schema v2 layout / legacy artifacts absent | ERROR |
| Reference / fixture playbooks ↔ phases alignment | ERROR |
| No playbook clones in clusterctl root | ERROR |
| Policy dirs not treated as deployable | OK skip |

### Per deployable cluster

| Check | Severity |
|-------|----------|
| `cluster.yaml` schema v2 load | ERROR |
| Forbidden key `stacks:` (`stacks_removed`) | ERROR |
| `playbooks` ↔ `phases` resolve | ERROR |
| Inline phase alias → phase ref in `phases:` | ERROR |
| Top-level `phase_aliases:` (`phase_aliases_removed` — ADR 007) | ERROR |
| Inventory groups ↔ phase intent (`phases:`) | ERROR / WARNING |
| postgresql / redis / kafka / k8s / infra group contracts | ERROR / WARNING |
| Playbook repo readiness markers (after sync) | ERROR |
| `playbooks.lock` drift | WARNING (`--strict` → ERROR) |
| Legacy `group_vars/all/cluster.yml` present | ERROR (`cluster_yml_legacy` — ADR 003; text: `FAIL […]`) |
| Legacy monolithic `secrets.yml` present | ERROR (`secrets_legacy_monolith`; text: `FAIL […]`) |
| `k8s_cluster_domain` without `cluster_domain` | ERROR (`cluster_domain_missing`) |
| Docker executor config (image/tag) | ERROR |
| Optional in-container smoke (`run --dry-run`) | ERROR |

Data-plane / agent / infra / provision details: [compute-provision.md](stacks/compute-provision.md), [redis.md](stacks/redis.md), [postgresql.md](stacks/postgresql.md), [kafka.md](stacks/kafka.md), [jenkins-agent.md](stacks/jenkins-agent.md), [gitlab-runner.md](stacks/gitlab-runner.md), [infra-edge.md](stacks/infra-edge.md).

Policy stubs (`default/default`, `*/default`) in `--all` yield `OK: cluster_policy_skipped`.

## Phase intent ↔ inventory

| Phase intent | Expect groups |
|--------------|---------------|
| k8s | `k8s_lbs`, `k8s_masters`, `k8s_workers` |
| infra | `infra_platform` |
| postgresql | `pgsql_etcd_cluster`, `pgsql_cluster`, `pgsql_lbs` |
| redis | masters/replicas/proxies/`redis_lbs` |
| kafka | `kafka_controllers`, `kafka_brokers` |

Codes: `phase_intent_*_no_inventory` (ERROR) /
`inventory_*_phases_omitted` (WARNING).

Mismatch → ERROR/WARNING with hint (add groups or edit `phases:`).

Present `stacks:` key → load fails with **`stacks_removed`** (ADR 005); omit the
key and keep plan SoT in `phases:`.

## Smoke

`./cluster smoke` = validate + execution plan build (no full deploy). In Jenkins, usually before `run` (`RUN_SMOKE=true`).

```
  smoke = validate --> build execution plan  (no full deploy)
```

## Offline CI gate

Public gate (as in GitHub Actions); labs not required:

```bash
./tests/run_ci.sh
```

```
  ./tests/run_ci.sh
       |
       +--> packaging smoke
       +--> unittest discover
       +--> ci_preflight --skip-tests
       +--> public template YAML parse
       +--> publish hygiene + pre-publish audit
```

Inside: packaging smoke → `unittest discover` → `ci_preflight --skip-tests` →
parse YAML under `clusters/_template` / `clusters/default` → `tests/check_publish_hygiene.sh` →
`tests/check_pre_publish_audit.py`.

Before a public remote — checklist [pre-publish.md](pre-publish.md).

Preflight only (legacy scans + org/public baseline fixture + `validate --repo`):

```bash
python3 -m clusterctl.tools.ci_preflight
# faster locally:
python3 -m clusterctl.tools.ci_preflight --skip-tests
```

No hardware / no live PVE / no docker against org registry.

## Typical fixes

| Symptom | Action |
|---------|--------|
| Root `.ansible` exists | CLI auto-purges at startup (`./cluster`, `ansible_env`); if purge fails (permissions), `rm -rf .ansible .ansible_facts_cache` or fix ownership |
| Unknown phase alias | Check inline aliases in leaf `phases:` (ADR 007) |
| Phase intent / inventory mismatch | Fix `hosts` or leaf `phases:` / group_vars |

| Repo not ready | `./cluster repos sync` or fix `source: local` path |
| Docker image missing | Set `execution.image` + `tag` |

See [cluster-config-v2.md](cluster-config-v2.md), [jenkins.md](jenkins.md).
