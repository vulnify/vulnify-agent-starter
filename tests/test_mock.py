"""Mock mode goes through the real Vulnify client and shows ALLOW, REVIEW, and BLOCK."""
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

from vulnify import Vulnify

from starter.main import main
from starter.mock_api import start_mock, stop_mock


class MockApiTest(unittest.TestCase):
    def test_sdk_check_sees_all_three_decisions(self):
        server, url = start_mock(approve_reviews=False)
        try:
            client = Vulnify(api_key="vln_test_mock", base_url=url, retries=0, timeout=3)
            read = client.check(agent="StarterAgent", action="READ_DATA", resource="Support Tickets")
            export = client.check(
                agent="StarterAgent",
                action="EXPORT_DATA",
                resource="Sales Reports",
                destination="EXTERNAL_EMAIL",
                records_affected=800,
            )
            delete = client.check(
                agent="StarterAgent",
                action="DELETE_DATA",
                resource="Production Database",
                records_affected=10000,
            )
        finally:
            stop_mock(server)
        self.assertEqual(read.final_decision, "ALLOW")
        self.assertEqual(read.policy["name"], "allow-reads")
        self.assertFalse(read.degraded)
        self.assertEqual(export.final_decision, "REVIEW")
        self.assertEqual(export.review["status"], "PENDING")
        self.assertEqual(export.policy["name"], "review-bulk-external-export")
        self.assertEqual(delete.final_decision, "BLOCK")
        self.assertEqual(delete.policy["name"], "block-production-deletes")

    def test_approved_review_returns_allow_on_final_decision(self):
        server, url = start_mock(approve_reviews=True)
        try:
            client = Vulnify(api_key="vln_test_mock", base_url=url, retries=0, timeout=3)
            export = client.check(
                agent="StarterAgent",
                action="EXPORT_DATA",
                resource="Sales Reports",
                destination="EXTERNAL_EMAIL",
                records_affected=800,
            )
            outcome = client.wait_for_review(export.id, timeout=5, poll=0.01)
        finally:
            stop_mock(server)
        self.assertEqual(export.final_decision, "REVIEW")
        self.assertEqual(outcome, "ALLOW")

    def test_cli_mock_prints_three_outcomes_and_does_not_run_the_risky_tools(self):
        code, out, err = _run(["--mock"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("No request is sent to api.vulnify.io.", out)
        self.assertIn("ALLOW", out)
        self.assertIn("REVIEW", out)
        self.assertIn("BLOCK", out)
        self.assertIn("allow-reads", out)
        self.assertIn("review-bulk-external-export", out)
        self.assertIn("block-production-deletes", out)
        self.assertIn("ran: Ticket T-1042", out)
        self.assertIn("not run", out)
        self.assertNotIn("Exported", out)
        self.assertNotIn("Dropped", out)
        self.assertNotIn("vln_test_mock", out)
        self.assertNotIn("vln_test_mock", err)

    def test_cli_mock_approve_review_runs_only_the_export(self):
        code, out, err = _run(["--mock", "--approve-review"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("REVIEW approved, now ALLOW", out)
        self.assertIn("Exported 800 records", out)
        self.assertIn("BLOCK", out)
        self.assertNotIn("Dropped", out)

    def test_missing_key_points_at_signup_and_mock(self):
        code, out, err = _run([], drop_env=True, isolated=True)
        self.assertEqual(code, 1, out + err)
        self.assertIn("https://app.vulnify.io", out)
        self.assertIn("--mock", out)
        self.assertNotIn("vln_", out)

    def test_approve_review_without_mock_is_refused(self):
        code, out, err = _run(["--approve-review"], drop_env=True, isolated=True)
        self.assertEqual(code, 2, out + err)
        self.assertIn("Vulnify or in Slack", out)

    def test_placeholder_key_is_refused(self):
        code, out, err = _run([], env={"VULNIFY_API_KEY": "vln_test_replace_me"}, isolated=True)
        self.assertEqual(code, 1, out + err)
        self.assertIn("https://app.vulnify.io", out)

    def test_live_key_warns_without_printing_the_key(self):
        # Closed port, so this never reaches api.vulnify.io. Fail closed still finishes the script.
        fake_key = "vln_live_" + "not_a_real_key"
        code, out, err = _run(
            [],
            env={"VULNIFY_API_KEY": fake_key, "VULNIFY_BASE_URL": "http://127.0.0.1:1"},
            isolated=True,
        )
        self.assertEqual(code, 0, out + err)
        self.assertIn("LIVE", err)
        self.assertIn("could not be reached", out)
        self.assertNotIn("ran:", out)
        self.assertNotIn(fake_key, out)
        self.assertNotIn(fake_key, err)


def _run(argv, env=None, drop_env=False, isolated=False):
    previous = os.environ.copy()
    cwd = os.getcwd()
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        if isolated:
            os.chdir("/tmp")
        if drop_env:
            os.environ.pop("VULNIFY_API_KEY", None)
            os.environ.pop("VULNIFY_MOCK", None)
            os.environ.pop("VULNIFY_BASE_URL", None)
        if env:
            os.environ.update(env)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
    finally:
        os.environ.clear()
        os.environ.update(previous)
        os.chdir(cwd)
    return code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
