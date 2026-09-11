# Отчёт: `clusterctl` (CLI `./cluster`)

> Maintainer note: этот файл лежит в [`notes/`](README.md), не в корне репозитория
> и не в операторских [`docs/`](../docs/). Операторский SoT execute-verb —
> [`docs/clusterctl.md`](../docs/clusterctl.md) + ADR 009.

Источник правды: код `clusterctl/__main__.py` + связанные модули, живой `--help`
пакета **atlas-clusterctl** (версия **0.1.0** на момент отчёта).

Актуализация: remediation **фаз 0–7** + **ADR 009** (`run` = единственный execute
verb; ``stage``/``play`` **removed**; policy `catalog` / `merge_e` / `collapse`).
Сверяйте с `./cluster --help` / `./tests/run_ci.sh` при изменении CLI.

Точки входа:

```bash
./cluster <command> [options]          # wrapper: ставит ATLAS_CLUSTER_ROOT и cd в корень
python3 -m clusterctl <command> […]    # то же без wrapper
```

Назначение: lifecycle-контроллер Atlas-кластеров по **schema v2** —
`playbooks:` (каталог sibling-репозиториев) + `phases:` (порядок плана и inline CLI-алиасы).

---

## 1. Что умеет продукт (функциональные области)

| Область | Команды | Суть |
|---------|---------|------|
| Выбор кластера | `use`, `list` | active id, обзор дерева |
| Scaffold | `init` | создать leaf из `_template/*` или копии другого leaf |
| Проверка | `validate`, `smoke` | конфиг/инвентарь/репо-гейты + plan smoke |
| Планирование | `plan`, `stages` | показать эффективный план фаз / список фаз |
| Исполнение | `run` | ansible по фазам (local или docker) |
| Синхронизация реп | `repos` / `playbooks` | clone/update git/local playbook repos |
| Интроспекция | `config`, `workspace` | effective YAML, ansible env, пути workspace |
| Runtime | `--executor` | override `local` / `docker` |

Типичный поток оператора:

```
init → use → repos sync → validate [--strict] → plan -v → run --phases …
```

Предпочтительный scaffold (публичное дерево):

```
./cluster init demo/k8s --template k8s_full --dns-suffix demo.example.com
```

---

## 2. Глобальные опции

Доступны **до или после** подкоманды (нормализуются в `cli_args.normalize_global_argv`).

| Опция | Значения | Назначение |
|-------|----------|------------|
| `-h` / `--help` | — | справка |
| `--version` | — | версия CLI (`cluster 0.1.0`) |
| `--cluster ID` | `env/name`, alias, `default` | какой leaf; иначе `CLUSTER_ID` → `.cluster-active` → `default` |
| `--executor MODE` | `local` \| `docker` | runtime override поверх `cluster.yaml` `execution.mode` |

Примеры:

```bash
./cluster --cluster demo/k8s validate
./cluster validate --cluster demo/k8s
./cluster --executor local run --phases init..k8s-addons
```

Конфликт двух разных значений одного глобального флага → ошибка.

`cli_args.SUBCOMMANDS` включает `playbooks` / `repos` (SoT; `docker_executor`
реэкспортирует тот же набор).

---

## 3. Выбор активного кластера

Приоритет:

```
--cluster (CLI)
  → CLUSTER_ID (env)
  → .cluster-active (файл в корне checkout)
  → default
```

Опционально в leaf / cascade `cluster.yaml`: `cluster_id_aliases` (короткие имена
для `use` / `--cluster`). Builtin map пуст (soft-compat Phase 4) — alias только
из cascade. YAML-ключ `role_repos:` при load → hard ERROR.

Деплойный id: `env/name` (например `dev/mxhash`, `ci/jenkins`).  
Policy stubs: `default/default`, `<env>/default` — в `list` помечаются `[policy]`,
run/validate для них ограничены.

---

## 4. Команды по одной

### 4.1. `use`

```text
./cluster use [-h] cluster_id
```

