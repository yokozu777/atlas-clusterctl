# jenkins_seed_inventory

Minimal offline `clusters/` tree for Jenkins seed scanners:

- `clusterctl.tools.list_deployable_clusters` (`CLUSTER_ID` membership)
- `clusterctl.tools.list_cluster_phases` (`CLUSTER_ID → phases` reference map)
- `clusterctl.tools.list_cluster_limits` (`CLUSTER_ID →` LIMIT catalog:
  groups then host keys)

| Path | Role |
|------|------|
| `fixture/postgresql` | Deployable + phases + YAML `hosts` (`pgsql_*` groups / `10.20.0.*`) |
| `fixture/redis` | Deployable + phases + YAML `hosts` (`redis_*` groups / `10.30.0.*`) |
| `lab/alpha` | Deployable + phases + YAML `hosts` (`alpha` / `10.40.0.*`) |
| `fixture/hosts_only` | Deployable layout for the **scanner** (INI `hosts` only — ADR 003 usable). Omitted from phases map **and** limits map (extractors are YAML-only) |
| `fixture/default`, `default/default` | Policy — **not** deployable |
| `_template/ignored` | Underscore env — skipped |
| `fixture/broken_empty` | Empty dir — not usable |

Membership = deployable layout for the choice dropdown, not a validate/smoke
guarantee. Phases map = YAML `phases:` catalog only (no inventory `when:`).
Limits map = YAML inventory groups + host **keys** only. Deploy empty `PHASES` /
`LIMIT` use plan SoT / omit `--limit` — see follow-ups in `docs/jenkins-seed.md`.

See `tests/test_list_deployable_clusters.py`, `tests/test_list_cluster_phases.py`,
`tests/test_list_cluster_limits.py`.
