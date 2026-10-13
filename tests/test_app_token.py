import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

MODULE_FILE = Path(__file__).resolve().parents[1] / "scripts/with-app-token.py"
SPEC = importlib.util.spec_from_file_location("memo_app_token", MODULE_FILE)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ScopedAppTokenTests(TestCase):
    def test_default_is_read_only(self):
        self.assertEqual(module.validate_permission_scope("automation", []),
                         {"contents": "read"})

    def test_guardian_can_write_only_checks(self):
        self.assertEqual(module.validate_permission_scope("guardian", ["checks=write"]),
                         {"checks": "write"})
        with self.assertRaises(ValueError):
            module.validate_permission_scope("guardian", ["contents=write"])
        with self.assertRaises(ValueError):
            module.validate_permission_scope("guardian", ["pull_requests=write"])

    def test_release_cannot_edit_checks_or_workflows(self):
        for perm in ("checks=write", "workflows=write", "administration=write"):
            with self.subTest(perm=perm), self.assertRaises(ValueError):
                module.validate_permission_scope("release", [perm])

    def test_unknown_duplicate_or_malformed_scope_fails(self):
        for perms in (
            ["contents=admin"], ["contents"], ["weird=read"],
            ["contents=read", "contents=write"]
        ):
            with self.subTest(perms=perms), self.assertRaises(ValueError):
                module.validate_permission_scope("automation", perms)

    def test_allowlisted_repositories_only(self):
        self.assertEqual(len(module.ALLOWED_REPOS), 9)
        self.assertNotIn("unknown-repo", module.ALLOWED_REPOS)

    @patch.object(module, "github_request")
    @patch.object(module, "key_for")
    @patch.object(module, "signed_jwt", return_value="signed.jwt")
    @patch.object(module, "get_app_id", return_value=5298579)
    def test_installation_token_is_scoped_to_exactly_one_repository(
        self, get_id, jwt, key, http
    ):
        http.side_effect = [
            {"id": 5298579, "slug": "memo-labs-automation"},
            [{"id": 987, "app_id": 5298579, "account": {"login": "memolabs-dev"}}],
            {"token": "test-token-only"},
        ]
        self.assertEqual(
            module.mint_token("automation", "cuesheet", {"contents": "read"}),
            "test-token-only"
        )
        self.assertEqual(http.call_args.args[0], "POST")
        self.assertEqual(http.call_args.args[1],
                         "/app/installations/987/access_tokens")
        self.assertEqual(
            http.call_args.args[3],
            {"repositories": ["cuesheet"], "permissions": {"contents": "read"}}
        )

    @patch.object(module, "github_request", return_value={"id": 3, "slug": "wrong-app"})
    @patch.object(module, "key_for")
    @patch.object(module, "signed_jwt", return_value="signed.jwt")
    @patch.object(module, "get_app_id", return_value=5298579)
    def test_wrong_app_identity_fails_closed(self, *_):
        with self.assertRaises(RuntimeError):
            module.mint_token("automation", ".github", {"contents": "read"})

    @patch.object(module, "github_request")
    @patch.object(module, "key_for")
    @patch.object(module, "signed_jwt", return_value="signed.jwt")
    @patch.object(module, "get_app_id", return_value=5298579)
    def test_missing_org_installation_fails_closed(self, _id, _jwt, _key, http):
        http.side_effect = [
            {"id": 5298579, "slug": "memo-labs-automation"},
            [{"id": 300, "app_id": 5298579, "account": {"login": "other-org"}}],
        ]
        with self.assertRaises(RuntimeError):
            module.mint_token("automation", ".github", {"contents": "read"})

    def test_missing_app_identity_metadata_fails(self):
        with patch.object(module, "IDENTITIES_PATH", Path("/no-such-memo-labs-metadata.json")):
            with self.assertRaises(ValueError):
                module.get_app_id("guardian")

    def test_unlisted_repository_is_rejected_before_token_mint(self):
        with self.assertRaises(ValueError):
            module.mint_token("automation", "not-an-org-repo", {"contents": "read"})

    def test_private_key_must_have_owner_only_permissions(self):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as td:
            with patch.object(module, "KEY_DIR", Path(td)):
                key = Path(td) / "memo-labs-automation.private-key.pem"
                key.write_text("dummy data, never a real key")
                os.chmod(key, 0o644)
                with self.assertRaises(ValueError):
                    module.key_for("automation")
                os.chmod(key, 0o600)
                self.assertEqual(module.key_for("automation"), key)

    def test_symlinked_private_key_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.pem"
            target.write_text("dummy")
            key = root / "memo-labs-automation.private-key.pem"
            key.symlink_to(target)
            with patch.object(module, "KEY_DIR", root):
                with self.assertRaises(ValueError):
                    module.key_for("automation")

    def test_cli_operation_must_target_selected_repo(self):
        valid = [
            ["gh", "api", "repos/memolabs-dev/cuesheet", "--jq", ".full_name"],
            ["gh", "api", "/repos/memolabs-dev/cuesheet/pulls", "-X", "GET"],
            ["gh", "pr", "list", "-R", "memolabs-dev/cuesheet"],
            ["gh", "issue", "list", "--repo=memolabs-dev/cuesheet"],
        ]
        for command in valid:
            with self.subTest(command=command):
                module.validate_command(command, "cuesheet")

    def test_cli_rejects_other_hosts_or_repository_targets(self):
        blocked = [
            ["gh", "api", "repos/memolabs-dev/drop"],
            ["gh", "api", "graphql"],
            ["gh", "api", "https://example.invalid/collect"],
            ["gh", "api", "repos/memolabs-dev/cuesheet/../../other"],
            ["gh", "api", "repos/memolabs-dev/cuesheet", "--hostname=example.invalid"],
            ["gh", "api", "repos/memolabs-dev/cuesheet", "-H", "Authorization: overridden"],
            ["gh", "pr", "list", "-R", "memolabs-dev/drop"],
            ["gh", "issue", "list"],
            ["gh", "issue", "list", "-R", "memolabs-dev/cuesheet", "--web"],
            ["gh", "auth", "status"],
        ]
        for command in blocked:
            with self.subTest(command=command), self.assertRaises(ValueError):
                module.validate_command(command, "cuesheet")

    def test_cli_process_environment_replaces_inherited_github_settings(self):
        import os
        with patch.dict(os.environ, {
            "GH_HOST": "example.invalid",
            "GH_REPO": "untrusted/elsewhere",
            "GH_CONFIG_DIR": "/tmp/untrusted",
            "GH_ENTERPRISE_TOKEN": "old-credential",
        }):
            env = module.restricted_env("synthetic-test-token")
        self.assertEqual(env["GH_HOST"], "github.com")
        self.assertEqual(env["GH_TOKEN"], "synthetic-test-token")
        self.assertEqual(env["GITHUB_TOKEN"], "synthetic-test-token")
        self.assertEqual(env["GH_PROMPT_DISABLED"], "1")
        for key in ("GH_REPO", "GH_CONFIG_DIR", "GH_ENTERPRISE_TOKEN"):
            self.assertNotIn(key, env)

    def test_external_redirect_with_authorization_is_rejected(self):
        request = module.Request("https://api.github.com/app", headers={
            "Authorization": "Bearer synthetic-test-token"
        })
        for url in ("https://example.invalid/collect", "http://api.github.com/"):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                module.GitHubOnlyRedirect().redirect_request(
                    request, None, 302, "Moved", {}, url
                )