| Аргумент | Описание |
|----------|----------|
| `cluster_id` | id кластера (`env/name`, cascade alias или `default`) |

**Делает:** пишет canonical id в `.cluster-active`, печатает путь файла.  
Не загружает полный контекст валидации.

---

### 4.2. `list`

```text
./cluster list [-h]
```

**Делает:** перечисляет кластеры под деревом `clusters/` (с учётом
`ATLAS_CLUSTERS_ROOT` / `.config`). Метки:

- `← active` — совпадает с `.cluster-active`
- `[policy]` — не deployable
- `[config fragment only]` — id есть, но load упал как «нет полного конфига»

---

### 4.3. `init`

```text
./cluster init [-h] [--from FROM] [--template [NAME]] [--display-name NAME]
               [--dns-suffix DOMAIN] [--no-validate] [--force] ID
```

| Аргумент / опция | Описание |
|------------------|----------|
| `ID` | новый id (`env/name`) |
| `--from FROM` | копировать с `clusters/<FROM>/` (default `default`; **игнорируется** при `--template`) |
| `--template [NAME]` | копировать scaffold из `clusters/_template/` (без NAME — корень template; с NAME — `_template/<NAME>/`) |
| `--display-name NAME` | `cluster.yaml` `display_name` (иначе = id) |
| `--dns-suffix DOMAIN` | проставить `dns_domain_suffix` во все Leaf DNS overlays `atlas-*.yml` |
| `--no-validate` | не гонять post-init validate |
| `--force` | заменить существующий `clusters/<id>/` |

Публичные scaffolds: `k8s_full`, `infra_edge`, `redis`, `postgresql`, `kafka`, `jenkins_agent`.

**Делает:** создаёт leaf (cluster.yaml, hosts, group_vars…), правит id/DNS по опциям,
по умолчанию validate, печатает next steps (`use`, secrets).

**Важно (известный баг product-layout):** flat `clusters/default/` в публичном дереве
содержит только `hosts` / `pub_keys` + вложенный `default/default/` (org baseline).
Дефолтный `--from default` копирует этот flat целиком → leaf **без** top-level
`cluster.yaml` и с лишним nested `default/`. Рекомендуемый путь:

```bash
./cluster init demo/k8s --template k8s_full --dns-suffix demo.example.com
# или явно: --from default/default  (fragment) + добор runtime — см. docs/clusters.md
```

`init --from` / `export_template --from` **не** связаны с retired `plan`/`run` `--from`/`--to`
(ADR 008).

---

### 4.4. `validate`

```text
./cluster validate [-h] [--repo] [--all] [--json] [--strict] [--skip-docker-smoke]
```

| Опция | Описание |
|-------|----------|
| `--repo` | только repository-level checks (baseline, layout), без конкретного leaf |
| `--all` | все кластеры под `clusters/` **+** repo |
| `--json` | JSON-отчёт (`severity: "error"|"warning"|"ok"`) |
| `--strict` | warnings → exit 1 |
| `--skip-docker-smoke` | не делать docker pull / in-container smoke |

Поведение:

- без флагов → validate **активного/указанного** `--cluster`
- `--repo` (без `--all` и без `--cluster`) → только repo
- load-ошибки `stacks_removed` / `phase_aliases_removed` уходят в structured report

Текстовый отчёт (`format_report_text`): префиксы **`OK` / `WARN` / `FAIL`**
(для Severity.ERROR → `FAIL [code]`). Summary печатает `error(s)` / `warning(s)`.

Legacy soft-compat (Phase 4):

| Код | Текст | Поведение |
|-----|-------|-----------|
| `secrets_legacy_monolith` | `FAIL […]` | monolithic `secrets.yml` **не** мержится |
| `cluster_yml_legacy` | `FAIL […]` | `group_vars/all/cluster.yml` запрещён; **пока ещё мержится**, если файл есть |
| `cluster_domain_missing` | `FAIL […]` | `k8s_cluster_domain` alone ≠ workspace-id source |

