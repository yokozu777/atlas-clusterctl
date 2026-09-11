#!/usr/bin/env python3
"""Pre-publish audit against the git index (what the next commit would ship).

Gates (exit 1 on failure):
  - no clusters/ci or clusters/dev paths in the index
  - no legacy secrets.yml / secrets.yaml tracked (product *.secrets.yml OK + Vault)
  - no root Jenkinsfile (sample lives under examples/internal/)
  - no org hostnames / Welcomeback / private-key markers outside allowlist
  - no Cyrillic in tracked product .py/.yml/.yaml (docs/tests/examples.internal OK)

Informational WARN (does not fail):
  - HEAD tree still contains lab paths (staged deletion not yet committed)
  - history sample still contains Welcomeback (needs filter-repo / orphan — see docs)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FINGERPRINT_RE = re.compile(
    r"(?:gitea|harbor|upload|nexus)\.mxhash\.com|"
    r"(?<![A-Za-z0-9_-])mxhash\.com|"
    r"/var/lib/mxhash|"
    r"[Ww]elcomeback|"
    r"BEGIN (?:OPENSSH |RSA )?PRIVATE KEY",
    re.IGNORECASE,
)

# Paths allowed to mention fingerprints for history / tooling context.
ALLOWLIST_RE = re.compile(
    r"^(?:SECURITY\.md|CHANGELOG\.md|docs/|tests/|notes/|examples/internal/"
    r"|clusterctl/cluster_layout\.py)"
)

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

# Product sources where Cyrillic must not appear (operator-facing docs may be RU).
CYRILLIC_SCAN_SUFFIXES = {".py", ".yml", ".yaml"}
CYRILLIC_ALLOW_PREFIXES = ("docs/", "tests/", "notes/", "examples/internal/")

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".pyc",
}


def _git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _indexed_files() -> list[str]:
    return [line for line in _git_output("ls-files").splitlines() if line.strip()]


def _publish_candidate_files() -> list[str]:
    """Indexed paths plus non-ignored untracked files (next-commit candidates)."""
    indexed = _indexed_files()
    other = [
        line
        for line in _git_output("ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    ]
    return sorted(set(indexed) | set(other))


def _is_allowlisted(rel: str) -> bool:
    return bool(ALLOWLIST_RE.match(rel))


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    indexed = _indexed_files()
    indexed_set = set(indexed)
    candidates = _publish_candidate_files()

    # --- labs must not be in the index ---
    lab_hits = sorted(
        rel for rel in indexed if rel.startswith(("clusters/ci/", "clusters/dev/"))
    )
    if lab_hits:
        errors.append(
            "clusters/ci|dev still in git index "
            f"({len(lab_hits)} paths) — git rm --cached + keep gitignore"
        )
        for rel in lab_hits[:12]:
            errors.append(f"  - {rel}")
        if len(lab_hits) > 12:
            errors.append(f"  - … +{len(lab_hits) - 12} more")

    # --- legacy monolithic secrets.yml must not be tracked ---
    # Product overlays (atlas-redis.secrets.yml) are intentional + Vault-friendly.
    secret_hits = [
        rel
        for rel in indexed
        if Path(rel).name in ("secrets.yml", "secrets.yaml")
    ]
    if secret_hits:
        errors.append("tracked legacy secrets.yml / secrets.yaml (use *.secrets.yml + Vault):")
        errors.extend(f"  - {rel}" for rel in secret_hits)

    # --- root Jenkinsfile removed from product path ---
    if "Jenkinsfile" in indexed_set:
        errors.append(
            "root Jenkinsfile is tracked — move to examples/internal/ (org sample only)"
        )
    if not (ROOT / "examples" / "internal" / "Jenkinsfile").is_file():
        # Allow missing during partial checkouts; prefer presence when publishing.
        warnings.append("examples/internal/Jenkinsfile missing on disk")

    # --- required publish surface ---
    for rel in (
        "LICENSE",
        "SECURITY.md",
        "README.md",
        "docs/pre-publish.md",
        "docs/local-labs.md",
        ".github/workflows/ci.yml",
        "tests/run_ci.sh",
        "tests/check_publish_hygiene.sh",
    ):
        # File may be untracked but present on disk during publish prep.
        if rel not in indexed_set and not (ROOT / rel).is_file():
            errors.append(f"missing required publish file: {rel}")

    # --- fingerprint scan on publish candidates (index + untracked) ---
    fp_hits: list[str] = []
    for rel in candidates:
        if _is_allowlisted(rel):
            continue
        path = ROOT / rel
        if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if FINGERPRINT_RE.search(line):
                fp_hits.append(f"{rel}:{lineno}:{line.strip()[:160]}")
    if fp_hits:
        errors.append("org fingerprint / secret markers in publish candidate paths:")
        errors.extend(f"  - {h}" for h in fp_hits[:40])
        if len(fp_hits) > 40:
            errors.append(f"  - … +{len(fp_hits) - 40} more")

    # --- Cyrillic in product py/yml ---
    cyr_hits: list[str] = []
    for rel in candidates:
        if any(rel.startswith(p) for p in CYRILLIC_ALLOW_PREFIXES):
            continue
        path = ROOT / rel
        if path.suffix.lower() not in CYRILLIC_SCAN_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if CYRILLIC_RE.search(line):
                cyr_hits.append(f"{rel}:{lineno}:{line.strip()[:120]}")
    if cyr_hits:
        errors.append(
            "Cyrillic found in product .py/.yml/.yaml "
            "(RU docs under docs/ are OK):"
        )
        errors.extend(f"  - {h}" for h in cyr_hits[:40])
        if len(cyr_hits) > 40:
            errors.append(f"  - … +{len(cyr_hits) - 40} more")

    # --- WARN: HEAD tree still has labs (need commit of staged rm) ---
    try:
        head_labs = [
            line
            for line in _git_output("ls-tree", "-r", "--name-only", "HEAD").splitlines()
            if line.startswith(("clusters/ci/", "clusters/dev/"))
        ]
    except RuntimeError:
        head_labs = []
    if head_labs and not lab_hits:
        warnings.append(
            f"HEAD commit still lists {len(head_labs)} clusters/ci|dev paths — "
            "commit the staged lab removal before a public push "
            "(working tree labs can remain via gitignore)"
        )

    # --- WARN: recent history still embeds Welcomeback (rewrite separately) ---
    try:
        hist = subprocess.run(
            ["git", "grep", "-I", "-n", "Welcomeback", "HEAD"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if hist.returncode == 0 and hist.stdout.strip():
            warnings.append(
                "Welcomeback still reachable from HEAD tree/history — "
                "rotate credentials and rewrite history before public GitHub "
                "(see docs/pre-publish.md); working-tree scrub alone is not enough"
            )
    except OSError:
        pass

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        print("FAIL: pre-publish audit", file=sys.stderr)
        return 1

    print(
        f"OK: pre-publish audit "
        f"(indexed={len(indexed)} candidates={len(candidates)}, labs=0, secrets.yml=0, "
        f"fingerprint/cyrillic clean; warnings={len(warnings)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
