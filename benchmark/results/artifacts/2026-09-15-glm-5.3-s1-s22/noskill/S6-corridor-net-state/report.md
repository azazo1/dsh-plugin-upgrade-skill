# S6 · Corridor Net-State Judgment — Migration Report (alpha.1 → alpha.2)

**Verdict: the defense code must be DELETED.** The comment's claim ("readers will reject the marker; keep this when migrating to alpha.2") is wrong for alpha.2 and describes only the alpha.1 anomaly. Keeping the code is worse than dead weight: as intended it would strip the exact safety marker alpha.2 relies on.

## Evidence base

- Fixture (read-only, unchanged): `fixture/src/events.ts`, `fixture/README.md`, `fixture/package.json`.
- Local alpha.2 build inspection (read-only): `@deepseek-ai/dsh-session` (`lib/types/types.d.ts`, `lib/types/known-event-types.d.ts`, `lib/types/index.d.ts`, `lib/index.js`, `lib/surface.js`) and `@deepseek-ai/dsh-session-persistence` (`lib/index.js`, README).
- Closed-book constraint honored: no network, no fixture modification, no environment built.

## 1. Fate of the defense code across the version corridor

Corridor semantics of `SessionEvent.ignorable` (envelope-level marker, distinct from `SESSION_FORMAT_VERSION` structural bumps):

| Stage | Semantics | Source |
|---|---|---|
| pre-alpha.1 | `ignorable` is the compatibility mechanism for unknown/third-party event types | alpha.2 docs (below) |
| alpha.1 (DSH-0.1.2-A1-02) | `ignorable` temporarily removed; a third-party persistent event carrying the marker could be refused, so producers deleted it defensively | fixture comment + fixture README (IDs attested only by fixture — otherwise **unconfirmed**) |
| **alpha.2 (target, DSH-0.1.2-A2-01)** | **Retention semantics restored** (remove-then-restore). `ignorable` is back and is *the* mechanism for out-of-repo plugin events | fixture README; confirmed against the installed alpha.2 build |

Independent alpha.2 build evidence (not just the comment):

- `SessionEvent.ignorable?: true` exists on the envelope (`dsh-session/lib/types/types.d.ts:478`) with the contract: absent means **required**; a reader meeting an unrecognized type without the marker MUST refuse reconstruction rather than silently drop it; a writer sets `true` **only on purely informational records whose loss cannot affect reconstruction**.
- The persistence reader fails closed: `dsh-session-persistence/lib/index.js:184` throws `SessionFormatUnsupportedError` for an event type outside `KNOWN_SESSION_EVENT_TYPES` **unless** `ignorable === true`. Event-name registration was explicitly rejected as a substitute; the persisted marker is the compatibility mechanism (`known-event-types.d.ts`, citing the retained-decision note `2026-08-30-retain-ignorable-external-session-events.md` — "retain").
- The surface fold treats unknown ignorable records as opaque, never changing the model-visible surface (`dsh-session/lib/surface.js:180`).

Consequences for the fixture code:

1. **The defense is counterproductive in alpha.2.** `third-party/informational` is outside the known vocabulary, and the type name itself declares the event informational. Stripping `ignorable` makes it *required*, so any build that does not know the type refuses the entire log with `SessionFormatUnsupportedError` — exactly the failure the marker exists to prevent. The correct producer behavior is the opposite of the comment: an informational third-party event should **carry** `ignorable: true`.
2. **As written it is also a runtime no-op**: the object literal `{ type, payload }` never defines `ignorable`, so `delete (event as any).ignorable` deletes nothing. Its only live effect is the misleading comment and the risk that a future edit starts actually stripping a real marker.
3. Migration action: remove the `delete` line and its comment. Do not "keep it for safety" — alpha.2's reader semantics make the marker mandatory for skippable third-party records.

## 2. Correct producer semantics and what `Session.append(...)` callers should do

Producer rule (alpha.2 envelope contract): set `ignorable: true` only on purely informational records whose loss cannot affect reconstruction; every other event is required-by-default (absent marker). Required unknown events over-refuse (an inconvenience), never silently gut a session.

For an **ordinary plugin going through `Session.append(...)`**: do nothing about `ignorable` — and indeed it cannot. The public signature is

```ts
append<T extends SessionEventType>(type: T, data: SessionEventMap[T],
  ...opts: T extends SurfaceEventType ? [opts: SurfaceIntent<T>] : []): SessionEvent<T>
```

(`dsh-session/lib/types/index.d.ts:238` / implementation `lib/index.js:1170`). There is **no whole-event parameter and no `ignorable` parameter**: the harness constructs the envelope itself (`type`, `seq`, `time`, `data`, plus surface metadata only), validates it, and freezes it. Third-party vocabulary enters through declaration merging into `SessionEventMap`, not by passing raw envelopes.

The fixture's call `session.append(event)` does not match this API — it passes a whole event object where `(type, data)` is expected (**unconfirmed** what the plugin's actual session handle is in alpha.1; if alpha.1 accepted raw envelopes, that call shape itself needs migration to `(type, data)`).

**Unconfirmed / closed-book limits:**

- The corridor IDs `DSH-0.1.2-A1-02` / `DSH-0.1.2-A2-01` and the alpha.1 removal are attested only by the fixture's own README/comment; I could not verify alpha.1 artifacts directly.
- The precise alpha.2 channel by which an out-of-repo informational event acquires the persisted `ignorable: true` marker (append never stamps it and I found no stamping in the persistence writer) is **unconfirmed** from the installed build alone; it may be an envelope-level writer concern outside `Session.append`. Either way it is harness-owned, not something the plugin deletes or sets by hand.

## 3. Bottom line

- **Delete** the `delete (event as any).ignorable` defense and its comment when migrating to alpha.2.
- Informational third-party events should be *marked* `ignorable`, never unmarked; the marker is the restored alpha.2 compatibility mechanism and readers fail closed without it.
- Plugins using `Session.append` touch no envelope fields at all — `ignorable` is not part of that API surface.
