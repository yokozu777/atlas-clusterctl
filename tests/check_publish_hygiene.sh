#!/usr/bin/env bash
# Fail if tracked product sources contain org lab hostnames or secret fingerprints.
# Labs under clusters/ci|dev are gitignored and are not scanned.
# SECURITY.md / docs / tests / examples/internal may mention fingerprints for context.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Org FQDNs + lab password pattern historically present in this ecosystem.
# Note: bare lab id "dev/mxhash" is allowed in code/docs; hostname *.mxhash.com is not.
PATTERN='(^|[^A-Za-z0-9_-])((gitea|harbor|upload|nexus)\.)?mxhash\.com|/var/lib/mxhash|[Ww]elcomeback|BEGIN OPENSSH PRIVATE|BEGIN RSA PRIVATE'

# Historical notes + tests + legacy alias docs in cluster_layout.
ALLOWLIST_REGEX='(^|/)(SECURITY\.md|CHANGELOG\.md)$|(^|/)docs/|(^|/)tests/|(^|/)examples/internal/|(^|/)clusterctl/cluster_layout\.py$'

hits="$(
  # Restrict to published product trees (not gitignored labs).
  grep -rEIn "$PATTERN" \
    clusterctl \
    clusters/_template \
    clusters/default \
    README.md \
    pyproject.toml \
    requirements.txt \
    requirements-dev.txt \
    cluster \
    LICENSE \
    --include='*.py' --include='*.yml' --include='*.yaml' --include='*.md' \
    --include='*.toml' --include='*.txt' --include='*.sh' --include='*.cfg' \
    --exclude-dir=.git \
    --exclude-dir=workspace \
    --exclude-dir=__pycache__ \
    --exclude-dir=.venv \
    2>/dev/null || true
)"

# Drop allowlisted paths and comment-only noise.
filtered=""
if [[ -n "${hits}" ]]; then
  filtered="$(
    printf '%s\n' "$hits" \
      | grep -vE ':[0-9]+:[[:space:]]*#' \
      | grep -vE "${ALLOWLIST_REGEX}" \
      || true
  )"
fi

if [[ -n "${filtered}" ]]; then
  printf '%s\n' "${filtered}" >&2
  echo "ERROR: org fingerprint / secret material found in public product sources" >&2
  exit 1
fi

echo "OK: publish hygiene (no org hostnames / Welcomeback / private keys in product paths)"
