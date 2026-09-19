# S6 · Corridor Net-State Judgment — Migration Report

Fixture inspected (read-only, unchanged): `README.md`, `package.json`, `src/events.ts` under the S6-corridor-net-state evidence pack.

## The defense code under judgment

`src/events.ts` (entire source, 8 lines):

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

The "defense" is the `delete (event as any).ignorable` line plus its comment, which claims: (a) alpha.1 removed `SessionEvent.ignorable` (DSH-0.1.2-A1-02); (b) without deleting the marker, readers reject the event; (c) the code must be kept when migrating to alpha.2.

## 1. Fate of the defense code: DELETE it (do not keep)

Reasoning from the full corridor history, as recorded in the fixture's own `README.md`:

- **alpha.1 (DSH-0.1.2-A1-02):** `SessionEvent.ignorable` was temporarily removed. Under that host, a persistent event carrying the `ignorable` marker was rejected by readers, so a producer-side `delete` of the marker was a working (if mis-scoped) defense for that one host version.
- **alpha.2 (DSH-0.1.2-A2-01):** the retention semantics were **restored** — the README states this explicitly: "DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01 remove-then-restore". The net state across the corridor (alpha.1 removed, alpha.2 restored) is that the host again owns the marker's meaning and retention.
- The README states the conclusion directly: "**the correct action is to delete this defense**". The comment's "must be kept when migrating to alpha.2" is a stale alpha.1-era claim that describes exactly the state alpha.2 reversed. Keeping the delete under alpha.2 is actively harmful: it strips a marker the host is now willing to persist/interpret, changing event semantics on the producer side instead of letting the host apply its own retention rules.
- The comment itself is hearsay ("社区注释" — a community note); it asserts a future-host behavior that the same file's README contradicts. Per the brief's rule 3, the decision follows the recorded corridor evidence (A1-02 remove → A2-01 restore), not the comment.

Unconfirmed: the exact read/reject behavior of alpha.1 readers (no alpha.1 host source is in the pack); only its existence and effect are attested by the comment and the README's corridor labels.

## 2. Correct producer semantics and what a plugin via `Session.append(...)` should do

- **The marker belongs to the host/session-log envelope, not to the event producer.** `ignorable` is a session-log envelope property governing whether an event is required-on-read (whether a build that does not know the event type may refuse the log). Its presence/absence and persistence are decided by the host's format rules — here, restored in alpha.2 — not by each producer deleting fields defensively.
- **An ordinary plugin going through the public API should do nothing about `ignorable`:** build the event payload and call `session.append(event)`, full stop. The hint in the brief is correct: the public append surface may not even expose that parameter — a producer has no legitimate way to set it, and symmetrically no legitimate need to delete it. In this fixture the defense is doubly pointless even for alpha.1: the locally constructed `event` object never sets `ignorable` in the first place, so `delete (event as any).ignorable` deletes a property that does not exist. The defense is a no-op on its own object and can only matter if the host merges envelope fields — which is host behavior, not producer behavior to overrule.
- Correct rewritten producer (the whole defense removed):

```ts
export function produceExternalEvent(session: any, payload: any): void {
  session.append({ type: 'third-party/informational', payload })
}
```

## 3. Evidence basis and unconfirmed items

Decided on evidence, not the comment:

- **Evidence:** fixture `README.md` records the corridor as "DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01 remove-then-restore" and states "alpha.2 已恢复保留语义" / "the correct action is to delete this defense"; fixture `src/events.ts` shows the `delete` plus the stale keep-me comment; fixture `package.json` marks the material `"private": true`, test-only.
- **Unconfirmed (closed-book pack contains no host sources):** the precise alpha.1 reader rejection mechanism; whether alpha.2's restored semantics retain a producer-supplied marker verbatim or regenerate the envelope server-side. Neither affects the verdict: under alpha.2 the producer must not mutate the marker, and the public `Session.append(...)` surface gives it no parameter to do so anyway.

## Verdict

Delete the `delete (event as any).ignorable` line and its stale comment when migrating to alpha.2. Producers call `session.append(...)` with their event and never touch the `ignorable` envelope marker; the host owns retention semantics, and alpha.2's restored semantics (DSH-0.1.2-A2-01) make the alpha.1 defense both obsolete and harmful.
