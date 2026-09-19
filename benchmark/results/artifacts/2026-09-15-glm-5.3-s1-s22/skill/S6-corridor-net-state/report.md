# S6 · Corridor Net-State Judgment — Read-Only Migration Report

**Task**: analyze the fixture plugin's alpha.1-era "defense code" (pre-emptive `delete (event as any).ignorable` before a third-party persistent event write) against the target host **dsh-v0.1.2-alpha.2**, read-only.

**Mode**: A · inspect (read-only). No file under the fixture was modified; no build/install/mount was performed (the brief forbids creating a reproduction environment).

## Evidence base

- Fixture: `fixture/src/events.ts` (`produceExternalEvent`), `fixture/package.json` (`dsh-events-bench@0.1.0`, private, no DSH dependency declared), `fixture/README.md`.
- Skill corridor cards, connected by from→to metadata, not filename order:
  - DSH-0.1.2-A1-02 (`references/v0.1.2-alpha.1.md`) — `SessionEvent.ignorable` temporarily removed in alpha.1.
  - DSH-0.1.2-A2-01 (`references/v0.1.2-alpha.2.md`) — alpha.2 restores `ignorable` retention semantics for third-party persisted events (revert of A1-02).
  - API-05 (`references/api-migration-0.1.2-alpha.2.md`) — the field is restored on the **envelope/persistence/reload/transport**, but the public `Session.append()` still has no `ignorable` parameter.
- Pre-existing baseline: **not collected** (Mode A read-only; the brief forbids running package scripts/builds).

## 1. Fate of the defense code: **DELETE** (do not keep)

Corridor net state of the `ignorable` semantics, computed across the full edge chain (Mode C rule: read the whole corridor and compute the final net state; a field removed in an intermediate version and restored in the target is net-present — do not delete and re-add):

| Corridor edge | State of `SessionEvent.ignorable` | Card |
|---|---|---|
| ≤ rc.2 | Present on the event envelope | — |
| rc.2 → alpha.1 | **Removed**. alpha.1 cannot preserve the marker on third-party informational events; first-party readers treat unknown persisted events as required and reject the reload | DSH-0.1.2-A1-02 |
| alpha.1 → alpha.2 | **Restored** (revert of A1-02). Envelope/persistence/reload/transport keep the marker; unknown events **with** `ignorable: true` remain in loaded events after reload and old readers may omit their semantics; unknown events **without** the marker remain required-on-read (fail closed) | DSH-0.1.2-A2-01 |

Reasons the defense must go, decided by evidence rather than by the comment:

1. **The comment's premise is inverted for alpha.2.** It claims "without deleting the marker readers will reject it, so keep this when migrating to alpha.2." A2-01 says the opposite: adapters that keep *dropping* the marker are exactly what makes first-party readers reject sessions containing unknown events on alpha.2. The comment is a trap.
2. **The defense is a mechanical no-op as written.** The event literal `{ type: 'third-party/informational', payload }` never carries an `ignorable` property, so `delete (event as any).ignorable` deletes nothing. Its only real effect is to document and canonize the wrong alpha.1 behavior, plus it requires an `as any` cast — a migration smell per the precision checklist.
3. **The alpha.1-only rationale never applied to this producer anyway.** A1-02's recipe targets *final target = alpha.1*; for a final target of alpha.2 the card explicitly says to read A2-01 and compute the corridor net state first. A defense written for a removed-in-alpha.1 field has no reason to exist on a target where the field is restored.
4. The code is dead weight in the net state: deleting the `delete` line (and its comment) leaves behavior identical on alpha.2 while removing the false claim.

## 2. Correct producer semantics on alpha.2

- `ignorable: true` is a **producer-side omission-safety marker on the event envelope**, not a consumer-side filtering directive. It may be set only for informational events whose semantics a reader without the plugin can omit without affecting session reconstruction; the event still remains in loaded events after reload. Unknown events lacking the marker are required and fail closed.
- **What an ordinary plugin going through `Session.append(...)` should do: nothing — it cannot set the field.** The public live `Session.append()` on alpha.2 accepts only `type`, `data`, and `SurfaceIntent` (surface events only); it does not write `ignorable` into the event. Per API-05:
  - an out-of-repo custom event type can live-append and persist fine, yet throw `SessionFormatUnsupportedError` on the next **cold load**, refusing to restore the whole session — a silent-write/loud-read trap that a live smoke cannot catch;
  - it **cannot be bypassed** with casts, `delete`, object thawing, or hand-editing JSONL;
  - the correct alpha.2 pattern for out-of-repo plugins is to **not persist plugin state via custom `SessionEventMap` + `Session.append()`** — use a plugin-owned sidecar/store keyed by session id instead;
  - persistence/transport owners must preserve existing markers end-to-end (JSONL, SQLite, API transports, generated catalog), and the SQLite provider accepts only schema 20 (rejects 19, no auto-migrate).
- Concretely for this fixture: after deleting the defense, the remaining `session.append(event)` pattern itself is the larger problem. The code also passes a non-standard envelope shape (`{ type, payload }` as one object); the alpha.2 `append` signature is `(type, data, SurfaceIntent?)` — exact current signature **unconfirmed** against the target tag source (closed-book brief; only the ledger's statement was available). Since the event is informational third-party state, the recommendation is to move it out of the session log entirely (sidecar store) until upstream ships a supported `append(..., { ignorable: true })` or an equivalent formal mechanism.

## Skill report structure

- **pre-existing**: not collected (Mode A read-only).
- **Completed**: corridor net-state analysis of `ignorable` (≤rc.2 present → alpha.1 removal → alpha.2 restore); verdict on the defense code (**delete**); correct producer semantics and the `Session.append` capability gap; evidence cited from cards A1-02, A2-01, and API-05.
- **Skipped**: touchpoint classes other than #2 (events) — the fixture is a single `src/events.ts` with no UI/commands/subprocess/host-FS/channel surface; runtime cold-load reproduction — forbidden by the brief; migration planner script — unnecessary for a one-file fixture.
- **Pending/residual risk / unconfirmed**:
  - The exact alpha.2 `Session.append` parameter list is taken from the API ledger (API-05), not verified against the target tag source — closed-book brief; marked **unconfirmed**.
  - Whether any later corridor edge ships a public `ignorable` write surface was not verified beyond the alpha.2 cards (the fixture's target corridor ends at alpha.2).
  - Cold-load failure of this exact event was reasoned from the cards, not reproduced.
- **Rollback**: n/a — read-only analysis; nothing was changed anywhere.
- **Recommendations**: (1) delete the `delete (event as any).ignorable` line and its comment when migrating to alpha.2; (2) stop persisting third-party state via `Session.append` — use a session-id-keyed sidecar store; (3) re-evaluate a supported third-party persistent-event surface only after upstream ships a formal `ignorable` write mechanism; (4) remove `any` casts when the seam is redesigned.
