#!/usr/bin/env python3
"""Validate full-k8s SoT (local lab ``dev/mxhash`` or public ``_template/k8s_full``)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clusterctl.pipeline_fixture import (
    PUBLIC_REFERENCE_REL,
    REFERENCE_CLUSTER_ID,
    REFERENCE_CLUSTER_REL,
    load_reference_cluster_config,
)
from clusterctl.playbooks_validate import validate_org_baseline_playbooks


def main() -> int:
    config = load_reference_cluster_config(ROOT)
    config.validate()
    validate_org_baseline_playbooks(ROOT)
    assert config.playbooks is not None and config.phases is not None
    invocations = config.phases.invocation_count(config.playbooks)
    source = (
        REFERENCE_CLUSTER_REL.as_posix()
        if (ROOT / REFERENCE_CLUSTER_REL).is_file()
        else PUBLIC_REFERENCE_REL.as_posix()
    )
    label = config.cluster_id or REFERENCE_CLUSTER_ID
    print(
        f"OK: {label} ({source}) — {len(config.phases.phases)} phases, "
        f"{invocations} invocations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
