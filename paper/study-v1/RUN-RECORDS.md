# Study-v1 pilot run records

Development pilot infrastructure for the `budgeted-small-model-migration-v1` study.
This document describes `paper/study-v1/run-record.schema.json`, the validator
`paper/scripts/validate-study-run-records.py`, and the rules that separate a
recorded pilot cell from a claim.

**Status: no pilot has been run.** The repository contains zero pilot run records
and `paper/study-v1/config.json` still has `formalRunAllowed: false`. The
validator deliberately accepts that `not-started` state; it never invents a run
and never turns a failed, timed-out, setup-broken, or judge-broken attempt into a
score. Nothing here is a formal study result, and nothing here supports a claim
that D beats C.

## What a record is

The `pilot.json` plan defines 16 logical cells: the preselected development tasks
`H4-tsbuildinfo-trap`, `H6-remote-error-trap`, `H12-remote-result-boundary-trap`
and `H25-session-seed-boundary-trap`, each crossed with conditions `A`, `B`, `C`,
`D`. A pilot **record** is one attempt in one cell. A logical cell may hold more
than one attempt only when the extra attempts are declared retries of a recorded
original.

Each record carries the 27 required fields below, plus the optional `recordId`
and `schemaVersion`:

| Field | Meaning |
|---|---|
| `studyId` | Must be `budgeted-small-model-migration-v1`. |
| `taskId` | One of the four pilot tasks; other tasks are task replacement. |
| `condition` | `A`, `B`, `C` or `D`; anything else is condition replacement. |
| `modelRequested` | Requested model/configuration, `null` if unset. |
| `modelResolved` | Identity actually resolved from the service, `null` if unestablished. |
| `modelIdentityStatus` | `unverified`, `verified` or `mismatch`. |
| `reasoning` | Recorded reasoning setting, `null` if not configured. |
| `runKind` | `development-pilot` only; formal runs use a separate pipeline. |
| `attemptKind` | `original` or `retry`. |
| `startedAt` / `endedAt` | ISO 8601 timestamps or `null`. |
| `wallDurationMs` | Measured wall duration; `0` is measured, `null` is unknown. |
| `timeoutSeconds` | Configured time budget or `null`. |
| `status` | One of the seven status values below. |
| `exitCode` | Process exit code or `null`. |
| `artifactRootRelative` | Repository-relative artifact directory. |
| `materialManifestSha256` | SHA-256 of the mounted condition material. |
| `taskTreeSha` | Git tree id pinned in the task-annotation inventory. |
| `runnerVersion` | Runner version/commit or `null`. |
| `solverOutputPresent` / `patchPresent` | Whether those artifacts exist. |
| `judgeStatus` | `not-run`, `scored`, `judge-error`, `not-applicable` or `null`. |
| `tokenUsage` | `{input, cachedInput, output, totalReported}` object or `null`. |
| `cost` | `{amount, currency}` object or `null`. |
| `exceptions` | Array of recorded exception strings, or `null`. |
| `retryOf` | Reference to the attempt this one retries, or `null`. |
| `notes` | Free text or `null`. |

Every required field must be present. Omitting a field is invalid; when a value
was not measured, write an explicit `null`.

## Null versus zero

`null` means *not measured*. `0` means *measured as zero*. They are never
interchangeable:

- `tokenUsage: {input: 0, cachedInput: 0, output: 0, totalReported: 0}` is a real
  measurement of zero tokens.
- `tokenUsage: null` means tokens were not metered.
- `wallDurationMs: 0` is a real (instant) measurement; `wallDurationMs: null` is
  an unknown duration.
- `cost: {amount: 0, currency: "USD"}` is a measured zero spend; `cost: null` is
  unknown spend.

The validator rejects negative values, omitted fields, and impossible timing
(`endedAt` before `startedAt`, negative durations, and `wallDurationMs` that
disagrees with the timestamps beyond a 1000 ms tolerance).

## Status taxonomy

| Status | Terminal | Meaning |
|---|---|---|
| `success` | yes | Solver output exists; requires `solverOutputPresent: true`. |
| `task-failure` | yes | A real attempt produced evidence of failure (output, patch, or a scored judge packet). |
| `timeout` | yes | The time budget was exhausted. Never recorded as reward 0. |
| `setup-error` | yes | Environment/setup failed before a solver result existed. Never a task failure. |
| `solver-error` | yes | The solver process failed. |
| `judge-error` | yes | Judging failed. Never converted into a solver score of 0. |
| `incomplete` | no | The attempt is unfinished; blocks `pilotComplete`. |

`judgeStatus: "scored"` is rejected for `timeout`, `setup-error`, `solver-error`
and `judge-error`. Scores themselves are not part of a run record: a `score`,
`reward`, `grade` or equivalent field is rejected, and a score without
`artifactRootRelative`, `materialManifestSha256` and `taskTreeSha` can never be
stored here.

