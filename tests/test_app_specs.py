import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AppManifestTests(unittest.TestCase):
    def read_manifest(self, name):
        return json.loads((ROOT / "github-apps" / f"memo-labs-{name}.manifest.json").read_text())

    def test_guardian_is_read_only_except_checks(self):
        actual = self.read_manifest("guardian")
        self.assertEqual(actual["name"], "memo-labs-guardian")
        self.assertEqual(actual["default_permissions"], {
            "contents": "read", "pull_requests": "read",
            "actions": "read", "checks": "write"
        })
        self.assertEqual(actual["default_events"], [])
        self.assertFalse(actual["hook_attributes"]["active"])
        self.assertFalse(actual["public"])

    def test_release_permissions_are_separate_and_declared(self):
        actual = self.read_manifest("release")
        self.assertEqual(actual["name"], "memo-labs-release")
        self.assertEqual(actual["default_permissions"], {
            "contents": "write", "deployments": "write", "actions": "read"
        })
        self.assertNotIn("administration", actual["default_permissions"])
        self.assertFalse(actual["hook_attributes"]["active"])
        self.assertFalse(actual["public"])

    def test_guardian_workflow_has_only_manual_trigger(self):
        body = (ROOT / ".github/workflows/guardian-check-smoke.yml").read_text()
        self.assertIn("workflow_dispatch:", body)
        self.assertIn("conclusion='neutral'", body)
        self.assertNotIn("pull_request_target:", body)

    def test_release_workflow_cannot_publish(self):
        body = (ROOT / ".github/workflows/release-app-auth-smoke.yml").read_text()
        self.assertIn("workflow_dispatch:", body)
        self.assertIn("permission-contents: read", body)
        self.assertNotIn("release create", body)
        self.assertNotIn("deployment create", body)
        self.assertNotIn("permission-contents: write", body)

    def test_repo_access_workflow_is_explicit_and_readonly(self):
        body = (ROOT / ".github/workflows/app-repo-access-smoke.yml").read_text()
        self.assertIn("workflow_dispatch:", body)
        self.assertIn("permission-contents: read", body)
        self.assertNotIn("permission-contents: write", body)
        for repo in ["uni-protocol", "drop", "cuesheet", "lab-console", "emargo"]:
            self.assertIn(repo, body)

    def test_guardian_ci_preflight_is_manual_informational_and_non_mutating(self):
        body = (ROOT / ".github/workflows/guardian-ci-provenance-smoke.yml").read_text()
        self.assertIn("workflow_dispatch:", body)
        self.assertIn("github.ref == 'refs/heads/main'", body)
        self.assertIn("permissions:\n  contents: read", body)
        self.assertIn("persist-credentials: false", body)
        self.assertIn("python3 scripts/guardian-ci-preflight.py", body)
        self.assertNotIn("pull_request_target:", body)
        self.assertNotIn("permission-checks: write", body)
        self.assertNotIn("gh api -X POST", body)
        self.assertNotIn("gh pr merge", body)


if __name__ == "__main__":
    unittest.main()
