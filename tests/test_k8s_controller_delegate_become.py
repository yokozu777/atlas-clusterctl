"""Controller-delegated k8s tasks must not inherit play-level become.

Play-level become: true stays for SSH/sudo on nodes. Tasks that run on the
Ansible controller (delegate_to k8s_cluster_fact_host / kubeadm_join_fact_host)
must set become: false so krang does not call sudo.

Tasks delegated to kubeadm_join_run_host (the first control-plane node) must
set connection: ssh so a localhost play does not inherit connection: local.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any, Iterator

import yaml

SIBLING_ROOT = Path(__file__).resolve().parents[1].parent

CORE_REPO = SIBLING_ROOT / "atlas-k8s-core"
ADDONS_REPO = SIBLING_ROOT / "atlas-k8s-addons"

_CONTROLLER_DELEGATE_RE = re.compile(
    r"^(?:"
    r"\{\{\s*k8s_cluster_fact_host\s*\}\}|"
    r"\{\{\s*kubeadm_join_fact_host(?:\s*\|\s*default\([^)]+\))?\s*\}\})$"
)

_TASK_NEST_KEYS = ("block", "rescue", "always", "pre_tasks", "tasks", "post_tasks")

_JOIN_PUBLISH_NAMES = frozenset(
    (
        "Publish worker join command fact",
        "Publish control-plane join command fact",
    )
)


def _skip_unless_repo(path: Path) -> None:
    if not path.is_dir():
        raise unittest.SkipTest(f"sibling repo not present: {path}")


def _is_controller_delegate(delegate_to: Any) -> bool:
    if not isinstance(delegate_to, str):
        return False
    return bool(_CONTROLLER_DELEGATE_RE.match(delegate_to.strip()))


def _is_run_host_delegate(delegate_to: Any) -> bool:
    if not isinstance(delegate_to, str):
        return False
    return "kubeadm_join_run_host" in delegate_to


def _walk_task_maps(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, list):
        for item in node:
            yield from _walk_task_maps(item)
        return
    if not isinstance(node, dict):
        return
    if "delegate_to" in node:
        yield node
    for key in _TASK_NEST_KEYS:
        if key in node:
            yield from _walk_task_maps(node[key])


def _yaml_files(repo: Path) -> list[Path]:
    tasks_root = repo / "roles"
    if not tasks_root.is_dir():
        return []
    files = list(tasks_root.glob("*/tasks/**/*.yml"))
    files.extend(tasks_root.glob("*/tasks/**/*.yaml"))
    return sorted(files)


def _delegate_tasks(repo: Path) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in _yaml_files(repo):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        for task in _walk_task_maps(loaded):
            found.append((path, task))
    return found


def _controller_delegate_tasks(repo: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, task)
        for path, task in _delegate_tasks(repo)
        if _is_controller_delegate(task.get("delegate_to"))
    ]


def _all_repos_controller_tasks() -> list[tuple[Path, dict[str, Any]]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for repo in (CORE_REPO, ADDONS_REPO):
        matches.extend(_controller_delegate_tasks(repo))
    return matches


class K8sControllerDelegateBecomeTest(unittest.TestCase):
    def test_controller_delegates_set_become_false(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        matches = _all_repos_controller_tasks()
        self.assertGreaterEqual(len(matches), 11, matches)
        for path, task in matches:
            name = task.get("name", "<unnamed>")
            self.assertIs(
                task.get("become"),
                False,
                f"{path}: {name} delegates to controller but become is {task.get('become')!r}",
            )

    def test_no_literal_localhost_delegate_to(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        literals: list[str] = []
        for repo in (CORE_REPO, ADDONS_REPO):
            for path, task in _delegate_tasks(repo):
                delegate_to = task.get("delegate_to")
                if isinstance(delegate_to, str) and delegate_to.strip() == "localhost":
                    literals.append(f"{path}: {task.get('name', '<unnamed>')}")
        self.assertEqual(literals, [])

    def test_join_token_publish_sets_delegate_facts(self) -> None:
        _skip_unless_repo(CORE_REPO)
        found = [
            task
            for path, task in _controller_delegate_tasks(CORE_REPO)
            if task.get("name") == "Publish join token requirement flag"
        ]
        self.assertEqual(len(found), 1, found)
        self.assertIs(found[0].get("delegate_facts"), True)

    def test_generate_join_publish_uses_connection_local(self) -> None:
        _skip_unless_repo(CORE_REPO)
        found = [
            task
            for path, task in _controller_delegate_tasks(CORE_REPO)
            if task.get("name") in _JOIN_PUBLISH_NAMES
        ]
        self.assertEqual(
            {task.get("name") for task in found},
            set(_JOIN_PUBLISH_NAMES),
            found,
        )
        for task in found:
            self.assertEqual(task.get("connection"), "local", task.get("name"))

    def test_cluster_state_play_keeps_become_true(self) -> None:
        _skip_unless_repo(CORE_REPO)
        playbook = CORE_REPO / "playbooks/cluster_core.yaml"
        docs = yaml.safe_load(playbook.read_text(encoding="utf-8"))
        state_plays = [
            play
            for play in docs
            if isinstance(play, dict)
            and any(
                isinstance(role, dict) and role.get("role") == "04_cluster_state"
                for role in (play.get("roles") or [])
            )
        ]
        self.assertEqual(len(state_plays), 1, state_plays)
        self.assertIs(state_plays[0].get("become"), True)

    def test_join_run_host_delegates_use_ssh_and_become(self) -> None:
        _skip_unless_repo(CORE_REPO)
        found = [
            (path, task)
            for path, task in _delegate_tasks(CORE_REPO)
            if _is_run_host_delegate(task.get("delegate_to"))
        ]
        self.assertGreaterEqual(len(found), 4, found)
        for path, task in found:
            name = task.get("name", "<unnamed>")
            self.assertEqual(
                task.get("connection"),
                "ssh",
                f"{path}: {name}",
            )
            self.assertIs(
                task.get("become"),
                True,
                f"{path}: {name} become is {task.get('become')!r}",
            )


if __name__ == "__main__":
    unittest.main()
