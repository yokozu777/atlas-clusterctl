#!/usr/bin/env bash
# Phase 6 Stage 5 / P1 — prepare inventory checkout as mode-B provision_tf_state_local_dir.
#
# Env (required): INV_DIR, INV_URL
# Env (optional):
#   INV_REF          — branch name (default: main); not a commit SHA
#   INV_FETCH_MODE   — shallow | full (default: shallow)
#                      seed → shallow (dropdown scan); deploy → full (TF SoT)
#                      --depth applies only to fresh clone OR already-shallow
#                      checkouts. Never re-shallow a full working tree (seed
#                      after deploy on persistent runners).
#   INV_RESET_HARD   — true|false (default: false). When true (seed checkbox):
#                      discard dirty outside tfstate/, and on ahead/diverged
#                      git reset --hard origin/<ref> (remote is SoT for seed scan).
#                      Deploy must leave this false/unset so unpushed TF commits
#                      are never silently dropped.
#
# Policy:
#   - Durable TF SoT is ${INV_DIR}/tfstate/<cluster_id>/ (same tree as clusters/).
#   - Never create controller tfstate-repo/ under the clusterctl checkout.
#   - Dirty outside tfstate/ → fail unless INV_RESET_HARD (no whole-repo reset).
#   - Dirty under tfstate/ → discard working tree only (not commits; CI mirror of
#     provision_tf_state_git_discard_local). Unpushed commits are never discarded
#     unless INV_RESET_HARD.
#   - Refresh is fetch + checkout named branch + merge --ff-only (never
#     checkout -B FETCH_HEAD). Local ahead / diverged → fail unless INV_RESET_HARD
#     (then reset --hard to origin/<ref>).
set -euo pipefail

INV_DIR="${INV_DIR:?INV_DIR is required}"
INV_URL="${INV_URL:?INV_URL is required}"
INV_REF="${INV_REF:-main}"
INV_FETCH_MODE="${INV_FETCH_MODE:-shallow}"
INV_RESET_HARD="${INV_RESET_HARD:-false}"

case "${INV_FETCH_MODE}" in
  shallow|full) ;;
  *)
    echo "inventory: FAIL — INV_FETCH_MODE must be shallow|full (got: ${INV_FETCH_MODE})" >&2
    exit 2
    ;;
esac

