# Changelog

All notable changes to `atlas-clusterctl` / `clusterctl` are documented here.

## [Unreleased] — publish readiness

### Changed (docker executor — host bind source)

- ``docker run -v`` left-hand side is the daemon host path (``docker inspect`` of
  the current container, or ``ATLAS_*_ROOT_HOST``), while the container path
  (and ``ATLAS_*_ROOT`` inside krang) stays POSIX. Enables atlas-ui worker on
  Docker Desktop where in-container paths are ``/atlas/...``. Native 1:1
  ``path:path`` mounts are unchanged when those env vars / inspect mounts are
  absent.

### Changed (public `_template` refresh from inventory `dev/`)

- Regenerated stack scaffolds from `atlas-inventory/clusters/dev/*` via
  thin `export_template` (no `--flatten-cascade`): `_template/default` holds
  env-policy compute/node-foundation knobs; leaves stay thin like `clusters/dev/*`.
- `./cluster init <env>/<name>` copies `_template/default` to
  `clusters/<env>/default/` when that env-policy directory is missing.
- `export_template` copies the full leaf tree, preserves YAML comments
  (block merge / line scrub, no `ruamel.yaml`), and allows `--from <env>/default`.
- Public `_template/*/cluster.yaml` playbook `url:` values point at GitHub
  role repos (`git@github.com:yokozu777/atlas-*.git`).
- Public `_template` scaffolds use `execution.mode: docker` and
  `execution.tag: latest` (`yokozu/krang`).

### Changed (Jenkins seed — AGENT choice from seed)

- Deploy job ``AGENT`` is a plain ``choiceParam`` filled at seed time from
  inventory ``hostname:`` under jenkins leaves (and ``jslave*`` / ``*.jenkins.*``
  elsewhere), merged with controller computers when readable. Avoids empty
  Active Choices / Pipeline sandbox blocking ``Jenkins.get()``. Re-run seed
  after agents or inventory change. Artifact: ``agent-choices.txt``.

### Fixed (Jenkins deploy — envParam sandbox)

- ``envParam`` no longer calls ``Class.isArray()`` (Script Approval rejects
  ``TypeDescriptor$OfField.isArray`` on modern JDKs). Use ``instanceof Object[]``
  instead; Active Choices multi remains ``instanceof Collection``.

### Changed (Jenkins seed — LIMIT hierarchical UI)

- Seed ``LIMIT`` checkboxes use hierarchical Active Choices value→label maps
  (group then nested hosts; optional ``(hostname: dns)`` in labels). Helper
  ``list_cluster_limits --ui``; seed artifact stores ordered ``[{value,label},…]``
  so JsonSlurper keeps order. Submitted ``--limit`` values remain group/host
  **keys**. ADR 011 / contract / operator docs updated.
- Fixes: UI keeps ``all.hosts`` orphans (parity with flat catalog); group label
  wins on host-key collisions; Groovy ``escapeSq`` also escapes newlines in
  embedded labels.

### Added (Jenkins seed — LIMIT follow-up Phase 5)

- Acceptance for ``LIMIT`` cascade: offline gate proves fixture map + add-leaf
  artifact + empty omit ``--limit`` + Active Choices wiring; live org checklist
  in ``docs/jenkins-seed.md``. Gate:
  ``tests/test_jenkins_seed_limits_param_phase5.py``.

### Added (Jenkins seed — LIMIT follow-up Phase 4)

- Operator docs polish for ``LIMIT`` cascade: ``docs/jenkins.md`` (re-seed on
  ``hosts``/groups, host-key / empty-UI / advanced-pattern notes, Script Approval
  wording) + seed README troubleshooting (IP keys, empty map, cascade stale).
  Contract operator-notes table. Gate:
  ``tests/test_jenkins_seed_limits_param_phase4.py``.

### Added (Jenkins seed — LIMIT follow-up Phase 3)

- Job DSL ``activeChoiceReactiveParam('LIMIT')`` with ``choiceType('CHECKBOX')``
  and ``referencedParameter('CLUSTER_ID')``; seed-time ``switch`` embed from
  ``CLUSTER_LIMITS_JSON`` (no form-render ``JsonSlurper``). Empty selection omits
  ``--limit``; multi → CSV via existing ``envParam``. Gate:
  ``tests/test_jenkins_seed_limits_param_phase3.py``.

### Added (Jenkins seed — LIMIT follow-up Phase 2)

- Seed stage **List cluster limits map**: writes / archives
  ``examples/internal/seed/cluster-limits.json`` via
  ``list_cluster_limits --all --allow-empty``; warns for deployable ids missing
  from the map; passes ``CLUSTER_LIMITS_JSON`` into Job DSL (seed-time ``switch``
  preview; ``LIMIT`` stays ``stringParam`` until Phase 3). Gate:
  ``tests/test_jenkins_seed_limits_param_phase2.py``.

### Added (Jenkins seed — LIMIT follow-up Phase 1)

- Helper ``clusterctl.tools.list_cluster_limits``:
  ``collect_limits_for_cluster`` / ``collect_limits_parts_for_cluster`` /
  ``collect_limits_map`` (YAML inventory → groups then host keys; ``--all`` /
  ``--allow-empty`` / ``--structured``). Fixture leaves gain YAML ``hosts``;
  ``ci/hosts_only`` INI stays omitted from the map. Gates:
  ``tests/test_list_cluster_limits.py``,
  ``tests/test_jenkins_seed_limits_param_phase1.py``.

### Added (Jenkins seed — LIMIT follow-up Phase 0)

- Contract lock for deploy ``LIMIT`` cascade off ``CLUSTER_ID``:
  [ADR 011](docs/adr/011-jenkins-limits-active-choices.md) +
  ``docs/jenkins-seed.md`` ``LIMIT`` follow-up. Empty ``LIMIT`` omits
  ``--limit``; target UI = Active Choices groups+hosts (host-key SoT); UI still
  ``stringParam`` until Phase 3. Gate:
  ``tests/test_jenkins_seed_limits_param_phase0.py``.

### Fixed (Jenkins seed — PHASES path C / ADR 010)

- Job DSL ``choiceType('CHECKBOX')`` (not ``PT_CHECKBOX``) — controller Job DSL
  enum is ``SINGLE_SELECT|MULTI_SELECT|CHECKBOX|RADIO``.

### Added (Jenkins seed — PHASES path C / ADR 010)

- Unlock Active Choices cascade for deploy ``PHASES``: seed embeds
  ``CLUSTER_PHASES_JSON`` into ``activeChoiceReactiveParam`` checkboxes keyed off
  ``CLUSTER_ID`` ([ADR 010](docs/adr/010-jenkins-phases-active-choices.md)).
  Empty selection remains plan SoT. Deploy ``envParam`` joins multi-select to CSV.
  Plugin ``uno-choice`` required. Gate:
  ``tests/test_jenkins_seed_phases_param_phase4.py`` (cascade delivered).

### Fixed (Jenkins seed — PHASES follow-up remediation Phase E)

- CLI: ``--allow-empty`` without ``--all`` → ``error: --allow-empty requires --all``
  (exit 2).
- Docs: distinct banners ``CLUSTER_ID Phase 0–5`` vs ``PHASES follow-up Phase 0–5``;
  stable HTML anchor ``phase-5-acceptance-phases-follow-up``; seed
  ``allowEmptyArchive`` comment.

