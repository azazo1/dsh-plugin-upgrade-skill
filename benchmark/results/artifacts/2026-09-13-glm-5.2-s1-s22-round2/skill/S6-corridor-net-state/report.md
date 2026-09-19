# S6 · Corridor Net-State Judgment — Migration Report (read-only)

**Task**: assess the fate of the alpha.1-era "defense code" in `src/events.ts` (deleting the `SessionEvent.ignorable` marker before a third-party persistent event write) when migrating to host **dsh-v0.1.2-alpha.2**.
**Mode**: Mode A / read-only corridor analysis (plugin-upgrade skill). No file under the fixture was modified; no build, install, or reproduction environment was created (per brief restrictions).
**Fixture identity**: `dsh-events-bench` v0.1.0, `"private": true`, ESM, single source file `src/events.ts`; fixture read via read-only tools; git state not collected (fixture directory is read-only evidence; benchmark repo rules forbid touching it — **unconfirmed** beyond file contents).

## Evidence base (closed-book, primary = skill reference cards)

| Fact | Source |
|---|---|
| alpha.1 (DSH-0.1.2-A1-02) **temporarily removed** `SessionEvent.ignorable`; alpha.1 cannot preserve the marker on third-party informational events; first-party readers reject reloads containing unknown persisted events | `references/v0.1.2-alpha.1.md`, card A1-02 |
| alpha.2 (DSH-0.1.2-A2-01, Type: fix) **restores** `ignorable` for third-party persisted events — envelope/persistence/reload/transport retention semantics; explicit "revert of DSH-0.1.2-A1-02"; adapters that keep dropping the marker will make first-party readers reject Sessions with unknown events | `references/v0.1.2-alpha.2.md`, card A2-01 |
| A1-02 itself instructs: "If the final target is alpha.2 or later, first read A2-01 to compute the corridor net state; **do not delete the producer marker and then restore it**" | card A1-02 migration recipe |
| API-05: alpha.2's public `Session.append()` still only accepts `type`, `data`, and `SurfaceIntent` (surface events only); it **does not write `ignorable`**; a custom type can live-append and persist but throws `SessionFormatUnsupportedError` on the next cold load (silent write / loud read) | `references/api-migration-0.1.2-alpha.2.md`, API-05 |
| `rollup-0.1.2.md` names `ignorable` as the canonical remove-then-restore example for net-state computation | rollup, line 53 |

The fixture's own `README.md` also states the trap ("alpha.2 已恢复保留语义，这段防御应当删除") — consistent with the cards, but the decision below rests on the reference cards, not the comment (requirement 3).

## 1. Fate of the defense code: **DELETE**

Corridor net state for `SessionEvent.ignorable` (rc.2 → alpha.1 → alpha.2):

- **rc.2 (0.1.1-rc.2)**: marker exists on the envelope; producers of third-party informational events could rely on retention semantics.
- **alpha.1**: removed (A1-02). During this window, unknown persisted events without a known type are treated as required and reject the reload; the marker cannot be preserved even if written.
- **alpha.2 (target)**: **restored** (A2-01). Retention semantics are back on envelope/persistence/reload/transport; JSONL, SQLite, API transports, and the generated catalog must preserve the field as-is.

Net state at target = marker exists and must be **preserved end-to-end**. Per the skill's net-state rule (Mode C step 2) and A1-02's own recipe, a field removed in an intermediate version and restored in the target is **not** delete-then-re-add: code written to defend against the alpha.1 removal window is obsolete at alpha.2. Keeping it is not merely dead code — A2-01 marks it **actively harmful**: "old adapters that keep dropping the marker will make first-party readers reject Sessions containing unknown events." The comment's claim that it "must be kept when migrating to alpha.2" is exactly backwards; it is a textbook comment-over-facts trap. Additionally, the `delete (event as any).ignorable` line is a runtime no-op on a freshly constructed literal that never sets the field — it survives only as misleading documentation of the wrong invariant.

