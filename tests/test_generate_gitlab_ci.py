"""GitLab CI seed generator (spec:inputs dropdowns from inventory scan)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "examples" / "internal" / "seed" / "generate_gitlab_ci.py"


class GenerateGitlabCiTest(unittest.TestCase):
    def test_build_from_fixture_artifacts(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("generate_gitlab_ci", GEN)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Minimal artifacts shaped like seed scanners.
        ids = ["fixture/postgresql", "fixture/redis"]
        phases = {
            "fixture/postgresql": ["provision", "init", "postgresql"],
            "fixture/redis": ["provision", "init", "redis"],
        }
        limits = {
            "fixture/postgresql": [
                {"value": "pgsql_cluster", "label": "pgsql_cluster"},
                {"value": "10.20.0.1", "label": "   └ 10.20.0.1"},
            ],
            "fixture/redis": ["redis"],
        }
        text = mod.build_gitlab_ci(ids, phases, {k: mod._limit_values(v) for k, v in limits.items()}, prefer="fixture/redis")
        self.assertIn('default: "fixture/redis"', text)
        self.assertIn('- "fixture/redis"', text)
        self.assertIn('- "fixture/postgresql"', text)
        self.assertIn('"__none__"', text)
        self.assertIn('default: "__none__"', text)
        self.assertIn("type: string", text)
        self.assertIn('$[[ inputs.cluster_id ]] == "fixture/postgresql"', text)
        self.assertIn('- "postgresql"', text)
        self.assertIn('- "pgsql_cluster"', text)
        # CSV-of-all when 2+ values (string single-select stand-in for multi).
        self.assertIn('- "provision,init,postgresql"', text)
        self.assertIn("include:", text)
        self.assertIn("gitlab-ci.jobs.yml", text)
        self.assertNotIn("options: []", text)
        self.assertNotIn("type: array", text)
        self.assertNotIn('default:\n            - "__none__"', text)

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            (tdir / "ids.txt").write_text("fixture/postgresql\nfixture/redis\n", encoding="utf-8")
            (tdir / "phases.json").write_text(json.dumps(phases), encoding="utf-8")
            (tdir / "limits.json").write_text(json.dumps(limits), encoding="utf-8")
            out = tdir / "out.yml"
            rc = mod.main(
                [
                    "--ids",
                    str(tdir / "ids.txt"),
                    "--phases",
                    str(tdir / "phases.json"),
                    "--limits",
                    str(tdir / "limits.json"),
                    "--output",
                    str(out),
                    "--prefer",
                    "fixture/postgresql",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out.is_file())
            loaded = list(__import__("yaml").safe_load_all(out.read_text(encoding="utf-8")))
            self.assertEqual(len(loaded), 2)
            opts = loaded[0]["spec"]["inputs"]["cluster_id"]["options"]
            self.assertEqual(opts[0], "fixture/postgresql")

    def test_jobs_file_has_seed(self) -> None:
        jobs = (ROOT / "examples" / "internal" / "gitlab-ci.jobs.yml").read_text(encoding="utf-8")
        self.assertIn("\nseed:\n", jobs)
        self.assertIn("generate_gitlab_ci.py", jobs)
        self.assertIn("[skip ci]", jobs)
        self.assertIn("\ndeploy:\n", jobs)
        self.assertNotIn("\npublic-ci:\n", jobs)
        self.assertNotIn("./tests/run_ci.sh", jobs)
        self.assertIn("ci_preflight --skip-tests", jobs)
        self.assertIn("INVENTORY_GIT_URL:-ssh://git@gitea.mxhash.com/root/atlas-inventory.git", jobs)
        self.assertIn("INPUT_INVENTORY_GIT_URL", jobs)
        self.assertNotIn("inventory_git_url is required for seed", jobs)
        self.assertIn("setup_venv", jobs)
        self.assertIn("python3 -m venv .venv", jobs)
        self.assertNotIn("image: python:", jobs)
        self.assertIn("__none__", jobs)
        # Phase 6 Stage 5 / P1
        self.assertIn("prepare_inventory_checkout.sh", jobs)
        self.assertIn("TFSTATE_GIT_DISCARD_LOCAL", jobs)
        self.assertIn("provision_tf_state_git_discard_local=true", jobs)
        self.assertIn("INV_FETCH_MODE=full", jobs)
        self.assertIn("INV_FETCH_MODE=shallow", jobs)
        self.assertIn("resource_group: atlas-clusterctl-inventory", jobs)
        self.assertNotIn("mkdir -p tfstate-repo", jobs)


if __name__ == "__main__":
    unittest.main()