**Exit:** `0` если нет ERROR; при `--strict` ещё и нет WARN.

---

### 4.5. `smoke`

```text
./cluster smoke [-h] [--all] [--json] [--no-repo]
```

| Опция | Описание |
|-------|----------|
| `--all` | все кластеры (также default, если `--cluster` не задан) |
| `--json` | JSON |
| `--no-repo` | пропустить repo-level checks |

**Делает:** validate + построение execution plan smoke на кластер(а).  
Exit `0` только если все отчёты ok и plan smoke ok.

---

### 4.6. `plan`

```text
./cluster plan [-h] [--phases|-p SELECTOR] [--verbose|-v] [--json]
```

| Опция | Описание |
|-------|----------|
| `--phases` / `-p` | `NAME` \| `start..end` \| `a,b,c` (ADR 008; CSV ≥2 имён) |
| `-v` / `--verbose` | перечислить **каждую** ansible-invocation |
| `--json` | JSON плана |

**Делает:** строит эффективный план из cascade `phases:` (+ inventory `when` filters),
**без** запуска ansible. Требует включённый playbooks runner.

Retired: `plan`/`run` `--from`/`--to` **удалены** (ADR 008 Phase 4).

---

### 4.7. `run`

Канонический execute-verb (ADR 009). Overrides через
`apply_run_cli_overrides` (`catalog` / `merge_e` / `collapse`).

```text
./cluster run [-h] [--phases|-p SELECTOR] [--tags TAGS] [--limit LIMIT]
              [-e VAR] [--root-ssh] [--git-ssh] [--dry-run]
```

| Опция | Описание |
|-------|----------|
| `--phases` / `-p` | срез фаз (`NAME` \| `start..end` \| `a,b,c`) |
| `-e` / `--extra-vars` | alone → **`merge_e`** (на каждую catalog invocation, без collapse); с `--tags`/`--limit`/`--root-ssh` — на collapsed invocation |
| `--tags` | ansible `--tags` (default `all`); selective → single-phase **collapse** |
| `--limit` | ansible `--limit`; selective → collapse. Env `LIMIT` — fallback (CLI wins) |
| `--root-ssh` | root SSH extra-vars (init); selective → collapse |
| `--git-ssh` | `GIT_SSH_COMMAND` для git-over-ssh ролей; **не** схлопывает |
| `--dry-run` | печать плана + список invocations **без** исполнения |

Multi-phase + `--tags` / `--limit` / `--root-ssh` → **ERROR** (сузьте `--phases NAME`).

**Делает:** синхронизирует/исполняет invocations выбранного диапазона фаз через
`AnsibleRunner`. При `execution.mode=docker` (и без force-local) может
переделегировать в контейнер. Пишет run-log в `workspace/<id>/logs/`
(или в `OUTPUT_FILE`, если задан).

Пустой plan после filters / selector → **ERROR** (`ensure_run_plan_nonempty`), не silent ok.

---

### 4.8. `stages`

```text
./cluster stages [-h] [--baseline]
```

| Опция | Описание |
|-------|----------|
| `--baseline` | только org baseline / reference phases (игнор active cluster) |

**Делает:** человекочитаемый список эффективных фаз (alias → ref → playbook file,
число invocations). Для non-deployable leaf без `--baseline` автоматически
падает в baseline mode.

---

### 4.9. `stage`

**Removed** (ADR 009 alias-removal). Use `./cluster run --phases PHASE`.

Historical: thin alias of `run` (§4.7) via `_cmd_run_execute` +
`apply_run_cli_overrides`. List helper `./cluster stages` (§4.8) is unrelated.

Operator SoT: [`docs/clusterctl.md`](../docs/clusterctl.md) ·
ADR: [`009-unify-run-stage-play.md`](../docs/adr/009-unify-run-stage-play.md).

---

### 4.10. `play`

**Removed** (ADR 009 alias-removal). Use
`./cluster run --phases NAME [--tags …] [-e …]`.

Same path/policy as `run` (§4.7; `merge_e` / `collapse`).

