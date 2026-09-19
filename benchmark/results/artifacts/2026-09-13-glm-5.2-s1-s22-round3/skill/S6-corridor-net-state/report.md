# S6 · Corridor Net-State Judgment — `SessionEvent.ignorable` defense code (read-only report)

**Task**: analyze the alpha.1-era "defense code" in the fixture (it `delete`s the `ignorable` marker before appending a third-party persistent event) for a migration whose target host is **0.1.2-alpha.2**, and decide its fate by evidence, not by the code comment.

**Mode**: Mode A-style read-only inspection per the plugin-upgrade skill (the benchmark brief is the standing authorization; nothing under the fixture was modified, and no build/install/migration was performed — the brief forbids it).

## Identity and inputs

- Fixture: \`dsh-events-bench\` 0.1.0, private, ESM, single source file `src/events.ts`.
- Corridor segment in scope: 0.1.1-rc.2 → 0.1.2-alpha.1 → 0.1.2-alpha.2 (the "remove-then-restore" pair the skill's rollup calls the canonical net-state example).
- Evidence base: skill reference cards `v0.1.2-alpha.1.md` (DSH-0.1.2-A1-02), `v0.1.2-alpha.2.md` (DSH-0.1.2-A2-01), `api-migration-0.1.2-alpha.2.md` (API-05), `rollup-0.1.2.md`. Closed-book constraint honored: no network, no reference answers, no environment outside the fixture and the skill.

## 1. Fate of the defense code: **DELETE** — and the comment's claim is wrong in both halves

### Full history of the semantics across the corridor

| Edge | What happened | Card |
|---|---|---|
| rc.2 → alpha.1 | `SessionEvent.ignorable` **temporarily removed** (breaking). alpha.1 cannot preserve the `ignorable: true` marker on third-party informational events; first-party readers meeting unknown persisted events reject the reload, treating them as required. | DSH-0.1.2-A1-02 |
| alpha.1 → alpha.2 | **Restored** (type: fix). Envelope/persistence/reload/transport retention semantics are back: unknown events **with** `ignorable: true` survive reload and old readers may omit their semantics; unknown events **without** the marker remain required-on-read (fail closed). | DSH-0.1.2-A2-01 |

Net state across the corridor (skill rule: read the full corridor and compute the final state; a field removed in an intermediate version and restored in the target must not be deleted-and-re-added — A1-02's own recipe says "do not delete the producer marker and then restore it"): **alpha.2 behaves as if the removal never happened for this field**. The `rollup-0.1.2.md` reference explicitly names this exact pair as the canonical example.

### Why the code must go

1. **Its premise is inverted.** On alpha.2, dropping the marker is precisely what makes first-party readers reject a session containing unknown events (A2-01 symptom: "old adapters that keep dropping the marker will make first-party readers reject Sessions containing unknown events"). The defense code, if it ever actually stripped a marker, is now an *attack* on loadability, not a defense.
2. **The comment's two claims are both false for alpha.2**: (a) "readers will reject it otherwise" — readers reject unknown events *lacking* the marker, not carrying it; (b) "must be kept when migrating to alpha.2" — A2-01 is the revert of A1-02; the corridor's net state restores the retention semantics.
3. **It was the wrong medicine even for alpha.1.** A1-02's recipe for an alpha.1 target is not "delete the marker before writing"; it is to *stop writing that unknown persisted event* (or use event vocabulary the target already knows), because alpha.1 cannot preserve the marker through persistence at all. Actively deleting it only guarantees the failure mode. (Also note: in the fixture the `delete` operates on a freshly-built literal that never had the key, so as literal code it is a no-op — but its documented intent is the dangerous part, and intent is what a migration must fix.)

### But deleting the line is not the whole fix — see §2

The correct migration outcome is: **remove the marker-stripping defense and its comment, and stop treating `Session.append(...)` as a supported third-party persistence seam on alpha.2** (details below).

## 2. Correct producer semantics on alpha.2, and what an ordinary plugin using `Session.append(...)` should do

### Envelope semantics (unchanged, restored)

- `ignorable: true` is a **producer-side omission-safety marker**: a reader that does not know the event type may continue only if the event already carries it; a missing field means required.
- It is **not** a consumer-side filtering directive; marked events remain in loaded events after reload.
- Eligibility: only auxiliary/informational events whose absence does not change core or durable session semantics for a reader without the producing plugin.

### The public-API gap (the decisive fact for this plugin)

API-05: alpha.2 restores `ignorable?: true` on the *envelope*, but the public live `Session.append(...)` **only accepts `type`, `data`, and `SurfaceIntent`** (the last being for surface events only) — there is **no `ignorable` parameter**, and the append path will not write the marker into the event. Consequences for an out-of-repo custom type:

- Live append succeeds and the event persists — but on the next **cold load** the unknown, unmarked event throws `SessionFormatUnsupportedError` and the **whole Session is refused**. A silent write / loud read that a live-only smoke will not catch.
- This cannot be bypassed with casts, `as any`, thawing objects, or hand-editing JSONL (API-05 explicitly), and the fixture's `session: any` / `(event as any)` typing hides exactly this fact from the compiler.

Notably this remains true well beyond alpha.2: the 0.1.5-alpha.2 card (DSH-0.1.5-A2-05 context) still states "`Session.append()` has no `ignorable` channel", so the gap is long-lived — do not wait for an imminent fix.

### What this plugin should actually do on alpha.2

1. **Delete the `delete (event as any).ignorable` line and its comment** (the asked-about defense).
2. **Do not persist `third-party/informational` via `Session.append()` at all.** Best practice (API-05): use a plugin-owned sidecar/store keyed by session id for plugin state on alpha.2.
3. If an existing persisted custom event exists from earlier versions, run a real persist → process-restart/cold-load test; treat cold-load refusal as a migration blocker and remove that persistence scheme rather than swallowing the error.
4. Re-evaluate third-party persistent events only after upstream ships a supported `append(..., { ignorable: true })` or another formal mechanism that persists the omission-safety marker; registering an event name alone is not sufficient.
5. Persistence/transport owners (not this plugin) must instead preserve existing markers end-to-end (JSONL/SQLite/API transports and the generated catalog preserve the field as-is; unknown unmarked events keep failing closed; SQLite provider takes only schema 20).

## Verification performed vs. not performed

- **Performed (read-only)**: fixture source review; corridor edge resolution via `references/README.md`-connected cards (A1-02 ↔ A2-01 revert pair, API-05 ledger, rollup net-state note); grep across all corridor references confirming no later `ignorable` append channel appears through 0.1.5-alpha.2.
- **Not performed (forbidden by the brief)**: baseline build/typecheck/test runs, dependency installation, real cold-load reproduction, runtime mount. The behavior claims above rest on the skill's curated cards and their cited upstream sources (alpha.2 `Session.append()` implementation and cold-load unknown-event guard links in API-05), which I could not open (closed-book, no network).
- **Unconfirmed items**: (a) the exact runtime shape of the fixture's `session.append(event)` call — the fixture types `session` as `any` and passes a whole envelope object where the documented signature is `(type, data)`; whether it even appends as intended on any host version is unconfirmed; (b) whether any real alpha.1-era sessions with unmarked unknown events exist in this plugin's deployment — unconfirmed; if they do, they are already unreadable by design (fail closed) and require the A1-02/A2-01 remedies (stop writing / export before schema changes), not marker surgery.

## Skipped

- Touchpoint classes #1, #3–#7 (source patches, host FS, UI/commands, custom channels, subprocess): no hits — the fixture's single function touches only the session-event seam (#2 events).
- Plugin SemVer bump planning (Mode C step 6): not applicable to a read-only report; if the fix is implemented later, bump the plugin's own version, not the DSH host version.

## Pending / residual risk

- The fixture README independently states the correct action is to delete the defense; I judged from the corridor cards, and the two agree.
- Implementation of the fix (delete line + move persistence to a sidecar) is out of scope here (read-only task); when done it needs the persist → cold-load verification from §2.3.

## Recommendation summary

**Delete the defense code and its comment. On alpha.2 the retention semantics are restored, so stripping the marker causes exactly the rejection it claims to prevent; and because the public `Session.append(...)` cannot set `ignorable` at all, this plugin must not persist custom third-party events through it — use a plugin-owned sidecar store until upstream ships a supported marker-aware append surface.**
