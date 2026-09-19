# S6 · Corridor Net-State Judgment — Migration Diagnostic Report

**Mode**: A · inspect (read-only, per plugin-upgrade skill). The fixture was not modified; no dependencies installed, no builds, no network.
**Target host**: DSH `0.1.2-alpha.2` (source plugin written against the alpha.1 corridor).
**Corridor**: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (connected via the `from`/`to` metadata in `references/v0.1.2-alpha.1.md` and `references/v0.1.2-alpha.2.md`, never by filename order).

## 1. Fate of the defense code: DELETE

The defense in `src/events.ts` must be **deleted** when migrating to alpha.2. The code comment claiming that it must be kept when migrating to alpha.2 is wrong, and the skill's Mode C discipline mandates deciding by evidence and computing the **corridor net state**, not by a comment.

Evidence — the full history of the `ignorable` semantics across the corridor:

1. **Before alpha.1 (rc.2 and earlier)**: `SessionEvent.ignorable` existed. Third-party persisted informational events could carry `ignorable: true`; first-party readers could omit them on reload, while unknown events without the marker remained required-on-read.
2. **alpha.1 — removed (DSH-0.1.2-A1-02, breaking)**: card `v0.1.2-alpha.1.md` documents that "alpha.1 cannot preserve the `ignorable: true` marker on third-party informational events". The card's prescription for an alpha.1 target is explicitly **not** what this fixture does: "Temporarily stop writing that unknown persisted event, or switch to public event vocabulary ... If the final target is alpha.2 or later, first read DSH-0.1.2-A2-01 to compute the corridor net state; **do not delete the producer marker and then restore it**." So even at the alpha.1 snapshot the defense was a misapplied workaround: alpha.1's answer was to stop writing the event, not to `delete` a marker the runtime was already dropping.
3. **alpha.2 — restored (DSH-0.1.2-A2-01, fix)**: card `v0.1.2-alpha.2.md` states "now that alpha.2 restores it" and warns in its Symptoms: "**old adapters that keep dropping the marker will make first-party readers reject Sessions containing unknown events**". The fixture README confirms the chain: "The target alpha.2 restored the retention semantics (DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01 remove-then-restore) — **the correct action is to delete this defense**.".

**Net state**: the field was removed in an intermediate version and restored in the target. Per the skill's rule ("When a field is removed in an intermediate version and restored in the target, do not delete and re-add it"), the defense is net-zero at best and actively harmful on alpha.2: keeping it produces external events without `ignorable: true`, which alpha.2's first-party readers treat as **required-on-read unknown events** and reject on reload — the exact failure the alpha.2 card describes. The comment's predicted rejection ("without deleting the marker readers will reject it") described only the alpha.1 snapshot; on alpha.2 the polarity is inverted.

## 2. Correct producer semantics, and what an ordinary plugin via `Session.append(...)` should do

Per DSH-0.1.2-A2-01:

- **Marker meaning**: `ignorable: true` is a **producer-side declaration** that an informational event's semantics can be omitted by an old reader without affecting reconstruction. It is **not a consumer-side filtering directive**, and ignorable events remain in loaded events after reload.
- **Retention**: alpha.2 restores retention across the envelope / persistence / reload / transport layers: "JSONL, SQLite, API transports, and the generated catalog must preserve the field as-is; unknown events without the marker remain required-on-read." (Operator note from the same card: the SQLite provider accepts only schema 20 and rejects schema 19 and other schemas; back up/export or rebuild before upgrading.)
- **Ordinary plugin via the public API**: the card is explicit that "the public live `Session.append(...)` **still has no `ignorable` parameter**". An ordinary plugin that only calls `Session.append(...)` therefore: (a) cannot set the marker through that entry point; (b) must **not** fake it — the card says such plugins "should mark the producer seam as a capability gap **rather than faking a public entry via cast**". The fixture's `delete (event as any).ignorable` is the distorted mirror of exactly that mistake: it reaches past the public surface with an `as any` cast instead of acknowledging the gap.
- **Consequences for this fixture**: delete the `delete (event as any).ignorable` line and the misleading comment. With the defense gone, `produceExternalEvent` appends a plain third-party event through the public API; on alpha.2 it is persisted as a required-on-read unknown event unless the plugin owns an envelope/persistence seam that legitimately carries the marker. If the event truly is informational and must be omittable by old readers, record the capability gap (or move to a seam that owns the envelope) rather than casting.

## 3. Evidence basis and unconfirmed items

- The decision rests on the two corridor cards (DSH-0.1.2-A1-02, DSH-0.1.2-A2-01), their cited upstream primary sources (the alpha.2 decision note `2026-08-30-retain-ignorable-external-session-events.md` and the alpha.2 release notes), and the fixture README's own statement of the remove-then-restore chain — not on the in-code comment, which the README itself labels a trap ("社区注释（陷阱：alpha.2 已恢复保留语义，这段防御应当删除）").
- **Unconfirmed (closed-book limits)**: the exact alpha.2 public type signature of `Session.append` / `SessionEvent` could not be re-derived from packed declarations here (no network, no target-tag source in the pack); the statement that the public live API has no `ignorable` parameter is taken from card DSH-0.1.2-A2-01. Whether the surrounding plugin has a legitimate envelope/persistence seam is unverifiable from the fixture (only `README.md`, `package.json` (`dsh-events-bench` 0.1.0, `private: true`, ESM), and `src/events.ts` exist). Neither gap changes the verdict.

## Summary of recommended actions

1. **Delete** the `delete (event as any).ignorable` line and the misleading comment in `src/events.ts`.
2. Keep appending through the public `Session.append(...)`; do not cast to fake the marker.
3. If the event is genuinely omittable informational content and the plugin owns a persistence/envelope seam, set `ignorable: true` **only** at that seam; otherwise record the producer-seam capability gap.
4. Verify on a real alpha.2 host: an external event with the marker survives reload; an unknown event without the marker is rejected (fail closed); a plain `Session.append` path is not documented as supporting the field.