> `apply_play_cli_overrides` — collapse-on-`-e`, **tests only**
> (`resolve_play_phase_target` / former CLI shape).

Operator SoT: [`docs/clusterctl.md`](../docs/clusterctl.md) ·
ADR: [`009-unify-run-stage-play.md`](../docs/adr/009-unify-run-stage-play.md).

---

### 4.11. `config`

```text
./cluster config {show|effective} …
```

#### `config show [PHASE] [--json]`

| Аргумент | Описание |
|----------|----------|
| `PHASE` | alias или `repo/entry` (default **`k8s-addons`**) |
| `--json` | JSON |

**Делает:** показать resolved ansible environment для фазы (inventory, roles path,
extra vars hints и т.п.).

#### `config effective [--json]`

**Делает:** показать **merged** schema v2 `cluster.yaml` после cascade
(`default/default` → `<env>/default` → leaf). Полезно проверить inline `phases:`
и playbooks после оверлеев.

---

### 4.12. `workspace`

```text
./cluster workspace {show|id|reset} …
```

| Подкоманда | Опции | Делает |
|------------|-------|--------|
| `show` | — | cluster id, workspace id, пути runtime |
| `id` | — | только workspace id (для shell) |
| `reset` | `--yes` / `-y` | удалить дерево `workspace/<id>/` (без `-y` — confirm) |

Workspace id резолвится (priority):

```
CLUSTER_WORKSPACE_ID
  → cluster.yaml workspace_id
  → literal cluster_workspace_id (без Jinja)
  → cluster_domain   (+ dns_domain_suffix)
```

Vars fallback для org baseline: только `clusters/default/default` (flat
`clusters/default/group_vars` **игнорируется**, Phase 4).

`k8s_cluster_domain` **alone** не является источником workspace-id (Phase 4);
ожидайте `cluster_domain` (часто `k8s_cluster_domain: "{{ cluster_domain }}"`).

---

### 4.13. `playbooks` и `repos`

Два имени — **один API** (`repos_cmd` делегирует в `playbooks_cmd`).

```text
./cluster playbooks|repos {sync|status|show} …
```

#### `sync`

| Опция | Описание |
|-------|----------|
| `--dry-run` | показать planned git/local actions без выполнения |
| `--repo NAME` | только один repo из `playbooks:` |
| `--phase-ref REPO/ENTRY` | sync repo, владеющий этой фазой |
| `--phase ALIAS` | то же через inline-alias (или ref) |

**Делает:** clone/update git repos / проверка local paths по `sync:` policy
(`always` / `if_missing` / `never`), readiness markers.

#### `status`

Готовность materialized repos (на диске / markers).

#### `show`

Resolved playbooks config + readiness summary.

Канон Python API: `clusterctl.playbooks_repos` (`ResolvedPlaybookRepo`,
`ctx.playbook_repos`). Модуль `clusterctl.role_repos` — deprecated shim
(DeprecationWarning при import).

---

## 5. Фазы и алиасы (как адресация работает)

SoT — список `phases:` в effective `cluster.yaml` (ADR 007):

```yaml
phases:
  - provision: atlas-compute-provision/provision
  - init: atlas-node-foundation/init
  - k8s-core: atlas-k8s-core/cluster
  - k8s-addons: atlas-k8s-addons/addons
```

| Форма в CLI (`--phases` / `-p`) | Смысл |
|--------------------------------|--------|
| short alias (`provision`) | из derived map inline-алиасов |
| full ref (`atlas-redis/cluster`) | прямой `repo/entry` |
| bare ref без alias в YAML | только по полному `repo/entry` |

Типичные алиасы `k8s_full` (**4** фазы плана): `provision`, `init`, `k8s-core`,
`k8s-addons`. Golden PVE templates — отдельный template `pve_templates` (`templates`).
Другие templates: `infra` / `init-infra` / `init-infra-post`, `redis`, `postgresql`,
`kafka`, `jenkins-agent`.

