import copy
import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

P = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("land", P / "scripts/land.py")
land = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(land)

REPO = "memolabs-dev/memo-bridge"
SHA = "a" * 40
POLICY = {"repository": REPO, "required_checks": []}


def pr(**overrides):
    data = {
        "number": 7, "state": "open", "draft": False, "changed_files": 2,
        "head": {"sha": SHA, "ref": "feat/x", "repo": {"full_name": REPO}},
        "base": {"ref": "main", "repo": {"default_branch": "main"}},
        "user": {"login": "memo-labs-automation[bot]"}, "labels": [],
    }
    data.update(overrides)
    return data


FILES = [{"filename": "server/index.mjs"}, {"filename": "tests/a.test.mjs"}]


def run(name="test", **overrides):
    data = {"name": name, "head_sha": SHA, "status": "completed", "conclusion": "success"}
    data.update(overrides)
    return data


NO_STATUS = {"state": "pending", "statuses": []}


def decide(p=None, files=None, runs=None, total=None, status=None, policy=None, sha=SHA):
    runs = [run()] if runs is None else runs
    return land.decide(p or pr(), FILES if files is None else files, runs,
                       len(runs) if total is None else total, status or NO_STATUS, sha, policy or POLICY)


class LandingDecisionTests(TestCase):
    def test_verified_pull_request_lands(self):
        verdict = decide()
        self.assertTrue(verdict["land"], verdict)
        self.assertEqual(verdict["reason"], "verified")
        self.assertEqual(verdict["contract"], "memo-labs/landing@0.1.0")

    def test_pull_request_state_refusals(self):
        cases = {
            "not_open": pr(state="closed"),
            "head_moved": pr(head={"sha": "b" * 40, "repo": {"full_name": REPO}}),
            "external_branch": pr(head={"sha": SHA, "repo": {"full_name": "someone/fork"}}),
            "not_default_branch": pr(base={"ref": "feat/x", "repo": {"default_branch": "main"}}),
            "draft": pr(draft=True),
            "untrusted_author": pr(user={"login": "random-user"}),
            "hold_label": pr(labels=[{"name": "hold-merge"}]),
        }
        for reason, candidate in cases.items():
            verdict = decide(p=candidate)
            self.assertFalse(verdict["land"], reason)
            self.assertEqual(verdict["reason"], reason)

    def test_trusted_authors_are_the_owner_and_the_app_only(self):
        self.assertEqual(land.TRUSTED_AUTHORS, ("guillaume-flambard", "memo-labs-automation[bot]"))
        for login in land.TRUSTED_AUTHORS:
            self.assertTrue(decide(p=pr(user={"login": login}))["land"], login)

    def test_retired_drop_agent_bot_is_untrusted(self):
        verdict = decide(p=pr(user={"login": "drop-agent-bot"}))
        self.assertFalse(verdict["land"])
        self.assertEqual(verdict["reason"], "untrusted_author")

    def test_deleted_head_repository_is_external(self):
        self.assertEqual(decide(p=pr(head={"sha": SHA, "repo": None}))["reason"], "external_branch")

    def test_invalid_sha_is_refused(self):
        self.assertEqual(decide(sha="HEAD")["reason"], "invalid_sha")

    def test_protected_paths_need_a_human(self):
        for path in (".github/workflows/ci.yml", "Dockerfile", "app/Dockerfile.prod", "ansible/site.yml",
                     "stacks/emargo/compose.yml", "scripts/deployment/run.sh", "deploy/k8s.yml"):
            files = [{"filename": "README.md"}, {"filename": path}]
            verdict = decide(files=files)
            self.assertEqual(verdict["reason"], "protected_paths", path)
            self.assertIn(path, verdict["paths"])

    def test_rename_out_of_a_protected_path_is_protected(self):
        files = [{"filename": "docs/ci.yml", "previous_filename": ".github/workflows/ci.yml"}, {"filename": "a"}]
        self.assertEqual(decide(files=files)["reason"], "protected_paths")

    def test_repository_specific_protected_paths(self):
        policy = {**POLICY, "extra_protected": [r"^migrations/"]}
        files = [{"filename": "migrations/001.sql"}, {"filename": "a"}]
        self.assertEqual(decide(files=files, policy=policy)["reason"], "protected_paths")

    def test_non_exhaustive_file_list_is_refused(self):
        self.assertEqual(decide(p=pr(changed_files=3))["reason"], "files_not_exhaustive")
        self.assertEqual(decide(p=pr(changed_files=101), files=[{"filename": "x"}] * 101)["reason"], "files_not_exhaustive")

    def test_checks_must_all_be_complete_green_and_on_this_sha(self):
        self.assertEqual(decide(runs=[])["reason"], "wait_no_checks")
        self.assertEqual(decide(runs=[run(), run("lint", status="in_progress", conclusion=None)])["reason"],
                         "wait_checks_running")
        for conclusion in ("failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"):
            self.assertEqual(decide(runs=[run(), run("lint", conclusion=conclusion)])["reason"], "checks_failed")
        self.assertEqual(decide(runs=[run(head_sha="c" * 40)])["reason"], "check_for_other_sha")
        self.assertEqual(decide(total=150)["reason"], "checks_not_exhaustive")
        self.assertTrue(decide(runs=[run(), run("optional", conclusion="skipped"), run("info", conclusion="neutral")])["land"])

    def test_commit_statuses_are_part_of_the_verdict(self):
        pending = {"state": "pending", "statuses": [{"context": "ci/legacy", "state": "pending"}]}
        failed = {"state": "failure", "statuses": [{"context": "ci/legacy", "state": "failure"}]}
        green = {"state": "success", "statuses": [{"context": "ci/legacy", "state": "success"}]}
        self.assertEqual(decide(status=pending)["reason"], "wait_status_pending")
        self.assertEqual(decide(status=failed)["reason"], "status_failed")
        self.assertTrue(decide(status=green)["land"])
        self.assertTrue(decide(runs=[], status=green)["land"], "a status alone can verify a commit")

    def test_required_receipts_must_be_present_and_green(self):
        policy = {**POLICY, "required_checks": ["UNI governance receipt"]}
        self.assertEqual(decide(policy=policy)["reason"], "wait_required_checks")
        skipped = [run(), run("UNI governance receipt", conclusion="skipped")]
        self.assertEqual(decide(runs=skipped, policy=policy)["reason"], "wait_required_checks")
        green = [run(), run("UNI governance receipt")]
        self.assertTrue(decide(runs=green, policy=policy)["land"])

    def test_decision_does_not_mutate_inputs(self):
        candidate, files, runs = pr(), copy.deepcopy(FILES), [run()]
        before = copy.deepcopy((candidate, files, runs))
        decide(p=candidate, files=files, runs=runs)
        self.assertEqual((candidate, files, runs), before)


