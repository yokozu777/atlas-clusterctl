# Pre-publish checklist (`atlas-clusterctl`)

Operator checklist before opening a **public** remote. This does **not** rewrite git
history — that is a separate, destructive step after the working tree is green.

Companion: [`SECURITY.md`](../SECURITY.md), [`local-labs.md`](local-labs.md),
[`./tests/run_ci.sh`](../tests/run_ci.sh).

## Phase 7 status — working-tree publish readiness

| Track | Status |
|-------|--------|
| Automated gates (`./tests/run_ci.sh`, hygiene, pre-publish audit) | **Ready** (exit 0; history WARN allowed) |
| Working-tree / index checklist below | **Ready** (items marked `[x]` are verified) |
| Credential rotation for historical fingerprints | **Operator-owned** (keep `[ ]`) |
| `[project.urls]` Source/Documentation | **Operator-owned** — fill when the public remote URL is known |
| History rewrite / orphan publish | **Operator-owned** (never automated; see below) |

Phase 7 closes **working-tree publish readiness**. Opening a public GitHub/GitLab
still requires the operator-owned rows (rotation + history rewrite or explicit
acceptance that old blobs remain reachable).

## Status of publish steps 0–6

| Step | Focus | Expectation before this checklist |
|------|--------|-----------------------------------|
| 0 | Hygiene + local/public split | Labs gitignored; `git rm --cached` staged if needed |
| 1 | Scrub `_template` / `default` | `example.com` / `CHANGEME` in public scaffolds |
| 2 | Docs templates-first | No required `use <lab-id>` for public readers |
| 3 | Dual-track tests | Unittest green without `clusters/ci` / `dev` |
| 4 | Packaging | `pyproject.toml`, requirements, standalone README; no placeholder `[project.urls]` until public remote exists |
| 5 | CI | `./tests/run_ci.sh` + `.github/workflows/ci.yml` |
| 6 | Local labs runbook | [`local-labs.md`](local-labs.md) + contract tests |

## Automated gates (run locally)

```bash
./tests/run_ci.sh
# includes: hygiene + pre-publish audit (git index)

python3 tests/check_pre_publish_audit.py
./tests/check_publish_hygiene.sh
```

`check_pre_publish_audit.py` inspects the **git index** (what the next commit would ship):

- no `clusters/ci/` or `clusters/dev/` paths
- no tracked legacy `secrets.yml` / `secrets.yaml` (product `*.secrets.yml` OK; Vault recommended)
- no root `Jenkinsfile` (sample under `examples/internal/` only)
- no org hostnames / `Welcomeback` / private-key markers outside allowlist
- no Cyrillic in product `.py` / `.yml` / `.yaml` (`docs/` may stay RU)

Informational **WARN** (does not fail the gate): `Welcomeback` / lab paths still
reachable from **git history** — fix via history rewrite before a public remote.

## Manual checklist

### Working tree / next commit

- [x] `./tests/run_ci.sh` exits 0 (with or without local labs on disk)
- [x] `git ls-files clusters/ci clusters/dev` is **empty**
- [x] `git check-ignore -v clusters/dev/k8s/cluster.yaml` reports ignored (if in-tree lab present)
- [x] Lab paths are absent from the index (no `clusters/ci|dev` to ship); commit any
      remaining publish-readiness diffs on your release branch before the first public push
- [x] Publish surface is present and tracked: `LICENSE`, `SECURITY.md`, `.github/`,
      `pyproject.toml`, `requirements*.txt`, `docs/local-labs.md`, `docs/pre-publish.md`,
      CI helpers under `tests/`
- [ ] When the public remote URL is known, add `[project.urls]` Source/Documentation
      (never private forge hostnames; do not use fake placeholders)
- [x] Public scaffolds under `clusters/_template/` and `clusters/default/` use
      `example.com` / `CHANGEME` for DNS identity; product hygiene rejects org FQDNs /
      `Welcomeback` / private keys (RFC1918 placeholders in examples are intentional)
- [x] Root has no `scripts/` directory (layout convention — use `./cluster` / `tests/`)

### Credentials

- [ ] Rotate any passwords / tokens that appeared in historical labs or templates
      (including fingerprints matching `Welcomeback*`, org registry/Gitea accounts)
- [x] Confirm no live legacy `secrets.yml` / `secrets.yaml` is tracked:
      `git ls-files | grep -E '(^|/)secrets\.ya?ml$'` (empty).
      Product `atlas-*.secrets.yml` may be tracked when Vault-encrypted (preferred).

### Push dry-run (no labs in payload)

```bash
# Index must already exclude labs:
git ls-files clusters/ci clusters/dev   # empty

# What the next commit would contain under clusters/:
git ls-files clusters/ | head

# Optional pack of the index tree (no working-tree ignored labs):
git archive --format=tar -o /tmp/atlas-clusterctl-index.tar HEAD
# After committing lab removals, re-run archive and confirm:
tar -tf /tmp/atlas-clusterctl-index.tar | grep -E '^clusters/(ci|dev)/' || echo 'OK: no labs in archive'
```

Do **not** `git add clusters/ci` or `clusters/dev`.

## History rewrite (separate, after green working tree)

Current `HEAD` / older commits still contain former lab trees and password fingerprints
(pre-publish audit emits a **WARN** for `Welcomeback` in history). Working-tree scrub
alone is **not** enough for a public GitHub.

Choose one:

1. **`git filter-repo` / BFG** — purge paths and blob strings (`mxhash.com`, `Welcomeback`,
   former `clusters/ci|dev`, embedded credentials), then force-replace remotes; or
2. **Orphan branch** — export only the cleaned tree onto a new root commit and publish that.

Document the rewrite in the release notes. Re-clone after rewrite; keep local labs via
gitignore restore ([local-labs.md](local-labs.md)).

This repository does **not** automate filter-repo (destructive; operator-owned).

## Done criteria

| Criterion | Phase 7 (this doc) | Public remote open |
|-----------|--------------------|--------------------|
| Automated gates green on the tree you intend to publish | required | required |
| Working-tree checklist `[x]` items verified | required | required |
| Operator checklist (`[project.urls]`, credential rotation) | optional until remote known | required |
| History rewrite (or orphan) **or** explicit acceptance of historical blobs | out of scope here | required (rewrite strongly recommended) |

Filter-repo / orphan publish remains **out of scope** for automated CI.
