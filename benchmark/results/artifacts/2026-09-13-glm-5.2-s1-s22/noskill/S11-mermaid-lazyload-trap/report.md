# S11 · Mermaid Lazy-Load Trap — Diagnosis Report

Evidence reviewed: `chunk-route.ts`, `console-split-chunks.txt`, `console-403-windows.txt`, `ci-note.md` (read-only fixture).

---

## 1. Incident 1 — why the split-chunk approach failed

**Observed:** `mermaid-chunk.js` itself loads (200), then its own imports `./src-BfvxrPJe.js` and `./pie-WAS4IAKB-CQHCQWWM.js` return 404, and the browser reports `Failed to fetch dynamically imported module: .../mermaid-chunk.js`.

**Mechanism.** With the bundler's default code-splitting, a dynamically imported entry point is emitted as a *chunk graph*, not a single file: `mermaid-chunk.js` is the entry chunk, and its static imports (mermaid's per-diagram modules like `pie`, `src`, etc., plus shared helpers) are emitted as *sibling chunks* in the same output directory. The browser resolves those sibling specifiers **relative to the importing chunk's URL** (`/dsh-attach-input/resources/...`) and fetches each one itself. Only `mermaid-chunk.js` was shipped in the package (the fixture note confirms: "the sibling files listed in its import statements were NOT shipped"), so every sibling fetch 404s — and per spec, if *any* module in a dynamic-import graph fails to fetch or instantiate, the whole `import()` promise rejects with "Failed to fetch dynamically imported module", even though the entry chunk itself loaded fine.

**Build-side fix.** Make the lazy chunk self-contained so `import()` needs exactly one file:

- Bundle mermaid as a single entry with code-splitting disabled for it — e.g. Rollup `output.inlineDynamicImports: true` for that build (or a separate single-file build with `output.manualChunks: undefined` / esbuild `--bundle --format=esm --splitting=false`), so all of mermaid is inlined into `mermaid-chunk.js`; or
- If splitting must stay on, ship the *entire* emitted chunk directory (all 97 siblings) and have the route serve any of them — but for a lazily-imported library inside a plugin package, one self-contained chunk is the robust choice (which is what attempt 2 correctly did).

A build-side assertion should fail the release if the shipped chunk contains relative import specifiers pointing at files not present in `lib/` (see §5).

---

## 2. Incident 2 — the exact flaw in the containment guard (403 on Windows, green on Linux)

**Observed:** the *second* guard fires ("path escapes the plugin lib") for a path plainly inside the lib dir, but only on the production Windows host. The debugging output in `ci-note.md` is the smoking gun:

```
LIB_DIR   = "E:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib"
realpath  = "e:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\mermaid-chunk.js"
`        ^ lowercase drive letter

**Mechanism, precisely.**

- `LIB_DIR` is derived from `new URL('.', import.meta.url)` → `fileURLToPath` → `normalize`. A `file://` URL preserves the casing that appears in the URL string, which on this host came out as uppercase **`E:\`**.
- `fs.realpathSync()` on Windows does not echo the input string: it resolves the path through the object manager and returns the **canonical on-disk casing**, and for the drive root Windows reports the casing the volume was mounted/installed with — here lowercase **`e:\`** (Windows paths are case-preserving but case-*insensitive*; there is no single authoritative casing, and different APIs return different ones).
- The guard then does a **byte-wise, case-sensitive** `file.startsWith(LIB_DIR + sep)`. `"e:\dsh\..." .startsWith("E:\dsh\...")` is false → 403.

Platform matrix explained:

| Platform | LIB_DIR vs realpath | `startsWith` | Result |
|---|---|---|---|
| Linux CI | identical bytes (case-sensitive FS, realpath == input casing) | true | green |
| Win11 laptop | URL happened to carry the same casing realpath returns | true | green |
| Win Server 2022, `E:\dsh` | URL-derived `E:` vs realpath `e:` | **false** | 403 |

So it is not "Windows is unreliable": it is *case-sensitive string comparison applied to a case-insensitive path namespace where two different APIs legitimately return different casings for the same file*. The first guard (`abs.startsWith(LIB_DIR + sep)`) is redundant-but-harmless here — both inputs derive from the same string; the realpath guard is the one that diverges.

---

## 3. Fix direction for the guard + the extra serving requirement

**Fix.** Stop comparing path strings with `startsWith`. Use `path.relative`, which encodes the platform's own path semantics, and reject when the result escapes:

```ts
import { relative, isAbsolute } from 'node:path'

