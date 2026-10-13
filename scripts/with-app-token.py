#!/usr/bin/env python3
"""Execute a GitHub CLI operation with a narrowly scoped GitHub App token.

No PAT needed to mint the token. Secrets are never printed or saved by this
program. Running a command requires the explicit --execute flag.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit

ORG = "memolabs-dev"
ROOT = Path(__file__).resolve().parent.parent
KEY_DIR = Path.home() / ".config/memolabs/secrets/github-app"
IDENTITIES_PATH = Path.home() / ".config/memolabs/app-identities.json"
KNOWN_IDS = {"automation": 5298579}
ALLOWED_REPOS = frozenset((
    ".github", "cuesheet", "uni-protocol", "problem-intelligence-engine",
    "drop", "lab-hub", "kollio-v3", "emargo", "lab-console"
))


def encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def get_app_id(kind):
    if kind in KNOWN_IDS:
        return KNOWN_IDS[kind]
    if not IDENTITIES_PATH.is_file() or IDENTITIES_PATH.is_symlink():
        raise ValueError("Missing local App identity metadata; complete registration first")
    identities = json.loads(IDENTITIES_PATH.read_text(encoding="utf-8"))
    app_id = identities.get(kind)
    if type(app_id) is not int or app_id < 1:
        raise ValueError("Missing valid App ID for requested identity")
    return app_id


def validate_permission_scope(kind, permission_text):
    manifest = json.loads(
        (ROOT / "github-apps" / f"memo-labs-{kind}.manifest.json").read_text()
    ) if kind != "automation" else {
        "default_permissions": {
            "contents": "write", "pull_requests": "write",
            "issues": "write", "actions": "read",
        }
    }
    maximum = manifest["default_permissions"]
    requested = {}
    for raw in permission_text:
        if "=" not in raw:
            raise ValueError("Permissions must use permission=read or permission=write")
        scope, level = raw.split("=", 1)
        if scope in requested or scope not in maximum or level not in ("read", "write"):
            raise ValueError("Duplicate, unknown or invalid permission")
        if level == "write" and maximum[scope] != "write":
            raise ValueError("The selected App cannot write this permission scope")
        requested[scope] = level
    if not requested:
        requested = {"contents": "read"}
    return requested


def key_for(kind):
    path = KEY_DIR / f"memo-labs-{kind}.private-key.pem"
    if path.is_symlink() or not path.is_file():
        raise ValueError("App key unavailable in the local protected key store")
    bits = path.stat().st_mode
    if not stat.S_ISREG(bits) or bits & 0o077:
        raise ValueError("App key must be a regular file accessible only to owner (0600)")
    return path


def signed_jwt(app_id, private_key):
    now = int(time.time())
    header = encode(b'{"alg":"RS256","typ":"JWT"}')
    payload = encode(json.dumps(
        {"iat": now - 60, "exp": now + 480, "iss": str(app_id)},
        separators=(",", ":")
    ).encode())
    signing_input = (header + "." + payload).encode()
    signature = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private_key)],
        input=signing_input, capture_output=True, check=True, timeout=12
    ).stdout
    return signing_input.decode() + "." + encode(signature)


class GitHubOnlyRedirect(HTTPRedirectHandler):
    """Reject redirects that could send bearer credentials to another host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urlsplit(newurl)
        if destination.scheme != "https" or destination.hostname != "api.github.com":
            raise RuntimeError("Cross-host GitHub API redirect rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def github_request(method, endpoint, jwt_or_token, data=None):
    if not endpoint.startswith("/") or "://" in endpoint:
        raise ValueError("Only relative GitHub API paths are permitted")
    headers = {
        "Authorization": "Bearer " + jwt_or_token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Memo-Labs-Installation-Token",
    }
    payload = json.dumps(data).encode() if data is not None else None
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = Request(
        "https://api.github.com" + endpoint, headers=headers,
        method=method, data=payload
    )
    try:
        with build_opener(GitHubOnlyRedirect()).open(req, timeout=22) as response:
            return json.load(response)
    except (HTTPError, URLError) as exc:
        # Never forward API bodies or request headers which can contain credentials.
        status = getattr(exc, "code", "network error")
        raise RuntimeError(f"GitHub API request failed ({status})") from None


def mint_token(kind, repo, permissions):
    if repo not in ALLOWED_REPOS:
        raise ValueError("Repository is not in the authorized Memo Labs inventory")
    if permissions != validate_permission_scope(
        kind, [f"{name}={level}" for name, level in permissions.items()]
    ):
        raise ValueError("Requested permissions did not validate")
    app_id = get_app_id(kind)
    jwt = signed_jwt(app_id, key_for(kind))
    app = github_request("GET", "/app", jwt)
    if app.get("id") != app_id or app.get("slug") != f"memo-labs-{kind}":
        raise RuntimeError("App identity mismatch")
    installations = github_request("GET", "/app/installations?per_page=100", jwt)
    matches = [
        x for x in installations
        if x.get("account", {}).get("login") == ORG
        and x.get("app_id") == app_id
    ]
    if len(matches) != 1:
        raise RuntimeError("Exactly one installation on memolabs-dev is required")
    info = github_request(
        "POST", f"/app/installations/{matches[0]['id']}/access_tokens",
        jwt, {"repositories": [repo], "permissions": permissions}
    )
    token = info.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Installation did not return a token")
    return token


def validate_command(command, repo):
    """Prevent routing the ephemeral token outside its authorized GitHub repo."""
    expected = f"{ORG}/{repo}"
    if len(command) < 3 or command[0] != "gh":
        raise ValueError("An explicit gh api, gh pr or gh issue operation is required")
    if command[1] not in ("api", "pr", "issue"):
        raise ValueError("Only gh api, gh pr or gh issue are supported")
    for item in command[2:]:
        if item in ("--hostname", "-H", "--header", "--web", "--editor"):
            raise ValueError("Unsupported command flag when using an App token")
        if (item.startswith("--hostname=") or item.startswith("--header=")
                or item.startswith("-H") and len(item) > 2):
            raise ValueError("Host or authorization header overrides are disallowed")
    if command[1] == "api":
        endpoint = command[2].lstrip("/")
        base = "repos/" + expected
        if not (endpoint == base or endpoint.startswith(base + "/")):
            raise ValueError("GitHub API endpoint must be inside the selected repository")
        segments = endpoint.split("/")
        if any(segment in ("..", ".") for segment in segments) or "?" in endpoint:
            raise ValueError("Relative API paths and query strings are not permitted")
        return
    # gh pr / gh issue must always receive an explicit matching -R/--repo,
    # even when the working tree belongs to a different repository.
    provided = []
    for i, item in enumerate(command[2:], start=2):
        if item in ("-R", "--repo"):
            if i + 1 >= len(command):
                raise ValueError("Repository selector has no value")
            provided.append(command[i + 1])
        elif item.startswith(("--repo=", "-R=")):
            provided.append(item.split("=", 1)[1])
    if not provided or any(value != expected for value in provided):
        raise ValueError("gh pr/issue command needs matching -R/--repo")


def restricted_env(token):
    env = os.environ.copy()
    for key in ("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
                "GH_CONFIG_DIR", "GH_REPO", "GH_HOST", "GH_DEBUG", "GH_PAGER"):
        env.pop(key, None)
    env["GH_HOST"] = "github.com"
    env["GH_TOKEN"] = token
    env["GITHUB_TOKEN"] = token
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", choices=("automation", "guardian", "release"), default="automation")
    parser.add_argument("--repo", choices=sorted(ALLOWED_REPOS), default=".github")
    parser.add_argument("--permission", action="append", default=[], metavar="SCOPE=LEVEL")
    parser.add_argument("--execute", action="store_true",
                        help="Actually mint a token and execute the command")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="Command following --, beginning with gh")
    args = parser.parse_args()
    permissions = validate_permission_scope(args.app, args.permission)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    try:
        validate_command(command, args.repo)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"App={args.app}, repository={ORG}/{args.repo}, scope={permissions}", file=sys.stderr)
    if not args.execute:
        print("DRY RUN: no token minted; add --execute to run", file=sys.stderr)
        return 0
    token = mint_token(args.app, args.repo, permissions)
    env = restricted_env(token)
    # No shell, no token on command line, no token in inherited git config.
    finished = subprocess.run(command, env=env, timeout=300)
    return finished.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Unable to complete App command: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
