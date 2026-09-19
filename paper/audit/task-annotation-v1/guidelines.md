# Task annotation v1 — annotation guidelines

This document is the annotation authority for the T5 incident-family task
annotation. It defines **what may be labeled, from which evidence, and how**.
Annotators follow this document plus the blinded packet
(`packet/tasks.json`) — nothing else.

> Status: **PREPARE complete. ANNOTATE not started.** No annotations exist
> yet. No one may treat a single person's labels as a completed annotation.

## 1. Observable labels only

An annotation describes the **task / incident**, never the model's mental
state and never a measured outcome.

**Forbidden annotations** (any of these makes the annotation invalid):

- "the model does not know this knowledge"
- "this knowledge is outside the model's training data / priors"
- "the model must have seen this"
- "easy because models score high"
- "the skill helped this task"
- any difficulty derived from reward / delta / activation / condition scores
- any family grouping justified by a measured result

**Permitted evidence sources** (exactly what the blinded packet contains):

- the task instruction (`instruction.md` text, pinned)
- the task README summary / environment / verifier contract (pinned)
- task.toml metadata (name, version, description, keywords — pinned)
- the fixture file listing (pinned)
- authority card texts referenced by the instruction (pinned)
- the machine-derived interaction mode
- git provenance (task tree SHA, inventory commit)

Everything else — results, rewards, deltas, activation rates, model names,
exposure-ledger columns, holdout verdicts, skill revision SHAs — is
**excluded from the packet** and must not be used as annotation evidence.

## 2. Dimensions do not conflate

| Dimension | Source | Annotated? |
|---|---|---|
| Task ID prefix (S/M/H) | task naming | — (a prefix is not a dimension) |
| `interaction_mode` | machine-derived from the pinned registry (`Static`/`Hands-on`) | no |
| `incident_family` | human annotation (this protocol, P0) | yes |
| `observable_trap_type` | human annotation (this protocol, P0) | yes |
| `difficulty` | **deferred to P1 in this v1** | no |

Concretely: the `H` prefix does not imply Hands-on (H4 and H6 are Static),
does not imply Hard, does not imply any trap type, and does not imply any
incident family. The prefix rule is a human rule: no machine check can prove
a label was not prefix-derived, so the validator instead requires every
filled row to carry non-empty `family_evidence` and `rationale`, and the
adjudicator discards any label whose stated evidence reduces to the ID
prefix. Annotators must ground every label in the packet evidence.

## 3. incident_family (P0)

**Definition.** Two tasks belong to the same incident family only when they
primarily test the **same underlying migration incident / contract change /
root-cause family**. Grouping requires **shared causal/source evidence** of
at least one of these forms:

- the same upstream breaking change (e.g. the same removed API surface,
  the same renamed service, the same changed registration contract);
- the same migration fact (e.g. the same corridor rule that both tasks
  require the agent to apply);
- the same real incident transformed into multiple task variants.

**Not sufficient for grouping** (these alone never justify a shared family):

- both tasks touch "Session", "Web", "storage", or any other surface name;
- both tasks have the same interaction mode;
- both tasks share an ID prefix;
- both tasks were built by the same author or in the same PR.

**Card handling.** The same card does not automatically mean the same family
— one card may bundle several semantic changes, and two tasks citing the same
card may exercise different changes. Different cards do not automatically
mean different families — if two cards document the same underlying incident
(e.g. a card and its corridor rollup describing one breaking change), the
annotator may merge the tasks into one family but must explain the shared
underlying incident in `family_evidence`.

**Naming.** `family_id` must be a stable slug of the underlying incident,
never task-dependent: `session-event-ledger-removal`, not `family-h20`.
The same `family_id` must carry the identical `family_short_name` on every
row of one annotator.

**Unresolved.** `incident_family_id = unresolved` is allowed, but only with
a non-empty `rationale` and `confidence = low`; unresolved rows are not
silently dropped and flow into the disagreement/adjudication pipeline.

## 4. observable_trap_type (P0)

One of a fixed vocabulary, chosen from **observable task design** — what the
fixture/task plants, not how any model behaved.

