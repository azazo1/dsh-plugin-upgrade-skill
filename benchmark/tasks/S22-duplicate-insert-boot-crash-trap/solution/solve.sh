#!/bin/bash
# Oracle solution: write the reference report to the agent output directory (does not touch the fixture, honoring read-only discipline).
set -e
mkdir -p /app/agent-output/S22-duplicate-insert-boot-crash-trap
cp "$(dirname "$0")/report.md" /app/agent-output/S22-duplicate-insert-boot-crash-trap/report.md
