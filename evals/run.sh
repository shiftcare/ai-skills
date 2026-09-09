#!/bin/sh
set -eu

cd "$(dirname "$0")"
export DEEPEVAL_TELEMETRY_OPT_OUT=1
export DEEPEVAL_UPDATE_WARNING_OPT_IN=0

started=$(date +%s)
status=0
uv run deepeval test run test_connection.py test_tasks.py -n "${EVAL_WORKERS:-4}" "$@" || status=$?

# DeepEval overwrites .latest_run_full.json on every run, so archiving is what
# makes a run durable: report.py pools every file in runs/, which is how a
# narrow run (-k "...") adds samples to a case instead of replacing the matrix.
# Name the archive for when the run finished rather than the source mtime, so
# two runs in the same second can't land on the same file.
run_data=.deepeval/.latest_run_full.json
if [ ! -f "$run_data" ]; then
  :
elif [ "$(stat -f %m "$run_data" 2>/dev/null || stat -c %Y "$run_data")" -lt "$started" ]; then
  # An interrupted run can leave the previous run's results in place; archiving
  # those would double-count them into the pool.
  echo "run.sh: no new results written; keeping the existing archive" >&2
else
  mkdir -p runs
  archive="runs/$(date +%Y-%m-%d-%H%M%S).json"
  if [ -e "$archive" ]; then
    archive="runs/$(date +%Y-%m-%d-%H%M%S)-$$.json"
  fi
  cp "$run_data" "$archive"
  # A failing matrix is the run that most needs reading, so report on it too.
  uv run python report.py
fi

exit "$status"
