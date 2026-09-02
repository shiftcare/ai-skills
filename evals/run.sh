#!/bin/sh
set -eu

cd "$(dirname "$0")"
export DEEPEVAL_TELEMETRY_OPT_OUT=1
export DEEPEVAL_UPDATE_WARNING_OPT_IN=0
exec uv run deepeval test run . "$@"
