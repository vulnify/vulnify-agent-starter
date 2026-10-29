"""The starter policy files match the SDK schema and the offline evaluator."""
import subprocess
import unittest
from pathlib import Path

from vulnify.cli import _read_kind

from starter.policies import decide, load_cases, load_policies, repo_root

ROOT = repo_root()


class PolicyFileTest(unittest.TestCase):
    def test_schema_accepts_policies_and_cases(self):
        policies = _read_kind(str(ROOT / "vulnify" / "policies"), "Policy")
        cases = _read_kind(str(ROOT / "vulnify" / "tests"), "PolicyTest")
        names = sorted(doc["data"]["metadata"]["name"] for doc in policies)
        self.assertEqual(names, ["allow-reads", "block-production-deletes", "review-bulk-external-export"])
        self.assertGreaterEqual(len(cases), 1)

    def test_offline_evaluator_matches_policy_tests(self):
        policies = load_policies()
        for case in load_cases():
            got = decide(case["input"], policies)
            expect = case["expect"]
            self.assertEqual(got["decision"], expect["decision"], case["name"])
            if "policy" in expect:
                self.assertEqual(got["policy"], expect["policy"], case["name"])

    def test_small_external_export_is_outside_the_review_rule(self):
        got = decide(
            {
                "agent": "StarterAgent",
                "action": "EXPORT_DATA",
                "resource": "Sales Reports",
                "destination": "EXTERNAL_EMAIL",
                "recordsAffected": 99,
            },
            load_policies(),
        )
        self.assertEqual(got["decision"], "ALLOW")
        self.assertIsNone(got["policy"])

    def test_internal_export_is_outside_the_review_rule(self):
        got = decide(
            {
                "agent": "StarterAgent",
                "action": "EXPORT_DATA",
                "resource": "Sales Reports",
                "destination": "INTERNAL",
                "recordsAffected": 800,
            },
            load_policies(),
        )
        self.assertEqual(got["decision"], "ALLOW")
        self.assertIsNone(got["policy"])

    def test_block_wins_over_allow(self):
        policies = [
            {
                "metadata": {"name": "allow-everything"},
                "spec": {
                    "action": "ANY",
                    "resource": "ANY",
                    "decision": "ALLOW",
                    "enabled": True,
                    "mode": "ENFORCE",
                },
            },
            {
                "metadata": {"name": "block-deletes"},
                "spec": {
                    "action": "DELETE",
                    "resource": "ANY",
                    "decision": "BLOCK",
                    "enabled": True,
                    "mode": "ENFORCE",
                },
            },
        ]
        got = decide({"action": "DELETE_DATA", "resource": "Production Database"}, policies)
        self.assertEqual(got["decision"], "BLOCK")
        self.assertEqual(got["policy"], "block-deletes")

    def test_disabled_and_monitor_policies_do_not_enforce(self):
        policies = [
            {
                "metadata": {"name": "block-deletes"},
                "spec": {
                    "action": "DELETE",
                    "resource": "ANY",
                    "decision": "BLOCK",
                    "enabled": False,
                    "mode": "ENFORCE",
                },
            },
            {
                "metadata": {"name": "watch-deletes"},
                "spec": {
                    "action": "DELETE",
                    "resource": "ANY",
                    "decision": "BLOCK",
                    "enabled": True,
                    "mode": "MONITOR",
                },
            },
        ]
        got = decide({"action": "DELETE_DATA"}, policies)
        self.assertEqual(got["decision"], "ALLOW")
        self.assertIsNone(got["policy"])

    def test_max_records_is_inclusive(self):
        policies = [
            {
                "metadata": {"name": "review-up-to-100"},
                "spec": {
                    "action": "DELETE",
                    "resource": "ANY",
                    "decision": "REVIEW",
                    "enabled": True,
                    "mode": "ENFORCE",
                    "condition": {"maxRecords": 100},
                },
            }
        ]
        held = decide({"action": "DELETE_DATA", "recordsAffected": 100}, policies)
        missed = decide({"action": "DELETE_DATA", "recordsAffected": 101}, policies)
        self.assertEqual(held["decision"], "REVIEW")
        self.assertEqual(missed["decision"], "ALLOW")

    def test_env_is_gitignored_and_example_is_not(self):
        ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", ".env"], check=False)
        example = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", ".env.example"], check=False)
        local = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", ".env.local"], check=False)
        self.assertEqual(ignored.returncode, 0)
        self.assertEqual(local.returncode, 0)
        self.assertNotEqual(example.returncode, 0)

    def test_no_keys_committed(self):
        allowed = {"vln_test_replace_me", "vln_test_mock"}
        skip = {".git", ".venv", "__pycache__", ".ruff_cache"}
        for path in Path(ROOT).rglob("*"):
            if not path.is_file() or skip.intersection(path.parts):
                continue
            if path.suffix in {".pyc", ".png", ".whl"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in _key_tokens(text):
                self.assertIn(token, allowed, f"{path}: {token}")


def _key_tokens(text: str):
    import re

    return re.findall(r"vln_(?:live|test)_[A-Za-z0-9_]+", text)


if __name__ == "__main__":
    unittest.main()
