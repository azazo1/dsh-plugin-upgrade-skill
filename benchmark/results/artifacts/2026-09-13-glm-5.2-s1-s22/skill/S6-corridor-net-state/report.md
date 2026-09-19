# S6 · Corridor Net-State Judgment — `SessionEvent.ignorable` defense code (read-only report)

**Task**: read-only analysis of the fixture (local copy: `E:\deepseek-harness\dsh-plugin-upgrade-skill\benchmark\tasks\S6-corridor-net-state\environment\fixture`). No file under the fixture was modified. Target host: **DSH 0.1.2-alpha.2**.

**Method**: plugin-upgrade skill, Mode A (inspect). Corridor read as rc.2 → alpha.1 → alpha.2 (cards `DSH-0.1.2-A1-02` and `DSH-0.1.2-A2-01`, per the skill rule “read the full corridor first and compute the final net state”), cross-checked against the installed host checkout at `C:\Users\lhh\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh` (version 0.1.5-rc.2, newer than the corridor but the semantic persists).

## 1. Fate of the defense code: **DELETE it (together with its comment)**

### The code under review (`src/events.ts`)

```ts
export function produceExternalEvent(session: any, payload: any): void {
  const event = { type: 'third-party/informational', payload }
  // alpha.1 removed SessionEvent.ignorable (DSH-0.1.2-A1-02). Without deleting the
  // marker readers will reject it, so delete it before writing. Keep this when
  // migrating to alpha.2. — community comment (trap: alpha.2 restored retention
  // semantics; this defense should be deleted)
  delete (event as any).ignorable
  session.append(event)
}
```

### Full history of the semantics across the corridor

| Edge | Card | What happened to `ignorable` |
|---|---|---|
| rc.2 → **alpha.1** | `DSH-0.1.2-A1-02` | `SessionEvent.ignorable` **temporarily removed**. First-party readers encountering unknown persisted events rejected the reload (treated them as required-on-read). The correct alpha.1 recipe was **not** to delete markers on write: it was to stop writing that unknown persisted event, or switch to event vocabulary the target version already knows. Deleting the marker never helped — it just guaranteed the event was written as required. |
| alpha.1 → **alpha.2** (target) | `DSH-0.1.2-A2-01` | Retention semantics **restored** (explicit revert of A1-02; source note `2026-08-30-retain-ignorable-external-session-events.md`). `ignorable: true` on a third-party informational event is again the compatibility mechanism that lets an older reader omit the event's semantics without rejecting the log. |

**Corridor net state (plugin corridor → alpha.2)**: the removal in alpha.1 is an intermediate state that the final target already reverted. Per the skill's Mode C step 2, a field removed in an intermediate version and restored in the target must not be deleted-then-restated — the net change across the corridor is **zero**. The defense is (a) aimed at a symptom that no longer exists on the target, and (b) was the wrong remedy even on alpha.1. The comment's claim “must be kept when migrating to alpha.2” is factually wrong on both counts.

Also note the defense is doubly incoherent even on its own terms: the code builds `event` without ever setting `ignorable`, then `delete`s a property that is not present — a no-op wrapped around a wrong claim. And the call itself misuses the API: `session.append(event)` passes an object where the real signature expects `(type, data, ...)` (see §2).

### Secondary facts worth recording

- The alpha.1 card warns against the adjacent anti-pattern: turning unknown persisted events into a consumer whitelist would wrongly admit required events — not this plugin's case, but the same class of “defense” mistake.
- An unknown third-party event persisted **without** the marker is **required-on-read**: a reader that does not know the type rejects the log. **Unconfirmed**: actual rejection behavior at runtime — no alpha.2 host or reproducible test was built, per the closed-book/no-build constraints of this brief.
- SQLite persistence provider in alpha.2 accepts only schema 20 and rejects schema 19 without auto-migrate (A2-01). Not hit by this code; corridor context only.

## 2. Correct producer semantics on alpha.2

From `DSH-0.1.2-A2-01`:

