"""Explicit owner-only private GitHub project enrollment on macOS.

This is separate from the historical *public* pilot allowlist.
No private repository is allowed unless the owner has provisioned a local,
private (0600) policy file for an authenticated Memo Bridge process on his Mac:
the Mac runtime (MEMO_BRIDGE_AGENT_MODE=runtime, which serves his remote connector)
or his local stdio server (MEMO_BRIDGE_AGENT_MODE=stdio).

Two owner files may enroll a repository, each checked the same way (fixed path in the
account's home, regular file, no symlink, owner uid, mode 0600, bounded size, exact schema,
owner_sub equal to MEMO_BRIDGE_OWNER_SUB):
- owner-policy/private-repos.json       {schema, owner_sub, repos: ["owner/repo", ...]}
- owner-policy/external-projects.json   {schema, owner_sub, projects: [{name, path, repo}, ...]},
  the owner's checkouts outside MEMOLABS_ROOT; enrolling one enrolls its repository.
A malformed or untrusted file enrolls nothing; the other file is judged on its own.

A NEW lease on an enrolled repository also needs MEMO_BRIDGE_LEDGER_OWNER_CALL=1, which Memo
Bridge sets per call for the owner's own principals only (fix pass of memo-bridge#258): the Mac
runtime also serves hub:owner, hub:readonly and reader:, which must never claim a private
repository. The current holder's own checks (verify, heartbeat: holding=True) do not need it.

lease_key() gives the owner's key for the names of private lease refs (issue_lease.py), from a
third owner file checked the same way:
- owner-policy/lease-key.json           {schema, owner_sub, key: 64 hex}, path in
  MEMO_BRIDGE_OWNER_LEASE_KEY_FILE.
"""
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

SCHEMA = "memolabs.owner-private-repos.v1"
EXTERNAL_SCHEMA = "memolabs.owner-external-projects.v1"
LEASE_KEY_SCHEMA = "memolabs.owner-lease-key.v1"
OWNER_CALL = "MEMO_BRIDGE_LEDGER_OWNER_CALL"
KEY_HEX = re.compile(r"^[0-9a-f]{64}$")
OWNER = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# The owner's namespaces (owner decision of 2026-10-22): his organization and his own account.
REPO = re.compile(r"^(?:memolabs-dev|guillaume-flambard)/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
MAX_BYTES = 16 * 1024
MAX_REPOS = 100
MAX_EXTERNAL = 20  # memo-bridge server/projects/external-projects.mjs
MODES = frozenset({"runtime", "stdio"})
POLICY_DIR = (".local", "share", "memo-bridge", "owner-policy")


def _mode_ok(env):
    mode = env.get("MEMO_BRIDGE_AGENT_MODE")
    if mode not in MODES:
        return False
    # The Mac runtime also carries its own enablement switch; the stdio server has none.
    return mode != "runtime" or env.get("MEMO_BRIDGE_MAC_RUNTIME_ENABLED") == "enabled"


def _read_owner_file(env, variable, filename, home, uid):
    """The parsed JSON object of one owner file, or None when absent, untrusted or malformed."""
    expected = home.joinpath(*POLICY_DIR, filename)
    path = env.get(variable)
    if not isinstance(path, str) or path != str(expected):
        return None
    try:
        if os.path.realpath(path) != path:
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or
                    (info.st_mode & 0o077) or not (0 < info.st_size <= MAX_BYTES)):
                return None
            data = os.read(fd, MAX_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) > MAX_BYTES:
            return None
        obj = json.loads(data.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError, TypeError, UnicodeError):
        return None


def _unique_repos(repos):
    if (not isinstance(repos, list) or len(repos) > MAX_REPOS or
            any(not isinstance(r, str) or not REPO.fullmatch(r) for r in repos) or
            len({r.lower() for r in repos}) != len(repos)):
        return None
    return repos


