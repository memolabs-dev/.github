#!/usr/bin/env python3
"""Register Memo Guardian via GitHub's official App Manifest web handshake.

No GitHub API or gh CLI endpoint can bypass owner consent. This script
handles manifest submission and the *post-consent* key/CI configuration.
It never prints private keys, client secrets, or installation tokens.
"""
import argparse
import html
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
import webbrowser

ORG = "memolabs-dev"
APP = "memo-labs-guardian"
APP_KIND = "guardian"
REPO = "memolabs-dev/.github"
ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "github-apps" / f"{APP}.manifest.json"
SECRET_DIR = Path.home() / ".config" / "memolabs" / "secrets" / "github-app"
KEY_PATH = SECRET_DIR / f"{APP}.private-key.pem"

def run_gh(*args, input_text=None):
    result = subprocess.run(["gh", *args], input=input_text, capture_output=True,
                            text=True, timeout=45)
    if result.returncode:
        # Never print CLI stderr with potentially sensitive content.
        raise RuntimeError("GitHub CLI command failed: " + " ".join(args[:3]))
    return result.stdout.strip()

def doctor():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = ({"contents":"read", "pull_requests":"read", "actions":"read", "checks":"write"}
                if APP_KIND == "guardian" else
                {"contents":"write", "deployments":"write", "actions":"read"})
    if manifest.get("default_permissions") != expected or manifest.get("default_events") != []:
        raise RuntimeError("Unexpected manifest permission or event scope")
    if manifest.get("name") != APP or manifest.get("public") is not False:
        raise RuntimeError("Unexpected manifest identity/public scope")
    if manifest.get("hook_attributes", {}).get("active") is not False:
        raise RuntimeError("Webhooks must be inactive")
    print(APP, "manifest validated.")
    print("GitHub CLI session: ", run_gh("api","user","--jq",".login"))
    print("Key exists:", KEY_PATH.exists())
    print("Registration needs a GitHub web authorization step.")

def safe_store_key(pem):
    if not pem.startswith("-----BEGIN ") or "PRIVATE KEY-----" not in pem:
        raise RuntimeError("GitHub returned an invalid private key")
    for directory in (SECRET_DIR.parent.parent, SECRET_DIR.parent, SECRET_DIR):
        if directory.is_symlink():
            raise RuntimeError("Refusing secret storage under a symlink")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(pem)
        output.flush()
        os.fsync(output.fileno())

