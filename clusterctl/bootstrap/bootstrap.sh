#!/bin/bash
# Bootstrap controller environment before ansible-playbook (clusterctl).
set -euo pipefail

ROOT="${ATLAS_CLUSTER_ROOT:?ATLAS_CLUSTER_ROOT is required}"
WORKSPACE="${CLUSTER_WORKSPACE_ROOT:?CLUSTER_WORKSPACE_ROOT is required}"
cd "$ROOT"

# Playbook repo availability is enforced by clusterctl (./cluster repos sync + resolver).
# shellcheck source=mitogen.sh disable=SC1091
source "${ROOT}/clusterctl/bootstrap/mitogen.sh"
ansible_mitogen_configure_strategy_plugins

# Install Galaxy collections under workspace — never repo root (validate --repo blocks .ansible/).
# requirements.yml lives in playbook repos; clusterctl sets PLAYBOOK_REQUIREMENTS_FILES.
COLLECTIONS="${ANSIBLE_COLLECTIONS_PATHS:-${WORKSPACE}/.ansible/collections}"
mkdir -p "${COLLECTIONS}"
export ANSIBLE_COLLECTIONS_PATHS="${COLLECTIONS}"

if [[ -z "${PLAYBOOK_REQUIREMENTS_FILES:-}" ]]; then
  echo "bootstrap: no playbook requirements.yml files (skip galaxy install)"
else
  IFS=':' read -r -a REQ_FILES <<< "${PLAYBOOK_REQUIREMENTS_FILES}"
  for req in "${REQ_FILES[@]}"; do
    [[ -n "${req}" && -f "${req}" ]] || continue
    echo "bootstrap: ansible-galaxy collection install -r ${req}"
    ansible-galaxy collection install -r "${req}" -p "${COLLECTIONS}"
  done
fi
