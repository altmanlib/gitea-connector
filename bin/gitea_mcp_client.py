#!/usr/bin/env python3
"""MCP client for the official Gitea MCP server (stdio), with a local
credential-injecting proxy.

Why the proxy exists: the vault surrogate is only swapped for the real token
when it sits at the registered placement, the `access_token` query parameter
on requests to the Gitea host. The MCP server sends its token in an
Authorization header instead, so the wrapper runs a loopback proxy: the
server talks to the proxy, the proxy strips the placeholder Authorization
header and forwards each request to Gitea with the surrogate placed in the
`access_token` query parameter, where the swap happens.

Usage:
  gitea_mcp_client.py list-tools
  gitea_mcp_client.py call-tool --name <tool> --arguments-file <path-to-json>

Environment:
  GITEA_BASE_URL    Gitea instance base URL, e.g. https://git.example.com (required)
  GITEA_CREDENTIAL  Registered credential name (default custom.gitea)
  GITEA_MCP_BIN     Path to the gitea-mcp binary (default: beside this file)
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import dynamic_credential_entry

BASE = os.environ.get("GITEA_BASE_URL", "").rstrip("/")
CRED = os.environ.get("GITEA_CREDENTIAL", "custom.gitea")
if not BASE:
    print("Set GITEA_BASE_URL to your Gitea instance, e.g. https://git.example.com", file=sys.stderr)
    sys.exit(2)
BIN = os.environ.get(
    "GITEA_MCP_BIN",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "gitea-mcp"),
)
TIMEOUT = 60

# Reviewed tools from the official server. Anything not listed here stays
# blocked until it is reviewed and added. See CONNECTOR.md for the record.
# This set holds the read-only tools of server v1.11.0. Every write tool
# stays blocked until its operation is reviewed on its own.
ALLOWED_TOOLS = {
    "actions_config_read",
    "actions_run_read",
    "attachment_read",
    "compare_commits",
    "get_commit",
    "get_commit_status",
    "get_dir_contents",
    "get_file_contents",
    "get_gitea_mcp_server_version",
    "get_latest_release",
    "get_me",
    "get_release",
    "get_repository_tree",
    "get_tag",
    "get_user_orgs",
    "issue_read",
    "label_read",
    "list_branches",
    "list_commits",
    "list_issues",
    "list_my_repos",
    "list_org_repos",
    "list_pull_requests",
    "list_releases",
    "list_tags",
    "milestone_read",
    "notification_read",
    "package_read",
    "project_read",
    "pull_request_read",
    "search_issues",
    "search_org_teams",
    "search_repos",
    "search_users",
    "timetracking_read",
    "wiki_read",
}


def surrogate():
    entry = dynamic_credential_entry(CRED, "access_token")
    return str(entry["surrogate"]).strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused")


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _forward(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        parts = urllib.parse.urlsplit(BASE + self.path)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        query.append(("access_token", surrogate()))
        url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
        req = urllib.request.Request(url, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() in ("host", "authorization", "content-length", "connection", "accept-encoding"):
                continue
            req.add_header(key, value)
        req.add_header("User-Agent", "Claude-Gitea-Connector/1.0")
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(req, timeout=30) as resp:
                status, headers, data = resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            status, headers, data = e.code, e.headers, e.read()
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() in ("connection", "transfer-encoding", "content-length"):
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = _forward
    do_POST = _forward
    do_PUT = _forward
    do_PATCH = _forward
    do_DELETE = _forward
    do_HEAD = _forward
    do_OPTIONS = _forward


class McpStdio:
    def __init__(self, argv):
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1
        )
        self.inbox = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self.inbox.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def request(self, method, params=None):
        self.next_id += 1
        rid = self.next_id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        import time

        end = time.time() + TIMEOUT
        while time.time() < end:
            try:
                incoming = self.inbox.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                break
            if incoming.get("id") == rid:
                return incoming
        raise TimeoutError(f"no response to {method} within {TIMEOUT}s")

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main():
    parser = argparse.ArgumentParser(prog="gitea_mcp_client.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-tools")
    p_call = sub.add_parser("call-tool")
    p_call.add_argument("--name", required=True)
    p_call.add_argument("--arguments-file", required=True)
    args = parser.parse_args()

    proxy = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    port = proxy.server_address[1]
    threading.Thread(target=proxy.serve_forever, daemon=True).start()

    client = McpStdio([BIN, "-t", "stdio", "-H", f"http://127.0.0.1:{port}", "-T", "managed-by-proxy"])
    try:
        init = client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "muse-gitea-connector", "version": "1.0"},
            },
        )
        if "error" in init:
            print(json.dumps(init["error"], ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        client.notify("notifications/initialized")

        if args.cmd == "list-tools":
            tools, cursor = [], None
            while True:
                params = {"cursor": cursor} if cursor else {}
                page = client.request("tools/list", params)
                if "error" in page:
                    print(json.dumps(page["error"], ensure_ascii=False, indent=2), file=sys.stderr)
                    return 1
                result = page.get("result", {})
                tools.extend(result.get("tools", []))
                cursor = result.get("nextCursor")
                if not cursor:
                    break
            print(json.dumps(tools, ensure_ascii=False, indent=2))
            return 0

        if args.cmd == "call-tool":
            if args.name not in ALLOWED_TOOLS:
                print(f"tool not in allowlist: {args.name}", file=sys.stderr)
                return 1
            with open(args.arguments_file, "r", encoding="utf-8") as fh:
                arguments = json.load(fh)
            reply = client.request("tools/call", {"name": args.name, "arguments": arguments})
            if "error" in reply:
                print(json.dumps(reply["error"], ensure_ascii=False, indent=2), file=sys.stderr)
                return 1
            result = reply.get("result", {})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result.get("isError") else 0
        return 2
    finally:
        client.close()
        proxy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
