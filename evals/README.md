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
for i in 1 2 3 4 5; do ./evals/run.sh; done
```

To repeat a run, loop it. Each run archives its own file in `runs/` and the report pools them, so five runs give five paired comparisons per model rather than overwriting each other. There is no repeat counter to keep in step: the report pairs the with-skill and no-skill arms of a group in order, so appending a sixth run later simply adds a sixth comparison.

Results pool only where they are comparable. Every result carries a `scenarioHash` over the suite's `CASES` and a `skillHash` over the installed skill's files, both taken from the working tree so uncommitted edits count. Editing a prompt or a rubric changes the scenario hash and separates the new results from the old; editing the skill mid-accumulation renders as a labelled before/after comparison rather than averaging two different skills together. Each version gets its own roll-up and sample counts, with the current working tree first, so `n` restarts at zero after an edit. A run's no-skill results count as the control for whichever skill version ran beside them in that file. Results archived before hashes existed are labelled as unverified.

A run that loses its API quota part-way is stopped rather than ground through. Three consecutive scenarios raising anything other than an assertion (the agent runner exiting non-zero, an agent subprocess timing out after 600 seconds, the judge's SDK rejecting a call) end the session, and any real result in between resets the count. Metric failures never count. When the judge fails inside a metric, DeepEval still records the test case as successful with an unscored metric; the report drops such results from the pool and the provenance table counts them per run file.

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

Reports are written to `reports/<YYYY-MM-DD-HHMMSS>.html` at the repository root, named from the newest pooled result file's modification time so each run keeps its own file instead of overwriting the last one. `-o` overrides the path. The `reports/` directory is committed but its contents are not.

With no arguments, `report.py` pools every archived run in `runs/` at the repository root, falling back to DeepEval's own `.deepeval/.latest_run_full.json` when nothing has been archived. Pooling is what makes a narrow run useful: `./run.sh -k invoice` archives its own results and the next report adds them to that case's samples rather than replacing the matrix. The report opens with a table naming each pooled file and its result count, and each case reports its own sample count, so a case covered by one narrow run is not mistaken for one covered by five full matrices.

The HTML remains local and contains the full prompts, tool outputs, and judge reasons. “Results saved” uses the newest pooled file's modification time, and “Download latest run JSON” returns that file's source data — not the whole pool, whose files are already in `runs/`.

## Privacy

Evaluation results and judge reasons contain real account data. Keep `.deepeval/`, and the repository-root `reports/` and `runs/`, local. Both carry a self-ignoring `.gitignore`; moving them nearer the repository root makes an accidental `git add` easier, so check `git status` is clean after generating a report. Never run `deepeval view`, upload results, or share result files. Credentials remain in the ignored `.auth/` or `.env` files and must never be committed.
