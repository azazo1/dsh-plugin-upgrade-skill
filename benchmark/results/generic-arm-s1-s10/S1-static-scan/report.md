# S1 · Static Touchpoint Scan Report — legacy-plugin (dsh 0.1.1 era → 0.1.2-alpha.2)

**Scan mode:** read-only. No file under the fixture directory was modified, added, or deleted; nothing was executed or installed. The fixture cannot be compiled by design; this report is a static coupling inventory only.

**Methodology:** framework-agnostic migration procedure — inventory the coupling surface per category, record file/line and confidence for every hit, classify each upstream change by net state across the release corridor, and mark everything that cannot be determined from the given materials as *undetermined* rather than guessed.

**Materials scanned (complete file list of the fixture):**

| File | Role |
|---|---|
| `package.json` | manifest / metadata |
| `cordis.patch.yml` | profile composition + patch declaration |
| `patch.yml` | source-patch surface declaration |
| `scripts/apply-patch.mjs` | patch applier + headless-CLI probe |
| `src/index.ts` | plugin activation entry (all runtime coupling) |
| `README.md` | fixture's own touchpoint table (used as a cross-check, not as ground truth) |

---

## 1. Per-category results

### Touchpoint #1 — Source patch: **HIT**

- `patch.yml:2-6` — declares a patch `surface` targeting host source file `src/session/view/SessionView.ts`, with a string replacement `export function renderSessionView` → `export function renderSessionViewPatched`. This is a **text-level patch against a host source file by path and content**: it couples to (a) the host's internal file layout, (b) the exact source text of the target line, (c) the host's patch-application mechanism.
- `cordis.patch.yml:2-6` — profile composition entry `id: legacy-plugin` with `patch: [patch.yml]`, wiring the patch surface into the profile.
- `scripts/apply-patch.mjs:1-9` — reads `patch.yml` and applies it against a host source tree located via the `DSH_HARNESS_SOURCE_ROOT` environment variable; couples to that env-var contract and to the patch file format.
- `package.json:6-8` — `"apply-patch": "node scripts/apply-patch.mjs"` script wiring.

**Coupling nature:** any host-side change to the patched file's path, its content near the anchor string, the patch declaration format, or the harness env-var contract breaks this touchpoint — usually silently (a no-op patch) rather than with an error. Confidence: high (explicit declarations).

### Touchpoint #2 — Events: **HIT**

- `src/index.ts:15-19` — **producer** of a durable event: `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: { text: 'fixture' } })`. Couples to the event channel name `session/event`, the event envelope shape, and specifically the **`ignorable` marker field** on an external informational event.
- `src/index.ts:20-22` — **consumer**: `ctx.on('session/event', ...)` logging `event.type`. Couples to the same channel and envelope on the receive path.

**Coupling nature:** the producer's use of `ignorable: true` sits exactly on a corridor-folded change (see §2). The consumer only reads `event.type` and is the lower-risk side, but shares the channel-name coupling. Confidence: high.

### Touchpoint #3 — Service / Remote: **HIT**

- `src/index.ts:25-28` — command handler `rename-session` obtains the host API proxy via `ctx.get('apiProxy')` and calls `apiProxy.invoke('session.rename', { id, title })`.
- `src/index.ts:29-32` — command handler `list-providers` does `ctx.get('apiProxy')` and `return apiProxy.invoke('llm.providers')`.

**Coupling points:** the service locator key `'apiProxy'`; the RPC method names `session.rename` and `llm.providers`; their request payload shape (`{ id, title }`) and (for `llm.providers`) the response shape that is returned verbatim to callers. Any rename, removal, signature change, or auth/permission change on the proxy service or those two methods breaks this touchpoint. Confidence: high on the coupling locations; the exact upstream status of these two method names is **not determinable from the given materials**.

### Touchpoint #4 — Host directory / filesystem: **HIT**

- `src/index.ts:35-38` — handler `write-note` builds a hard-coded path `join(homedir(), '.dsh', 'profiles', 'default')` (`src/index.ts:36`) and writes `legacy-note.txt` into it (`src/index.ts:37`).

**Coupling points:** the host's on-disk profile directory layout (`~/.dsh/profiles/<profile>/`), the assumption that a profile named `default` exists and is writable, and the absence of any host-provided API for locating the profile directory. Any change to the profile directory scheme, per-profile layout, or write permissions breaks this silently (wrong location) or loudly (ENOENT/EACCES). Confidence: high.

### Touchpoint #5 — UI / commands / tools: **HIT**