### Fixed (Jenkins seed — PHASES follow-up remediation Phase D)

- Docs lock: seed ``cluster-phases.json`` is **inventory ``clusters/`` only** (no
  ``--product-clusters-root`` / no ``PRODUCT_CLUSTERS_ROOT`` seed param). Helper
  flag remains for offline use. Artifacts path + map≠post-``repos sync`` plan
  spelled out for operators.

### Fixed (Jenkins seed — PHASES follow-up remediation Phase C)

- Seed warns (non-fatal) when deployable ids are missing from
  ``cluster-phases.json`` (``ids_missing_from_phases_map``).
- ``list_cluster_phases`` CLI prints ``error: …`` without traceback on unexpected
  load/YAML failures (exit 2).

### Fixed (Jenkins seed — PHASES follow-up remediation Phase B)

- Expectation lock: PHASES follow-up ``Phase 0–5 done`` does **not** mean UI
  fills ``PHASES`` from ``CLUSTER_ID`` (path C still deferred). Docs / seed
  README / DSL point operators at seed job Artifacts for ``cluster-phases.json``.

### Fixed (Jenkins seed — PHASES follow-up remediation Phase A)

- Semantics: seed ``cluster-phases.json`` / ``list_cluster_phases`` = YAML
  ``phases:`` only (no ``when:``). Deploy empty ``PHASES`` = plan SoT without
  ``--phases`` (may differ from the map). Live checklist no longer requires
  map ≡ ``./cluster plan``. Docs + helper CLI wording aligned.

### Added (Jenkins seed — PHASES follow-up Phase 5)

- Acceptance: offline gate proves fixture/seed ``cluster-phases.json`` map matches
  leaf catalogs; deploy empty ``PHASES`` omits ``--phases``; live org checklist
  in ``docs/jenkins-seed.md``. Gate:
  ``tests/test_jenkins_seed_phases_param_phase5.py``.

### Changed (Jenkins seed — PHASES follow-up Phase 4)

- Path C (Active Choices / reactive ``PHASES``) formally **deferred and locked**
  for this follow-up — no cascade plugin in samples; ``PHASES`` stays
  ``stringParam``. Unlock requires a later ADR. Gate:
  ``tests/test_jenkins_seed_phases_param_phase4.py``.

### Added (Jenkins seed — PHASES follow-up Phase 3)

- Seed Pipeline stage **List cluster phases map**: writes / archives
  ``examples/internal/seed/cluster-phases.json`` via
  ``list_cluster_phases --all --allow-empty`` (reference-only; not UI cascade).
  Empty map → ``{}`` without failing Job DSL. Gate:
  ``tests/test_jenkins_seed_phases_param_phase3.py``.

### Added (Jenkins seed — PHASES follow-up Phase 2)

- Shared helper ``clusterctl.tools.list_cluster_phases``:
  ``collect_phases_for_cluster`` / ``collect_phases_map`` (YAML catalog → short
  ``PHASES`` names; ``--refs`` / ``--all`` CLI). Fixture leaves gain inline
  ``phases:``; ``hosts_only`` stays deployable without phases. Gate:
  ``tests/test_jenkins_seed_phases_param_phase2.py`` (+
  ``tests/test_list_cluster_phases.py``).

### Changed (Jenkins seed — PHASES follow-up Phase 1)

- Path A: Job DSL ``PHASES`` description + operator docs
  (``jenkins.md`` Stages, internal/seed READMEs) spell out **empty = all leaf
  phases**; deploy Plan stage comment points at the contract. Gate:
  ``tests/test_jenkins_seed_phases_param_phase1.py``.

### Added (Jenkins seed — PHASES follow-up Phase 0)

- Contract lock in ``docs/jenkins-seed.md``: empty deploy ``PHASES`` ⇒ full leaf
  catalog; no Job DSL / Active Choices cascade off ``CLUSTER_ID``; ``TAGS``/``LIMIT``
  unchanged; seed phases map (path B) deferred to later phases. Gate:
  ``tests/test_jenkins_seed_phases_param_phase0.py``.

### Fixed (Jenkins seed — follow-up Phase C)

- Hygiene: seed/DSL comments say Phase 0–5 + UI SoT; sample git defaults unified
  to ``ssh://git@…``; ``*_GIT_REF`` documented as branch names (not SHA);
  Phase 5 acceptance table — Offline **done** / Live = org checklist. Gate:
  ``tests/test_jenkins_seed_followup_c.py``.
- Job DSL: rename local ``scriptPath`` → ``jfScript`` (variable shadowed Job DSL
  method ``scriptPath(…)`` → ``String.call()`` on controller).

### Fixed (Jenkins seed — follow-up Phase B)

- Deploy samples: ``envParam`` so missing string params never become the literal
  ``"null"`` in ``environment {}``; Prepare ``requireSeedManagedParams`` fails if
  ``CLUSTER_ID`` or seed booleans are absent; boolean ``when`` uses ``== true`` /
  ``!= true``. Job DSL seeds ``EXECUTION_DOCKER_TAG`` only for Docker
  ``Jenkinsfile`` (omitted for ``.local``). Docs: choice = deployable layout, not
  validate/smoke guarantee. Gate: ``tests/test_jenkins_seed_followup_b.py``.

### Fixed (Jenkins seed — follow-up Phase A)

- Seed / deploy inventory checkout: if ``INVENTORY_DIR`` already has ``.git`` but
  ``origin`` ≠ ``INVENTORY_GIT_URL``, run ``git remote set-url`` before fetch.
- Job DSL deploy SCM: ``lightweight(false)`` with ``wipeOutWorkspace`` (avoid
  lightweight+wipe surprises). Docs: seed side effects (each seed Build rewrites
  deploy params + SCM). Gate: ``tests/test_jenkins_seed_followup_a.py``.

### Changed (Jenkins seed — Phase 5)

- Acceptance closed: offline chain proof (add leaf → seed id list → DSL
  ``choice CLUSTER_ID`` contract → deploy binds ``params.CLUSTER_ID``) in
  ``tests/test_jenkins_seed_phase5.py``; live controller checklist in
  ``docs/jenkins-seed.md``. Phases 0–5 done.

### Changed (Jenkins seed — Phase 4)

- Hardened shared scanner:
  ``collect_deployable_cluster_ids`` in
  ``clusterctl/tools/list_deployable_clusters.py``; committed fixture
  ``tests/fixtures/jenkins_seed_inventory/``; unit/CLI coverage in
  ``tests/test_list_deployable_clusters.py``. Gate:
  ``tests/test_jenkins_seed_phase4.py``.

### Changed (Jenkins seed — Phase 3)

- Operator docs polish: crisp bootstrap / day-to-day / re-seed workflow in
  ``docs/jenkins.md``, ``docs/jenkins-seed.md``, ``examples/internal/`` READMEs,
  and root ``README.md`` Jenkins section (removed stale Deps/venv guidance).
  Manual-only trigger called out; seed troubleshooting table. Gate:
  ``tests/test_jenkins_seed_phase3.py``.

### Changed (Jenkins seed — Phase 2)

- Deploy samples (``Jenkinsfile`` / ``.local``) omit Declarative ``parameters {}``
  so a deploy run no longer resets seed-managed ``choice CLUSTER_ID``. UI SoT =
  seed Job DSL full params template. Prepare fails fast if ``CLUSTER_ID`` is
  missing. Docs: ``docs/jenkins-seed.md``, ``docs/jenkins.md``. Gate:
  ``tests/test_jenkins_seed_phase2.py``.

