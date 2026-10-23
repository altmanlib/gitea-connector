#!/usr/bin/env python3
"""Generic Gitea API helper for a Muse custom connector.

Environment:
  GITEA_BASE_URL    Base URL of the Gitea instance, e.g. https://git.example.com
  GITEA_CREDENTIAL  Registered credential name, default custom.gitea

Usage:
  gitea.py version
  gitea.py user
  gitea.py repos [--limit N]
  gitea.py request METHOD /api/v1/path [--data '<json>']
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import url_with_surrogate_query_param

BASE = os.environ.get("GITEA_BASE_URL", "").rstrip("/")
CRED = os.environ.get("GITEA_CREDENTIAL", "custom.gitea")
if not BASE:
    print("Set GITEA_BASE_URL to your Gitea instance, e.g. https://git.example.com", file=sys.stderr)
    sys.exit(2)
HOST = urllib.parse.urlsplit(BASE).hostname


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call(method, path, data=None):
    url = url_with_surrogate_query_param(BASE + path, CRED, allowed_hosts=[HOST])
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    # Some instances sit behind a CDN that bans the default Python user agent.
    req.add_header("User-Agent", "Muse-Gitea-Connector/1.0")
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def emit(status, text):
    try:
        payload = json.loads(text)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        pass
    print(f"HTTP {status}")
    print(text)
    return 0 if status < 300 else 1


def main():
    parser = argparse.ArgumentParser(prog="gitea.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    sub.add_parser("user")
    p_repos = sub.add_parser("repos")
    p_repos.add_argument("--limit", type=int, default=50)
    p_req = sub.add_parser("request")
    p_req.add_argument("method")
    p_req.add_argument("path")
    p_req.add_argument("--data")
    args = parser.parse_args()

    if args.cmd == "version":
        return emit(*call("GET", "/api/v1/version"))
    if args.cmd == "user":
        return emit(*call("GET", "/api/v1/user"))
    if args.cmd == "repos":
        status, text = call("GET", f"/api/v1/user/repos?limit={args.limit}")
        if status < 300:
            names = [r.get("full_name") for r in json.loads(text)]
            print(f"HTTP {status}")
            print(json.dumps(names, ensure_ascii=False, indent=2))
            return 0
        return emit(status, text)
    if args.cmd == "request":
        data = json.loads(args.data) if args.data else None
        return emit(*call(args.method.upper(), args.path, data))
    return 2


if __name__ == "__main__":
    sys.exit(main())
