# S1 Static Touchpoint Scan

## Scope and method

Scanned read-only:

- `/app/fixture/README.md`
- `/app/fixture/package.json`
- `/app/fixture/cordis.patch.yml`
- `/app/fixture/patch.yml`
- `/app/fixture/src/index.ts`
- `/app/fixture/scripts/apply-patch.mjs`

The fixture was not executed. No installation, migration, publication, or external access was performed. The fixture has no git diff after the scan.

The corridor card IDs below use the seven touchpoint cards in order: `A1-01` through `A1-07`. The event mapping applies the target-version net state: alpha.1's intermediate removal of the ignorable marker is folded away because alpha.2 restores the producer/persistence contract.

## Summary

| Touchpoint | Hit? | Corridor card | Hit files/lines |
|---|---|---|---|
| #1 Source patch | Yes | `A1-01` | `cordis.patch.yml:1-6`; `patch.yml:1-6`; `scripts/apply-patch.mjs:5-9` |
| #2 Events | Yes | `A1-02` | `src/index.ts:13-22` |
| #3 Service/Remote | Yes | `A1-03` | `src/index.ts:24-32` |
| #4 Host directory | Yes | `A1-04` | `src/index.ts:34-38` |
| #5 UI/commands/tools | Yes | `A1-05` | `src/index.ts:9-10, 40-43` |
| #6 Custom channel | Yes | `A1-06` | `src/index.ts:45-54` |
| #7 Subprocess/output parsing | Yes | `A1-07` | `src/index.ts:56-67`; `scripts/apply-patch.mjs:11-19` |

## Detailed findings

### #1 Source patch — hit — `A1-01`

Files and lines:

- `cordis.patch.yml:1-6` declares the plugin patch composition and includes `patch.yml`.
- `patch.yml:2-6` declares a source surface targeting `src/session/view/SessionView.ts` and performs an exact textual replacement from `renderSessionView` to `renderSessionViewPatched`.
- `scripts/apply-patch.mjs:5-6` requires `DSH_HARNESS_SOURCE_ROOT`, but does not use its value; `:8-9` reads `patch.yml` from the process working directory and prints it.

Concrete coupling: the plugin depends on the old patch declaration format/surface, the old internal target path, and the old exact symbol text. Its helper also assumes a particular harness environment variable and current working directory. These are source-patch touchpoints for `A1-01`.

### #2 Internal/persistent events — hit — `A1-02`

File and lines: `src/index.ts:13-22`.

Concrete coupling:

- `ctx.emit('session/event', ...)` produces an external informational event with type `legacy/informational-note`.
- The payload includes `ignorable: true` and a `payload` object (`:15-19`).
- `ctx.on('session/event', ...)` consumes the event and assumes a `SessionEvent`-shaped object with `.type` (`:20-22`).

Corridor folding: the source comment records that alpha.1 removed the ignorable marker and alpha.2 restored its producer/persistence contract. The relevant target-state mapping is therefore `A1-02` for the event producer/consumer and persistence contract, including the final restored marker; it is not treated as a lasting alpha.1 removal.

### #3 Internal service/Remote — hit — `A1-03`

File and lines: `src/index.ts:24-32`.

Concrete coupling:

- The `rename-session` handler obtains the legacy Host service with `await ctx.get('apiProxy')` (`:25-27`) and calls `apiProxy.invoke('session.rename', { id, title })`.
- The `list-providers` handler repeats the `ctx.get('apiProxy')` lookup (`:29-31`) and calls `apiProxy.invoke('llm.providers')`.

This is direct dependency on the legacy `apiProxy` service name, lookup shape, and invoke-based Remote method names. It maps to `A1-03`.

### #4 Host filesystem/directory — hit — `A1-04`

File and lines: `src/index.ts:34-38`.

Concrete coupling:

- Imports `homedir()` and `join()` (`:5-6`).
- Constructs the fixed host/profile path `~/.dsh/profiles/default` (`:36`).
- Writes directly to `legacy-note.txt` with `writeFileSync` (`:37`).

The plugin assumes host ownership and stability of a particular profile directory and bypasses an abstracted host storage boundary. This maps to `A1-04`.

### #5 UI/commands/tools — hit — `A1-05`

File and lines: `src/index.ts:9-10, 40-43`.

Concrete coupling:

- Imports the private UI path `@deepseek-ai/dsh-session-view/internal` (`:10`), explicitly identified as a path removed by UI decomposition (`:9`).
- Registers `legacy.openView` through `ctx.contributes.registerCommand` and directly constructs `new SessionView({ enhanced: true })` (`:40-43`).

This couples the plugin to a private UI module and the old command/contribution registration surface. It maps to `A1-05`.

### #6 Custom channel — hit — `A1-06`

File and lines: `src/index.ts:45-54`.

Concrete coupling:

- Creates a private HTTP server with `createServer` (`:47-49`).
- Binds a fixed loopback port and address, `43121` on `127.0.0.1` (`:51`).
- Documents the unregistered `/api/legacy` endpoint (`:51`) and returns a raw response (`:49`).
- The code explicitly bypasses the Host Gateway authentication model (`:45`); `void startLegacyBridge` keeps the bridge definition present even though it is not invoked.

This is a custom out-of-band channel rather than a Host Gateway channel, with fixed endpoint/network assumptions and no Gateway authentication integration. It maps to `A1-06`.

### #7 Subprocess/output parsing — hit — `A1-07`

Files and lines:

- `src/index.ts:56-67` spawns `dsh --profile headless`, reads `child.stdout` data chunks, converts each chunk to text, and immediately calls `JSON.parse` (`:59-63`), looking for a `final` event.
- `scripts/apply-patch.mjs:11-19` makes the same incompatible assumption for synchronous headless output: it treats final text as newline-delimited JSON, splits on `\n`, parses every nonblank line, and looks for `event.type === 'final'`.

Concrete coupling: both wrappers assume headless stdout is JSONL event output. The fixture identifies the target behavior as final text, so the parse strategy and `final` event contract are stale. The async wrapper also assumes each `data` callback is one complete logical line. This maps to `A1-07`.

## No-hit requirement

There are no no-hit categories: all seven requested categories have positive static evidence above. Accordingly, there are no files to list as ruled out for a no-hit category.

The scanned file set was the complete fixture file set listed in the scope section. Even for a category with no textual match, a static no-hit result would not prove “no problem”: runtime registration can be indirect, dependencies can carry the coupling, configuration can be interpreted by the host, and behavior can depend on dynamic values or protocol responses. This report is therefore a static touchpoint inventory, not an executable compatibility verdict.
