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
- `bin/gitea.py` — the API helper (Python 3, standard library only).

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

## Notes learned the hard way

- Register the placement as `query_param:access_token`. With
  `query_param:token` the stored parameter name came back corrupted in one
  real setup and every call went out anonymous.
- Some instances sit behind a CDN that bans the default Python user agent
  (Cloudflare Error 1010). The helper therefore sends a named user agent.
- Instances can require sign-in for the whole API, so even the version
  endpoint needs the credential.
