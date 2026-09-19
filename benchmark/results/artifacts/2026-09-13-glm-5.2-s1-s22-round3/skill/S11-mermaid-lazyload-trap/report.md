# S11 · Mermaid Lazy-Load Trap — Diagnosis Report (Read-Only, Mode A)

Plugin: `@org/dsh-attach-input` v0.4.0 (community Web plugin, lib-only bundle).
Task: derive root causes for three rollout incidents from the static evidence pack and convert them into concrete fixes plus regression coverage. No files outside the report directory were written; the fixture was only read.

## Evidence consulted

- `fixture/chunk-route.ts` — attempt-2 host prefix route serving the plugin `lib/` dir
- `fixture/console-split-chunks.txt` — attempt 1: entry chunk 200, sibling chunks 404
- `fixture/console-403-windows.txt` — attempt 2: 403 on Windows production host
- `fixture/ci-note.md` — environment matrix plus the printed `LIB_DIR` / `realpath` values

---

## 1 · Incident 1 — why the split-chunk approach failed

**Observation.** The entry chunk `mermaid-chunk.js` loads (200, 8.1 kB), then the browser 404s on `src-BfvxrPJe.js` and `pie-WAS4IAKB-CQHCQWWM.js`, and the whole dynamic import rejects with `TypeError: Failed to fetch dynamically imported module`. The fixture note is decisive: the shipped `lib/` contained `mermaid-chunk.js` but **not** the 97 sibling files its import statements reference.

**Mechanism.** A dynamic `import()` of a large module graph does not load one file. The bundler (Rollup/Vite/esbuild class) splits the graph into an entry chunk plus sibling chunks — here mermaid's per-diagram dialect modules (pie, flowchart, etc., hence names like `pie-*.js`). The entry chunk contains *static* relative-import statements (`import "./pie-WAS4IAKB.js"`) whose specifiers resolve against the **served chunk URL**, not against the original source tree. Two independent failure modes combine:

1. **Shipped-asset mismatch.** Only the hand-picked entry chunk was copied into the published package; the sibling chunks the bundler emitted alongside it were not shipped. Any one missing sibling makes the browser abort the *entire* module instantiation — a module graph is all-or-nothing, so one 404 fails the original `import()` even though the entry file itself returned 200.
2. **Route surface mismatch.** Even if shipped, the route's prefix and its `.m?js` filter must cover every sibling's URL; anything else the bundler emits (other extensions, nested paths) is invisible to a hand-maintained file list.

**Build-side fix.** Make the lazily-imported artifact *self-contained*: configure the bundler to emit exactly one file for the lazy entry — Rollup/Vite `output.inlineDynamicImports: true` (or a dedicated single-file lib-mode build / esbuild `--bundle` with splitting disabled) — so `import()` fetches one URL with no sibling specifiers. That is what attempt 2 correctly did. The general rule: either inline everything into one chunk, or ship the bundler's **complete emitted asset manifest** (all chunks plus hashed assets) and let the route serve that whole directory — never hand-pick a subset of a split graph.

## 2 · Incident 2 — the exact flaw in the containment guard

The guard (both checks):

```ts
const abs = normalize(join(LIB_DIR, rel))
if (!abs.startsWith(LIB_DIR + sep)) → 403          // check A: string prefix, lexical
file = normalize(realpathSync(abs))
if (!file.startsWith(LIB_DIR + sep)) → 403          // check B: realpath result vs NON-realpath base
```

**Mechanism.** Check B compares a `realpathSync` result against `LIB_DIR`, which was produced by `normalize(fileURLToPath(...))` — a purely *lexical* path that still carries whatever drive-letter case the runtime string happened to have. On Windows, `fs.realpathSync` (libuv) returns the canonical drive letter in **lowercase** — on this host `E:` goes in and `e:` comes out, exactly as the CI-note debug print shows:

```
LIB_DIR  = "E:\\dsh\\...\\lib"
realpath = "e:\\dsh\\...\\lib\\mermaid-chunk.js"
```

`String.startsWith` is case-sensitive, so the `e:` path never starts with the `E:` base and check B rejects every request with 403 — including paths plainly inside `lib/`. Per-platform behavior:

| Platform | realpathSync vs lexical base | Result |
|---|---|---|
| Linux CI | no drive letters; realpath returns the identical string (same case, same separators) | check B passes — green |
| Windows laptop, `c:` already lowercase in the tooling | realpath's lowercase drive matches by luck | passes |
| Windows Server, `E:` uppercase | realpath lowercases the drive → case mismatch | **403 on every chunk** |

So it is not 'Windows is unreliable': it is **comparing a canonicalized path against a non-canonicalized base with a case-sensitive string operation**. Windows drive-letter case is not stable across `normalize`/`fileURLToPath` versus `realpathSync`, and NTFS is case-insensitive anyway, so any case-only difference denotes the very same directory.

(Check A is latent-buggy too — it shares the case-sensitivity weakness and should be replaced together.)

## 3 · Fix direction for the guard + the other serving requirement

**Fix: canonicalize both sides and compare structurally, not lexically.**