CLI phase window — **только** `--phases` / `-p` (ADR 008 Phase 5):

| Селектор | Смысл |
|----------|--------|
| `NAME` | одна фаза |
| `start..end` | inclusive window по порядку leaf `phases:` |
| `a,b,c` | explicit set (порядок leaf; mid-skip допускается) |

`execution.mode`:

- `local` — ansible на хосте контроллера
- `docker` — делегирование mutating команд (`run`) в образ
  (`execution.image`/`tag`, override env ниже)

---

## 6. Окружение и локальный конфиг

### 6.1. Часто используемые env

| Переменная | Назначение |
|------------|------------|
| `ATLAS_CLUSTER_ROOT` | корень checkout controller (ставит `./cluster`) |
| `ATLAS_CLUSTERS_ROOT` | дерево live inventory (приоритетнее `.config`) |
| `ATLAS_WORKSPACE_ROOT` | parent для `workspace/` |
| `ATLAS_CLUSTERCTL_CONFIG` | путь к local config YAML вместо `.config/config.yaml` |
| `CLUSTER_ID` | active cluster override |
| `CLUSTER_EXECUTOR` | `local` / `docker` |
| `CLUSTER_EXECUTOR_FORCE_LOCAL` | форс local даже при docker в YAML |
| `CLUSTER_WORKSPACE_ID` | override workspace dir name |
| `EXECUTION_DOCKER_IMAGE` / `EXECUTION_DOCKER_TAG` | docker image override |
| `PLAYBOOKS_*_REF` / `_PATH` / `_SOURCE` | per-repo sync overrides |
| `SSH_KEY` | SSH key для runner (default `~/.ssh/id_rsa`) |
| `LIMIT` | fallback ansible `--limit` для `run` (CLI `--limit` wins; `resolve_run_limit`) |
| `OUTPUT_FILE` | tee run log в указанный файл вместо session dir |
| `SKIP_DOCKER_SMOKE` (и аналоги в validate) | отключение docker smoke в validate path |

### 6.2. `.config/config.yaml` (gitignored)

Резолв inventory/workspace без env:

1. env (`ATLAS_CLUSTERS_ROOT` / `ATLAS_WORKSPACE_ROOT`)
2. поля в `.config/config.yaml`
3. `$ATLAS_CLUSTER_ROOT/clusters` и `…/workspace`

Шаблон: `.config/config.yaml.example`. Подробнее: `docs/local-labs.md`.

---

## 7. Смежные entry points (не `./cluster`, но часть clusterctl)

| Модуль | Назначение |
|--------|------------|
| `python3 -m clusterctl.ansible_env {export\|export-workspace\|show}` | bash `export` для ad-hoc ansible |
| `python3 -m clusterctl.tools.export_template --from ID --template NAME` | maintainer: leaf → `_template/<name>` (ADR 004) |
| `python3 -m clusterctl.tools.ci_preflight [--skip-tests]` | offline CI preflight |
| `python3 -m clusterctl.tools.generate_org_cluster_fixture` | fixture baseline |
| `python3 -m clusterctl.tools.check_no_legacy_repos` | анти-legacy grep gate |
| `python3 -m clusterctl.tools.purge_legacy_materialized_repos` | чистка legacy repos |

Offline CI-обёртка репозитория: `./tests/run_ci.sh`
(packaging → unittest → ci_preflight → template YAML → hygiene → pre-publish audit).

---

## 8. Статус remediation и открытые хвосты

Закрыты **Фаза 6** (packaging / `playbooks_repos`), **Фаза 7** (pre-publish /
working-tree publish readiness) и **ADR 009** (unify `run`/`stage`/`play`) —
см. таблицу ниже. Post-cleanup A1–A5 + B (LIMIT, hints, SoT counts, Jenkins,
`play -e` E2E, notes/helper docstring; alias hard-removal Phases 0–3).

### 8.1. Закрыто (фазы 0–7 + ADR 009)

