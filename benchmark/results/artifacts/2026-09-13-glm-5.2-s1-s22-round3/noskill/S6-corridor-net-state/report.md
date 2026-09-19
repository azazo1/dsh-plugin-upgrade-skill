# S6 · Corridor Net-State Judgment — Migration Report (alpha.1 → alpha.2)

**Verdict: delete the defense code.** The `delete (event as any).ignorable` line (and its comment) in `src/events.ts` must be removed when migrating to alpha.2. It is dead at best and actively wrong at worst.

## Evidence

Fixture inspected read-only (`fixture/src/events.ts`, `fixture/README.md`, `fixture/package.json`); nothing under the fixture was modified.

The code:

```ts
const event = { type: 'third-party/informational', payload }
delete (event as any).ignorable   // "alpha.1 removed SessionEvent.ignorable (DSH-0.1.2-A1-02)..."
session.append(event)
```

Two independent facts kill it:

1. **It never did anything, even on alpha.1.** The object literal `{ type, payload }` never contains an `ignorable` property, so the `delete` is a no-op on every version. A no-op cannot be "required for readers to accept the event".
2. **The corridor history goes remove-then-restore.** Per the fixture README, the retention semantics were removed in alpha.1 (DSH-0.1.2-A1-02) and **restored in alpha.2** (DSH-0.1.2-A2-01). The comment's claim that the defense "must be kept when migrating to alpha.2" is exactly backwards: the condition it was written for (no `ignorable` in the format) no longer holds on the target host.

## 1. Fate of the defense code

**Delete.** Reasoning across the full corridor:

- *Pre-alpha.1 / alpha.2 (restored):* `SessionEventMap` members are required-on-read by default; an event carrying `ignorable: true` in its typed declaration may be omitted/refused by builds that don't know the type. The marker is part of the **event type declaration** (declaration merging on the event map), not something producers toggle per-call.
- *alpha.1 (removed):* the marker didn't exist in the format. But even then, this code's `delete` was a no-op (see fact 1) — the comment's threat model ("readers will reject it otherwise") describes a property this object never had.
- *alpha.2:* semantics restored, so the stated justification is void on the target host regardless.

There is no version in the corridor where this line is load-bearing. Keep nothing.

## 2. Correct producer semantics

`ignorable` is an ownership question, not a write-time toggle:

- Whether a session event is ignorable-by-unknown-builds is declared **once, on the event type** via declaration merging in the event map (`ignorable: true` in the typed event declaration with its `@mode`/payload JSDoc). It is metadata of the *event kind*, owned by whoever defines the event type.
- An ordinary third-party plugin producing an event through `Session.append(...)` should simply append the typed payload: `session.append({ type: 'third-party/informational', payload })`. The public `append` API surface does not even expose an `ignorable` parameter — producers cannot and should not set, unset, or delete it per call.
- Marking anything unverifiable: the exact alpha.1/alpha.2 changelog identifiers beyond what the fixture README states (DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01) are taken from the fixture; this is a closed-book brief, so the surrounding release history is **unconfirmed** outside the fixture. It does not change the verdict, which rests on the no-op nature of the code and the restored alpha.2 semantics stated in the fixture.

## 3. Recommended migrated code

```ts
export function produceExternalEvent(session: any, payload: any): void {
  session.append({ type: 'third-party/informational', payload })
}
```

(If the plugin's event type genuinely needs unknown-build tolerance on alpha.2, that is solved by declaring the event type with `ignorable` in its `SessionEventMap` declaration merging — never by mutating the event object at the producer.)
