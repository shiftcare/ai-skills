# MCP eval harness

Requires Node 22, npm, Python 3.12, `uv`, and access to a ShiftCare MCP server.

Set `MCP_URL` in the environment or in `evals/.env`:

```sh
MCP_URL=https://mcp.au.shiftcare.com/mcp
```

Install and log in once through the browser:

```sh
cd evals
npm install
node auth.mjs login
```

Print a refreshed access token and run the offline tests:

```sh
node auth.mjs token
node --test tests/
```

Tokens refresh automatically; `login` is needed once per machine, or again if the refresh token is revoked.
