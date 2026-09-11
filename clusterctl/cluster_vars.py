"""Emit cluster variable paths for shell scripts (inventory group_vars / host_vars)."""

from __future__ import annotations

import argparse
import os
import shlex
import sys

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.paths import list_cluster_ids, repo_root


def export_env(ctx: ClusterContext) -> str:
    lines = [
        f"export CLUSTER_ID={shlex.quote(ctx.cluster_id)}",
        f"export CLUSTER_INVENTORY={shlex.quote(str(ctx.inventory))}",
        f"export CLUSTER_GROUP_VARS_DIR={shlex.quote(str(ctx.config_dir / 'group_vars'))}",
        f"export CLUSTER_HOST_VARS_DIR={shlex.quote(str(ctx.config_dir / 'host_vars'))}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cluster inventory var paths (group_vars/ and host_vars/)"
    )
    parser.add_argument("--cluster", metavar="ID")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env", help="print bash export CLUSTER_* for shell integration")
    list_p = sub.add_parser("list", help="list cluster ids under clusters/")
    list_p.add_argument("--paths", action="store_true", help="print config dir paths")
    paths_p = sub.add_parser("paths", help="print group_vars/all/*.yml paths")
    paths_p.add_argument(
        "--hosts",
        action="store_true",
        help="print host_vars/* paths (TAB-separated: hostname<TAB>path)",
    )
    args = parser.parse_args(argv)

    try:
        root = repo_root()
        os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))

        if args.command == "list":
            ids = list_cluster_ids(root)
            if not ids:
                print("(no clusters under clusters/)")
            for cluster_id in ids:
                if getattr(args, "paths", False):
                    print(root / "clusters" / cluster_id)
                else:
                    print(cluster_id)
            return 0

        ctx = ClusterContext.load(cluster_id=args.cluster)
        if args.command == "paths":
            if getattr(args, "hosts", False):
                for hostname, path in ctx.host_var_files:
                    print(f"{hostname}\t{path}")
            else:
                for path in ctx.group_var_files:
                    print(path)
        elif args.command == "env":
            print(export_env(ctx))
        return 0
    except ClusterctlError as exc:
        print(f"cluster_vars: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
