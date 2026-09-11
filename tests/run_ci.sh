#!/usr/bin/env bash
# Local parity with .github/workflows/ci.yml (public track — no live labs required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export ATLAS_CLUSTER_ROOT="${ATLAS_CLUSTER_ROOT:-$ROOT}"
# Isolate workstation inventory / workspace overrides from public CI.
unset ATLAS_CLUSTERS_ROOT || true
unset ATLAS_WORKSPACE_ROOT || true
# Ignore local config.yaml (may point at private inventory on operator machines).
export ATLAS_CLUSTERCTL_CONFIG="${TMPDIR:-/tmp}/atlas-clusterctl-ci-empty-$$.yaml"
: > "$ATLAS_CLUSTERCTL_CONFIG"
# Do not inherit workstation PLAYBOOKS_* / lab overrides into CI gates.
for key in $(env | awk -F= '/^PLAYBOOKS_/ {print $1}'); do
  unset "${key}" || true
done

echo "== packaging / layout smoke =="
test -f LICENSE
test -f SECURITY.md
test -f README.md
test -f pyproject.toml
test -f requirements.txt
test -f requirements-dev.txt
test -f .github/workflows/ci.yml
test -x cluster
test -x tests/run_ci.sh
test -x tests/check_publish_hygiene.sh
test -f tests/check_public_templates_yaml.py
test -f tests/check_pre_publish_audit.py
test -f docs/pre-publish.md
test -d clusters/_template/k8s_full
test -f clusters/_template/k8s_full/cluster.yaml
# Public leaf templates (./cluster init --template <name>)
for leaf in infra_edge jenkins_agent kafka postgresql redis; do
  test -d "clusters/_template/${leaf}"
  test -f "clusters/_template/${leaf}/cluster.yaml"
done
test -f clusters/default/default/cluster.yaml
# Convention: no repo-root scripts/ (use ./cluster + tests/ helpers)
test ! -d scripts
echo "OK: packaging layout"

echo "== unittest (public + optional lab skips) =="
python3 -m unittest discover -s tests -q

echo "== ci_preflight (legacy + org baseline + validate --repo) =="
python3 -m clusterctl.tools.ci_preflight --skip-tests

echo "== public template YAML parse =="
python3 tests/check_public_templates_yaml.py

echo "== publish hygiene scan =="
./tests/check_publish_hygiene.sh

echo "== pre-publish audit (git index + candidates) =="
python3 tests/check_pre_publish_audit.py

echo "CI checks passed."
