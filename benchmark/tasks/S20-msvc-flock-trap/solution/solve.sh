#!/bin/bash
# Oracle solution: copy the reference report into the agent-output directory
# (the fixture stays untouched — read-only task).
set -e
DIR="$(dirname "$0")"
OUT=/app/agent-output/S20-msvc-flock-trap
mkdir -p "$OUT"
cp "$DIR/report.md" "$OUT/report.md"
