# Gitea

- `custom.gitea` connects Muse to a self-hosted Gitea instance through its REST API v1.

- It authenticates with the registered `api_key` credential, which Gitea reads as the `access_token` query parameter.

- The helper lives at `~/workspace/custom-connectors/custom.gitea/bin/gitea.py` in this repository layout. Set `GITEA_BASE_URL` to the instance base URL before calling it, and set `GITEA_CREDENTIAL` when the registered credential name differs from `custom.gitea`.

- An instance can require sign-in for all API calls, so even public looking endpoints need the credential.

- An instance behind a CDN can ban the default Python user agent. The helper sends `Muse-Gitea-Connector/1.0` for that reason, so keep that header.

## Connect

- Register the connection with `credentials.request_api_access` and the details below. Replace the example host with the real instance host and reuse the same details to reconnect:

```json
{
  "provider": "gitea",
  "auth_scheme": "api_key",
  "placement": "query_param:access_token",
  "api_hosts": ["git.example.com"]
}
```

- Register the placement as `query_param:access_token`. A first version of this connector used `query_param:token` and the stored parameter name came back corrupted, which made every call anonymous. The `access_token` name stored correctly and Gitea accepts it for the same token type.

- Before the first change in a conversation, prove access with a harmless read:

```text
GITEA_BASE_URL=https://git.example.com python3 ~/workspace/custom-connectors/custom.gitea/bin/gitea.py user
```

## Credentials

- The registered connection holds the credential. Helpers import `/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py`, which returns an `hsurr:` surrogate and places it where the provider reads the key. Muse swaps in the real credential only on an approved request to a registered host.

- Never put a key, token, password or cookie in this doc, a helper, a command argument, an environment variable or a log. Never ask the user to paste one in chat.

- Keep redirects disabled on authenticated requests. The helper already does this.

- On a 401 or 403, check the request first. Confirm that the helper attached the credential, that the host is registered and that the placement and scopes match.

- Only when a request that carried the credential is still rejected, call `credentials.request_api_access` with the details above and `"reconnect": true`.

## Read the instance version

- Read the Gitea version of the instance. This changes nothing:

```text
GITEA_BASE_URL=https://git.example.com python3 ~/workspace/custom-connectors/custom.gitea/bin/gitea.py version
```

- Verified against a Gitea 28.2.0 instance on 2026-10-23, returning HTTP 200 with the version field.

## Read the current user

- Read the profile of the account the token belongs to. This changes nothing:

```text
GITEA_BASE_URL=https://git.example.com python3 ~/workspace/custom-connectors/custom.gitea/bin/gitea.py user
```

- Read the `login`, `id` and `is_admin` fields to confirm the identity. Verified on 2026-10-23.

## List the current user's repositories

- List full names of repositories the current user owns. This changes nothing:

```text
GITEA_BASE_URL=https://git.example.com python3 ~/workspace/custom-connectors/custom.gitea/bin/gitea.py repos --limit 50
```

- The `--limit` flag sets how many entries come back and defaults to 50. Gitea list endpoints paginate with `page` and `limit` parameters, and the instance configuration caps the page size. Verified on 2026-10-23.

## Send a generic request

- Call any API path with any method. Pass a JSON body with `--data` for writes:

```text
GITEA_BASE_URL=https://git.example.com python3 ~/workspace/custom-connectors/custom.gitea/bin/gitea.py request GET /api/v1/user
```

- GET is verified through the commands above. Other methods are untested, so read the state back after any write to confirm what happened.

## Call through the official MCP server

- The connector also wraps the official Gitea MCP server from gitea.com/gitea/gitea-mcp, pinned at v1.11.0. Download the binary from its releases page, verify it against the release checksums file and point `GITEA_MCP_BIN` at it.

- The client is `bin/gitea_mcp_client.py` in this repository layout, with `list-tools` and `call-tool` commands. It starts the server over stdio for one invocation and exits, so nothing stays resident.

- The server sends its token in an Authorization header, but the surrogate is only swapped at the registered placement, the `access_token` query parameter. The client therefore runs a loopback proxy. The server connects to the proxy with a placeholder token, the proxy strips that header and forwards each request with the surrogate in the query parameter, and the swap happens on that final hop.

- List every tool the server offers:

```text
GITEA_BASE_URL=https://git.example.com python3 bin/gitea_mcp_client.py list-tools
```

- Call one tool with its arguments as a JSON object in a file:

```text
GITEA_BASE_URL=https://git.example.com python3 bin/gitea_mcp_client.py call-tool --name get_me --arguments-file <path-to-json>
```

- The client has an allowlist. It holds the read-only tools of server v1.11.0, 35 of them, and blocks every write tool until that operation is reviewed on its own.

- Verified on 2026-10-23 against a real instance. The calls get_gitea_mcp_server_version, get_me and list_my_repos all returned the expected data, and get_me proves the proxied authentication works.

- Server v1.11.0 offers 61 tools. Always read the current list with list-tools instead of trusting a remembered tool name.

## Recover from errors

- A 403 with the message Only signed in user is allowed to call APIs means the request carried no usable credential and Gitea treated it as anonymous. Check the placement and the registered host first.

- A 401 with the message invalid username, password or token means Gitea rejected the credential. Check the token value and its scopes before reconnecting.

- A 403 from Cloudflare with Error 1010 means the user agent is banned. Confirm the helper still sends `Muse-Gitea-Connector/1.0`.

- After a failed or timed-out change, check the current state with a read before trying again, because the first request may have completed.

## Limits

- One registration covers the hosts listed in `api_hosts`. Register another connector for a second instance.

- Write operations beyond the generic request command are not wrapped yet.

## Related skills

- Use `muse.skill_search` to find other skills and `muse.connector_search` to find other connectors.