def store_app_identity(kind, app_id):
    """Persist only the public App ID for later short-lived token minting."""
    import tempfile
    if not isinstance(app_id, int) or app_id <= 0:
        raise ValueError("App ID must be a positive integer")
    location = SECRET_DIR.parent.parent / "app-identities.json"
    if location.is_symlink():
        raise RuntimeError("Refusing symlink identity metadata file")
    existing = json.loads(location.read_text()) if location.exists() else {}
    if not isinstance(existing, dict):
        raise RuntimeError("Invalid local app identity registry")
    if kind in existing and existing[kind] != app_id:
        raise RuntimeError("Refusing to replace a different registered App ID")
    existing[kind] = app_id
    fd, temp_path = tempfile.mkstemp(prefix=".app-identities-", dir=str(location.parent))
    try:
        os.chmod(temp_path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(existing, out, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, location)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def register():
    doctor()
    if KEY_PATH.exists():
        raise RuntimeError(f"{APP} key already exists. Refusing duplicate registration.")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    state = secrets.token_urlsafe(28)
    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_address[1]
    callback = f"http://127.0.0.1:{port}/callback"
    manifest["redirect_url"] = callback
    results = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            path = urlsplit(self.path)
            if path.path == "/":
                url = f"https://github.com/organizations/{ORG}/settings/apps/new?state={state}"
                form = (
                    "<!doctype html><html><body><p>Ouverture de GitHub...</p>"
                    f'<form id="go" method="post" action="{html.escape(url, quote=True)}">'
                    f'<input type="hidden" name="manifest" value="{html.escape(json.dumps(manifest),quote=True)}">'
                    '</form><script>document.getElementById("go").submit()</script></body></html>'
                )
                data = form.encode()
            elif path.path == "/callback":
                q = parse_qs(path.query)
                if q.get("state", [None])[0] != state or not q.get("code"):
                    self.send_error(403)
                    return
                results["code"] = q["code"][0]
                data = b"<p>Consentement recu. La configuration continue dans le Terminal.</p>"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server.RequestHandlerClass = Handler
    server.timeout = 2
    print("Ouverture du navigateur pour l'enregistrement GitHub officiel...")
    webbrowser.open(f"http://127.0.0.1:{port}/")
    deadline = time.monotonic() + 600
    while not results.get("code") and time.monotonic() < deadline:
        server.handle_request()
    server.server_close()
    code = results.get("code")
    if not code:
        raise RuntimeError("Consent was not completed within 10 minutes; no app created by this script.")
    req = Request(
        "https://api.github.com/app-manifests/" + code + "/conversions",
        data=b"", method="POST",
        headers={"Accept":"application/vnd.github+json", "User-Agent":"Memo-Labs-Guardian-Registrar"}
    )
    with urlopen(req, timeout=30) as resp:
        app = json.load(resp)
    if app.get("slug") != APP or app.get("owner", {}).get("login") != ORG:
        raise RuntimeError("Unexpected GitHub App/organization in conversion response")
    safe_store_key(app["pem"])
    # Only public numeric App IDs are saved; no token, PEM or client secret.
    store_app_identity(APP_KIND, int(app["id"]))
    print("Registered:", APP, "(app id:", app["id"], ")")
    print("Private key safely stored on Mac with mode 0600.")
    try:
        run_gh("variable","set",f"MEMOLABS_{APP_KIND.upper()}_CLIENT_ID","--repo",REPO,"--body",app["client_id"])
        run_gh("secret","set",f"MEMOLABS_{APP_KIND.upper()}_PRIVATE_KEY","--repo",REPO,input_text=app["pem"])
        print("GitHub Actions variable and encrypted secret configured.")
    except Exception:
        print("GitHub Actions credentials not yet configured (CLI authorization failure).")
        print("PEM remains only in local secret store; please check gh authorization.")
    print("GitHub must authorize the installation on the selected .github repository.")
    webbrowser.open(f"https://github.com/apps/{APP}/installations/new")
    print(f"After installation, run: python3 scripts/register-guardian.py --app {APP_KIND} --verify")

def verify():
    doctor()
    installed = json.loads(run_gh("api",f"/orgs/{ORG}/installations"))
    matched = [x for x in installed.get("installations", []) if x.get("app_slug") == APP]
    if not matched:
        raise RuntimeError(f"{APP} is not yet installed on memolabs-dev.")
    print("Guardian installation detected:", matched[0]["id"])
    workflow = "guardian-check-smoke.yml" if APP_KIND == "guardian" else "release-app-auth-smoke.yml"
    run_gh("workflow","run",workflow,"-R",REPO,"--ref","main")
    print(APP, "verification workflow triggered; review Actions for success.")
    print("This is NOT a code-quality, release or production acceptance check.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", choices=("guardian", "release"), default="guardian")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doctor",action="store_true")
    group.add_argument("--register",action="store_true")
    group.add_argument("--verify",action="store_true")
    args = parser.parse_args()
    APP_KIND = args.app
    APP = f"memo-labs-{APP_KIND}"
    MANIFEST_PATH = ROOT / "github-apps" / f"{APP}.manifest.json"
    KEY_PATH = SECRET_DIR / f"{APP}.private-key.pem"
    try:
        if args.doctor: doctor()
        elif args.register: register()
        else: verify()
    except Exception as err:
        print("ERROR:", str(err), file=sys.stderr)
        sys.exit(1)