```ts
const REAL_LIB_DIR = realpathSync(LIB_DIR)              // canonicalize the base once at startup
// per request:
const file = realpathSync(abs)                          // already canonical
const relFromBase = relative(REAL_LIB_DIR, file)
if (relFromBase === '' || relFromBase.startsWith('..') || isAbsolute(relFromBase)) → 403
```

Why robust on both platforms: `path.relative` compares *within one canonical form* (both sides went through `realpathSync`, so drive-letter case, 8.3 short names, symlinks, and separator style are already resolved); escape is detected structurally (`..` or absolute result) rather than by string prefix. The symlink-escape protection of the original check B is preserved: a symlink inside `lib/` pointing outside resolves to a path whose `relative` result starts with `..`. On Windows additionally compare case-insensitively (or rely on both sides being realpath output, which is stable).

**Other serving requirement:** the response must carry a **JavaScript MIME type**. The route already sets `content-type: application/javascript; charset=utf-8`, and that is not optional: module scripts (`import()`) are subject to strict MIME checking, so a 200 response with `text/plain`, `application/octet-stream`, or no Content-Type makes the browser reject the module with exactly the same 'Failed to fetch dynamically imported module' symptom as a 404/403. A lazy-load route that forgets the MIME header fails even when the guard and the file are fine.

## 4 · Incident 3 — why both handlers fire on one Ctrl+scroll

**Mechanism.** The diagram zoom handler and the pane's font-size handler are `wheel` listeners attached to **different nodes on the same propagation chain** (zoom on the diagram element inside the modal, font-size on an ancestor pane/container or window). A wheel event bubbles from the deepest target upward, so a single Ctrl+scroll inside the fullscreen modal reaches *both* listeners: the modal's handler zooms the SVG, the event keeps bubbling, and the pane's handler also sees `ctrlKey` and changes font size. Neither handler calls `stopPropagation()`, and the modal was never established as a gesture boundary — one gesture, two owners.

**Ownership rule.** The innermost fullscreen overlay owns the gesture while it is open: the modal's wheel listener must be registered with `{ passive: false }` and, when it handles a Ctrl+wheel, call **both** `preventDefault()` (cancel the browser's ctrl-wheel page-zoom default) and `stopPropagation()` — or register in the **capture phase** on the modal root and stop there — so no ancestor pane handler ever observes the event. Inverse rule for the pane handler: it must ignore wheel events whose target lies inside an open overlay (or be structurally unreachable while the modal is mounted). One gesture = exactly one owner, decided at the topmost-rendered interactive surface.

## 5 · Regression tests that would have caught each incident

**Incident 1 — chunk-graph completeness (build/packaging test):**

- After build, parse the emitted lazy entry for static sibling specifiers (`import "./…"` or the bundler's manifest) and assert every referenced file exists in the published package's `lib/`; with the single-file config, assert the build emits **exactly one** chunk and zero sibling assets for the mermaid entry.
- One headless-browser e2e: load a markdown view with a mermaid fence, await the dynamic import through the real route, assert an SVG rendered (not the code-block fallback) and the console shows no 'Failed to fetch dynamically imported module'.

**Incident 2 — containment guard vs canonicalization (unit test):**

- Table-driven route test in a temp dir: valid `mermaid-chunk.js` → 200 with `application/javascript`; traversal payloads (`..%2f..%2fsecret.js`, absolute-path injection) → 403; missing file → 404; symlink inside `lib/` pointing outside → 403 after realpath.
- The case trap, made deterministic: exercise the guard with a base whose drive-letter case differs from the realpath output — exactly the `E:` versus `e:` production shape. On Windows run the fixture from a drive whose URL-string case differs from realpath's; on CI simulate by asserting the guard uses `relative(realpathSync(LIB_DIR), …)` rather than `startsWith(LIB_DIR…)`, e.g. feeding a mixed-case copy of the lib dir. Old code fails this test with 403; fixed code passes.
- MIME assertion: every 200 response carries a JS MIME type (guards the 'other serving requirement').

**Incident 3 — gesture exclusivity (DOM/event test):**

- Render the reading pane with the zoom modal open, add a spy on the pane's font-size handler, dispatch `new WheelEvent('wheel', { ctrlKey: true, deltaY: -120, bubbles: true, cancelable: true })` on the diagram element, and assert: exactly one zoom action occurred, `defaultPrevented` is true, and the pane font-size handler was **not** invoked. The same dispatch with the modal closed must still reach the pane handler (proves the rule is scoped to the overlay, not a global kill switch).

---

## Skill-mode notes

- Mode A (inspect, read-only) per `plugin-upgrade`; no migration, install, or version switch was performed and none is needed for this diagnosis.
- Baseline (Mode C pre-existing failures): not collected — no code was built or run; the fixture is static evidence only.
- Pending/residual risk: the plugin's exact bundler is unknown, so the single-file flag is named per-family (`inlineDynamicImports` / lib-mode / `--bundle`) rather than as one verified config line; the modal's actual DOM structure is inferred from the reported symptom (two listeners on one propagation chain), since only the route source is in the evidence pack.
