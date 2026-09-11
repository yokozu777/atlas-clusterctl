#!/usr/bin/env python3
"""Parse public cluster YAML scaffolds (clusters/_template, clusters/default)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    ROOT / "clusters" / "_template",
    ROOT / "clusters" / "default",
)


def _should_parse(path: Path) -> bool:
    if path.suffix in {".yml", ".yaml"}:
        return True
    return path.name in {"hosts", "cluster.yaml"}


def main() -> int:
    errors: list[str] = []
    parsed = 0
    for base in SCAN_ROOTS:
        if not base.is_dir():
            errors.append(f"missing directory: {base.relative_to(ROOT)}")
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or not _should_parse(path):
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel}: {exc}")
                continue
            if path.name == "cluster.yaml" and raw is not None and not isinstance(raw, dict):
                errors.append(f"{rel}: expected mapping, got {type(raw).__name__}")
                continue
            parsed += 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OK: parsed {parsed} YAML files under clusters/_template and clusters/default")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
