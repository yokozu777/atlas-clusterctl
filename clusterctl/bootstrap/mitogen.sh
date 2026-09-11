#!/bin/bash
# Mitogen strategy plugin path for ansible-playbook (clusterctl bootstrap).
set -euo pipefail

ansible_mitogen_configure_strategy_plugins() {
  if [[ -n "${ANSIBLE_STRATEGY_PLUGINS:-}" && -d "${ANSIBLE_STRATEGY_PLUGINS}" ]]; then
    return 0
  fi

  local strategy_dir
  strategy_dir="$(
    python3 -c 'import ansible_mitogen, pathlib; print(pathlib.Path(ansible_mitogen.__file__).resolve().parent / "plugins" / "strategy")' \
      2>/dev/null
  )" || strategy_dir=

  if [[ -z "$strategy_dir" || ! -d "$strategy_dir" ]]; then
    return 0
  fi

  export ANSIBLE_STRATEGY_PLUGINS="$strategy_dir"
}

ansible_mitogen_unset_strategy_plugins() {
  unset ANSIBLE_STRATEGY_PLUGINS
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  ansible_mitogen_configure_strategy_plugins
  printf 'ANSIBLE_STRATEGY_PLUGINS=%s\n' "${ANSIBLE_STRATEGY_PLUGINS:-}"
fi
