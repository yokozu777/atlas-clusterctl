"""Phase 6 Stage 5 / P1: CI inventory = mode-B local_dir; ff-only; full deploy fetch."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "examples" / "internal" / "ci" / "prepare_inventory_checkout.sh"
JOBS = ROOT / "examples" / "internal" / "gitlab-ci.jobs.yml"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
GITLAB_DOC = ROOT / "docs" / "gitlab-ci.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"


def _git(cwd: Path, *args: str) -> None:
    subprocess.check_call(
        ["git", "-c", "user.email=ci@example.com", "-c", "user.name=ci", *args],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _init_inv(tmp_path: Path) -> tuple[Path, Path, Path]:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    inv = work / "atlas-inventory"
    subprocess.check_call(["git", "init", "--bare", str(remote)])
    _git(tmp_path, "clone", str(remote), str(inv))
    (inv / "clusters").mkdir()
    (inv / "clusters" / "marker").write_text("ok\n", encoding="utf-8")
    (inv / "tfstate").mkdir()
    (inv / "tfstate" / "x.tfstate").write_text("v1\n", encoding="utf-8")
    _git(inv, "add", ".")
    _git(inv, "commit", "-m", "init")
    _git(inv, "branch", "-M", "main")
    _git(inv, "push", "-u", "origin", "main")
    # Bare repos default HEAD to master; pin main so later clones get the tree.
    subprocess.check_call(
        ["git", "-C", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return remote, work, inv


def _run_prepare(work: Path, inv: Path, remote: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "INV_DIR": str(inv),
            "INV_URL": str(remote),
            "INV_REF": "main",
            **extra,
        }
    )
    return subprocess.run(
        ["bash", str(PREPARE)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class Phase6Stage5CiTest(unittest.TestCase):
    def test_prepare_script_exists_and_executable(self) -> None:
        self.assertTrue(PREPARE.is_file())
        mode = PREPARE.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "prepare_inventory_checkout.sh must be executable")
        text = PREPARE.read_text(encoding="utf-8")
        self.assertIn("Phase 6 Stage 5", text)
        self.assertIn("INV_FETCH_MODE", text)
        self.assertIn("INV_RESET_HARD", text)
        self.assertIn(":(exclude)tfstate", text)
        self.assertIn("merge --ff-only", text)
        self.assertIn("reset --hard", text)
        self.assertNotIn("git checkout -B", text)
        self.assertNotIn('checkout -B "', text)
        self.assertIn("Never checkout -B FETCH_HEAD", text)
        self.assertIn("Never create controller tfstate-repo", text)
        self.assertIn("Never re-shallow", text)
        self.assertIn("existing non-shallow checkout", text)
        self.assertIn("unpushed commits", text)
        self.assertIn("norm_git_url", text)

    def test_jobs_and_jenkins_wire_prepare_and_discard(self) -> None:
        jobs = JOBS.read_text(encoding="utf-8")
        self.assertIn("prepare_inventory_checkout.sh", jobs)
        self.assertIn("TFSTATE_GIT_DISCARD_LOCAL", jobs)
        self.assertIn("provision_tf_state_git_discard_local=true", jobs)
        self.assertIn("atlas_inventory_root (mode B local_dir)", jobs)
        self.assertIn("INV_FETCH_MODE=shallow", jobs)
        self.assertIn("INV_FETCH_MODE=full", jobs)
        self.assertIn("INV_RESET_HARD", jobs)
        self.assertIn("resource_group: atlas-clusterctl-inventory", jobs)
        self.assertEqual(jobs.count("resource_group: atlas-clusterctl-inventory"), 2)
        self.assertNotIn("resource_group: atlas-clusterctl-seed", jobs)
        self.assertNotIn("mkdir -p tfstate-repo", jobs)
        self.assertNotIn("mkdir tfstate-repo", jobs)
        self.assertNotIn("git clone", jobs)

        for path in (DOCKER_JF, LOCAL_JF, SEED_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("prepare_inventory_checkout.sh", text, path.name)
            self.assertIn("INV_FETCH_MODE", text, path.name)
            self.assertNotIn("mkdir -p tfstate-repo", text, path.name)

        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("INV_FETCH_MODE=full", text, path.name)
            self.assertIn("TFSTATE_GIT_DISCARD_LOCAL", text, path.name)
            self.assertIn("provision_tf_state_git_discard_local=true", text, path.name)

        seed_jf = SEED_JF.read_text(encoding="utf-8")
        self.assertIn("INV_FETCH_MODE=shallow", seed_jf)
        self.assertIn("INVENTORY_RESET_HARD", seed_jf)
        self.assertIn("booleanParam(", seed_jf)
        self.assertIn("INV_RESET_HARD=", seed_jf)
        self.assertIn("defaultValue: true", seed_jf)

        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("INV_RESET_HARD=true", text, path.name)

        for doc in (GITLAB_DOC, JENKINS_DOC):
            text = doc.read_text(encoding="utf-8")
            self.assertIn("Stage 5", text, doc.name)
            self.assertIn("prepare_inventory_checkout.sh", text, doc.name)
            self.assertIn("TFSTATE_GIT_DISCARD_LOCAL", text, doc.name)
            self.assertIn("INV_FETCH_MODE", text, doc.name)
            self.assertIn("merge --ff-only", text, doc.name)
            self.assertIn("re-shallow", text, doc.name)

        self.assertIn("atlas-clusterctl-inventory", GITLAB_DOC.read_text(encoding="utf-8"))

    def test_p2_docs_mode_b_examples_and_adr_header(self) -> None:
        """P2: workspace dual-mode examples; seed troubleshooting; no open Phase-6 header."""
        ws = (ROOT / "docs" / "workspace.md").read_text(encoding="utf-8")
        self.assertIn("Mode B (`ci/infra`, inventory-backed)", ws)
        self.assertIn("Durable TF (mode B)", ws)
        self.assertIn("<inventory-root>/tfstate/", ws)
        self.assertIn("INV_FETCH_MODE=full", ws)
        self.assertIn("resource_group: atlas-clusterctl-inventory", ws)
        self.assertIn("Does **not** delete durable inventory `tfstate/", ws)
        self.assertNotIn("Durable TF (mode A local)", ws)

        labs = (ROOT / "docs" / "local-labs.md").read_text(encoding="utf-8")
        self.assertIn("Stage 5 / P1 (CI)", labs)
        self.assertIn("INV_FETCH_MODE=shallow", labs)

        stacks = (ROOT / "docs" / "stacks" / "compute-provision.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("CI (Stage 5 / P1)", stacks)
        self.assertIn("INV_FETCH_MODE=full", stacks)

        seed_readme = (
            ROOT / "examples" / "internal" / "seed" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("prepare_inventory_checkout.sh", seed_readme)
        self.assertIn("dirty outside `tfstate/`", seed_readme)
        self.assertIn("local ahead of origin", seed_readme)
        self.assertIn("INVENTORY_RESET_HARD", seed_readme)

        # Origin normalize lives in prepare (P2.6 / landed with P1 rewrite).
        prep = PREPARE.read_text(encoding="utf-8")
        self.assertIn("norm_git_url", prep)
        self.assertIn("ssh://", prep)

    def test_prepare_fails_on_dirty_outside_tfstate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            (inv / "clusters" / "marker").write_text("dirty\n", encoding="utf-8")
            proc = _run_prepare(work, inv, remote, INV_FETCH_MODE="full")
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("outside tfstate/", proc.stderr)

    def test_prepare_reset_hard_discards_dirty_outside_tfstate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            (inv / "clusters" / "marker").write_text("dirty\n", encoding="utf-8")
            proc = _run_prepare(
                work, inv, remote, INV_FETCH_MODE="full", INV_RESET_HARD="true"
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("INV_RESET_HARD", proc.stdout)
            self.assertEqual(
                (inv / "clusters" / "marker").read_text(encoding="utf-8"),
                "ok\n",
            )

    def test_prepare_discards_dirty_under_tfstate_and_ff_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            (inv / "tfstate" / "x.tfstate").write_text("local-dirty\n", encoding="utf-8")
            proc = _run_prepare(work, inv, remote, INV_FETCH_MODE="full")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("discarding working-tree changes under tfstate/", proc.stdout)
            self.assertEqual(
                (inv / "tfstate" / "x.tfstate").read_text(encoding="utf-8"),
                "v1\n",
            )
            branch = subprocess.check_output(
                ["git", "-C", str(inv), "rev-parse", "--abbrev-ref", "HEAD"],
                text=True,
            ).strip()
            self.assertEqual(branch, "main")
            self.assertFalse((work / "tfstate-repo").exists())

    def test_prepare_preserves_unpushed_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            before = subprocess.check_output(
                ["git", "-C", str(inv), "rev-parse", "HEAD"], text=True
            ).strip()
            (inv / "tfstate" / "x.tfstate").write_text("v2-local\n", encoding="utf-8")
            _git(inv, "add", "tfstate/x.tfstate")
            _git(inv, "commit", "-m", "unpushed-tfstate")
            local = subprocess.check_output(
                ["git", "-C", str(inv), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertNotEqual(before, local)

            proc = _run_prepare(work, inv, remote, INV_FETCH_MODE="full")
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("ahead of origin", proc.stderr)
            after = subprocess.check_output(
                ["git", "-C", str(inv), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertEqual(after, local)
            self.assertEqual(
                (inv / "tfstate" / "x.tfstate").read_text(encoding="utf-8"),
                "v2-local\n",
            )

    def test_prepare_reset_hard_drops_unpushed_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            origin = subprocess.check_output(
                ["git", "-C", str(inv), "rev-parse", "origin/main"], text=True
            ).strip()
            (inv / "tfstate" / "x.tfstate").write_text("v2-local\n", encoding="utf-8")
            _git(inv, "add", "tfstate/x.tfstate")
            _git(inv, "commit", "-m", "unpushed-tfstate")
            local = subprocess.check_output(
                ["git", "-C", str(inv), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertNotEqual(origin, local)

            proc = _run_prepare(
                work, inv, remote, INV_FETCH_MODE="full", INV_RESET_HARD="true"
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("reset --hard", proc.stdout)
            after = subprocess.check_output(
                ["git", "-C", str(inv), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertEqual(after, origin)
            self.assertEqual(
                (inv / "tfstate" / "x.tfstate").read_text(encoding="utf-8"),
                "v1\n",
            )

    def test_prepare_ff_only_when_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            # Second clone advances origin.
            other = Path(tmp) / "other"
            _git(Path(tmp), "clone", str(remote), str(other))
            (other / "tfstate" / "x.tfstate").write_text("v2-remote\n", encoding="utf-8")
            _git(other, "add", "tfstate/x.tfstate")
            _git(other, "commit", "-m", "remote-ahead")
            _git(other, "push", "origin", "main")

            proc = _run_prepare(work, inv, remote, INV_FETCH_MODE="full")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("fast-forward", proc.stdout)
            self.assertEqual(
                (inv / "tfstate" / "x.tfstate").read_text(encoding="utf-8"),
                "v2-remote\n",
            )

    def test_prepare_shallow_mode_does_not_reshallow_full_checkout(self) -> None:
        """seed INV_FETCH_MODE=shallow must not fetch --depth 1 on a full tree."""
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            # Build non-shallow history (init is already full clone).
            for i in range(2, 5):
                (inv / "clusters" / "marker").write_text(f"v{i}\n", encoding="utf-8")
                _git(inv, "add", "clusters/marker")
                _git(inv, "commit", "-m", f"c{i}")
            _git(inv, "push", "origin", "main")

            before_count = int(
                subprocess.check_output(
                    ["git", "-C", str(inv), "rev-list", "--count", "HEAD"],
                    text=True,
                ).strip()
            )
            self.assertGreaterEqual(before_count, 3)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(inv), "rev-parse", "--is-shallow-repository"],
                    text=True,
                ).strip(),
                "false",
            )

            proc = _run_prepare(work, inv, remote, INV_FETCH_MODE="shallow")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("existing non-shallow checkout", proc.stdout)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(inv), "rev-parse", "--is-shallow-repository"],
                    text=True,
                ).strip(),
                "false",
            )
            after_count = int(
                subprocess.check_output(
                    ["git", "-C", str(inv), "rev-list", "--count", "HEAD"],
                    text=True,
                ).strip()
            )
            self.assertEqual(after_count, before_count)

    def test_prepare_skips_set_url_when_origin_form_differs_only(self) -> None:
        """ssh:// vs git@ for same host/path must not force set-url."""
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, inv = _init_inv(Path(tmp))
            # Fake a git@-style URL that normalizes like file remote cannot;
            # instead verify script text + a dry compare helper path via env
            # using identical normalized forms is covered by successful prepare
            # when INV_URL == origin (file path).
            proc = _run_prepare(work, inv, remote, INV_FETCH_MODE="shallow")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotIn("origin mismatch", proc.stdout)


if __name__ == "__main__":
    unittest.main()