def _private_repos(obj, sub):
    if obj is None or set(obj) != {"schema", "owner_sub", "repos"}:
        return []
    if obj["schema"] != SCHEMA or obj["owner_sub"] != sub:
        return []
    return _unique_repos(obj["repos"]) or []


def _external_repos(obj, sub):
    if obj is None or set(obj) != {"schema", "owner_sub", "projects"}:
        return []
    projects = obj["projects"]
    if (obj["schema"] != EXTERNAL_SCHEMA or obj["owner_sub"] != sub or not isinstance(projects, list) or
            len(projects) > MAX_EXTERNAL):
        return []
    repos = []
    names = set()
    for item in projects:
        if (not isinstance(item, dict) or set(item) != {"name", "path", "repo"} or
                not isinstance(item["name"], str) or not NAME.fullmatch(item["name"]) or
                item["name"] in names or
                not isinstance(item["path"], str) or not os.path.isabs(item["path"]) or
                "\0" in item["path"] or os.path.normpath(item["path"]) != item["path"]):
            return []
        names.add(item["name"])
        repos.append(item["repo"])
    return _unique_repos(repos) or []


def _owner_context(environ, platform, home, uid):
    """(env, home, uid, sub) of the owner's Memo Bridge on his Mac, or None."""
    env = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    uid = os.geteuid() if uid is None else uid
    # The account's home from the password database, never $HOME: Memo Bridge runs this script
    # as the ledger child with HOME pointed at a private gh configuration directory
    # (memo-bridge server/coordinator/credentials.mjs ghChildEnv), so Path.home() would name
    # that directory and the owner's policy file would never match.
    if home is None:
        try:
            home = pwd.getpwuid(uid).pw_dir
        except (KeyError, OSError):
            return None
    if platform != "darwin" or env.get("MEMO_BRIDGE_HOST") != "mac" or not _mode_ok(env):
        return None
    sub = env.get("MEMO_BRIDGE_OWNER_SUB")
    if not isinstance(sub, str) or not OWNER.fullmatch(sub):
        return None
    return env, Path(home), uid, sub


def _enrolled(repo, ctx):
    env, home, uid, sub = ctx
    if repo in _private_repos(_read_owner_file(
            env, "MEMO_BRIDGE_OWNER_PRIVATE_REPOS_FILE", "private-repos.json", home, uid), sub):
        return True
    return repo in _external_repos(_read_owner_file(
        env, "MEMO_BRIDGE_OWNER_EXTERNAL_PROJECTS_FILE", "external-projects.json", home, uid), sub)


def allowed(repo, *, holding=False, environ=None, platform=None, home=None, uid=None):
    """Fail closed on malformed, inaccessible or non-owner Mac policy."""
    if not isinstance(repo, str) or not REPO.fullmatch(repo):
        return False
    ctx = _owner_context(environ, platform, home, uid)
    if ctx is None:
        return False
    if not holding and ctx[0].get(OWNER_CALL) != "1":
        return False
    return _enrolled(repo, ctx)


def lease_key(repo, *, environ=None, platform=None, home=None, uid=None):
    """The owner's 32-byte key for an enrolled repository's lease names, or None (public,
    non-enrolled, off the owner's Mac, or no trusted key file)."""
    if not isinstance(repo, str) or not REPO.fullmatch(repo):
        return None
    ctx = _owner_context(environ, platform, home, uid)
    if ctx is None or not _enrolled(repo, ctx):
        return None
    env, home, uid, sub = ctx
    obj = _read_owner_file(env, "MEMO_BRIDGE_OWNER_LEASE_KEY_FILE", "lease-key.json", home, uid)
    if (obj is None or set(obj) != {"schema", "owner_sub", "key"} or obj["schema"] != LEASE_KEY_SCHEMA or
            obj["owner_sub"] != sub or not isinstance(obj["key"], str) or not KEY_HEX.fullmatch(obj["key"])):
        return None
    return bytes.fromhex(obj["key"])