### Changed (Jenkins seed — Phase 1)

- Seed sample under ``examples/internal/seed/``: Pipeline checks out inventory,
  lists deployable ids via ``python3 -m clusterctl.tools.list_deployable_clusters``,
  then Job DSL (``seed_deploy_jobs.groovy``) refreshes deploy job(s)
  ``choice CLUSTER_ID`` plus full params template (``TAGS`` / ``LIMIT`` /
  ``EXTRA_VARS``, …). Empty scan fails. Manual trigger only. Gate:
  ``tests/test_jenkins_seed_phase1.py``. Until Phase 2, re-run seed if a deploy
  run resets UI ``CLUSTER_ID`` back to string.

### Changed (Jenkins seed — Phase 0)

- Locked contract for a **manual** seed job that refreshes deploy-job
  ``CLUSTER_ID`` as a Jenkins ``choice`` (Job DSL; no cron/webhook; no Active
  Choices). Docs: ``docs/jenkins-seed.md``; stub ``examples/internal/seed/``.
  Gate: ``tests/test_jenkins_seed_phase0.py``.

### Changed (Jenkins samples — TAGS / LIMIT)

- ``examples/internal/Jenkinsfile`` (+ ``.local``): job params ``TAGS`` /
  ``LIMIT`` → optional ``--tags`` / ``--limit`` on each Run phase (with
  ``EXTRA_VARS``). Non-empty selective overrides need single-phase ``PHASES``.
  Run step uses ``bash`` (arrays; Jenkins ``sh`` is often dash). Docs:
  ``docs/jenkins.md``.

### Fixed (ADR 009 — alias removal Phase 5)

- ``./tests/run_ci.sh`` green after ``stage``/``play`` hard remove (1004 tests,
  skipped=84). Renamed ``_merge_extra_into_stage`` →
  ``_merge_extra_into_phase_plan`` so ADR 008 retired-dest grep does not
  false-positive on the former helper name. Gate:
  ``tests/test_adr_009_alias_removal_phase5.py`` (does **not** subprocess
  ``run_ci``; locks acceptance artifacts).

### Changed (ADR 009 — alias removal Phase 4)

- Migrated external callers to ``./cluster run --phases``: six
  ``atlas-inventory`` lab READMEs + ``atlas-compute-provision``
  ``docs/adr/001-tfstate-repo-prefix.md``. Sibling markdown scan clean. Gate:
  ``tests/test_adr_009_alias_removal_phase4.py`` (skips if siblings absent).

### Changed (ADR 009 — alias removal Phase 3)

- Maintainer notes / operator docs: **no live teach** of ``stage`` / ``play``
  (``notes/report_clusterctl.md`` §4.9/§4.10 → **Removed**; cheatsheet dropped
  alias comments). CHANGELOG Breaking migration text polished. Gate:
  ``tests/test_adr_009_alias_removal_phase3.py``.

### Fixed (ADR 009 — alias removal Phase 2)

- ADR 009 / cutover gates no longer require ``stage``/``play`` wiring or
  “aliases retained”. Dedicated gate:
  ``tests/test_adr_009_alias_removal_phase2.py``.

### Breaking (ADR 009 — alias removal Phase 1)

- **Removed** CLI ``./cluster stage`` and ``./cluster play`` (unknown
  subcommands — argparse “invalid choice”). Migrate:

  | Was | Use |
  |-----|-----|
  | ``./cluster stage NAME`` | ``./cluster run --phases NAME`` |
  | ``./cluster play NAME [--tags T] [-e E]`` | ``./cluster run --phases NAME […]`` |

  ``./cluster stages`` (list helper) unchanged. CLI gate:
  ``tests/test_adr_009_alias_removal_phase1.py``; docs/notes gate:
  ``tests/test_adr_009_alias_removal_phase3.py``.

### Changed (ADR 009 — alias removal Phase 0)

- Locked **hard remove** of deprecated CLI ``stage`` / ``play`` (no Variant S stub).
  External caller inventory (inventory READMEs + compute-provision ADR) recorded in
  ADR 009; aliases **still in tree** until Phase 1. Gate:
  ``tests/test_adr_009_alias_removal_phase0.py``.

### Fixed (ADR 009 — audit Phase 3)

- Maintainer ``notes/report_clusterctl.md`` §4.9 ``stage`` / §4.10 ``play``
  compressed to short deprecated cards (point at ``docs/clusterctl.md`` + ADR 009;
  no duplicate flag tables). Gate: ``tests/test_adr_009_notes_helper_b.py``.

### Fixed (ADR 009 — audit Phase 2)

- ADR Status no longer reads as continuous ``run_ci``-via-unittest: ``run_ci`` =
  acceptance-time / CI workflow; Phase 5 gate does **not** subprocess it.
  Context table marked **historical pre–Phase 1** (policy → Decision / Current
  runtime). Asserts: Phase 5 + ``tests/test_adr_009_coverage_a5.py``.

### Fixed (ADR 009 — audit Phase 1 / A2 follow-up)

- ``docs/cluster-config-v2.md`` Typical order no longer leads with ``templates``
  (matches ``provision → init → <stack>``; factory stays ``pve_templates``-only).
