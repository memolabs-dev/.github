"""Contract tests: GitHub Issue preflight must fail closed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock

path = Path(__file__).resolve().parents[1] / "scripts" / "issue_preflight.py"
spec = importlib.util.spec_from_file_location("issue_preflight", path)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


REPO = "memolabs-dev/.github"
NUMBER = 28


def repo_info(**kwargs):
    return {"full_name": REPO, "private": False, "archived": False, **kwargs}


def issue_info(**kwargs):
    data = {
        "number": NUMBER,
        "html_url": f"https://github.com/{REPO}/issues/{NUMBER}",
        "state": "open", "state_reason": None, "updated_at": "2026-10-13T12:00:00Z",
        "labels": [{"name": "agent:ready"}, {"name": "priority:p1"}],
        "body": "Some UNTRUSTED text; $(whoami); \`rm -rf\`",
    }
    data.update(kwargs)
    return data


def fake_calls(meta=None, issue=None, status=0):
    responses = [repo_info() if meta is None else meta, issue_info() if issue is None else issue]
    fn = Mock(side_effect=[
        subprocess.CompletedProcess([], status, json.dumps(responses[0]), "error"),
        subprocess.CompletedProcess([], status, json.dumps(responses[1]), "error"),
    ])
    return fn


class PreflightTests(unittest.TestCase):
    def test_valid_issue_yields_receipt_not_a_claim(self):
        fn = fake_calls()
        result = preflight.assess(REPO, NUMBER, runner=fn)
        self.assertEqual(result["decision"], "DRY_RUN_ELIGIBLE_NOT_CLAIMED")
        self.assertFalse(result["execution_performed"])
        self.assertFalse(result["lease_acquired"])
        self.assertNotIn("UNTRUSTED", json.dumps(result))
        self.assertEqual(fn.call_count, 2)
        for call in fn.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[:4], ["gh", "api", "-X", "GET"])
            self.assertEqual(len(argv), 5)

    def test_disallows_other_repo_and_invalid_issue_input_without_api(self):
        for repo, num in [
            ("memolabs-dev/emargo", NUMBER), ("guillaume-flambard/lab-infra", NUMBER),
            ("memolabs-dev/drop;echo pwnd", NUMBER), (REPO, "-1"),
            (REPO, "123/../../x"), (REPO, "0"),
        ]:
            with self.subTest(repo=repo, num=num):
                with self.assertRaises(preflight.PreflightDenied):
                    preflight.assess(repo, num, runner=Mock())

    def test_label_policy(self):
        cases = [
            [{"name": "priority:p1"}],
            [{"name": "agent:ready"}],
            [{"name": "agent:ready"}, {"name": "priority:p0"}, {"name": "priority:p2"}],
        ] + [
            [{"name": "agent:ready"}, {"name": "priority:p1"}, {"name": blocker}]
            for blocker in sorted(preflight.BLOCKED_LABELS)
        ]
        for labels in cases:
            with self.subTest(labels=labels):
                with self.assertRaises(preflight.PreflightDenied):
                    preflight.assess(REPO, NUMBER, runner=fake_calls(issue=issue_info(labels=labels)))

    def test_closed_pull_request_or_identity_mismatch(self):
        cases = [
            {"state": "closed"},
            {"pull_request": {"url": "https://api.github.com/pulls/28"}},
            {"number": 77},
            {"html_url": "https://evil.example/issue"},
            {"updated_at": None},
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                with self.assertRaises(preflight.PreflightDenied):
                    preflight.assess(REPO, NUMBER, runner=fake_calls(issue=issue_info(**extra)))

    def test_requires_verified_public_repo(self):
        for meta in [
            dict(repo_info(), private=True), dict(repo_info(), archived=True),
            dict(repo_info(), full_name="memolabs-dev/other"),
            dict(repo_info(), private=None),
        ]:
            with self.subTest(meta=meta):
                with self.assertRaises(preflight.PreflightDenied):
                    preflight.assess(REPO, NUMBER, runner=fake_calls(meta=meta))

    def test_denies_failed_github_call(self):
        fn = Mock(return_value=subprocess.CompletedProcess([], 1, "", "token=SECRET 403"))
        with self.assertRaisesRegex(preflight.PreflightDenied, "Cannot verify"):
            preflight.assess(REPO, NUMBER, runner=fn)
        self.assertNotIn("SECRET", str(fn.call_args))


if __name__ == "__main__":
    unittest.main()
