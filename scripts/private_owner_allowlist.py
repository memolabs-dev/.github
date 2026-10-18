"""Explicit owner-only private GitHub project enrollment on macOS.

This is separate from the historical *public* pilot allowlist.
No private repository is allowed unless the owner has provisioned a local,
private (0600) policy file for the authenticated Mac runtime.
"""
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

SCHEMA = "memolabs.owner-private-repos.v1"
OWNER = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
REPO = re.compile(r"^memolabs-dev/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
MAX_BYTES = 16 * 1024


def allowed(repo, *, environ=None, platform=None, home=None, uid=None):
    """Fail closed on malformed, inaccessible or non-owner Mac runtime policy."""
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
            return False
    home = Path(home)
    if (platform != "darwin" or env.get("MEMO_BRIDGE_HOST") != "mac" or
            env.get("MEMO_BRIDGE_AGENT_MODE") != "runtime" or
            env.get("MEMO_BRIDGE_MAC_RUNTIME_ENABLED") != "enabled" or
            not isinstance(repo, str) or not REPO.fullmatch(repo)):
        return False
    sub = env.get("MEMO_BRIDGE_OWNER_SUB")
    if not isinstance(sub, str) or not OWNER.fullmatch(sub):
        return False
    expected = home / ".local" / "share" / "memo-bridge" / "owner-policy" / "private-repos.json"
    path = env.get("MEMO_BRIDGE_OWNER_PRIVATE_REPOS_FILE")
    if not isinstance(path, str) or path != str(expected):
        return False
    try:
        if os.path.realpath(path) != path:
            return False
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or
                    (info.st_mode & 0o077) or not (0 < info.st_size <= MAX_BYTES)):
                return False
            data = os.read(fd, MAX_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) > MAX_BYTES:
            return False
        obj = json.loads(data.decode("utf-8"))
        if not isinstance(obj, dict) or set(obj) != {"schema", "owner_sub", "repos"}:
            return False
        repos = obj["repos"]
        if (obj["schema"] != SCHEMA or obj["owner_sub"] != sub or
                not isinstance(repos, list) or len(repos) > 50 or
                any(not isinstance(r, str) or not REPO.fullmatch(r) for r in repos) or
                len({r.lower() for r in repos}) != len(repos)):
            return False
        return repo in repos
    except (OSError, ValueError, TypeError, UnicodeError):
        return False