- A2 gate catches Unicode/``Typical order`` regressions + duplicate
  ``fact_caching`` sentences in stack docs; deduped
  ``jenkins-agent.md`` / ``kafka.md`` (and removed a corrupted ``yaml`.`` fragment).

### Fixed (ADR 009 — post-cleanup B)

- ``apply_play_cli_overrides`` docstring: tests-only / DO NOT use from CLI
  (collapse-on-``-e`` is historical; production uses ``apply_run_cli_overrides``).
  Maintainer ``notes/report_clusterctl.md`` primary examples → ``run --phases``.
  Gate: ``tests/test_adr_009_notes_helper_b.py``.

### Fixed (ADR 009 — post-cleanup A5)

- CLI E2E: deprecated ``play … -e … --dry-run`` keeps ``merge_e`` (no collapse);
  ADR Phase 5 scope note: unittest gate checks ``run_ci.sh`` exists — full green
  is ``.github/workflows/ci.yml`` / acceptance-time. Gate:
  ``tests/test_adr_009_coverage_a5.py`` (+ Phase 5 ``test_sample_play_dry_run_merge_e``).

### Fixed (ADR 009 — post-cleanup A4)

- Jenkins docs / Pipeline comments: typical plan example is
  ``[1/4] atlas-compute-provision/provision`` (not ``…/templates``). Gate:
  ``tests/test_adr_009_jenkins_plan_example_a4.py``.

### Fixed (ADR 009 — post-cleanup A3)

- Validate / ``repo_conventions`` hints teach ``./cluster run --phases`` /
  ``./cluster run --dry-run`` (no ``stage`` / ``play``). Gate:
  ``tests/test_adr_009_hints_a3.py``.

### Fixed (ADR 009 — post-cleanup A2)

- SoT docs phase counts match public scaffolds: ``k8s_full`` / ``infra_edge`` are
  **4 phases** (start at ``provision``); README + stack phase maps no longer
  imply a leading ``templates`` plan step. Gate:
  ``tests/test_adr_009_sot_phase_counts_a2.py``.

### Fixed (ADR 009 — post-cleanup A1)

- Env ``LIMIT`` is resolved for **all** execute verbs (``run`` / ``stage`` /
  ``play``) via ``resolve_run_limit`` before ``apply_run_cli_overrides`` (CLI
  ``--limit`` wins). Removed ``honor_limit_env`` play-only path. Ansible
  last-mile prefers planned ``invocation.limit`` over env. Docs:
  ``docs/clusterctl.md``. Gate: ``tests/test_adr_009_limit_unify_a1.py``.

### Changed (ADR 009 — Phase 5)

- Offline ``./tests/run_ci.sh`` + sample ``run --phases … -e … --dry-run`` green;
  ADR complete. Deprecated ``stage`` / ``play`` aliases **retained** (stderr
  warning; hard removal deferred). Gate:
  ``tests/test_adr_009_unify_run_stage_play_phase5.py``.

### Changed (ADR 009 — Phase 4)

- Operator docs teach ``./cluster run --phases`` as the canonical execute path
  (``clusterctl.md``, stacks, quick starts). ``stage`` / ``play`` remain short
  deprecated-alias sections. Gate:
  ``tests/test_adr_009_unify_run_stage_play_phase4.py``.

### Changed (ADR 009 — Phase 3)

- Jenkins samples: ``EXTRA_VARS`` param + Run via ``./cluster run --phases`` with
  safe ``-e`` argv (no ``eval``). Docs: ``docs/jenkins.md``. Gates:
  ``tests/test_adr_009_unify_run_stage_play_phase3.py``,
  ``tests/test_phase6_e2e_signoff.py``.

### Changed (ADR 009 — Phase 2)

- ``stage`` / ``play`` are deprecated aliases of ``run`` (stderr warning; shared
  ``_cmd_run_execute`` + ``apply_run_cli_overrides``). ``play -e`` alone is
  ``merge_e`` (no collapse). Gates:
  ``tests/test_adr_009_unify_run_stage_play_phase2.py``.

### Changed (ADR 009 — Phase 1)

- ``./cluster run`` accepts ``--tags`` / ``--limit`` / ``-e`` / ``--root-ssh`` /
  ``--git-ssh`` and applies ``apply_run_cli_overrides`` (``catalog`` /
  ``merge_e`` / ``collapse``; multi-phase selective overrides ERROR).
  ``stage`` / ``play`` unchanged until Phase 2. Gates:
  ``tests/test_adr_009_unify_run_stage_play_phase1.py``,
  ``tests/test_run_overrides_contract.py``.

### Changed (ADR 009 — Phase 0)

- Locked contract to unify `run` / `stage` / `play` into one execute verb:
  [docs/adr/009-unify-run-stage-play.md](docs/adr/009-unify-run-stage-play.md).
  Policy helper `clusterctl/run_overrides.py` (`catalog` / `merge_e` / `collapse`);
  **no argparse wiring** yet. Gates:
  `tests/test_adr_009_unify_run_stage_play_phase0.py`,
  `tests/test_run_overrides_contract.py`.

### Changed (mixed-OS kafka/redis — Phase 1)

- `_template/kafka` and `_template/redis` foundation `pkg_repos`: mixed-OS base
  set (ubuntu + debian-main/security + OL9_*), matching
  `example_leaf_lists.foundation_ci/{kafka,redis}`.

### Changed (pkg repos — Phase 6)

- `_template` / stack docs: foundation overlays use `pkg_repos`; infra_edge
  mirror gate is `setup_apt_rpm_nginx: "{{ setup_pkg_repo_nginx }}"`.
  Dead `use_internal_rpm_apt_repo` knobs removed from redis/kafka product
  inventory overlays. Drift/grep gates: sibling foundation
  `tests/test_pkg_repos_phase6.py`.

### Changed (pkg repos — Wave D)

- Stack docs: k8s_full/`dev/mxhash` require full guest `pkg_repos` (not empty);
  jenkins lists containerd; infra_edge notes cleanup⇒non-empty. Package-repo
  SoT remains inventory + `_template` (not `tfstate-repo/`).

### Fixed (pkg repos — post-Wave D)

- Shared `_template/group_vars` foundation stub: `cleanup_repositories: false`
  with empty `pkg_repos` (was cleanup∧empty).

### Changed (golden PVE templates — Phase C)

- Documented publish + unpin: org inventory leaves restore `source: git` for
  `atlas-compute-provision` after Phase A lands on gitea `main`.

### Changed (golden PVE templates — Phase B)

- Stack scaffolds omit `provision_pve_templates`; only `_template/pve_templates`
  (factory) keeps the build catalog (`id` + `image_url`). Stacks clone by
  `hosts.provision.clone` name alone. Docs updated accordingly.

### Changed (golden PVE templates — Phase 5)

- Public scaffolds use golden clone names (`ubuntu-base` /
  `oracle-base` / `debian-base`, VMIDs 400100–400102); default stack `phases:`
  start at `provision`. New `--template pve_templates` factory leaf keeps
  `image_url` for builds. Docs/quickstarts teach build-once / clone-many.

### Changed (maintainer notes)

- Moved internal `report_clusterctl.md` under `notes/` and added
  `notes/product-improvements.md` (plain-language product backlog). Pre-publish
  allowlists treat `notes/` as maintainer surface, not operator docs.

### Fixed (ADR 008 cleanup Variant B — audit Phase A)

- Corrected Cleanup Phase 3 evidence count (`66 OK`); clarified product Phase 5
  `run_ci` green (acceptance-time) vs Variant B offline proof (ADR 008 suite);
  marked historical Cleanup Phase 1 acceptance items and the archival ADR 008
  Phase 4 dual-gate CHANGELOG note as superseded by Variant B.

### Changed (controller hygiene — ADR 008 cleanup Phase C)

- Ignore `/tfstate.local.bak-*/` beside existing `/tfstate-repo/` and
  `/tfstate.legacy-bak-*/`. Phase 3 basename gate skips both bak prefixes
  generically (not one-off dirname literals).

### Changed (ADR 008 cleanup Variant B — Phase 3)

- Closed Variant B: script basename scrubbed from operator docs; inventory `.sh`
  gone; ADR 008 suite + permanent argparse/dest-name hygiene green. Gate:
  `tests/test_adr_008_legacy_window_cleanup_phase3.py`. Dual docs anti-regression
  gate fully retired. Full `./tests/run_ci.sh` still surfaces unrelated
  pre-existing public-track debt (pre-publish / docker validate) — not Variant B.

### Changed (ADR 008 cleanup Variant B — Phase 2)

- Deleted sibling inventory `scripts/check-no-legacy-phase-window.sh` (twin SoT
  for retired `plan`/`run --from/--to` docs scan). Dual docs anti-regression
  gate fully gone after Phase 1 Python scanner removal. Gate:
  `tests/test_adr_008_legacy_window_cleanup_phase2.py`. Cleanup Phase 3 =
  verify + close.

### Changed (ADR 008 cleanup Variant B — Phase 1)

- Removed Python docs anti-regression twin SoT: `tests/adr_008_legacy_cli.py` and
  `tests/test_adr_008_legacy_cli.py`. Phase 2/4 gates no longer scan operator
  docs for CLI-like `cluster plan|run --from/--to` or invoke inventory
  `check-no-legacy-phase-window.sh`. Permanent hygiene kept: argparse reject +
  `from_stage`/`to_stage` dest-name allowlist grep. Gate:
  `tests/test_adr_008_legacy_window_cleanup_phase1.py`. Inventory `.sh` deletion
  = Cleanup Phase 2.

### Changed (ADR 008 cleanup Variant B — Phase 0)

- Locked post-complete cleanup **Variant B**: full purge of plan/run
  `--from`/`--to` anti-regression scaffolding (Python docs scanner + inventory
  `check-no-legacy-phase-window.sh`). Permanent hygiene stays argparse +
  `from_stage`/`to_stage` dest ban. `init --from` / `export_template --from`
  remain out of scope. Gate:
  `tests/test_adr_008_legacy_window_cleanup_phase0.py`. Code purge = Cleanup
  Phases 1–2 (not this phase).

### Changed (TF state operator verify — ADR 001 Phase 4)

- Documented live `07_tf_state_pull` verify for `ci/infra` against
  `tfstate-repo/tfstate/ci/infra/` (sibling ADR 001 Phase 4).
- Inventory keeps `tfstate/` tracked; `/workspace/` ignored (atlas-inventory).

### Changed (TF state migrate — ADR 001 Phase 3)

- Documented live inventory remote layout `tfstate/<cluster_id>/` (bare root `ci/` /
  `dev/` state trees retired on atlas-inventory).
- `.gitignore`: ignore `$ATLAS_CLUSTER_ROOT/tfstate-repo/` and `tfstate.legacy-bak-*/`
  (controller checkout + retired pre-ADR clones).

### Changed (TF state docs — ADR 001 Phase 2)

- `docs/workspace.md`: three-tree layout (`clusters` / `workspace` / `tfstate-repo`),
  controller vs in-repo path table, leaf overlay guidance (repo/push only).
- `docs/stacks/compute-provision.md`: durable TF path table + pointer to sibling
  `docs/tfstate.md` / ADR 001.
- `docs/README.md` / `docs/adr/README.md` / `docs/local-labs.md`: link durable TF docs (Phase 2).

### Changed (pre-publish Phase 7)

- Working-tree publish readiness closed: `docs/pre-publish.md` Phase 7 status
  banner; verifiable checklist items marked `[x]` (labs absent from index,
  publish surface tracked, hygiene + pre-publish audit green).
- Operator-owned leftovers explicitly separated: credential rotation, history
  rewrite / orphan publish, and `[project.urls]` once a public remote exists.
- Gate: `tests/test_pre_publish_phase7.py`.

### Changed (packaging Phase 6)

- `pyproject.toml`: removed placeholder `github.com/example/…` Documentation URL
  (public Source/Documentation filled at publish — see `docs/pre-publish.md`;
  private forge hostnames stay out of product metadata).
- `optional-dependencies.dev`: no longer duplicates `PyYAML`; empty beyond
  runtime deps (matches `requirements-dev.txt` / stdlib unittest). Ansible and
  lint tools remain sibling-repo concerns.
- `ClusterContext.default_profile` → deprecated alias of `legacy_profile`
  (`DeprecationWarning`).
- `primary_cluster_var_file()` → deprecated alias of `optional_cluster_var_file`
  (`DeprecationWarning`).

### Changed (soft-compat Phase 5 — `role_repos` → playbooks API)

- Canonical resolved-repos view lives in `clusterctl.playbooks_repos`
  (`ResolvedPlaybookRepo`, `ResolvedPlaybooksRepos`, `ctx.playbook_repos`,
  `build_resolved_playbooks_repos`). YAML SoT remains `playbooks:`.
- `clusterctl.role_repos` is a **deprecated re-export shim** (`DeprecationWarning`
  on import); aliases (`RoleRepoSpec`, `RoleReposConfig`, `ctx.role_repos`, …)
  keep old callers working until the shim is removed in a later cut.
- `workspace_repos_root` / `WORKSPACE_REPOS_DIRNAME` owned by
  `clusterctl.playbooks_paths` (no dependency on the shim).

### Changed (soft-compat Phase 4)

- Legacy `group_vars/all/secrets.yml` / `secrets.yaml`: **not merged**; validate
  `FAIL [secrets_legacy_monolith]` (was WARN). Use `atlas-*.secrets.yml` only.
  `export_template` still scrubs legacy `secrets.yml` if present so public
  scaffolds cannot leak credentials.
- Legacy `group_vars/all/cluster.yml`: validate `FAIL [cluster_yml_legacy]` (Severity.ERROR; was WARN; ADR 003 follow-up). Still merged if present so values remain visible
  while operators delete the file.
- Builtin cluster id alias `dev-mxhash.com` removed — declare
  `cluster_id_aliases` on the leaf / cascade (inventory labs already do).
- Flat `clusters/default` workspace-vars fallback removed — only
  `clusters/default/default` is used; org overlays moved there. `init --from default`
  borrows `group_vars` from `default/default` when the flat scaffold lacks them.
- `k8s_cluster_domain` alone is no longer a workspace-id source; require
  `cluster_domain` (optional `k8s_cluster_domain: "{{ cluster_domain }}"`).

### Fixed

- ADR 007 follow-up: reject duplicate phase refs at `parse_phases_config` (not
  only validate); `phases_config_to_raw` errors on inconsistent
  `PhasesConfig` instead of emitting a non-round-trippable dump; cascade
  `merge_phases_configs` treats explicit `phases: []` as list replace (omit
  still inherits).

### Added

- [ADR 008](docs/adr/008-phases-cli-selector.md) — unified `--phases` CLI
  selector (replace `--from` / `--to`). Phase 0: grammar locked
  (`single` | `start..end`; CSV deferred with hard ERROR at Phase 0);
  `parse_phases_selector` helper + contract matrix; **no argparse wiring** yet.
  Phase 1: `--phases`/`-p` on `plan`/`run`; dual-read `--from`/`--to`; mixing
  styles → ERROR (`resolve_cli_phase_window`). Phase 2: docs/stacks/templates
  happy-path on `--phases`; argparse marks `--from`/`--to` deprecated.
  Phase 3: comma / CSV explicit set (`a,b,c`) with leaf `phases:` order
  (skip-middle; lifts Phase 0 CSV deferral); `select_explicit_phase_refs` /
  `CliPhaseWindow.only_phases`.
  Phase 4: removed `plan`/`run` `--from`/`--to` (`from_stage`/`to_stage`);
  `resolve_cli_phase_window` is `--phases`-only; grep-gate bans retired dests
  under `clusterctl/` (`init --from` / `export_template --from` unchanged).
  Follow-up: `_add_phases_selector_flag` rename; reject Unicode `…` / en-em dash
  lookalikes for `..`; clarify CSV ≥2 in help/docs; quiet argparse SystemExit
  stderr in phase gates.   Follow-up (gates): shared
  `tests/adr_008_legacy_cli.py` bans CLI-like `cluster plan|run … --from|--to`
  (not bare prose); Phase 2 ≡ Phase 4 hard-ban (no deprecated/legacy line skip);
  inventory `scripts/check-no-legacy-phase-window.sh` embeds the same
  `PLAN_RUN_LEGACY_PHASE_WINDOW_PATTERN` (Phase 4 sibling test runs the script).
  *(Superseded by Variant B Cleanup Phases 0–3: Python docs scanner + inventory
  `.sh` purged; permanent hygiene = argparse + `from_stage`/`to_stage` dest ban
  only.)*
  Follow-up: lookalike errors split — Unicode ellipsis → ASCII `..`; en/em dash →
  ASCII `-` in names or `..` for ranges.
  Phase 5: offline `./tests/run_ci.sh` green (no live labs); ADR complete.
- [ADR 007](docs/adr/007-phases-inline-aliases.md) — inline phase aliases in
  `phases:` (remove top-level `phase_aliases:`). Phase 0: contract + matrix;
  **no YAML deletion**, **no parse change** yet. Phase 1: engine parse/dump/merge
  + `PhaseAliasesRemovedError`; public `_template/**` rewritten to inline form
  (inventory still Phase 3). Phase 2: public tree verify-clean gate. Phase 3:
  sibling `atlas-inventory` labs rewritten to inline aliases. Phase 4: docs
  polish + fixture hygiene (operator docs inline-only; no redundant YAML
  `phase_aliases:` writers outside negative tests). Phase 5: offline
  `./tests/run_ci.sh` + sample validate/plan with short phase aliases green
  (no live labs); ADR complete. *(At Phase 5 time the window flags were still
  `--from`/`--to`; superseded by [ADR 008](docs/adr/008-phases-cli-selector.md)
  Phase 5 — use `--phases` / `-p`.)*
- [ADR 004](docs/adr/004-universal-export-template.md) — universal maintainer
  `export_template` (`--from` + `--template`); multi-stack tests cover all known
  scaffolds. Phases 0–4 complete.
- [ADR 006](docs/adr/006-redundant-playbooks-enabled.md) — redundant
  `playbooks_enabled: true`; enable is inferred from `playbooks:` (keep
  `false` as kill switch). Phase 0: contract + infer/cascade test matrix.
  Phase 1: `playbooks_feature_enabled` omit→infer aligned with
  `effective_playbooks_enabled`; user-facing errors/hints say define
  `playbooks:` (no mandatory `set playbooks_enabled: true`). Phase 2: dropped
  redundant `true` from public `_template/*/cluster.yaml` and
  `clusters/default/default/cluster.yaml`. Phase 3: dropped redundant `true`
  from sibling `atlas-inventory` labs (`ci/*`, `dev/mxhash`, …). Phase 4:
  docs controller-contract polish + unittest fixture hygiene (omit redundant
  `"playbooks_enabled": True` where fixtures already carry `playbooks:`).
  Phase 5: offline `./tests/run_ci.sh` + sample validate/plan green (no live
  labs); ADR complete.
- [ADR 005](docs/adr/005-remove-cluster-stacks.md) — remove `cluster.yaml`
  `stacks:` / `skip_phase_refs`; plan SoT is `phases:` only. Phases 0–4 complete:
  Phase 0 contract; Phase 1 intent + `stacks_legacy` WARN; Phase 2 removed
  `stacks_skipped` / plan filter UX; Phase 3 deleted YAML key from templates/
  inventory + docs; Phase 4 deleted `clusterctl/stacks.py`, hard-reject at load,
  intent in `clusterctl/phase_intent.py`. Post-Phase-4 cleanup: (A) typed
  `StacksRemovedError` / issue code **`stacks_removed`** (not generic
  `cluster_load_failed`); (B) dead `load_phase_intent` removed, validate codes
  renamed to `phase_intent_*` / `inventory_*_phases_omitted` (legacy
  `stacks_*_no_inventory` / `*_stack_disabled` gone); (C) ADR/operator docs
  wording synced to runtime (`PhaseIntent`, hard delete of `stacks.py`, honest
  grep-gate checklist — no soft “migration helper” / live stack-flag API prose);
  (D) grep-gate strengthened — legacy validate codes + retired APIs
  (`apply_stacks_filter`, `StackFlags`, `load_phase_intent`, …) hard-banned under
  `clusterctl/`; repo-wide allowlist = CHANGELOG + ADR + phase gates + negative
  tests; (E) offline full verification via `./tests/run_ci.sh` (no live labs).

### Changed (ADR 004 — universal `export_template`, Phase 4)

- Deleted retired k8s-only shim module and its compat tests; grep-gate keeps the
  old name out of runtime/docs (CHANGELOG history + ADR/phase gates only).
- Removed `--clusters-root` alias from `export_template` (use matching
  `--source-root` / `--target-root`).
- `export_template` copies `*.secrets.yml` / legacy `secrets.yml` but empties
  all leaf values (`""`); Ansible Vault payloads are replaced with an empty stub.
### Changed (ADR 004 — universal `export_template`, Phase 3)

- Public SoT docs (`docs/local-labs.md`, `_template/*/README.md`, stacks,
  inventory lab READMEs) recommend **only** `export_template`; the legacy
  `export_k8s_full_template` module is no longer documented as the promote path.

### Removed

- `./cluster init --domain-prefix`: it rewrote `cluster_domain` across all Leaf
  DNS overlays and wiped stack prefixes (`redis.` / `kafka.` / `pgsql.` / …).
  Use `--dns-suffix` for the shared suffix; edit `cluster_domain` in `atlas-*.yml`
  when the stack prefix must change.

### Changed

- Operator docs clarify Leaf DNS ownership: `--dns-suffix` only; `cluster_domain`
  stack prefixes are template-owned (`docs/clusters.md#leaf-dns-identity`,
  `docs/clusterctl.md`, ADR 003 init table, `_template` READMEs).
