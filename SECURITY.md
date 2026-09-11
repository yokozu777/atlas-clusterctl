# Security

## Reporting

If you discover a security issue in this repository, please open a private report with the
maintainers (do not file a public issue with exploit details or credentials).

## Secrets in this repo

Do **not** commit plaintext live credentials:

- Proxmox API tokens / SSH passwords used by provision overlays
- DNS TSIG / RFC2136 secrets
- Jenkins / registry / CA / vault passwords
- SSH private keys
- legacy monolithic `secrets.yml` / `*.vault` with live values
- live inventories with production hosts
- terraform state blobs under `workspace/`

Prefer per-product overlays `group_vars/all/atlas-<repo>.secrets.yml` (Vault-encrypt in
place; **not** gitignored). Templates and siblings ship `CHANGEME` placeholders.
A monolithic `group_vars/all/secrets.yml` is **deprecated** (still gitignored if present —
do not use for new leaves).

## Local labs vs public tree

Working org labs (`ci/`, `dev/`, …) are **local-only**. Preferred wiring: a private
inventory tree pointed at by local `.config/config.yaml` (`clusters.path`) or
`ATLAS_CLUSTERS_ROOT` — template: [`.config/config.yaml.example`](.config/config.yaml.example),
runbook: [`docs/local-labs.md`](docs/local-labs.md). Optional `workspace.path` /
`ATLAS_WORKSPACE_ROOT` relocates runtime trees ([`docs/workspace.md`](docs/workspace.md)).

In-tree `clusters/ci/` and `clusters/dev/` (if used) stay on the workstation for
`./cluster use` / `validate` / `run`, but are **gitignored** and must not be pushed to a
public remote. Published scaffolds live under `clusters/_template/` and `clusters/default/`.

Restore or keep labs outside the public tree (private inventory repo, private backup, or
local-only directories already present on disk).

## Git history note (pre-publish)

This repository’s history and former tracked labs contained org hostnames and lab credentials,
including:

- DNS / FQDN suffixes such as `mxhash.com`, `dev-mxhash.com`
- Sibling / registry hosts such as `gitea.mxhash.com`, `harbor.mxhash.com`, `upload.mxhash.com`
- Lab password fingerprints matching `Welcomeback*`
- Default Jenkins pipeline targeting `dev/mxhash` with site credential ids (`ssh_git`, built-in agent)

Working-tree **tracked** product paths are scrubbed toward neutral `example.com` /
`CHANGEME` values. Historical blobs remain reachable until history is rewritten.

The root `Jenkinsfile` was an org-coupled controller pipeline (site job names, lab cluster ids,
Cyrillic operator messages). It is no longer part of the product path; a **portable** sample lives
under `examples/internal/` (neutral `CLUSTER_ID`, optional credential parameter,
Docker agent `Jenkinsfile` + local-agent `Jenkinsfile.local`).

## Guardrails (publish track)

- `.gitignore` excludes `clusters/ci/`, `clusters/dev/`, and deprecated monolithic `secrets.yml`
  (product `*.secrets.yml` stay trackable for Vault)
- `./tests/run_ci.sh` + `.github/workflows/ci.yml` run the public track (no labs required),
  fingerprint hygiene, and `tests/check_pre_publish_audit.py`
- `tests/test_local_labs_contract.py` asserts labs stay untracked / ignored when present
- Do not re-add live lab overlays to tracked paths

Full pre-publish checklist (push dry-run, credential rotation, history rewrite):
[`docs/pre-publish.md`](docs/pre-publish.md).

Before making this repository public:

1. Confirm no live secrets remain in **tracked** files; rotate anything that may have been pushed.
2. Confirm `git ls-files clusters/ci clusters/dev` is empty before push.
3. Follow [`docs/pre-publish.md`](docs/pre-publish.md) — including history rewrite
   (`git filter-repo` / BFG) or an orphan cleaned branch.
4. Assume historical blobs remain reachable until remotes are rewritten / force-replaced.