- `src/index.ts:10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'`: a deep import from a **private/internal subpath** of a host UI package. The inline comment states this path was "removed by UI decomposition" — i.e. this module specifier no longer resolves at the target version.
- `src/index.ts:41-43` — `ctx.contributes.registerCommand('legacy.openView', () => new SessionView({ enhanced: true }))`: couples to the command-contribution API (`ctx.contributes.registerCommand`) and to `SessionView`'s constructor options (`{ enhanced: true }`).

**Coupling points:** (a) the internal module specifier (load-time coupling — the plugin will fail at import/activate time, not at call time); (b) the command registration surface; (c) the component's constructor contract. Confidence: high that the import is a collision; the exact public replacement (if any) is **not determinable from the given materials**.

### Touchpoint #6 — Custom channel: **HIT**

- `src/index.ts:47-54` — `startLegacyBridge()` creates a plain HTTP server (`node:http`) listening on `127.0.0.1:43121` (line 51) answering every request with `'legacy'`; the comment marks the intended route `http://localhost:43121/api/legacy` and states it "bypasses the Host Gateway authentication model". The function is defined but never invoked (`void startLegacyBridge`, line 54) — the fixture is static-only.

**Coupling points:** a private loopback channel with a fixed port (collision risk), an unauthenticated request/response path that assumes host APIs are reachable without the gateway's auth model, and a route convention (`/api/legacy`). If the target version hardens the gateway or removes unauthenticated access to whatever this bridge fronts, the channel dies even though the code never crashes at scan time. Confidence: high on the coupling; the concrete gateway-side change is **not determinable from the given materials**.

### Touchpoint #7 — Subprocess / output parsing: **HIT (two sites)**

- `src/index.ts:57-67` — handler `headless-ask` spawns `dsh --profile headless <prompt>` and parses **each stdout chunk as one JSON object** (`JSON.parse(line.toString())`, line 62), expecting `{ type: 'final', text }`.
- `scripts/apply-patch.mjs:12-18` — `execFileSync('dsh', ['--profile', 'headless', 'ping'])`, then splits stdout on `\n` and `JSON.parse`s each line, again expecting `{ type: 'final', text }`.

**Coupling points:** the headless CLI's argv shape (`--profile headless`), its stdout **format**, and the event schema within that format. Both sites carry the *deliberately wrong wrapper assumption* (stated in the fixture's own comments): the target version's headless stdout is **final text, not JSONL**. Consequences differ per site: `apply-patch.mjs` parses per line and would throw on the first non-JSON line; `src/index.ts` parses per `data` *chunk* (not even per line), so it would have been fragile under the old format too and is doubly broken now. Confidence: high — the format change is stated in the fixture itself; the exact new output contract (plain text only? trailing newline? exit-code semantics?) is **not determinable from the given materials**.

---

## 2. Mapping hits to corridor change cards (0.1.1-rc.2 → 0.1.2-alpha.2)

**Honest limitation, stated plainly:** I do not have the upstream change-card list (the `A1-…`-style card IDs, the per-version changelog, or migration notes for this corridor). Inventing card IDs or mapping guesses would be worse than no mapping, so per-card IDs are **not determinable from the given materials**. What I can do — and do below — is (a) map each hit to a *described* corridor change where the fixture itself documents one, (b) mark hits where the card must be looked up, and (c) apply the corridor net-state (folding) rule where intermediate-version information is available.

### 2.1 Changes documented by the fixture itself

| Hit | Corridor change (as documented in fixture comments) | Net-state classification |
|---|---|---|
| #2 producer, `src/index.ts:15-19` | The `ignorable` marker on external informational events was **removed in an intermediate version (alpha.1)** and its **producer/persistence contract restored in the target (alpha.2)** | Per the folding rule: removed-then-restored ⇒ **zero net change**. Do **not** migrate the field away; keep `ignorable: true`. Classify as **behavioral / re-verify**: confirm at runtime that the restored contract really persists and marks these events as before (restore of a producer contract does not guarantee the consumer/rendering side is identical), but no code edit is indicated by the corridor alone |
| #5 internal import, `src/index.ts:10` | The private host/web-client path behind `@deepseek-ai/dsh-session-view/internal` was **removed by UI decomposition** | **Breaking (must edit):** load-time failure. Replacement symbol/subpath unknown — must be read from the upstream changelog or target-version source, not guessed |
| #7 both sites | Headless-mode stdout changed from **JSONL events to final text** | **Breaking (must edit):** both parsers must be rewritten (line-chunk JSON parsing → capture final text; also fix the per-`data`-chunk parsing in `src/index.ts` regardless). Also **behavioral:** exit-code/stderr semantics must be re-verified once known |

