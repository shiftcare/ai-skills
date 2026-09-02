# MCP eval harness

This local DeepEval harness compares the `shiftcare-mcp` skill across Claude and Codex models and evaluates three read-only MCP tasks.

## Setup

Requires Node 22, npm, Python 3.12, `uv`, the Codex CLI, and access to a ShiftCare MCP server.

```sh
cd evals
npm install
uv sync
```

Set `MCP_URL` in the environment or in `evals/.env` using the public URL for your region:

```sh
MCP_URL=https://mcp.au.shiftcare.com/mcp
```

Log in once through the browser:

```sh
node auth.mjs login
```

The harness resolves a token immediately before every test. `node auth.mjs token` reuses a token with more than 30 seconds left or silently refreshes it. `MCP_TOKEN` from the environment or `.env` overrides the saved login. Refresh tokens are single-use: if a refresh request is interrupted, the saved login is lost and `token` asks you to run `login` again.

## Run

From the repository root, run the full default matrix:

```sh
./evals/run.sh
```

The default models are `sonnet,haiku,gpt-5.6-terra,gpt-5.6-luna`. Override them with a comma-separated list and use normal pytest filters as needed:

```sh
EVAL_MODELS=haiku ./evals/run.sh -k connection
EVAL_MODELS=sonnet,gpt-5.6-luna ./evals/run.sh
```

Run only the offline unit tests from `evals/`:

```sh
uv run pytest tests/
node --test tests/
```

## Privacy

Evaluation results and judge reasons contain real account data. Keep `.deepeval/` local. Never run `deepeval view`, upload results, or share result files. Credentials remain in the ignored `.auth/` or `.env` files and must never be committed.