- `./cluster init --dns-suffix` fails hard (and rolls back the new leaf) when no
  overlay can receive the suffix (missing Leaf DNS files or missing
  `dns_domain_suffix` key).
- `export_template` / `scrub_leaf_dns_suffix_for_public_template` rewrite
  literal `cluster_domain` FQDNs to `"<prefix>.{{ dns_domain_suffix }}"` so live
  domains do not land in public templates.

### Changed (ADR 003 — optional `cluster.yml`, Phase 4)

- `./cluster validate` emits `WARN [cluster_yml_legacy]` when
  `group_vars/all/cluster.yml` is still present.
- Operator docs / stacks cleaned: Leaf DNS lives only in `atlas-*.yml`; external
  scripts must not `test -f …/cluster.yml`.
- ADR 003 Phases 0–4 complete.

### Changed (ADR 003 — optional `cluster.yml`, Phase 3)

- Deleted `group_vars/all/cluster.yml` from public `_template/*`, `clusters/default`,
  and inventory labs (`ci/*`, `dev/mxhash`).
- `CONVENTIONAL_GROUP_VARS_ALL` no longer lists `cluster.yml`.
- `export_k8s_full_template` removes any copied `cluster.yml` after DNS scrub.
- Follow-up: Phase 4 docs/warn for remaining external `test -f …/cluster.yml` scripts.

