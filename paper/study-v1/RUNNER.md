# study-v1 controlled solver runner

> **THIS IS DEVELOPMENT INFRASTRUCTURE. NOT A FORMAL RESULT PIPELINE YET.**

`paper/scripts/run-study-v1-cell.py` runs **one cell** of the
`budgeted-small-model-migration-v1` study: a single
`(task, condition)` pair, where condition is one of `A|B|C|D`
(`paper/study-v1/config.json`). This optional source-matched study is separate
from the current [inverted-U work plan](../INVERTED-U-WORKPLAN.zh.md).
`pilot-study-v1.py` only stages directories and
probes Docker, and `benchmark/report-judge/codex-judge.mjs` is a judge
transport, not a four-condition solver.

This runner does **not** run the pilot, does **not** run the formal study,
and produces **no D−C result and no paper claim**. It never edits
`formalRunAllowed`, `models[]`, `repetitions`, the final `N`, or any paper
text. A formal run remains blocked: the study is `candidate-not-frozen`.

## Usage

```sh
# DEFAULT: dry run — plan + materialize + record, zero model calls
python3 paper/scripts/run-study-v1-cell.py \
  --task H4-tsbuildinfo-trap --condition A \
  --model gpt-5.3-codex-spark --reasoning high \
  --artifact-root /persistent/artifacts

# real solver transport (explicit gate + explicit command)
python3 paper/scripts/run-study-v1-cell.py \
  --task H4-tsbuildinfo-trap --condition A \
  --model gpt-5.3-codex-spark --reasoning high \
  --artifact-root /persistent/artifacts \
  --execute --solver-command "harbor run -p benchmark/tasks/H4-tsbuildinfo-trap"
```

| Flag | Meaning |
|---|---|
| `--task` | must be a member of the pinned 56-task annotation inventory |
| `--condition` | `A` \| `B` \| `C` \| `D` |
| `--model` | requested model id, recorded verbatim (never silently swapped) |
| `--reasoning` | `low` \| `medium` \| `high` |
| `--artifact-root` | persistent artifact root (absolute; `/tmp` rejected unless `--allow-tmp`) |
| `--timeout` | solver timeout in seconds |
| `--dry-run` | plan only — **the default** |
| `--execute` | actually spawn the solver; requires `--solver-command` |
| `--expected-material-sha256` | fail unless the materialized package matches |
| `--materials-from` | offline materials tree for QC/tests |
| `--print-plan` | print the deterministic plan JSON |

## Isolation guarantees

Each cell gets:

- a **fresh working directory** per cell; a non-empty cell directory is
  rejected rather than reused;
- a **fresh agent/session** — no context is shared between cells;
- **only its own condition materials**, mounted read-only (`0444`), with the
  mount path confined to the cell directory;
- a **sandbox `HOME`** inside the cell, with `XDG_*` pointing into it;
- **native skill auto-discovery disabled** explicitly
  (`DSH_DISABLE_NATIVE_SKILLS=1`, `DSH_DISABLE_SKILL_AUTODISCOVERY=1`) and
  host skill/config variables (`CODEX_HOME`, `CLAUDE_CONFIG_DIR`,
  `AGENTS_SKILLS_DIR`, …) dropped;
- an **allowlisted environment** (`PATH`, `LANG`, `LC_ALL`, `LC_CTYPE`,
  `TERM`, `TZ` plus the explicit disables). Provider credentials
  (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `AWS_*`, `GITHUB_TOKEN`, …) never
  cross the boundary;
- a **writable workspace** separate from the read-only materials;
- **no network use by this runner**. The recorded policy is task-container
  outbound disabled; the runner itself performs no network access.

Material sets are checked for forbidden artifacts (`solution/`, `solve.sh`,
`tests/`, `judge.mjs`, `benchmark/results/`, `skills/`, …), path traversal,
and absolute paths. A task that exists only in the living benchmark (now 63
tasks) is rejected: the study authority is the pinned 56-task inventory.

## Recorded metadata

`<artifact-root>/<studyId>/<taskId>/<condition>/record.json` is written for
every cell (dry run included) with:

`studyId, taskId, condition, cellId, runKind, attemptKind, dryRun,
modelRequested, modelResolved, modelIdentityStatus, reasoning,
timeoutSeconds, startedAt, endedAt, wallDurationMs, status, exitClass,
exitCode, artifactRootRelative, materialManifestSha256, taskTreeSha,
runnerVersion, solverOutputPresent, stderrPresent, patchPresent,
judgeStatus, tokenUsage, cost, retryOf, exceptions, notes, isolation`

Policy details:

- **No credentials in artifacts.** Environment values, solver stdout/stderr,
  command arguments, and notes are redacted (secret assignments, `Bearer`
  tokens, token query parameters) before they are written.
- **No absolute host paths** in the record: absolute paths are replaced with
  `<redacted-path>`, and `artifactRootRelative` is relative to the artifact
  root.
- **Resolved model identity.** When the provider does not expose it,
  `modelResolved = null` and `modelIdentityStatus = "unverified"` — never a
  guessed or fabricated value. A resolved id that differs from the requested
  id is flagged `mismatch`.
- **Timestamps and durations** are the only time-derived fields. Injecting a
  clock (tests/QC) makes the whole record byte-identical between runs.
- **Material hashes** reuse the study authority's algorithm
  (`prepare-study-v1.py:package_hash`, SHA-256 over the pretty-printed sorted
  file manifest), so `materialManifestSha256` is directly comparable with
  `material-manifest.json` `arms[*].packageSha256` and `pilot.json`
  `materialSha256`.

## Exit classification

| Classification | Meaning | Exit code |
|---|---|---|
| `success` | solver exited 0 | 0 |
| `solver-timeout` | timeout exceeded | 1 |
| `solver-error` | non-zero exit, missing exit code, or adapter failure | 1 |
| `setup-error` | material/workspace/authority failure | 2 |
| `invalid-config` | bad CLI/config/inventory input | 2 |

A timeout is **not** a task failure and **not** reward 0; a `solver-error` is
a transport outcome, not a grade. Judge status, token usage, and cost are
`null` here — this runner does not judge and does not estimate spend.

Partial artifacts are preserved: if the adapter fails or the run is
interrupted, the cell keeps its materials, workspace, logs, and any
`record.json`/`INTERRUPTED` marker.

## Adapter interface

```python
class SolverAdapter:
    def spawn(self, spec: dict) -> dict: ...   # exitCode, stdout, stderr,
                                               # timedOut, resolvedModel, durationMs
```

- `MockSolverAdapter` — deterministic, offline, counts `calls`; used by dry
  runs and unit tests. It makes zero model calls.
- `CommandSolverAdapter` — the real transport, reachable only via
  `--execute --solver-command`.

## Material authority

Material bytes are never redefined here. The runner consumes the existing
authority: `paper/study-v1/generated/material-manifest.json` for the arm
layout and hashes, and `prepare-study-v1.py:build_materials` for the bytes.
`--materials-from <dir>` provides an offline tree for QC/tests.

## Tests

```sh
python3 -m unittest discover -s paper/scripts -p 'test_study_runner.py'
```

72 tests cover the inventory authority (including rejection of the living
benchmark's extra tasks), condition material sets, environment/secret
isolation, path confinement, `/tmp` policy, fresh-cell policy, determinism,
timeout/error classification, resolved-model honesty, artifact preservation,
and secret redaction. They require no model, no network, and no Docker.