## Token accounting

The declared convention is recorded in `tokenUsage.accounting` and defaults to
`input-includes-cached`:

- **`input-includes-cached`** (default): `input` is the full prompt total and
  already contains `cachedInput`, so `totalReported == input + output`. Adding
  `cachedInput` on top is a double count and is rejected.
- **`input-excludes-cached`**: `input` excludes cache hits, so
  `totalReported == input + cachedInput + output`.

The validator enforces the declared convention, rejects cached input larger than
an inclusive `input`, rejects unknown conventions, and rejects negative counts.

## Provenance

Any record with a produced artifact — `solverOutputPresent: true`,
`patchPresent: true`, or `status: "success"` — must carry all three provenance
fields: `artifactRootRelative`, `materialManifestSha256`, `taskTreeSha`.

- `artifactRootRelative` must be a relative POSIX path. Absolute paths, `/tmp`
  and other temporary roots, `..` traversal, backslashes, `~`, and embedded
  username/home segments (for example `Users/…` or `home/…`) are rejected.
- `materialManifestSha256` must be 64 lowercase hex characters and, for a pilot
  cell, must equal the `materialSha256` recorded in `qc/pilot.json`.
- `taskTreeSha` must be the 40-character lowercase git tree id pinned for that
  task in `paper/audit/task-annotation-v1/inventory.json`. The inventory pins 56
  tasks; members of the wider living benchmark that are not in that pinned set
  are rejected.

## Retries

Failed attempts are data, not noise. Every attempt is recorded:

1. The first attempt is `attemptKind: "original"`.
2. A later attempt is `attemptKind: "retry"` and must set `retryOf`.
3. `retryOf` must resolve to an existing record — either its `recordId` or the
   implicit `taskId/condition` identity — in the **same** task+condition cell.
4. A retry chain must terminate at an original attempt and must not loop.
5. The original record stays in the set. It must not be deleted, marked
   superseded, or replaced by the retry.

Rejected: hidden retries (`attemptKind: "retry"` without `retryOf`), unregistered
retries (`retryOf` pointing at a missing record), a cell whose retries exist but
whose original is absent, `retryOf` cycles and chains that do not end at an
original, more than one original per cell, and metadata that selects a best
attempt (`bestOf`, `selectedRun`, `discardedAttempts`, …). Best-of-N selection
and deleting the failures are not permitted; the counts must survive the
analysis.

`unresolvedRetries` counts retries that do not yet have a terminal status. An
in-progress set is schema-valid but is never reported as a complete pilot.

## `pilotComplete`

`pilotComplete` is `true` only when all of the following hold:

- every one of the 16 logical cells is present exactly once as a logical cell
  (extra allowed only as a declared retry of a recorded original);
- there are no missing cells, no extra tasks or conditions, and no duplicate
  attempts;
- every cell holds at least one terminal status;
- `unresolvedRetries == 0`; and
- the record set has no validation errors.

When records exist, `--check-plan` rejects a set that is missing a plan cell or
contains a non-plan cell, so the exit code gates on plan conformance. When no
records exist at all, the plan check reports `not-started` and exits 0.

## Running the validator

```bash
# Plan integrity and completion; accepts the current not-started state.
python3 paper/scripts/validate-study-run-records.py --check-plan
# Plan conformance for a records directory or file.
python3 paper/scripts/validate-study-run-records.py --check-plan --records paper/study-v1/qc/runs
# One record or record set.
python3 paper/scripts/validate-study-run-records.py --check-record path/to/record.json
# A directory of *.json records, with a deterministic summary.
python3 paper/scripts/validate-study-run-records.py --check-directory paper/study-v1/qc/runs
python3 -m unittest discover -s paper/scripts -p 'test_study_run_records.py'
```

Output is deterministic JSON on stdout with sorted errors and cells. Exit codes
are `0` valid, `1` invalid, `2` usage or authority/configuration error. The
validator is read-only and offline: no model calls, no network, and no mutation
of `benchmark/tasks/**`, `skills/**`, `benchmark/results/**` or historical results.

## Scope and non-claims

This is development pilot infrastructure, not a formal result pipeline. It
validates record shape, provenance, plan conformance, and retry integrity — it
does not grade solutions, does not run a solver, and does not estimate effect
sizes. Completing all 16 cells would still be development evidence: the pilot is
excluded from the formal main table, one model's 16 cells cannot support a D−C
claim, and the study remains `candidate-not-frozen` with `formalRunAllowed:
false` until its material/QC, isolation, model configuration, and protocol
freeze requirements are satisfied (see [study status](README.zh.md) and
[configuration](config.json)). Removing old paper plans does not relax these gates.
