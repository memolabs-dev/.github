import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import private_owner_allowlist as policy

SUB = "b31f467f-7326-49c7-91f1-3659a177ec9e"
CDKF = "memolabs-dev/clinical-data-knowledge-foundation"


class PrivateOwnerAllowlistTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name).resolve()
        self.path = self.home / ".local/share/memo-bridge/owner-policy/private-repos.json"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "schema": policy.SCHEMA, "owner_sub": SUB, "repos": [CDKF]
        }))
        self.path.chmod(0o600)
        self.env = {
            "MEMO_BRIDGE_HOST": "mac",
            "MEMO_BRIDGE_AGENT_MODE": "runtime",
            "MEMO_BRIDGE_MAC_RUNTIME_ENABLED": "enabled",
            "MEMO_BRIDGE_OWNER_SUB": SUB,
            "MEMO_BRIDGE_OWNER_PRIVATE_REPOS_FILE": str(self.path),
        }

    def allowed(self, repo=CDKF, **kwargs):
        return policy.allowed(repo, environ=self.env, platform="darwin",
                              home=self.home, uid=os.geteuid(), **kwargs)

    def test_explicit_owner_repo_is_eligible(self):
        self.assertTrue(self.allowed())
        self.assertFalse(self.allowed("memolabs-dev/unlisted"))

    def test_not_linux_probe_or_other_identity(self):
        self.assertFalse(policy.allowed(CDKF, environ=self.env, platform="linux",
                                        home=self.home, uid=os.geteuid()))
        for name, value in [("MEMO_BRIDGE_AGENT_MODE", "probe"),
                            ("MEMO_BRIDGE_HOST", "vps"),
                            ("MEMO_BRIDGE_OWNER_SUB", "00000000-0000-0000-0000-000000000000")]:
            bad = dict(self.env, **{name: value})
            self.assertFalse(policy.allowed(CDKF, environ=bad, platform="darwin",
                                            home=self.home, uid=os.geteuid()))

    def test_refuses_public_permissions_and_symlink(self):
        self.path.chmod(0o644)
        self.assertFalse(self.allowed())
        self.path.chmod(0o600)
        self.path.unlink()
        target = self.home / "elsewhere.json"
        target.write_text("{}")
        self.path.symlink_to(target)
        self.assertFalse(self.allowed())

    def test_refuses_wrong_schema_extra_keys_and_duplicate_repos(self):
        for data in [
            {"schema": policy.SCHEMA, "owner_sub": SUB, "repos": [CDKF], "extra": 1},
            {"schema": policy.SCHEMA, "owner_sub": SUB, "repos": [CDKF, CDKF.upper()]},
            {"schema": policy.SCHEMA, "owner_sub": SUB, "repos": ["other/private"]},
        ]:
            self.path.write_text(json.dumps(data))
            self.path.chmod(0o600)
            self.assertFalse(self.allowed())

    def test_home_comes_from_the_account_not_the_environment(self):
        # The Memo Bridge ledger child runs with HOME set to a private gh configuration directory.
        account = type("pw", (), {"pw_dir": str(self.home)})()
        with patch.object(policy.pwd, "getpwuid", return_value=account) as lookup, \
                patch.dict(os.environ, {"HOME": str(self.home / "gh-config")}):
            self.assertTrue(policy.allowed(CDKF, environ=self.env, platform="darwin", uid=os.geteuid()))
        lookup.assert_called_once_with(os.geteuid())
        other = type("pw", (), {"pw_dir": str(self.home / "someone-else")})()
        with patch.object(policy.pwd, "getpwuid", return_value=other):
            self.assertFalse(policy.allowed(CDKF, environ=self.env, platform="darwin", uid=os.geteuid()))
        with patch.object(policy.pwd, "getpwuid", side_effect=KeyError("no such uid")):
            self.assertFalse(policy.allowed(CDKF, environ=self.env, platform="darwin", uid=os.geteuid()))

    def test_owner_account_namespace_is_enrollable_and_others_are_not(self):
        personal = "guillaume-flambard/private-example"
        self.path.write_text(json.dumps({"schema": policy.SCHEMA, "owner_sub": SUB, "repos": [CDKF, personal]}))
        self.path.chmod(0o600)
        self.assertTrue(self.allowed(personal))
        self.assertTrue(self.allowed())
        for foreign in ["someone-else/private-example", "guillaume-flambard-x/private-example"]:
            self.assertFalse(self.allowed(foreign))
            self.path.write_text(json.dumps({"schema": policy.SCHEMA, "owner_sub": SUB, "repos": [CDKF, foreign]}))
            self.path.chmod(0o600)
            self.assertFalse(self.allowed(), "a foreign entry invalidates the whole file")

    def test_local_stdio_server_is_accepted_other_modes_are_not(self):
        stdio = {k: v for k, v in self.env.items() if k != "MEMO_BRIDGE_MAC_RUNTIME_ENABLED"}
        stdio["MEMO_BRIDGE_AGENT_MODE"] = "stdio"
        self.assertTrue(policy.allowed(CDKF, environ=stdio, platform="darwin", home=self.home, uid=os.geteuid()))
        self.assertFalse(policy.allowed(CDKF, environ=stdio, platform="linux", home=self.home, uid=os.geteuid()))
        self.assertFalse(policy.allowed(CDKF, environ=dict(stdio, MEMO_BRIDGE_HOST="vps"), platform="darwin",
                                        home=self.home, uid=os.geteuid()))
        runtime_off = {k: v for k, v in self.env.items() if k != "MEMO_BRIDGE_MAC_RUNTIME_ENABLED"}
        self.assertFalse(policy.allowed(CDKF, environ=runtime_off, platform="darwin", home=self.home, uid=os.geteuid()))
        for mode in ["hub", "operator", "", "STDIO"]:
            self.assertFalse(policy.allowed(CDKF, environ=dict(stdio, MEMO_BRIDGE_AGENT_MODE=mode), platform="darwin",
                                            home=self.home, uid=os.geteuid()))

    def test_limit_is_one_hundred_repositories(self):
        repos = [f"memolabs-dev/r{i}" for i in range(99)] + [CDKF]
        self.path.write_text(json.dumps({"schema": policy.SCHEMA, "owner_sub": SUB, "repos": repos}))
        self.path.chmod(0o600)
        self.assertTrue(self.allowed())
        self.path.write_text(json.dumps({"schema": policy.SCHEMA, "owner_sub": SUB, "repos": repos + ["memolabs-dev/r100"]}))
        self.path.chmod(0o600)
        self.assertFalse(self.allowed())