### Changed (ADR 003 — optional `cluster.yml`, Phase 2)

- `./cluster init --dns-suffix` patches `dns_domain_suffix` in every matching
  `atlas-*.yml` overlay (`clusterctl/leaf_dns.py`); init never invents
  `cluster.yml`. (`--domain-prefix` was removed; see Unreleased Removed.)
- `export_k8s_full_template` scrubs live `dns_domain_suffix` in overlays to
  `example.com` and removes any copied `cluster.yml` (Phase 3).
- CLI help / post-init hints point at `atlas-*.yml`, not `cluster.yml`.
- Follow-ups: Phase 3 delete stubs → Phase 4 docs/warn.

### Changed (ADR 003 — optional `cluster.yml`, Phase 1)

- Soft-require: missing `group_vars/all/cluster.yml` is OK when other
  `group_vars/all/*.yml` exist (`require_group_vars_all`).
- `ClusterContext.cluster_var_file` / `cluster_var_file_path` / `primary_cluster_var_file`
  are optional (`Path | None`).
- `config_dir_is_usable` accepts any mergeable group_vars, not only `cluster.yml`.
- Workspace-id baseline fallback merges all default `group_vars/all`, not a single stub.
- Operator docs / ADR updated to Phase 1 runtime; stubs remain until Phase 3.
- Follow-ups: Phase 2 init/CLI → Phase 3 delete stubs → Phase 4 docs/warn.