inv_reset_hard_enabled() {
  case "$(printf '%s' "${INV_RESET_HARD}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

# Match role 07_tf_state_pull origin compare (ssh://host/path ↔ git@host:path).
norm_git_url() {
  local u="${1:-}"
  u="${u%.git}"
  u="$(printf '%s' "$u" | sed -E 's|^ssh://([^@/]+@)?([^/]+)/|git@\2:|')"
  printf '%s' "$u" | tr '[:upper:]' '[:lower:]'
}

echo "inventory: ${INV_URL} @ ${INV_REF} → ${INV_DIR} (INV_FETCH_MODE=${INV_FETCH_MODE} INV_RESET_HARD=${INV_RESET_HARD})"
echo "inventory: Phase 6 mode B — durable TF under ${INV_DIR}/tfstate/ (no controller tfstate-repo/)"

if [ -d tfstate-repo ]; then
  echo "inventory: NOTE leftover controller tfstate-repo/ is unused for inventory-backed leaves;"
  echo "inventory:       durable SoT is ${INV_DIR}/tfstate/. Safe after green deploy: rm -rf tfstate-repo"
fi

if [ -d "${INV_DIR}/.git" ]; then
  CUR="$(git -C "${INV_DIR}" remote get-url origin 2>/dev/null || true)"
  if [ "$(norm_git_url "${CUR}")" != "$(norm_git_url "${INV_URL}")" ]; then
    echo "inventory: origin mismatch (${CUR:-none} → ${INV_URL}); updating remote"
    git -C "${INV_DIR}" remote set-url origin "${INV_URL}"
  fi

  # Persistent runner workspaces: refuse operator/config dirt outside tfstate/.
  OUTSIDE="$(
    git -C "${INV_DIR}" status --porcelain --untracked-files=all -- \
      . ':(exclude)tfstate' ':(exclude)tfstate/**'
  )"
  if [ -n "${OUTSIDE}" ]; then
    if inv_reset_hard_enabled; then
      echo "inventory: INV_RESET_HARD — discarding dirty paths outside tfstate/"
      printf '%s\n' "${OUTSIDE}"
      git -C "${INV_DIR}" reset --hard HEAD
      git -C "${INV_DIR}" clean -fd -- \
        . ':(exclude)tfstate' ':(exclude)tfstate/**'
    else
      echo "inventory: FAIL — local modifications outside tfstate/ in ${INV_DIR}" >&2
      echo "inventory:       (force=no; never whole-repo reset on inventory):" >&2
      printf '%s\n' "${OUTSIDE}" >&2
      echo "inventory: commit/stash those paths on the runner, or remove ${INV_DIR} and reclone." >&2
      echo "inventory: seed may set INV_RESET_HARD=true to align to origin." >&2
      exit 1
    fi
  fi

  INSIDE="$(
    git -C "${INV_DIR}" status --porcelain --untracked-files=all -- tfstate
  )"
  if [ -n "${INSIDE}" ]; then
    echo "inventory: discarding working-tree changes under tfstate/ only (CI; not commits)"
    if git -C "${INV_DIR}" rev-parse --verify HEAD >/dev/null 2>&1; then
      git -C "${INV_DIR}" checkout HEAD -- tfstate 2>/dev/null || true
    fi
    git -C "${INV_DIR}" clean -fd -- tfstate
  fi

  # Fetch policy:
  #   - full mode: unshallow if needed, then fetch without --depth
  #   - shallow mode + already shallow: fetch --depth 1 (keep shallow)
  #   - shallow mode + full history: fetch WITHOUT --depth (never re-shallow)
  IS_SHALLOW="$(git -C "${INV_DIR}" rev-parse --is-shallow-repository 2>/dev/null || echo false)"
  if [ "${INV_FETCH_MODE}" = "full" ]; then
    if [ "${IS_SHALLOW}" = "true" ]; then
      echo "inventory: deepening shallow clone for INV_FETCH_MODE=full"
      git -C "${INV_DIR}" fetch --unshallow origin 2>/dev/null \
        || git -C "${INV_DIR}" fetch --deepen 2147483647 origin
    fi
    git -C "${INV_DIR}" fetch origin "${INV_REF}"
  elif [ "${IS_SHALLOW}" = "true" ]; then
    git -C "${INV_DIR}" fetch --depth 1 origin "${INV_REF}"
  else
    echo "inventory: existing non-shallow checkout — fetch without --depth (INV_FETCH_MODE=shallow)"
    git -C "${INV_DIR}" fetch origin "${INV_REF}"
  fi

  if ! git -C "${INV_DIR}" rev-parse --verify --quiet "origin/${INV_REF}^{commit}"; then
    echo "inventory: FAIL — origin/${INV_REF} missing after fetch" >&2
    exit 1
  fi

  # Named branch (not detached). Never checkout -B FETCH_HEAD (drops unpushed commits).
  if git -C "${INV_DIR}" show-ref --verify --quiet "refs/heads/${INV_REF}"; then
    git -C "${INV_DIR}" checkout "${INV_REF}"
  else
    git -C "${INV_DIR}" checkout -b "${INV_REF}" "origin/${INV_REF}"
  fi

  LOCAL="$(git -C "${INV_DIR}" rev-parse HEAD)"
  REMOTE="$(git -C "${INV_DIR}" rev-parse "origin/${INV_REF}")"
  if [ "${LOCAL}" = "${REMOTE}" ]; then
    echo "inventory: already at origin/${INV_REF} (${LOCAL})"
  elif inv_reset_hard_enabled; then
    echo "inventory: INV_RESET_HARD — git reset --hard origin/${INV_REF}"
    echo "inventory:       local=${LOCAL} origin=${REMOTE}"
    git -C "${INV_DIR}" reset --hard "origin/${INV_REF}"
  else
    BASE="$(git -C "${INV_DIR}" merge-base HEAD "origin/${INV_REF}")"
    if [ "${LOCAL}" = "${BASE}" ]; then
      echo "inventory: fast-forward ${INV_REF} → origin/${INV_REF}"
      git -C "${INV_DIR}" merge --ff-only "origin/${INV_REF}"
    elif [ "${REMOTE}" = "${BASE}" ]; then
      echo "inventory: FAIL — local ${INV_REF} is ahead of origin/${INV_REF} (unpushed commits)" >&2
      echo "inventory:       local=${LOCAL} origin=${REMOTE}" >&2
      echo "inventory:       Push inventory (incl. tfstate/) from the runner, or reset only after" >&2
      echo "inventory:       confirming remote already has the durable TF SoT." >&2
      echo "inventory:       Seed may set INV_RESET_HARD=true to drop local commits." >&2
      exit 1
    else
      echo "inventory: FAIL — local ${INV_REF} has diverged from origin/${INV_REF}" >&2
      echo "inventory:       local=${LOCAL} origin=${REMOTE} merge-base=${BASE}" >&2
      echo "inventory:       Resolve on the runner (no silent reset; mode B TF SoT)." >&2
      echo "inventory:       Seed may set INV_RESET_HARD=true to align to origin." >&2
      exit 1
    fi
  fi
else
  rm -rf "${INV_DIR}"
  if [ "${INV_FETCH_MODE}" = "full" ]; then
    git clone --branch "${INV_REF}" "${INV_URL}" "${INV_DIR}"
  else
    git clone --depth 1 --branch "${INV_REF}" "${INV_URL}" "${INV_DIR}"
  fi
fi

test -d "${INV_DIR}/clusters"
test -d "${INV_DIR}/.git"

if [ ! -e "${INV_DIR}/tfstate" ]; then
  echo "inventory: NOTE ${INV_DIR}/tfstate/ not present yet — 07 creates per-cluster paths on first provision"
fi

# Explicit non-goal: do not mkdir/clone tfstate-repo beside clusterctl.
if [ -e tfstate-repo ] && [ ! -d tfstate-repo ]; then
  echo "inventory: WARN unexpected non-directory tfstate-repo path present" >&2
fi

echo "inventory: ready (clusters.path parent = mode-B local_dir; mode=${INV_FETCH_MODE})"