class ExternalProjectsTests(unittest.TestCase):
    REPO = "guillaume-flambard/private-example"

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name).resolve()
        self.path = self.home / ".local/share/memo-bridge/owner-policy/external-projects.json"
        self.path.parent.mkdir(parents=True)
        self.write({"schema": policy.EXTERNAL_SCHEMA, "owner_sub": SUB,
                    "projects": [{"name": "example", "path": str(self.home / "example"), "repo": self.REPO}]})
        self.env = {
            "MEMO_BRIDGE_HOST": "mac",
            "MEMO_BRIDGE_AGENT_MODE": "stdio",
            "MEMO_BRIDGE_OWNER_SUB": SUB,
            "MEMO_BRIDGE_OWNER_EXTERNAL_PROJECTS_FILE": str(self.path),
        }

    def write(self, data, mode=0o600):
        self.path.write_text(json.dumps(data))
        self.path.chmod(mode)

    def allowed(self, repo=REPO, env=None):
        return policy.allowed(repo, environ=env or self.env, platform="darwin", home=self.home, uid=os.geteuid())

    def test_an_external_project_enrolls_its_repository(self):
        self.assertTrue(self.allowed())
        self.assertFalse(self.allowed(CDKF))

    def test_untrusted_or_malformed_external_file_enrolls_nothing(self):
        good = {"schema": policy.EXTERNAL_SCHEMA, "owner_sub": SUB,
                "projects": [{"name": "example", "path": str(self.home / "example"), "repo": self.REPO}]}
        self.write(good, 0o644)
        self.assertFalse(self.allowed())
        item = good["projects"][0]
        for data in [
            dict(good, owner_sub="00000000-0000-0000-0000-000000000000"),
            dict(good, schema=policy.SCHEMA),
            dict(good, extra=1),
            dict(good, projects=[dict(item, path="relative/path")]),
            dict(good, projects=[dict(item, path=str(self.home / "x") + "/../example")]),
            dict(good, projects=[dict(item, name=f"p{i}", repo=f"memolabs-dev/p{i}") for i in range(21)]),
            dict(good, projects=[dict(item, name="Bad Name")]),
            dict(good, projects=[dict(item, repo="someone-else/private-example")]),
            dict(good, projects=[dict(item, extra=1)]),
            dict(good, projects=[item, dict(item, repo="guillaume-flambard/other")]),
        ]:
            with self.subTest(data=data):
                self.write(data)
                self.assertFalse(self.allowed())

    def test_external_file_only_at_its_fixed_path(self):
        other = self.home / "external-projects.json"
        other.write_text(self.path.read_text())
        other.chmod(0o600)
        self.assertFalse(self.allowed(env=dict(self.env, MEMO_BRIDGE_OWNER_EXTERNAL_PROJECTS_FILE=str(other))))
        self.path.unlink()
        self.path.symlink_to(other)
        self.assertFalse(self.allowed())

    def test_runtime_mode_reads_the_external_file_too(self):
        runtime = dict(self.env, MEMO_BRIDGE_AGENT_MODE="runtime", MEMO_BRIDGE_MAC_RUNTIME_ENABLED="enabled")
        self.assertTrue(self.allowed(env=runtime))


if __name__ == "__main__":
    unittest.main()