### Changed (ADR 003 — optional `cluster.yml`, Phase 0)

- Accepted [ADR 003](docs/adr/003-optional-cluster-yml.md): target leaf contract no
  longer treats `group_vars/all/cluster.yml` as identity SoT; DNS lives in
  `atlas-*.yml`, paths/workspace via inject, `provision_stack` in compute overlay.
- Operator contract documented in [docs/clusters.md](docs/clusters.md#leaf-filesystem-contract).

### Changed (per-product `*.secrets.yml` overlays)

- Conventional secrets live next to each product catalog:
  `atlas-redis.yml` + `atlas-redis.secrets.yml` (same for other siblings).
- Merge force-last order: non-secrets alphabetical → `*.secrets.yml` alphabetical
  → legacy `secrets.yaml` / `secrets.yml` (still accepted during migration).
- `CONVENTIONAL_GROUP_VARS_ALL` lists product catalogs + `*.secrets.yml` + `cluster.yml`
  (no monolithic `secrets.yml`).
- Validate: checks every secrets overlay; warns on legacy `secrets.yml`; prefers
  per-product files.
- Exemplar: `atlas-redis` / `_template/redis` / `ci/redis` move `vip_auth_pass` into
  `atlas-redis.secrets.yml`. Prefer Ansible Vault on that file (not gitignore).
- Phase 2 siblings: every product repo now ships `group_vars/all/atlas-*.secrets.yml`
  and must-add catalog keys (compute maps/gitea/dns_tf, infra sync freshness,
  foundation enable_repo/pki helpers, k8s-core LB/DNS/packages, k8s-addons
  debug_tooling, postgresql `haproxy_log_facility`). Templates/inventory = Phase 3–4.
- Phase 3 `_template/*`: each stack leaf ships matching `atlas-*.yml` +
  `atlas-*.secrets.yml` pairs aligned with siblings (identity stays in `cluster.yml`);
  legacy `secrets.yml.example` removed from templates.
- Phase 4 `atlas-inventory`: every lab leaf uses `atlas-*.secrets.yml`; legacy
  monolithic `secrets.yml` removed from labs.
- Phase 5 parity gate: `tests/test_catalog_secrets_parity_phase5.py` asserts
  sibling↔template key parity (identity/controller/other-stack maps excluded),
  secret keys only in `*.secrets.yml`, and inventory must-add / pair layout.
- Phase 6 docs: operator path is `atlas-<repo>.secrets.yml` + Vault only;
  monolithic `secrets.yml` / `secrets.yml.example` removed from public scaffolds;
  stack docs / SECURITY / pre-publish / local-labs aligned; sibling SECURITY
  paragraphs unified.

### Changed (group_vars named after sibling repos)

- Conventional overlays rename from playbook stems to sibling repo basenames:
  `init_nodes.yml`→`atlas-node-foundation.yml`,
  `provision_nodes.yml`→`atlas-compute-provision.yml`,
  `infra_hosts.yml`→`atlas-infra-edge.yml`,
  `kafka_cluster.yml`→`atlas-kafka.yml`,
  `postgresql_cluster.yml`→`atlas-postgresql.yml`,
  `redis_cluster.yml`→`atlas-redis.yml`,
  `jenkins_agent.yml`→`atlas-jenkins-agent.yml`,
  `cluster_core.yml`→`atlas-k8s-core.yml`,
  `cluster_addons.yml`→`atlas-k8s-addons.yml`.
- Unchanged: `cluster.yml` (identity), group-scoped files (`proxmox.yml`, …).
- Merge: alphabetical catalogs; secrets overlays force-last (see above).

### Changed (group_vars naming cleanup)

- Dropped `LEGACY_GROUP_VARS_RENAMES` and validate warning `group_vars_legacy_names`
  after templates + inventory use playbook-stem filenames. Any-file merge (PR1)
  remains; conventional names stay documentation-only.
- `secrets.yaml` is also deferred to the end of materialize order (with
  `secrets.yml` last if both exist).

### Changed (group_vars playbook-stem names)

- Public templates / `clusters/default` rename overlays to sibling playbook stems:
  `infra.yml`→`atlas-infra-edge.yml`, `prepare_hosts.yml`→`atlas-node-foundation.yml`,
  `provision.yml`→`atlas-compute-provision.yml`, `kafka.yml`→`atlas-kafka.yml`,
  `redis.yml`→`atlas-redis.yml`, `postgresql.yml`→`atlas-postgresql.yml`.
- `platform.yml` split → `atlas-k8s-core.yml` + `atlas-k8s-addons.yml`
  (`_template/k8s_full`).
- `atlas-jenkins-agent.yml`, `cluster.yml`, `secrets.yml` unchanged; managed
  `enable_repo_*` flags live in `atlas-node-foundation.yml` (former `repos.yml` merged away).
- Private inventory leaves renamed in atlas-inventory (`ci/*`, `dev/mxhash`) to the
  same convention.

### Changed (group_vars materialize)

- `discover_group_vars_all()` merges **all** `group_vars/all/*.{yml,yaml}` (not a fixed
  whitelist). Order is alphabetical by filename; `secrets.yml` is always last.
  Skips `*.example` and hidden files.

### Changed (infra-edge compose Phase 6)

- Default plan merges docker baseline into one invocation
  (`00_bootstrap_infra_repos,01_install_docker_engine,02_configure_docker_daemon`).
  Plan contract: 10 infra / 38 full (`tests/test_infra_edge_orchestration.py`).
  Sibling: parallel `compose_pull` default + `atlas_infra_edge_timing` phase metrics.

### Changed (infra-edge compose Phase 5)

- Deploy-role `main.yaml` is thin (`render.yaml` only; step-ca keeps `bootstrap.yaml`).
  Per-role `pre_pull_compose_images` removed — images come from `compose_pull`.
  `apply_runtime.yaml` kept as optional ad-hoc helpers, not imported by main.

### Changed (infra-edge compose Phase 4)

- **`_template/infra_edge`** and orchestration docs/tests use compose phase tags
  (`compose_render` → … → `compose_reconcile`) instead of legacy per-role deploy tags
  in the default plan. Lab `ci/infra` (private inventory) stays in lockstep.
- Docs: `docs/stacks/infra-edge.md` — “Adding a compose stack” (no `cluster.yaml` edit);
  plan contract pinned in `tests/test_infra_edge_orchestration.py` (see Phase 6 counts).

### Added (pre-publish audit)

- **`docs/pre-publish.md`** — checklist before a public remote: index gates, push dry-run,
  credential rotation, separate history rewrite / orphan notes.
- **`tests/check_pre_publish_audit.py`** — fail on labs/secrets in the git index, org
  fingerprints / Cyrillic in publish candidates; WARN when HEAD/history still embeds labs
  or `Welcomeback`.
- Wired into **`tests/run_ci.sh`**. Normalized leftover `ChangeMe123!` placeholders in
  `_template/k8s_full` to `CHANGEME`.

### Added (local labs workflow)

- **`docs/local-labs.md`** — operator runbook: keep/restore labs, `list` / `check-ignore` /
  `ls-files` checks, lab↔template map, scrub rules for `export_k8s_full_template`.
- **`tests/test_local_labs_contract.py`** — gitignore + docs contract; when labs exist,
  assert they are listed and ignored / not tracked.

### Added (CI / public gates)

- **`tests/run_ci.sh`** — local parity with GitHub Actions (packaging, unittest, preflight, template YAML, hygiene).
- **`.github/workflows/ci.yml`** — Python 3.12 public track (no live labs required).
- **`tests/check_publish_hygiene.sh`** — fail on org hostnames / Welcomeback / private-key markers in product paths.
- **`tests/check_public_templates_yaml.py`** — parse `clusters/_template` + `clusters/default` YAML scaffolds.

### Added (packaging surface)

- **`pyproject.toml`** — installable metadata, `PyYAML` dependency, optional `cluster` console script.
- **`requirements.txt`** / **`requirements-dev.txt`** — contributor pins for unittest track.
- Root **README** — standalone-first: compatibility, sibling playbook contract, labs vs public tree, development.

## [Unreleased] — atlas-* family cutover (phase 8)

### Added (phase 8 / PR-5)

- **`clusterctl.tools.ci_preflight`** — offline Jenkins gate: unittest, legacy scans, org baseline fixture, `validate --repo`.
- **`clusterctl.tools.purge_legacy_materialized_repos`** — remove retired playbook dirs under `workspace/*/repos/`.
- **`validate --repo`** — also fails on `legacy_repo_reference` (text scan) and `retired_workspace_repo` under workspace.
- **Jenkinsfile** — `CI preflight` stage before `Repos sync`.

### Changed (phase 8 / galaxy requirements PR-2)

- **Galaxy collections** — `requirements.yml` removed from `atlas-clusterctl`; bootstrap installs from effective playbook repos (`PLAYBOOK_REQUIREMENTS_FILES` → `ansible-galaxy collection install -r …` per repo).
- **`clusterctl.playbooks_requirements`** — discovery of `requirements.yml` under playbook repo roots (phase order, deduped paths).

### Added (phase 8 / PR-2)

- **`clusterctl.tools.check_no_legacy_repos`** — CI gate: zero references to retired repo names.

### Removed (phase 8 / PR-2)

- **`TBD/`** tree (legacy audits, frozen krang scripts, pre-migration archives).

### Changed (phase 8 / PR-2)

- **Controller env** — `K8S_CLUSTER_ROOT` → `ATLAS_CLUSTER_ROOT`; inject key `atlas_cluster_root` (was `k8s_cluster_root`).
- **Docs + group_vars comments** — only `atlas-*` playbook repo names.
- **README** — repo identity `atlas-clusterctl` (not `k8s_cluster`).

### Changed (phase 8 / PR-1)

- **Org baseline big rename** — playbook keys `atlas-node-foundation`, `atlas-infra-edge`, `atlas-compute-provision`, `atlas-k8s-core`, `atlas-k8s-addons`; Gitea URLs on `atlas-*.git`.
- **Phases / aliases** — all refs use atlas-* repos; removed `platform` alias (use `k8s-addons`).
- **Dev cascade** — `clusters/dev/default/cluster.yaml` keys match sibling directory names (no path shim).
- **CLI default phase** — `k8s-addons` (was `platform`).

### Breaking (phase 8)

- Playbook repo keys `init_roles`, `atlas-phase-0`, `atlas-phase-1` removed — update `PLAYBOOKS_*` env and phase refs.
- `platform` phase alias removed — use `k8s-addons` or `atlas-k8s-addons/addons`.
- `K8S_CLUSTER_ROOT` / `k8s_cluster_root` removed — use `ATLAS_CLUSTER_ROOT` / `atlas_cluster_root`.

## [Unreleased] — audit fix phases 0–7 (`move2platform`)

### Added (phase 7)

- **Cascade layout inheritance** — leaf `playbooks:` overrides without `layout:` inherit org baseline (`atlas-k8s-addons` keeps `layout: ''`).
- **`local_playbooks_override_block()`** test helper in `clusterctl.pipeline_fixture`.

### Removed (phase 7)

- `./cluster role-repos` CLI (use `./cluster repos` / `./cluster playbooks`).
- `ROLE_REPOS_*` env vars (use `PLAYBOOKS_*` only).
- `STAGE_BY_NAME` alias (`PHASE_BY_ALIAS` only).
- Leaf `role_repos:` / `role_repos_enabled:` in `cluster.yaml` — **ClusterctlError** on load.
- `check_docker_role_repos_host` Python alias.
- Deprecated functions in `role_repos.py` facade (`load_role_repos_defaults`, `resolve_role_repos_config`, leaf overlay merge, etc.).

### Added (phase 6)

- **`playbooks.lock`** — `workspace/<id>/playbooks.lock` with pinned git SHAs after `./cluster repos sync`; validate checks drift (`--strict` → ERROR).
- **Cluster-aware `./cluster stages`** — effective phases for active/deployable cluster; `--baseline` for org baseline list.
- **E2E sign-off tests** — `tests/test_phase6_e2e_signoff.py` mirrors Jenkins preflight matrix (offline-safe).

### Fixed

- **C-01** Workspace ID collision: `clusters/default/` scaffold uses `example.com` DNS (`k8s.example.com` workspace); canonical dev is `dev/mxhash` only.
- **C-02** `repo_root` inference: `load_cluster_config` without explicit `repo_root` resolves via `cluster_layout.infer_repo_root_from_config_dir()` (cascade-safe).
- **C-03** Docker / playbooks gates unified: `require_effective_playbooks_context()` and `require_phase_runner()` for `playbooks`, `repos`, `run`, `stage`, `ansible_env`, `smoke`, `config`.
- **H-01** Circular import `playbooks_validate` ↔ `playbooks_resolve` broken (validate uses org baseline only).
- **H-02** Docker executor single path: phase-runner mounts via `_docker_local_playbook_mounts` only.
- **H-03** Lazy `pipeline.py` load (no import-time org baseline read).
- **H-04** `workspace_id` fallback for legacy flat `default/` layout (stderr warning).
- **H-05** Duplicate playbooks block in `context.summary_lines` removed.
- **H-06** `clusters/dev-mxhash.com/` orphan `group_vars` removed (README redirect only).

### Changed

- Galaxy collections install to `workspace/<id>/.ansible/collections/` (not repo root `.ansible/`).
- `./cluster stages` lists **effective cluster phases** when active cluster is deployable; `--baseline` for org baseline only.
- Docs: `docs/playbooks.md` is canonical; `docs/role_repos.md` is a redirect.

### Breaking (behavioral)

- `./cluster playbooks sync` / `./cluster repos sync` require schema v2 playbooks context (effective playbooks enabled after cascade — infer from `playbooks:` or explicit flag); misconfigured clusters raise `ClusterctlError` instead of silent fallback.
- Leaf `role_repos:` / `role_repos_enabled:` in `cluster.yaml` rejected (phase 7).
- `./cluster role-repos` and `ROLE_REPOS_*` env removed (phase 7).