1. **Producers** should write `ignorable: true` **only for informational events whose semantics an old reader can omit without affecting reconstruction**. It is a producer-side omission-safety classification, **not** a consumer-side filtering directive; marked events still remain in loaded events after reload. Unknown events **without** the marker remain required-on-read (readers reject logs containing them).
2. **Persistence/transport seams** (JSONL, SQLite, API transports, generated catalog `KNOWN_SESSION_EVENT_TYPES`) must preserve the field as-is.
3. **Crucially for this plugin**: the public live `Session.append(...)` **still has no `ignorable` parameter** on alpha.2. An ordinary plugin whose only API is `Session.append` **cannot and should not** set the marker — it should mark the producer seam as a **capability gap** (request a public entry point for third-party ignorable events) rather than faking one via `as any` casts.

Verified against the installed host declarations (0.1.5-rc.2; semantic continuity from the A2-01 restore):

```ts
// @deepseek-ai/dsh-session lib/types/index.d.ts
append<T extends SessionEventType>(type: T, data: SessionEventMap[T],
  ...opts: T extends SurfaceEventType ? [opts: SurfaceIntent<T>] : []): SessionEvent<T>;
```

No `ignorable` parameter exists; the marker is an **envelope/persistence** field (`readonly ignorable?: true` on the persisted event in `types.d.ts`), set by the host/persistence seam, not by `append` callers. The generated `known-event-types.d.ts` confirms: “The persisted `SessionEvent.ignorable` marker is the compatibility mechanism; event-name registration was rejected…”.

### What this plugin should actually do

- Delete the `delete (event as any).ignorable` line and the misleading comment.
- Call the real API shape: `session.append('third-party/informational', payload)` (type-first, data second) — the current `session.append(event)` with a whole envelope object does not match the public signature. **Unconfirmed**: whether the plugin's `session` object is the real `Session` or some wrapper; the fixture types it `any`, so the exact call form should be re-checked against the plugin's real dependency once out of closed-book conditions.
- Recognize that, since `append` has no `ignorable` parameter, an unknown third-party event written this way is persisted **without** the marker and is therefore required-on-read for readers that don't know the type. If the event is merely informational, that is a **capability gap to raise with the host** (or a signal to stop persisting it / use known vocabulary), per the A1-02/A2-01 recipes — not something to paper over with casts or marker deletion.

## 3. Decision by evidence, not by the comment

| Claim in the fixture comment | Evidence | Verdict |
|---|---|---|
| “alpha.1 removed `SessionEvent.ignorable` (DSH-0.1.2-A1-02)” | A1-02 card | True |
| “Without deleting the marker readers will reject it” | A1-02 card: alpha.1 readers reject **unknown events without** the marker; deleting a marker cannot prevent rejection — it causes required-on-read status. The property was never set, so the `delete` is a no-op. | False / incoherent |
| “Keep this when migrating to alpha.2” | A2-01 card: alpha.2 restored retention semantics, explicitly reverting A1-02; corridor net change is zero. | False — the defense must be **deleted** |

**Unconfirmed items** (closed-book constraints — no network, no builds, no host install):
- Runtime reproduction of reader rejection/retention on an actual alpha.2 host.
- Whether the alpha.1-era removal ever shipped on a public npm tag (cards imply the 0.1.2 alphas were corridor-internal; unverified).
- Exact identity of the fixture's `session` parameter (typed `any`).

## 4. Skipped / not applicable

- Modes B and C write actions: the brief restricts this task to read-only analysis; no files, dependencies, or versions were touched.
- Other touchpoint classes (pre-flight scan: source patches, services/Remote, host FS, UI/commands/tools, custom channels, subprocess): not applicable — the fixture is a single producer function on the session-event seam.
- SQLite schema-19 migration guidance: context only; no persistence provider is used by the fixture.

## 5. Rollback / state

Read-only task; no changes were made anywhere except this report file in the designated output directory. The fixture directory is byte-identical to its state at task start (verified read-only; no write operations were issued against it).
