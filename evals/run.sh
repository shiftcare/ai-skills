#!/bin/sh
set -eu

cd "$(dirname "$0")"
export DEEPEVAL_TELEMETRY_OPT_OUT=1
export DEEPEVAL_UPDATE_WARNING_OPT_IN=0

status=0
uv run deepeval test run test_connection.py test_tasks.py -n "${EVAL_WORKERS:-4}" "$@" || status=$?

# A failing matrix is the run that most needs reading, so report on it too, and
# archive it first: DeepEval overwrites .latest_run_full.json on the next run,
# so an unarchived matrix is lost as soon as anything else runs.
run_data=.deepeval/.latest_run_full.json
if [ -f "$run_data" ]; then
  mkdir -p runs
  cp "$run_data" "runs/$(date -r "$run_data" +%Y-%m-%d-%H%M%S).json"
  uv run python report.py
fi

exit "$status"