const file = realpathSync(abs)
const relFromBase = relative(realLibDir, file)          // realLibDir = realpathSync(LIB_DIR), computed once at startup
if (relFromBase === '' || isAbsolute(relFromBase) || relFromBase.split(sep)[0] === '..') {
  res.writeHead(403).end('path escapes the plugin lib'); return
}
```

Why this is robust on both platforms:

- `realpathSync(LIB_DIR)` as the base puts **both** sides of the comparison in realpath-canonical form, eliminating the URL-vs-realpath casing divergence at the source.
- `path.relative` on Windows performs its comparison case-insensitively (it lowercases for comparison internally), so residual casing differences in subdirectory components still resolve to `''`-prefixed relative paths rather than mismatches; on Linux/POSIX it stays byte-exact, so containment remains strict where it must be.
- It also rejects the degenerate cases cleanly: `relFromBase === ''` (the lib dir itself), absolute results (different drive), and any `..` first segment (escape). Rejecting `relFromBase.split(sep)[0] === '..'` rather than `startsWith('..')` avoids false-positive rejection of a legitimate file literally named `..foo.js`.

(If a `startsWith` must be kept for style reasons, the minimum correct form is: normalize both sides via realpath *and* lowercase both on `process.platform === 'win32'` before comparing — but `relative` is the cleaner, self-documenting fix.)

**One other serving requirement for `import()` to work at all:** the response must carry a **JavaScript MIME type** (`application/javascript`, `text/javascript`). Module scripts — including dynamically imported ones — are subject to strict MIME-type checking; a chunk served as `text/plain`, `application/octet-stream`, or with a missing `Content-Type` is rejected by the browser before evaluation, producing the same "Failed to fetch dynamically imported module" failure. The route already sets `application/javascript; charset=utf-8` — that header is load-bearing and must not be dropped. (Additionally the URL must be same-origin or CORS-permitted; here it is same-origin via the host prefix route, so the MIME type is the operative requirement.)

---

## 4. Incident 3 — why BOTH handlers fire on one Ctrl+scroll

**Mechanism.** The zoom modal renders *inside* the pane's DOM subtree (or both handlers are attached to ancestors of the scroll target, e.g. the modal listens on its overlay element while the pane's font-size handler listens on the pane root or `window`/`document`). A `wheel` event **bubbles**: one Ctrl+scroll over the modal content produces a single event that propagates target → modal overlay → pane root → document. Neither handler calls `stopPropagation()`, so both listeners observe the same event — the modal zooms the diagram *and* the pane handler adjusts font size simultaneously. Ordering is irrelevant; the bug is that both handlers *own* the same event because they are on the same propagation path.

**Ownership rule.** *The innermost component that consumes a gesture owns it for the duration of its interaction:* while the fullscreen zoom modal is open, the modal's `wheel` handler is the sole owner of Ctrl+scroll within the modal, and it must terminate propagation (`evt.stopPropagation()` — `preventDefault()` alone does not stop other listeners on ancestors) so the pane never sees it. Concretely:

- Modal handler: on `wheel` with `ctrlKey`, apply diagram zoom, call `preventDefault()` **and** `stopPropagation()`; register/dispose it via `ctx.effect()` so closing the modal (or plugin stop) removes the listener and ownership returns to the pane.
- Equivalently stated as a scope rule: an ancestor-level gesture handler must be scoped to "no overlay currently claims the gesture" (e.g. the pane checks `evt.defaultPrevented` or an `activeModal` flag) — but the primary fix is stopPropagation at the consuming owner, not flags duplicated in every ancestor.

---

## 5. Regression tests that would have caught incidents 1–3

**Incident 1 — chunk completeness (build/packaging test):**
- After building the plugin lib, statically scan the emitted `mermaid-chunk.js` for module specifiers (relative `import`/`export ... from` / `import(...)`) and assert every referenced file exists in the shipped `lib/` directory. Fails on attempt 1 (the 97 missing siblings) before release.
- Stronger variant: build config test asserting the mermaid entry produces exactly one emitted chunk (`inlineDynamicImports` honored) — e.g. snapshot the rollup/esbuild `output` file list for the entry.

**Incident 2 — containment guard, cross-platform (route unit tests):**
- On Windows (or with an injected fake `realpathSync` returning a differently-cased path — e.g. base `E:\...\lib`, target `e:\...\lib\x.js`), assert a request for `/resources/x.js` returns **200**, not 403. This is the exact production failure.
- Traversal suite: `/resources/..%2f..%2fsecret.js`, `/resources/..\\..\\secret.js`, absolute-path payloads, and a symlink whose realpath lands outside lib → all must 403/404; a plain `/resources/mermaid-chunk.js` → 200 with `content-type: application/javascript` (covers the MIME requirement too).
- Run the guard as a pure function over path pairs on both CI matrices (Linux native + Windows runner) so the casing divergence is exercised, not just simulated.

**Incident 3 — gesture ownership (client/DOM test):**
- Render the pane with a mermaid diagram, open the zoom modal, dispatch a `WheelEvent` with `ctrlKey: true` on the modal content, and assert: the modal zoom callback ran exactly once AND the pane's font-size handler did not run (spy on it). Fails without `stopPropagation`.
- Lifecycle assertion: after closing the modal, a Ctrl+wheel on the pane reaches the pane handler again (modal listener disposed via `ctx.effect`), and a plugin-stop test asserts no wheel listeners remain.

---

## Summary of fixes

1. **Build:** emit one self-contained chunk (disable code splitting for the mermaid entry) or ship the whole chunk graph; gate with a chunk-completeness packaging test.
2. **Guard:** compare with `path.relative(realpathSync(LIB_DIR), realpathSync(abs))` and reject `''`/absolute/`..`-prefixed results — case-insensitive by construction on Windows, byte-strict on POSIX.
3. **Serving:** keep the strict JS `Content-Type` header; dynamic import fails without it.
4. **Events:** the open modal owns Ctrl+scroll — `preventDefault() + stopPropagation()` in the modal handler, registered and disposed via `ctx.effect()`.
