# Temporal holdout v1 — execution protocol (preregistered)

**Status**: preregistered, definition only. **Model calls made during
preregistration: 0.** No model was run, no result was produced, and no task,
skill, split, or paper conclusion was changed by this protocol. It fixes, in
advance and in writing, exactly how the merged temporal-holdout-v1 split
(PR #163, definition commit `2338be4fad1e21f578756689cb44c0b143bfc15d`) will
be executed when the time comes.

## Scope — what this is and is not

- **Is**: a formal execution preregistration. When execution-v1 starts, every
  design decision below is already frozen and machine-verifiable.
- **Is not**: a run. It contains no rewards, no trajectories, no results, and
  no measurements. `modelCallsMadeDuringPreregistration` is `0` and the
  validator refuses any other value.

## Frozen pins (all verified against local git objects)

| Pin | Value | Meaning |
|---|---|---|
| `selectionDefinitionCommit` | `2338be4f…` | the merged v1 split definition; its `primaryTasks` are the only tasks this protocol may execute |
| `skillSourceCommit` | `5f7234ba…` (2026-08-31) | the skill-knowledge freeze |
| `skillTree` | `817a48e6…` | the frozen `skills/plugin-upgrade` tree |
| `skillEntryBlob` | `a3ee71d3…` | the frozen SKILL.md blob |
| `taskSourceCommit` | `d4f7e8c2…` (2026-09-04) | the task-universe cutoff |

Each of the ten tasks additionally pins its own **tree SHA** at the task
source commit. The drift audit (`auditedAgainst` `ecab245c…`) found all ten
pinned task trees byte-identical between the task source commit and
origin/main at registration time — zero drift. Even if living main edits any
of the ten tasks later, formal execution uses the pinned git objects only;
living-main growth (the registry is now larger than the 52-task v1 universe)
never redefines this protocol.

| Task | pinnedTree |
|---|---|
| H4-tsbuildinfo-trap | `a3fc23c1…` |
| H7-locale-trap | `243cd036…` |
| H13-ghost-host-trap | `a1c1d94c…` |
| M3-session-projection | `0078b43c…` |
| M4-peer-prerelease-range | `dec596f0…` |
| S8-release-routing-trap | `43fc1fca…` |
| H20-session-events-ledger | `65341cab…` |
| H21-question-answerer-waterfall | `99a52b53…` |
| M13-repository-plugins-removal | `c3fc5397…` |
| M14-service-renames-0812 | `14f2b756…` |

## Design

- **120 logical slots** = 10 tasks × 2 models × 2 conditions × 3 attempts.
- **Models**: `deepseek/deepseek-v4-flash`, `openai/gpt-5.6-luna` — exactly
  these two, in this order.
- **Agent / reasoning / concurrency**: terminus-2, `high`, concurrency 1
  (one slot at a time; no parallel scheduling effects).
- **Conditions**:
  - `frozen-skill` — the frozen skill is materialized from
    `5f7234ba…:skills/plugin-upgrade` ONLY (tree `817a48e6…`, SKILL.md blob
    `a3ee71d3…`), verified against a file SHA-256 manifest before any slot;
    no other skill, no extra hints.
  - `no-injected-skill` — no Skill is mounted and no skill-related prompt
    augmentation is added; nothing else about the task prompt changes.
- **Materialization**: the pinned git objects are the only source for both
  the skill and the tasks. Copying the living checkout's task files and
  "fixing them back" is prohibited.

## Model resolution (honest preregistered status)

Harbor 0.22.0 resolves model IDs against the provider at run time and ships
no offline model catalog, so the dry-run resolution is recorded as
**`not-locally-resolvable`**. Repository evidence (the merged 2026-09-01
validation reports) shows both IDs previously resolved by Harbor
(`gpt-5.6-luna` via codex, `deepseek-v4-flash` via terminus-2). The protocol
does **not** silently swap models: the resolved model identity is recorded
per slot, and any resolved-model mismatch with the preregistered ID is an
infra failure — the slot is marked invalid-infra and receives at most one
replacement.

## Schedule (deterministic)

- Seed: `temporal-holdout-v1-t2-2026-09`.
- For each model × task group:
  `digest = sha256(scheduleSeed + "|" + model + "|" + task)`; the first digest
  byte's parity selects the sequence **ABBAAB** (even) or **BAABBA** (odd),
  where A = `frozen-skill` and B = `no-injected-skill`. Each condition
  contributes exactly 3 slots with attempts 1..3 in that sequence's order.
  Groups are ordered model-major then task order; slots are numbered 1..120.
- The committed `temporal-holdout-execution-v1.schedule.json` must regenerate
  byte-identically from the protocol and the seed; the generator's `--check`
  mode and the validator both refuse any drift. No clocks, no randomness.

## Policies (frozen)

- **Timeout**: agent timeout = 3 × the task's own pinned `[agent]`
  `timeout_sec` (H4/S8 = 900 s; the other eight tasks = 2700 s); verifier
  timeout = the task's pinned value unchanged. Changing any timeout after
  slot 1 aborts execution-v1.
- **Network**: task-container outbound traffic is **disabled — enforced
  technically** (network namespace / nftables / equivalent isolation), never
  by prompt instruction; the provider control plane stays allowed. A formal
  host must be Linux with a working enforcement mechanism — macOS Docker
  Desktop is NOT an acceptable no-network authority. Before formal slot 1 a
  **model-free canary** must run inside a task container (external DNS and
  HTTPS must FAIL; required loopback services must PASS) and its record is
  kept. Canary failure = HARD STOP: zero formal model slots until the
  enforcement is fixed and re-canaried.
- **Replacement**: only the preregistered infra failures are replaceable
  (provider 429/5xx, credential/setup failure, Docker failure, Harbor crash,
  container setup failure, network enforcement failure, resolved model
  mismatch, runner-caused artifact corruption). Wrong solutions, reward 0,
  partial rewards, agent loops, full-timeout runs, early stops, and valid
  verifier rejections are **valid scientific outcomes and are never re-run
  toward success**. At most ONE replacement per slot; the replacement keeps
  the same model/task/condition/logical attempt and is suffixed R1; original
  artifacts are retained and marked invalid-infra.
- **Artifacts**: persistent root only — `/tmp`-only or ephemeral CI-only
  retention is prohibited; a SHA-256 manifest per trial immediately after
  completion plus an aggregate manifest; no automatic cleanup.
- **Activation**: `not-measured`. Skill-supplied does not imply
  skill-opened, and the activation auditor has not been validated against
  terminus-2 trajectories, so this protocol makes no activation claim.
- **Analysis** (per model): per-task medians of the 3 rewards per condition;
  `taskDelta = skillMedian − noSkillMedian`; primary effect = mean task
  delta. Forbidden alternatives: best-of-3, last-run selection, raw pooled
  mean. NO REWARD is an anomaly/incomplete outcome, never a zero. Bootstrap:
  10000 replicates over **task-level paired deltas** (not individual
  trials), seed `20260907`, 95% percentile CI. Secondary two-sided Wilcoxon
  signed-rank over the 10 task deltas with zeros retained and midpoint
  ranks. **Retained gain** = `holdoutDelta / referenceDelta`, and a
  reference is usable only when it matches the formal run on model, agent,
  reasoning, network policy, 3-run median design, and reward semantics;
  otherwise `not-estimable-yet` — earlier networked calibrations (e.g. H21)
  are context, never the denominator.
- **Mid-run mutation**: after formal slot 1 starts, any change to tasks,
  judges, skill, protocol, schedule, agent, model, reasoning, Harbor
  version, network policy, timeouts, or analysis method aborts
  execution-v1; partial evidence is retained and a protocol v2 restarts
  from slot 1. Never continue 61/120 after changing a grader.
- **Privacy**: no private plugin names, private repositories, machine
  paths, tokens, API keys, or credentials in any committed artifact.

## Machine-readable files

- `benchmark/holdouts/temporal-holdout-execution-v1.json` — the protocol
  (frozen pins, design, policies).
- `benchmark/holdouts/temporal-holdout-execution-v1.schedule.json` — the
  committed deterministic 120-slot schedule.
- `benchmark/scripts/generate-temporal-holdout-schedule.mjs` — regenerates
  the schedule from the protocol + seed (`--check` exits 1 on drift).
- `benchmark/scripts/validate-temporal-holdout-execution.mjs` — deterministic
  validator: re-checks every pinned SHA against local git objects, the
  split-authority rule (protocol tasks must equal v1 `primaryTasks`
  exactly), the complete policy surface, and the schedule's determinism.
- `benchmark/scripts/validate-temporal-holdout-execution.test.mjs` and
  `benchmark/scripts/generate-temporal-holdout-schedule.test.mjs` — focused
  tests on synthetic git repositories (50 tests together).
- This document — the human-readable audit.

## What execution-v1 must do before slot 1

Run the validator against the checkout that will host the run; regenerate
the schedule with `--check`; materialize skill and tasks from the pinned git
objects and verify their SHAs; run the network canary; record the host,
Docker, Harbor, and isolation-mechanism facts. If anything fails, stop —
fix the infrastructure — and re-verify. Slot 1 starts only after every
check above passes.
