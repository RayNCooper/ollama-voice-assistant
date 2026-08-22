#!/usr/bin/env python3
"""Push the repo to GitHub using the Hermes Agent App token."""
import subprocess
import sys

sys.path.insert(0, "/workspace/scripts")
from gh_app_token import get_token

token = get_token()
repo = "https://x-access-token:%s@github.com/RayNCooper/ollama-voice-assistant.git" % token

def run(cmd):
    r = subprocess.run(cmd, cwd="/workspace/ollama-voice-assistant", capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print("ERR:", r.stderr.strip())
        sys.exit(r.returncode)

run(["git", "remote", "set-url", "origin", repo])
run(["git", "push", "origin", "main"])
run(["git", "remote", "set-url", "origin", "https://github.com/RayNCooper/ollama-voice-assistant.git"])
print("=== pushed + remote scrubbed ===")
