#!/usr/bin/env bash
# H26 oracle: apply the manifest fix and write the graded artifacts.
set -euo pipefail
cp -r "$(dirname "$0")/plugin/." /app/fixture/
mkdir -p /app/agent-output/H26-notlisted-trap
cat > /app/agent-output/H26-notlisted-trap/diagnosis.md <<'EOF'
# H26 · The Package That Installs But Never Registers — Diagnosis

## Symptom
`dsh plugin add` succeeds every time, yet the entry never appears in `dsh plugin list`.

## Two layers, one gap
- **Dependency installation** succeeds: the package lands in the profile's dependency
  tree (that is what `add` reports).
- **Plugin registration** never happens: the host only registers an installed package
  as a plugin when the package describes itself — `main`, the `exports` map, and the
  `dsh` block in `package.json`. This fixture's `package.json` carries none of them.

## Root cause
Missing plugin self-description in `package.json` (`main` / `exports` / `dsh`). Not a
host bug, and not an install problem.

## Why reinstalling cannot fix it
Reinstalling re-fetches the same manifest with the same missing fields — the install
layer was never broken. Clearing the npm/pnpm store changes nothing; the note in the
source ("reinstall and retry") is a red herring.

## Fix
Add the three declaration pieces to `package.json` (see the applied diff); `index.js`
needs no change — it was already written against 0.1.2-alpha.2.

## Verification (isolated profile `bench-h26`)
- `dsh plugin add` — ok
- `dsh plugin list` — `@demo/dsh-bench-notlisted` now listed
- headless cold boot — fails with `MISSING_CREDENTIAL` (no API key in the container),
  which is the alive signal: the plugin tree loaded and startup reached the host
  application layer. Exit code is not a criterion.
EOF
cat > /app/agent-output/H26-notlisted-trap/smoke.md <<'EOF'
# H26 · Smoke evidence

- `dsh plugin --profile bench-h26-notlisted-trap add /app/fixture` → exit 0
- `dsh plugin --profile bench-h26-notlisted-trap list` → contains `@demo/dsh-bench-notlisted`
- `dsh --profile bench-h26-notlisted-trap 'ping'` → `MISSING_CREDENTIAL` after the plugin
  tree loads (expected without an API key; proves activation reached the application layer)
EOF
echo "oracle applied"
