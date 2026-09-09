# MCP eval harness

This local DeepEval harness compares the `shiftcare-mcp` skill across Claude and Codex models and evaluates three read-only MCP tasks.

Each scenario measures tool correctness, task completion, step efficiency, argument correctness, response quality, and tool-result integrity. Connection verification also checks that `whoami` is the first MCP call. The model-based metrics make several judge calls per scenario, so narrow runs are useful while iterating.

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

The harness resolves a token immediately before every test, because access tokens expire after 300 seconds and a long run would otherwise reuse an expired one. `node auth.mjs token` reuses a token with more than 30 seconds left or silently refreshes it. `MCP_TOKEN` from the environment or `.env` overrides the saved login. Refresh tokens are single-use: if a refresh request is interrupted, the saved login is lost and `token` asks you to run `login` again.

## Run

From the repository root, run the full default matrix:

```sh
./evals/run.sh
```

The default models are `sonnet,haiku,gpt-5.6-terra,gpt-5.6-luna`. Override them with a comma-separated list and use normal pytest filters as needed:

```sh
EVAL_MODELS=haiku ./evals/run.sh -k connection
EVAL_MODELS=sonnet,gpt-5.6-luna ./evals/run.sh
EVAL_REPEATS=5 ./evals/run.sh
```

`EVAL_REPEATS` repeats each model, case, and skill-variant combination and defaults to `1`. Reports pair results by model and repeat so repeated runs remain independent comparisons.

Runs use four parallel workers by default. Set `EVAL_WORKERS` to tune concurrency:

```sh
EVAL_WORKERS=2 ./evals/run.sh
```

Model-based metrics run concurrently, with judge subprocesses bounded to four per worker. Set `EVAL_JUDGE_CONCURRENCY` to an explicit positive integer if provider limits require a lower bound. Total possible agent subprocesses are `EVAL_WORKERS × EVAL_JUDGE_CONCURRENCY`.

Sonnet judges responses by default. Override the judge when Claude is unavailable:

```sh
EVAL_JUDGE_MODEL=gpt-5.6-luna EVAL_MODELS=gpt-5.6-luna ./evals/run.sh -k connection
```

Run only the offline unit tests from `evals/`:

```sh
uv run pytest tests/
node --test tests/
```

## Report

Generate the private local HTML report from the latest full run or an explicit result file:

```sh
cd evals
uv run python report.py
uv run python report.py .deepeval/.latest_test_run.json -o somewhere/else.html
```

Reports are written to `reports/<YYYY-MM-DD-HHMMSS>.html`, named from the source result file's modification time so each run keeps its own file instead of overwriting the last one. `-o` overrides the path. The `reports/` directory is committed but its contents are not.

The HTML remains local and contains the full prompts, tool outputs, and judge reasons. “Results saved” uses the source result file's modification time, and Download JSON returns the complete source data.

## Privacy

Evaluation results and judge reasons contain real account data. Keep `.deepeval/` and `reports/` local. Never run `deepeval view`, upload results, or share result files. Credentials remain in the ignored `.auth/` or `.env` files and must never be committed.
