# S6 · Corridor Net-State Judgment — Migration Report (alpha.1 → alpha.2)

**Fixture (read-only):** `environment/fixture/src/events.ts` — `produceExternalEvent()`
**Target host:** alpha.2
**Verdict: DELETE the defense code.**

## 1. Fate of the defense code: delete

### What the code does

```ts
const event = { type: 'third-party/informational', payload }
// alpha.1 移除了 SessionEvent.ignorable（DSH-0.1.2-A1-02）。不删 marker 会被
// reader 拒绝，所以这里先把 marker 删掉再写。迁移到 alpha.2 时这段要继续
// 保留。——社区注释
delete (event as any).ignorable
session.append(event)
```

### Full history of the semantics across the version corridor

| Stage | Semantics of `SessionEvent.ignorable` |
|---|---|
| Before alpha.1 | `ignorable: true` on an event (envelope) marks it readable-optional: builds that do not know the event type may skip it instead of refusing the log. |
| alpha.1 (DSH-0.1.2-A1-02) | `ignorable` was **removed** from `SessionEvent`. Under required-on-read semantics, an unknown event type — with or without any marker — is grounds for a stricter reader to reject the session log. The "defense" of `delete`ing the marker was written against this state. |
| alpha.2 (DSH-0.1.2-A2-01) | The retention semantics was **restored** (remove-then-restore across the corridor). `ignorable` exists again, and unknown `SessionEventMap` members are required-on-read *unless* the envelope carries `ignorable: true`. |

The fixture README states this explicitly: "The target alpha.2 restored the retention semantics (DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01 remove-then-restore) — the correct action is to delete this defense." This is the only in-fixture authority for the alpha.2 state, and it matches the harness-wide session-format rule (unknown session event types are required-on-read by default unless marked `ignorable`).

### Why the comment's claim fails on alpha.2

1. **The comment argues from a transient net state.** "Readers will reject it without deleting the marker" was true only while alpha.1's removal was in force. On alpha.2 the marker is the *opt-in to being skipped*; deleting it is exactly backwards — it makes an unknown third-party event **more** likely to be rejected by a stricter reader, not less.
2. **"Must be kept when migrating to alpha.2" is a frozen conclusion from a superseded version.** Migration decisions must be re-derived against the target host's current semantics, not carried forward from alpha.1 comments.
3. **The defense is also dead code as written.** The literal `event` object built on the previous line never sets an `ignorable` property, so `delete (event as any).ignorable` is a no-op on this object in any case. It neither protects nor harms at runtime — but its comment actively misleads future maintainers, which is itself a reason to delete it.

## 2. Correct producer semantics on alpha.2

- `ignorable: true` is an **envelope-level, harness-owned retention marker**: it tells readers "if your build does not know this event type, you may skip this event instead of refusing the session log." Default absence means required-on-read.
- For a genuinely third-party/informational event that arbitrary reader builds will not know, the correct producer behavior is the **opposite of the defense**: the write should *carry* `ignorable: true` (assuming the event is genuinely skippable — informational, not needed to reconstruct model-visible input).
- **Ordinary plugins going through `Session.append(...)`** most likely do nothing: the public append API surface plausibly does not even expose `ignorable` as a caller parameter (it is part of the logged envelope, not the event payload), and it is the persistence/event-map layer that decides envelope flags. Third-party event types that need the marker would declare it through the supported extension mechanism, not by mutating the event object at the call site. **Unconfirmed:** the exact alpha.2 `Session.append` signature and whether it exposes an envelope/marker option — no API source is available in this closed-book fixture beyond the code shown, which passes a bare `{ type, payload }`.
- Also unconfirmed (closed-book): whether `third-party/*` type names are themselves reserved or validated by alpha.2 readers.

## 3. Evidence basis

- Decided by: fixture `README.md` (explicit statement of the A1-02 → A2-01 remove-then-restore corridor and the "delete this defense" directive) and the harness-wide session-format rule that unknown `SessionEventMap` members are required-on-read unless the envelope carries `ignorable: true`.
- The in-code comment was treated as a claim, not evidence; its premise ("readers reject the marker") is the alpha.1 net state and is false on the alpha.2 target.
- Marked unconfirmed: exact alpha.2 `Session.append` parameter surface; handling/reservation of `third-party/*` type names; precise wire location of `ignorable` in the logged envelope.

## Recommended replacement (illustrative only — fixture untouched)

```ts
export function produceExternalEvent(session: any, payload: any): void {
  // alpha.2 restores the retention semantics: unknown event types are
  // required-on-read unless the envelope carries ignorable: true. No marker
  // deletion is performed; third-party informational events opt in to being
  // skippable via the supported envelope mechanism, not by mutating the event.
  session.append({ type: 'third-party/informational', payload })
}
```

**Bottom line:** the `delete (event as any).ignorable` defense and its comment must be **deleted** for the alpha.2 migration. It defends against a removed alpha.1 semantics, is a no-op on the literal object anyway, and its comment would steer future maintainers to suppress the very marker that alpha.2 restored for exactly this third-party use case.