| Фаза | Итог |
|------|------|
| 0 | Docs quick-start SoT windows |
| 1 | Docs ↔ CLI flag names; Jenkins `PHASES` |
| 2 | `play --phase` / `--git-ssh` / empty `run` / `SUBCOMMANDS` |
| 3 | ADR 008 Phase 5 (`run_ci` + gate) |
| 4 | Soft-compat: secrets / `cluster.yml` FAIL / aliases / flat default / `k8s_cluster_domain` |
| 5 | Канон `playbooks_repos` / `ctx.playbook_repos`; shim `role_repos` |
| 6 | Packaging: нет placeholder `[project.urls]`; `[dev]=[]`; deprecate aliases |
| 7 | Working-tree publish readiness (`docs/pre-publish.md` + gate) |
| ADR 009 | `run` sole execute; ``stage``/``play`` **removed**; `catalog`/`merge_e`/`collapse` |

`playbooks` ≡ `repos` — намеренный dual UX.

### 8.2. Известные открытые проблемы (не блокируют daily use)

| # | Тип | Суть |
|---|-----|------|
| 1 | **Bug** | `init --from default` на product layout (см. §4.3) |
| 2 | Soft-compat | `cluster.yml` → `FAIL`, но **ещё мержится** (ADR 003 Future: stop-merge) |
| 3 | UX | cascade `cluster_id_aliases` логируются как «deprecated», хотя это канон |
| 4 | Soft-compat | shim `role_repos.py` + property `ctx.role_repos` / `cfg.role_repos` |
| 5 | Operator | credential rotation + history rewrite / orphan перед public remote; audit WARN `Welcomeback` в history |
| 6 | Operator | `[project.urls]` — заполнить при известном public remote |

---

## 9. Карта подсистем кода (для ориентира)

| Пакет/модуль | Роль |
|--------------|------|
| `__main__.py` | argparse + dispatch |
| `cli_args.py` / `phase_selector.py` | global argv, `--phases` |
| `run_overrides.py` | ADR 009 `classify` / `apply_run_cli_overrides` / `resolve_run_limit` |
| `phase_plan.py` | plan resolve; historical `apply_play_cli_overrides` (tests only) |
| `context.py` | ClusterContext (`playbook_repos`, paths, executor) |
| `playbooks_config.py` | schema v2 parse/merge/dump (`phases` inline aliases) |
| `playbooks_repos.py` | resolved playbook-repos view |
| `playbooks_paths.py` | layout / `workspace/.../repos` |
| `role_repos.py` | deprecated re-export shim (Фаза 5) |
| `phase_runner.py` / `ansible_runner.py` | исполнение |
| `playbooks_sync.py` / `playbooks_cmd.py` | sync/status/show |
| `validate.py` / `smoke.py` | гейты (`FAIL`/`WARN`/`OK`) |
| `cluster_init.py` | scaffolds |
| `cluster_vars_loader.py` / `workspace_id.py` | group_vars merge + workspace id |
| `docker_executor.py` / `execution.py` | local vs docker |
| `user_config.py` / `paths.py` / `workspace_*` | roots и workspace |
| `pyproject.toml` | install metadata (`pip install -e .` / `.[dev]`) |

---

## 10. Краткая шпаргалка

```bash
./cluster list
./cluster init demo/k8s --template k8s_full --dns-suffix demo.example.com
./cluster use demo/k8s
./cluster repos sync
./cluster validate --strict
./cluster plan -v
./cluster plan --phases provision..k8s-addons --json
./cluster run --dry-run
./cluster run --phases init..k8s-addons
./cluster run --phases provision -e provision_mode=destroy
./cluster run --phases k8s-addons --tags 41_envoy_gateway
./cluster run --phases k8s-addons --git-ssh
./cluster config effective
./cluster workspace show
./cluster smoke --all --no-repo
./tests/run_ci.sh
```

---

*Сгенерировано по коду atlas-clusterctl (post remediation 0–7 + ADR 009). При изменении CLI
сверяйте `./cluster --help`, `clusterctl/__main__.py` и `docs/clusterctl.md`.*
