# Architecture Decision Records

Accepted decisions that change clusterctl contracts. Prefer linking from
operator docs (`clusters.md`, stacks) rather than duplicating prose.

| ADR | Title | Status |
|-----|-------|--------|
| [003](003-optional-cluster-yml.md) | Optional `group_vars/all/cluster.yml` | Accepted (Phase 4) |
| [004](004-universal-export-template.md) | Universal `export_template` | Accepted (Phase 4) |
| [005](005-remove-cluster-stacks.md) | Remove `cluster.yaml` `stacks:` (phases SoT) | Accepted (Phase 4 + cleanup A–E) |
| [006](006-redundant-playbooks-enabled.md) | Redundant `playbooks_enabled: true` (infer) | Accepted (Phase 5) |
| [007](007-phases-inline-aliases.md) | Inline aliases in `phases:` (remove `phase_aliases:`) | Accepted (Phase 5) |
| [008](008-phases-cli-selector.md) | Unified `--phases` CLI selector (replace `--from`/`--to`) | Accepted (Phase 5 + cleanup B complete) |
| [009](009-unify-run-stage-play.md) | Unify `run` / `stage` / `play` into one execute verb | Accepted (Phase 5; alias hard-removal Phase 1–5 done) |
| [010](010-jenkins-phases-active-choices.md) | Jenkins deploy `PHASES` Active Choices cascade (path C) | Accepted |
| [011](011-jenkins-limits-active-choices.md) | Jenkins deploy `LIMIT` Active Choices cascade | Accepted (Phase 0–5) |

Numbering continues from historical ADR 001–002 (schema v2 / engine sign-off),
which were retired after cutover; those numbers are not reused.

Related sibling decision (TF durable path): atlas-compute-provision
`docs/adr/001-tfstate-repo-prefix.md` + `docs/tfstate.md` (Phase 4 variant A).
Operator summary: [workspace.md](../workspace.md).
