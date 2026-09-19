# Task annotation v1 — incident-family annotation pipeline

Outcome-blind, reproducible task annotation supporting incident grouping in the
[current work plan](../../INVERTED-U-WORKPLAN.zh.md). Groups the
56-task target pool by **underlying incident family** and **observable trap
mechanism** using only task-construction evidence — never model outcomes.

The `inventoryPlanReference` field preserves historical plan filenames verbatim
as provenance, not live links or current instructions. Those deleted plans can
be read at Git commit `c03140cafa718e96fd2b78d050922360d2f1db99`; inventory
membership, hashes, and annotation status were not changed by document cleanup.

## Status

| Phase | State |
|---|---|
| 1. PREPARE (blinded packet + tooling) | **complete** |
| 2. ANNOTATE (two independent annotators) | **not started** |
| 3. ADJUDICATE (third party on disagreements) | **not started** |
| 4. FREEZE (consensus mapping for analysis) | **not started** |

No annotations exist in this repo state. `inventory.annotationStatus` is
`not-started`, and the validator fails on any partially filled template.
A single person's labels can never be marked `complete`; a solo pass is at
best `single-pass-incomplete` and must not be reported as independent
validation. No consensus file exists and none may be fabricated.

## Why not annotate now?

This PR delivers the methodology and tooling so that the (human) annotation
review is not mixed with the actual labeling. The pipeline stays honest:

- labels are not produced by a model, by reward data, or by one agent
  impersonating two annotators;
- `task-exposure-ledger.csv` (`status`, `skill_revision`,
  `knowledge_holdout_v1`, `provisional_role`) and the temporal-holdout
  verdicts are **not** inputs to the annotators — exposure and incident
  grouping are independent dimensions and are joined only later, by
  `task_id`;
- this pipeline does not modify `temporal-holdout-v1`, the #201 execution
  preregistration, the #193 grading-v2 experiment, any task, judge, skill,
  or result.

## Files

- `inventory.json` — the pinned 56-task inventory (`pre-freeze-main56`,
  pinned to the main commit recorded in `inventoryCommit`; NOT a formal
  frozen benchmark snapshot — that is produced by the research plan's QC
  step and lives in `benchmark/snapshots/`).
- `packet/tasks.json` — the blinded, deterministic annotation packet:
  per task, the pinned instruction, README summary/environment/verifier
  contract, task.toml metadata, fixture file listing, and instruction-
  referenced card texts. All resolved from git objects at
  `inventoryCommit`. Outcome-scrubbed and leakage-guarded.
- `guidelines.md` — the annotation authority: observable-labels-only rule,
  dimension non-conflation, incident-family definition and evidence
  requirements, the trap-type controlled vocabulary, confidence rubric,
  difficulty deferral, and the four-phase protocol.
- `schema.json` — human-readable shape contract for every artifact.
- `templates/annotator-a.csv` / `annotator-b.csv` — pre-filled with all 56
  `task_id` rows (no task can be silently omitted); labels blank until a
  human annotator fills them under the independence declaration.
- `templates/adjudication.csv` — third-party-only disagreement template.

## Scripts (`paper/scripts/`)

- `generate-task-annotation-packet.mjs [--check]` — regenerates the packet
  deterministically from the pinned inventory; `--check` exits 1 on drift.
- `validate-task-annotations.mjs` — machine enforcement of everything in
  `schema.json`: inventory/packet pins, determinism, leakage guard,
  annotator completeness/consistency, adjudication rules, consensus
  prohibition.
- `measure-task-annotation-agreement.mjs` — after both submissions:
  pairwise co-clustering agreement + Adjusted Rand Index for families,
  raw agreement + Cohen's kappa for trap type, and the disagreement list.
  With missing submissions it prints `status: incomplete` and computes
  nothing.
- Test suites: `validate-task-annotations.test.mjs`,
  `measure-task-annotation-agreement.test.mjs`.

## Annotation flow (for the human annotators)

1. Read `guidelines.md` first; work only from `packet/tasks.json`.
2. Fill `templates/annotator-a.csv` (or `-b.csv`) independently — before
   first submission do not look at the other annotator's labels, any
   consensus, or any outcome data, and do not discuss disagreements.
   Fill the header declaration, annotator id, and timestamps.
3. When both are submitted, run
   `node paper/scripts/measure-task-annotation-agreement.mjs` to get the
   disagreement list.
4. A third party (never A, never B, and not called "annotator C") fills
   `templates/adjudication.csv` from the disagreement list only, seeing
   task evidence + both rationales.
5. Only then may a consensus mapping be generated and frozen for
   family-level analysis (bootstrap at the highest correlated level).