Migration action: remove the `delete` line **and** the alpha.1-era comment (together — keeping the comment without the code preserves the fallacy), in a dedicated branch, with the baseline recorded first.

## 2. Correct producer semantics on alpha.2, and what `Session.append(...)` callers should do

- `ignorable: true` is a **producer-side envelope marker** for informational events whose semantics a reader without the plugin can omit without affecting Session reconstruction. It is **not** a consumer-side filtering directive; marked events remain in loaded events after reload. Unknown events **without** the marker are required-on-read and fail closed.
- **The public `Session.append(...)` has no `ignorable` parameter** (A2-01 + API-05: accepts `type`, `data`, `SurfaceIntent`; `SurfaceIntent` is available to surface events only). Consequences for an ordinary plugin:
  1. Do **not** fake the field via `as any` casts, thawed objects, or hand-edited JSONL — API-05 states this cannot bypass the gap; writes appear to succeed live, then the next **cold load** refuses the whole Session (`SessionFormatUnsupportedError`).
  2. On alpha.2, out-of-repo plugins should **not** persist plugin state via custom `SessionEventMap` augmentation + `Session.append()`; use a plugin-owned sidecar/store keyed by Session id. Treat this as a **capability gap at the producer seam**, not something the plugin can work around.
  3. If reusing an existing known event, reuse only genuinely identical semantics; never disguise plugin state as a core/model-visible event.
  4. Re-evaluate third-party persistent events only after upstream ships a supported `append(..., { ignorable: true })` or equivalent formal mechanism; registering an event name alone is not enough.
  5. Persistence/transport owners (not this plugin's case) must preserve existing markers end-to-end and keep fail-closed behavior for unmarked unknown events.
- The fixture's own call `session.append(event)` (single object argument) does not match the public `append(type, data, ...)` signature either — a secondary type-surface defect to fix alongside removing the defense; **unconfirmed** against alpha.2 source (closed-book; derived from API-05's stated signature only).

## 3. Verification-by-evidence notes

- Decision grounded in: A1-02, A2-01, API-05, rollup-0.1.2 (all read in full for the relevant cards). Not grounded in the source comment or the fixture README.
- **Unconfirmed items** (closed-book brief; no network, no host source available): the exact alpha.2 `Session.append` implementation and `SessionEvent` type at the cited GitHub paths; alpha.2 runtime behavior (no cold-load test was run, since building a reproduction environment is forbidden); git HEAD equality of the fixture.
- Suggested validation once out of the closed-book context: persist → process-restart/cold-load test of any remaining custom append path (live append alone cannot catch the silent-write/loud-read gap); confirm unknown unmarked events are refused and marked ones survive reload.

## Report per skill structure

- **pre-existing**: not collected (Mode A read-only; fixture is static evidence, no baseline run permitted by the brief).
- **Completed**: corridor net-state computed (removed alpha.1 / restored alpha.2); verdict **delete the defense code and its comment**; producer semantics and `Session.append` guidance stated above.
- **Skipped**: no dependency/lockfile/enablement-resolution checks — the fixture has no DSH dependency cohort (`package.json` has none) and no profile/composition files; no build/typecheck/test runs (brief forbids creating a reproduction environment).
- **Pending/residual risk**: cold-load behavior unverifiable in this container; `session.append(event)` call-shape mismatch flagged but unconfirmed against alpha.2 sources; if the plugin's persisted events already exist in alpha.1-era logs, those sessions contain unmarked unknown events and remain unloadable even on alpha.2 (fail-closed by design) — needs an export/rebuild path assessment outside this task.
- **Rollback**: no writes performed anywhere except this report; nothing to roll back. (For the eventual real migration: dedicated branch, revert = restore the deleted two lines from the pre-migration commit.)
- **Recommendations**: move third-party persisted state to a plugin-owned sidecar keyed by Session id (API-05 best practice #1); track upstream for a supported `append(..., { ignorable: true })` producer surface before reintroducing persistent custom events; never trust in-source migration comments over corridor cards.