class LandingCommandTests(TestCase):
    def fake_gh(self, calls, merge_fails=False, retarget_fails=False, close_fails=False):
        def gh(args, as_json=True):
            calls.append(args)
            if args[:2] == ["pr", "merge"]:
                if merge_fails:
                    raise RuntimeError("gh pr merge failed (1)")
                return ""
            if args[:2] == ["pr", "view"]:
                return {"closingIssuesReferences": [
                    {"number": 14, "repository": {"name": "memo-bridge", "owner": {"login": "memolabs-dev"}}},
                    {"number": 3, "repository": {"name": "other", "owner": {"login": "memolabs-dev"}}}]}
            if args[:2] == ["issue", "close"]:
                if close_fails:
                    raise RuntimeError("gh issue close failed (1)")
                return ""
            if args[:2] == ["pr", "edit"]:
                if retarget_fails:
                    raise RuntimeError("gh pr edit failed (1)")
                return ""
            if args[:2] in (["workflow", "run"], ["api", "-X"]):
                return ""
            endpoint = args[1]
            if "pulls?state=open&base=feat/x" in endpoint:
                return [{"number": 9}]
            if endpoint.endswith("/pulls"):
                return [{"number": 7, "state": "open"}, {"number": 8, "state": "closed"}]
            if endpoint.endswith("/pulls/7"):
                return pr()
            if "/pulls/7/files" in endpoint:
                return FILES
            if "/check-runs" in endpoint:
                return {"total_count": 1, "check_runs": [run()]}
            if endpoint.endswith("/status"):
                return NO_STATUS
            raise AssertionError(endpoint)
        return gh

    def test_lands_with_exact_sha_and_dispatches_post_merge_workflows(self):
        calls = []
        with patch.object(land, "gh", self.fake_gh(calls)):
            code = land.main(["--repo", REPO, "--sha", SHA, "--dispatch", "ci.yml"])
        self.assertEqual(code, 0)
        merge = next(c for c in calls if c[:2] == ["pr", "merge"])
        self.assertEqual(merge, ["pr", "merge", "7", "--repo", REPO, "--squash", "--match-head-commit", SHA])
        retarget = calls.index(["pr", "edit", "9", "--repo", REPO, "--base", "main"])
        delete = calls.index(["api", "-X", "DELETE", f"repos/{REPO}/git/refs/heads/feat/x"])
        self.assertLess(retarget, delete, "stacked PRs move before the branch disappears")
        self.assertIn(["workflow", "run", "ci.yml", "--repo", REPO, "--ref", "main"], calls)
        self.assertFalse(any("8" in c for c in calls if c[:2] == ["pr", "merge"]), "closed PRs are ignored")

    def test_dry_run_never_merges(self):
        calls = []
        with patch.object(land, "gh", self.fake_gh(calls)):
            self.assertEqual(land.main(["--repo", REPO, "--sha", SHA, "--dry-run"]), 0)
        self.assertFalse(any(c[:2] == ["pr", "merge"] for c in calls))

    def test_refused_merge_is_reported_as_failure(self):
        calls = []
        with patch.object(land, "gh", self.fake_gh(calls, merge_fails=True)):
            self.assertEqual(land.main(["--repo", REPO, "--sha", SHA, "--dispatch", "ci.yml"]), 1)
        self.assertFalse(any(c[:2] == ["workflow", "run"] for c in calls), "nothing is dispatched after a refused merge")

    def test_invalid_sha_never_reaches_the_api(self):
        calls = []
        with patch.object(land, "gh", self.fake_gh(calls)):
            self.assertEqual(land.main(["--repo", REPO, "--sha", "main"]), 1)
        self.assertEqual(calls, [])

    def test_branch_is_kept_when_a_stacked_pr_cannot_be_retargeted(self):
        calls = []
        with patch.object(land, "gh", self.fake_gh(calls, retarget_fails=True)):
            self.assertEqual(land.main(["--repo", REPO, "--sha", SHA, "--dispatch", "ci.yml"]), 1)
        self.assertFalse(any(c[:3] == ["api", "-X", "DELETE"] for c in calls))
        self.assertIn(["workflow", "run", "ci.yml", "--repo", REPO, "--ref", "main"], calls,
                      "a retarget failure does not skip post-merge workflows")

    def test_linked_issues_in_the_same_repository_are_closed(self):
        calls = []
        with patch.object(land, "gh", self.fake_gh(calls)):
            self.assertEqual(land.main(["--repo", REPO, "--sha", SHA]), 0)
        closes = [c for c in calls if c[:2] == ["issue", "close"]]
        self.assertEqual([c[2] for c in closes], ["14"], "issues of other repositories are left alone")

    def test_missing_issue_permission_does_not_fail_the_landing(self):
        calls = []
        with patch.object(land, "gh", self.fake_gh(calls, close_fails=True)):
            self.assertEqual(land.main(["--repo", REPO, "--sha", SHA, "--dispatch", "ci.yml"]), 0)
        self.assertIn(["workflow", "run", "ci.yml", "--repo", REPO, "--ref", "main"], calls)
