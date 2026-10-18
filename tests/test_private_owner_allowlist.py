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


if __name__ == "__main__":
    unittest.main()