| Type | Guideline | Positive example (from packet reading) | Boundary example |
|---|---|---|---|
| `none` | No planted trap: a plain migration task with no misleading context, no pre-existing failure, no stale evidence | M1-host-migration: migrate a legacy plugin along the corridor, nothing planted to mislead | A task whose fixture merely contains *unfinished* code is still `none` — unfinished is not a trap |
| `misleading-guidance` | The task plants guidance (comments, notes, a colleague's advice, an instruction) that steers toward a **wrong change** | H1-plane-trap: comments steer toward a fatal host-plane change | S6-corridor-net-state: code written for an obsolete intermediate version looks like guidance but is **stale code** — annotate `stale-artifact` unless the misleading element is an explicit instruction |
| `pre-existing-failure` | The fixture ships with a failure that exists **before** the migration and is not caused by the upgrade the agent must diagnose as pre-existing | H2-baseline-trap: a test that was already red before the upgrade | A fixture that fails only because the migration was done wrong is not pre-existing-failure |
| `stale-artifact` | Stale build/cache/artifact or obsolete-version code masquerades as current evidence, and the trap is recognizing it as stale | H4-tsbuildinfo-trap: a stale build cache reports a deleted API as an error | A stale comment that merely misleads (no stale artifact) is `misleading-guidance` |
| `runtime-state` | The failure lives in **running process state**, not on disk/version metadata — the trap is trusting static facts over the live process | H13-ghost-host-trap: the running host predates the on-disk upgrade | A version-range mismatch visible in static files (no live process) is not runtime-state |
| `silent-contract-drift` | An API/contract changed without an obvious local error: everything is green in the fixture's environment but breaks in the real cohort | H5-runtime-export-drift: local install/typecheck/build/test all green, crash only on real cold boot | If the drift produces a clear compile error in the fixture, it is not silent |
| `multi-failure` | The task requires diagnosing **several distinct root causes** and the trap is incomplete diagnosis / attribution | S12-global-upgrade-ebusy-trap: two independent causes (EBUSY lock, silent downgrade) behind two failures | Two symptoms of one root cause is not multi-failure |
| `other` | A trap mechanism not covered above, with a non-empty `rationale` explaining the mechanism | (annotator-supplied) | If a listed type fits, `other` is invalid |

## 5. interaction_mode (machine-derived, not annotated)

Taken directly from the pinned registry (`benchmark/README.md` Type column)
at the inventory commit. Annotators never fill it; validators re-derive it
and refuse any mismatch.

## 6. difficulty — deferred to P1

This v1 does **not** ask annotators for difficulty. A reliable structural
rubric that does not consult model behavior has not been defined yet, and
the research plan ranks difficulty as P1. The `difficulty` column of the
templates stays blank; a non-blank value is a validation error in v1.

## 7. confidence rubric

- `high` — the packet contains direct evidence of the shared incident or
  trap mechanism (e.g. explicit version pair, named API change, planted
  artifact described in the task statement).
- `medium` — the grouping/type is well supported by task structure but the
  shared causal evidence is partially implicit.
- `low` — best-effort reading; used (and required) for `unresolved`.

## 8. Annotation procedure

1. **PREPARE (done)** — the blinded packet is generated deterministically
   from the pinned inventory.
2. **ANNOTATE (not started)** — Annotator A and Annotator B each complete
   their template from the packet **independently**: before first
   submission, neither sees the other's labels, no consensus, and no
   outcome/reward/results data; they do not discuss disagreements first.
   Each fills the independence declaration in the template header.
3. **ADJUDICATE** — after both submissions, the agreement script lists
   disagreements. A **third party** (not A, not B; the role is
   *adjudicator*, never "annotator C") sees only the task evidence, A's
   label + rationale, and B's label + rationale, then records A, B, or a
   new label with an adjudication reason.
4. **FREEZE** — the consensus mapping (generated only after adjudication
   completes) becomes the machine-readable input for family-level analysis.

If only one person is available, the status is
`single-pass-incomplete` — never `complete` — and no agreement or consensus
is produced from it.

## 9. Agreement metrics (documented before any label exists)

- **incident_family** — labels are arbitrary slugs, so raw label equality
  is not used. Primary: **pairwise co-clustering agreement** over all task
  pairs (both annotators same-family vs different-family); secondary:
  **Adjusted Rand Index** (label-permutation-invariant). Tasks marked
  `unresolved` by either annotator are excluded from both metrics and
  reported separately.
- **observable_trap_type** — fixed categorical vocabulary: **raw
  agreement** and **Cohen's kappa**. When the category distribution makes
  kappa undefined (e.g. all rows in one category), the output is
  `null`/`NA`, never a fabricated 0.
- **difficulty** — no agreement is computed for a deferred dimension.
