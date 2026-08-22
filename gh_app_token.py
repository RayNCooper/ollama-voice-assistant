#!/usr/bin/env python3
"""GitHub App helper for the Hermes Agent walled-garden.

Mints a short-lived installation access token for the Hermes Agent GitHub App
(Contents + Administration write, installed on NO existing repos). The App
auto-grants access to any repo it creates, so this token can only ever touch
repos the App itself creates — never pre-existing ones.

Usage:
  python3 gh_app_token.py            # print installation access token
  python3 gh_app_token.py --install  # print installation ID (one-time lookup)
"""
import json
import sys
import time
import urllib.request

import jwt

APP_ID = "4683246"
CLIENT_ID = "Iv23likCfCwdpjN1b8bJ"
KEY_PATH = "/workspace/secrets/GH_APP_HERMES_AGENT.pem"
API = "https://api.github.com"


def _jwt() -> str:
    with open(KEY_PATH) as f:
        key = f.read()
    now = int(time.time())
    return jwt.encode(
        {"iat": now, "exp": now + 600, "iss": APP_ID},
        key,
        algorithm="RS256",
    )


def _req(url, token, method="GET", body=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hermes-agent",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def get_installation_id() -> str:
    """Find the installation of this App on the owner account."""
    jwt_token = _jwt()
    data = _req(f"{API}/app/installations", jwt_token)
    if not data:
        raise RuntimeError("No installations found for the Hermes Agent App.")
    # Prefer the account-level install (no repo selection) if present.
    for inst in data:
        if inst.get("repository_selection") == "all":
            return str(inst["id"])
    return str(data[0]["id"])


def get_token() -> str:
    inst_id = get_installation_id()
    jwt_token = _jwt()
    data = _req(
        f"{API}/app/installations/{inst_id}/access_tokens",
        jwt_token,
        method="POST",
        body={},
    )
    return data["token"]


if __name__ == "__main__":
    if "--install" in sys.argv:
        print(get_installation_id())
    else:
        print(get_token())
