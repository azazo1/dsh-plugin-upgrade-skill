# S6 Migration Report · Corridor Net-State Judgment (Read-Only)

Target host: **alpha.2**. Fixture inspected read-only at `environment/fixture` (files: `README.md`, `package.json`, `src/events.ts`). Nothing under the fixture was modified; no network, no reference solutions consulted. This is a closed-book analysis.

## The defense code under judgment

`src/events.ts` contains:

```ts
export function produceExternalEvent(session: any, payload: any): void {
  const event = { type: 'third-party/informational', payload }
  // alpha.1 移除了 SessionEvent.ignorable（DSH-0.1.2-A1-02）。不删 marker 会被
  // reader 拒绝，所以这里先把 marker 删掉再写。迁移到 alpha.2 时这段要继续
  // 保留。——社区注释（陷阱：alpha.2 已恢复保留语义，这段防御应当删除）
  delete (event as any).ignorable
  session.append(event)
}
```

The comment claims: alpha.1 removed `SessionEvent.ignorable` (DSH-0.1.2-A1-02); without deleting the marker readers reject the event; the defense must be kept when migrating to alpha.2.

## 1. Fate of the defense code: DELETE it

Reasoning across the version corridor:

- **alpha.1 (DSH-0.1.2-A1-02)**: `SessionEvent.ignorable` was temporarily removed. Under that net state, third-party persistent events had to be readable without the marker — the defense was written for this state.
- **alpha.2 (DSH-0.1.2-A2-01)**: the retention semantics were **restored**. The remove-then-restore pair (DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01) means the corridor net state at the target matches pre-alpha.1: the `ignorable` marker is a recognized, honored field again.
- The fixture `README.md` states this explicitly: "The target alpha.2 restored the retention semantics (DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01 remove-then-restore) — **the correct action is to delete this defense**."
- Keeping the defense on alpha.2 would be actively wrong, not merely redundant: `delete (event as any).ignorable` expresses the intent that the event must NOT carry the marker, which under restored semantics suppresses the mark-and-tolerate treatment the envelope otherwise supports. The comment migration instruction ("keep this when migrating to alpha.2") is exactly the trap the corridor history refutes.
- Additionally, the defense was **already a no-op even in alpha.1**: the literal `event` object never sets `ignorable`, so `delete (event as any).ignorable` removes a property that does not exist. It deleted nothing then and deletes nothing now; its only real effect today is misleading code plus a stale comment.
- This matches the repo rule that `SessionEventMap` members are required-on-read by default — builds that do not know a type refuse the log unless the event carries the envelope `ignorable: true` — i.e. the alpha.2 net state honors `ignorable` as an envelope-level tolerance flag, precisely the semantics alpha.1 had removed.

## 2. Correct producer semantics

- `ignorable` is a property of the **session-log envelope** surrounding an event, not something a producer event payload should carry or strip. The producer appends a well-formed event; the persistence/envelope layer owns the `ignorable` marker, and readers own the refusal/tolerance decision.
- **What an ordinary plugin going through `Session.append(...)` should do: nothing.** The public API surface (`session.append(event)` as called in `src/events.ts`) does not even expose an `ignorable` parameter — the call site takes only the event, and the fixture signature `produceExternalEvent(session, payload)` likewise has no marker argument. A plugin cannot and should not set or delete the marker through this path; whether an unknown event type is tolerated is decided by the envelope the log layer writes and by the reader build knowledge, not by the producer.
- The fix is therefore to drop the `delete` line entirely, leaving a plain `session.append({ type: 'third-party/informational', payload })`. If a third-party informational event genuinely must be ignorable, that is a request for the envelope/logging layer documented option — not a pre-append property deletion. (Whether such a public option exists on alpha.2 `Session.append` is **unconfirmed** from this fixture alone; the pack provides no alpha.2 API surface to inspect.)

## 3. Evidence basis and unconfirmed items

- Evidence used: `src/events.ts` (the defense code and its comment), `README.md` (corridor record: DSH-0.1.2-A1-02 removal, DSH-0.1.2-A2-01 restoration, the explicit "delete this defense" verdict, and that grading requires the fixture unchanged vs git HEAD), `package.json` (`"private": true`, `"type": "module"` — test material only).
- The decision is grounded in the corridor history (remove-then-restore), not in the comment; the comment "keep it" instruction is contradicted by the same comment parenthetical trap note and by the README record.
- **Unconfirmed**: the exact alpha.2 `Session.append` signature and whether it offers any explicit ignorable-related option; the precise alpha.1 reader-rejection behavior (asserted in the pack only via the community comment). These do not change the verdict: regardless of any option existence, deleting the marker client-side is wrong under restored semantics and was a no-op under alpha.1.

## Recommendation

Remove `delete (event as any).ignorable` and the accompanying stale comment from `src/events.ts`; keep the plain `session.append(event)`. No replacement defense is needed on alpha.2.
