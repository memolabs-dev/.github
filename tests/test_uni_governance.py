import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UniGovernanceContractTests(unittest.TestCase):
    def test_trusted_verifier_registry_is_explicit(self):
        # Keep this test stdlib-only for macOS Python 3.9.
        text = (ROOT / ".uni/config.toml").read_text()
        self.assertIn('[verifiers."governance.tests"]', text)
        self.assertIn(
            "python3 -m unittest discover -s tests -p 'test_*.py'", text
        )
        self.assertIn('expect = "OK"', text)
        self.assertIn("tests/**", text)
        self.assertIn("scripts/**", text)
        self.assertIn("timeout = 180", text)

    def test_dsl_contract_has_a_required_claim(self):
        contents = (ROOT / "uni/intents/governance.uni").read_text()
        for required in (
            "VERSION 0.1", "DOMAIN software", "INTENT memolabs.governance",
            "CLAIM governance-tests REQUIRED", "USING governance.tests",
            "required_claims == VERIFIED", "critical_failures == 0"
        ):
            self.assertIn(required, contents)

    def test_workflow_runs_only_on_trusted_main_without_untrusted_pr_code(self):
        text = (ROOT / ".github/workflows/uni-governance.yml").read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("branches: [main]", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("pull_request_target:", text)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn(
            "uses: memolabs-dev/uni-protocol/adapters/github@7c78bcca315d45ad4ed456082e29ed70b43dbe66",
            text
        )

    def test_uni_runtime_outputs_are_not_tracked(self):
        lines = (ROOT / ".gitignore").read_text()
        for path in (".uni/evidence/", ".uni/decisions/", ".uni/artifacts/", ".uni/events.jsonl", ".uni/.registry.hash", ".uni/.registry.snapshot.toml"):
            self.assertIn(path, lines)


if __name__ == "__main__":
    unittest.main()
