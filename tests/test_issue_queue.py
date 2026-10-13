"""No-network tests for the read-only engineering queue."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock

script_path = Path(__file__).resolve().parents[1] / "scripts" / "issue_queue.py"
spec = importlib.util.spec_from_file_location("issue_queue", script_path)
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


def item(num, labels, repo="memolabs-dev/cuesheet", **kw):
    return {
        "number": num,
        "title": "Task " + str(num),
        "html_url": f"https://github.com/{repo}/issues/{num}",
        "repository_url": f"https://api.github.com/repos/{repo}",
        "labels": [{"name": x} for x in labels], **kw
    }


class QueueTests(unittest.TestCase):
    def test_only_eligible_tasks_and_priority_order(self):
        payload = {"items": [
            item(3, ["agent:ready", "priority:p2"]),
            item(1, ["agent:ready", "priority:p0"]),
            item(2, ["agent:ready", "needs:human", "priority:p0"]),
            item(4, ["agent:ready", "type:epic"]),
            item(5, ["agent:ready", "status:blocked"]),
            item(6, ["priority:p0"]),
            item(7, ["agent:ready"], pull_request={"url": "not-an-issue"}),
            item(8, ["agent:ready", "agent:working"]),
        ]}
        run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), ""))
        result = queue.get_queue(limit=20, runner=run)
        self.assertEqual([x["number"] for x in result], [1, 3])
        self.assertEqual([x["priority"] for x in result], ["P0", "P2"])
        argv = run.call_args.args[0]
        self.assertIn("org:memolabs-dev", " ".join(argv))
        self.assertIn('-label:"needs:human"', " ".join(argv))

    def test_scoped_personal_repo(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"items":[]}', ""))
        self.assertEqual(queue.get_queue(repo="guillaume-flambard/lab-infra", runner=run), [])
        argv = " ".join(run.call_args.args[0])
        self.assertIn("repo:guillaume-flambard/lab-infra", argv)
        self.assertNotIn("org:memolabs-dev", argv)

    def test_fail_closed_on_auth_errors(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 1, "", "403 denied"))
        with self.assertRaisesRegex(RuntimeError, "403"):
            queue.get_queue(runner=run)

    def test_bounds(self):
        with self.assertRaises(ValueError):
            queue.get_queue(limit=101)
        with self.assertRaises(ValueError):
            queue.get_queue(limit=0)


if __name__ == "__main__":
    unittest.main()