### 2.2 Hits whose card mapping requires the upstream card list

The following hits are real couplings, but whether a corridor change touches them — and which card ID carries it — **cannot be determined without the upstream changelog/card set for 0.1.1-rc.2 → 0.1.2-alpha.2**:

- #1 source-patch surface (`patch.yml`, `cordis.patch.yml`, `scripts/apply-patch.mjs`): need cards covering host source layout of `src/session/view/SessionView.ts`, the patch declaration format, and the harness env-var contract.
- #3 `apiProxy` + methods `session.rename` / `llm.providers` (`src/index.ts:25-32`): need cards covering the service locator and the Remote method registry.
- #4 hard-coded `~/.dsh/profiles/default` (`src/index.ts:35-38`): need cards covering the host's profile directory layout.
- #5 command registration `ctx.contributes.registerCommand` (`src/index.ts:41`): need cards covering the command-contribution API (distinct from the internal-import card, which is confirmed breaking).
- #6 loopback bridge (`src/index.ts:47-54`): need cards covering the host gateway's authentication model and any loopback/port policy.

### 2.3 How I would obtain and verify the card mapping (procedure)

1. Acquire the upstream changelog / release notes / migration-card set for **every version in the corridor, inclusive** (0.1.1-rc.2, all intermediates, 0.1.2-alpha.2) — never just the endpoints.
2. Build a net-state table: fold removed-then-restored fields to no-op (as done for `ignorable` above); collapse multi-step renames A→B→C to A→C; list behavior changes (defaults, ordering, output formats) alongside API removals.
3. Classify each card as breaking / behavioral / additive / informational, then join inventory hits (§1) to cards by coupling surface (module specifier, service key, method name, path, channel, CLI format).
4. Where a card's one-line description is ambiguous about semantics, read the upstream source at the target tag rather than guessing shapes.
5. Record the join in a migration log: hit → card ID → classification → required edit or re-verification.

---

## 3. Categories with no hits

**None.** All seven categories hit. The scan covered every file in the fixture (full list at the top), so "no empty category" is a statement about this six-file fixture, not about omitted files.

However, "every category hit" must not be read as "the inventory is provably complete", for three reasons:

1. **Manifest-level gaps are invisible couplings.** `package.json` declares no compatibility range, no peer/shared dependency on the host, no engines floor. That is not "no coupling" — it is *undeclared* coupling: the host may refuse to load or duplicate shared packages, and nothing in the manifest would say so. I cannot rule out shared-dependency duplication risk from a static scan of these files.
2. **Load-time vs call-time.** The #5 internal import (line 10) is a load-time coupling and would fail first; couplings behind it (e.g. #6's never-invoked bridge) would only surface after #5 is fixed. A static scan lists them all, but cannot tell which failure masks which at runtime.
3. **What static scan cannot see at all:** runtime-only behavior (event ordering, timing, gateway auth handshakes, actual headless output bytes), and any coupling in host-generated artifacts the plugin consumes but that are not present in this fixture. Each of these needs the layered verification ladder — static → install-time → cold start → functional probe → data → rollback — before "scanned clean" means anything.

---

## 4. Summary table

| # | Category | Hit? | Location(s) | Known corridor status |
|---|---|---|---|---|
| 1 | Source patch | Yes | `patch.yml:2-6`, `cordis.patch.yml:2-6`, `scripts/apply-patch.mjs:1-9`, `package.json:6-8` | Card lookup required |
| 2 | Events | Yes | `src/index.ts:15-19` (producer), `20-22` (consumer) | `ignorable` removed in alpha.1, restored in alpha.2 → **net: no change; re-verify** |
| 3 | Service/Remote | Yes | `src/index.ts:25-32` (`apiProxy`, `session.rename`, `llm.providers`) | Card lookup required |
| 4 | Host directory | Yes | `src/index.ts:35-38` (`~/.dsh/profiles/default`) | Card lookup required |
| 5 | UI/commands/tools | Yes | `src/index.ts:10` (internal import — **breaking**, removed by UI decomposition), `41-43` (`registerCommand`) | Import: confirmed breaking; command API: card lookup required |
| 6 | Custom channel | Yes | `src/index.ts:47-54` (loopback `127.0.0.1:43121`, `/api/legacy`) | Card lookup required (gateway auth model) |
| 7 | Subprocess/output parsing | Yes | `src/index.ts:57-67`, `scripts/apply-patch.mjs:12-18` | **Breaking:** headless stdout is final text, not JSONL |

**Read-only attestation:** this report was produced without modifying, adding, renaming, or deleting any file in the fixture, and without executing any fixture code.
