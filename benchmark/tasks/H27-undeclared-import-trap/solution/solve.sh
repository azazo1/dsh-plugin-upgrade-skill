#!/usr/bin/env bash
# H27 oracle: declare the dependency and write the graded artifacts.
set -euo pipefail
cp -r "$(dirname "$0")/plugin/." /app/fixture/
mkdir -p /app/agent-output/H27-undeclared-import-trap

cat > /app/agent-output/H27-undeclared-import-trap/diagnosis.md <<'DIAG'
# H27 · Declares Nothing, Crashes on Load — Diagnosis

## Symptom
Install succeeds, the entry is listed, and the cold boot dies with
`ERR_MODULE_NOT_FOUND: Cannot find package '@deepseek-ai/dsh-llm'`.

## Root cause
A runtime import (`ContentBlock` from `@deepseek-ai/dsh-llm`) whose package is
never declared in `dependencies`/`peerDependencies`. The install layer only
fetches what is declared, so the package was never fetched; the loader then
fails at resolve time. In the old cohort the host provided some packages
implicitly — that implicit provision is gone in 0.1.2, and an import without a
declaration is now a load-time crash by design.

## Why try/catch is not a fix
Swallowing the import degrades the capability silently: the plugin would "run"
without the feature the import exists for. The crash is the honest signal; the
missing declaration is the defect.

## Fix
Declare `@deepseek-ai/dsh-llm` in `peerDependencies` (cohort floor
`^0.1.2-alpha.1`). `index.js` is untouched — the code was correct.

## Verification (isolated profile `bench-h27`)
- `dsh plugin add` — ok
- `dsh plugin list` — `@demo/dsh-bench-undeclared` listed
- headless cold boot — `MISSING_CREDENTIAL` after the plugin tree loads (no API
  key in the container; the alive signal — exit code is not a criterion).
DIAG

cat > /app/agent-output/H27-undeclared-import-trap/smoke.md <<'SMOKE'
# H27 · Smoke evidence

- `dsh plugin --profile bench-h27-undeclared-import-trap add /app/fixture` → exit 0
- `dsh plugin list` → contains `@demo/dsh-bench-undeclared`
- headless cold boot → `MISSING_CREDENTIAL` after tree load (alive signal)
SMOKE
echo "oracle applied"
