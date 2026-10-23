# Gitea Connector for Muse

A custom connector that lets [Muse](https://muse.ai) work with a self-hosted
Gitea instance through its REST API: read the instance version, the current
user and repositories, and call any other API path through a generic request
command.

No credential lives in this repository. The Gitea access token is stored in
Muse's secure credential store and reaches requests only through a surrogate
exchange, so this code is safe to share as-is.

## Contents

- `CONNECTOR.md` — the connector doc Muse reads: setup details, verified
  commands, error recovery and limits.
- `connector.yaml` — the connector descriptor.
- `bin/gitea.py` — the REST API helper (Python 3, standard library only).
- `bin/gitea_mcp_client.py` — a client for the official Gitea MCP server,
  with a loopback proxy that injects the credential (see "MCP variant").

## Setup

1. In Gitea, create an access token under
   **Settings → Applications → Generate New Token**. Grant the scopes you
   need, for example `write:repository`, `write:issue` and `read:user`.
2. Ask Muse to set up a custom connector for Gitea. It registers the
   connection with these details and gives you a secure page to paste the
   token into (never paste a token into chat):

   - provider: `gitea`
   - auth scheme: `api_key`
   - placement: `query_param:access_token`
   - API hosts: your instance host, e.g. `git.example.com`

3. Copy this repository into `~/workspace/custom-connectors/custom.gitea/`.
4. Verify with a harmless read:

   ```sh
   GITEA_BASE_URL=https://git.example.com \
     python3 ~/workspace/custom-connectors/custom.gitea/bin/gitea.py user
   ```

## Usage

```sh
export GITEA_BASE_URL=https://git.example.com

python3 bin/gitea.py version
python3 bin/gitea.py user
python3 bin/gitea.py repos --limit 50
python3 bin/gitea.py request GET /api/v1/repos/owner/repo/issues
```

Set `GITEA_CREDENTIAL` when the registered credential name is not
`custom.gitea`.

## MCP variant

The connector also wraps the official Gitea MCP server
([gitea.com/gitea/gitea-mcp](https://gitea.com/gitea/gitea-mcp)), which exposes
61 tools in v1.11.0 covering repositories, issues, pull requests, workflows
and releases with typed schemas.

Download the pinned binary (this repo does not redistribute it) and verify it
against the release checksums:

```sh
curl -LO https://gitea.com/gitea/gitea-mcp/releases/download/v1.11.0/gitea-mcp_Linux_x86_64.tar.gz
curl -LO https://gitea.com/gitea/gitea-mcp/releases/download/v1.11.0/gitea-mcp_1.11.0_checksums.txt
sha256sum -c gitea-mcp_1.11.0_checksums.txt --ignore-missing
tar -xzf gitea-mcp_Linux_x86_64.tar.gz gitea-mcp
```

`bin/gitea_mcp_client.py` runs the server over stdio, one process per call,
and exposes `list-tools` and `call-tool` commands. Only reviewed read-only
tools are in its allowlist; write tools stay blocked until reviewed.

One integration detail matters: the server sends its token in an
`Authorization` header, while the credential surrogate is only swapped at the
registered placement (the `access_token` query parameter). The client
therefore runs a loopback proxy in front of the server. The server talks to
the proxy with a placeholder token, the proxy strips that header and forwards
each request to Gitea with the surrogate in the query parameter, where the
swap happens. The real token never appears in a file, an environment variable
or a command line.

```sh
export GITEA_BASE_URL=https://git.example.com
export GITEA_MCP_BIN=/path/to/gitea-mcp

python3 bin/gitea_mcp_client.py list-tools
echo '{}' > /tmp/args.json
python3 bin/gitea_mcp_client.py call-tool --name get_me --arguments-file /tmp/args.json
```

## Notes learned the hard way

- Register the placement as `query_param:access_token`. With
  `query_param:token` the stored parameter name came back corrupted in one
  real setup and every call went out anonymous.
- Some instances sit behind a CDN that bans the default Python user agent
  (Cloudflare Error 1010). The helper therefore sends a named user agent.
- Instances can require sign-in for the whole API, so even the version
  endpoint needs the credential.
