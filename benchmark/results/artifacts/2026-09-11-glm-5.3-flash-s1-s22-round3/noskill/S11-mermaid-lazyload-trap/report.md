# S11 · Mermaid Lazy-Load Trap — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.4.0 (mermaid rendering as a lazily imported chunk served by a new host prefix route).
Evidence: `fixture/chunk-route.ts`, `fixture/console-split-chunks.txt`, `fixture/console-403-windows.txt`, `fixture/ci-note.md`.

---

## 1. Incident 1 — why default split-chunking failed

Evidence (`console-split-chunks.txt`): `mermaid-chunk.js` loaded with **200 (8.1 kB)**, then two sibling chunks 404'd (`src-BfvxrPJe.js`, `pie-WAS4IAKB-CQHCQWWM.js`), followed by `TypeError: Failed to fetch dynamically imported module` and the plugin's fallback to a code block. The `ls` note in the same capture says it plainly: `mermaid-chunk.js` WAS shipped; "the sibling files listed in its import statements were NOT shipped with the package."

Mechanism — what breaks when a dynamically imported chunk has sibling imports:

- A bundler's default code-splitting does not emit the dynamic entry as one file. It factors shared modules out into additional sibling chunks and rewrites the dynamic entry to contain static `import "./pie-…-HASH.js"` statements referencing them by content-hashed file names.
- A dynamic `import()` is only the *entry point* of a module graph. Once the browser fetches the entry successfully (the 200), it must still resolve and fetch **every** static import in that graph from the **same origin and base URL** as the entry. Each sibling is a separate HTTP request with a separate failure mode; a single missing/unpublished sibling fails the whole import and rejects the original `import()` promise — exactly the observed "Failed to fetch dynamically imported module" even though the top-level chunk returned 200.
- Here the packaging step shipped only the entry file, so the hashed siblings (`pie-WAS4IAKB-…js`) existed at build time but not on the serving host → 404 → rejection.

Build-side fix: build the lazily loaded mermaid code as a **single self-contained chunk** so the dynamic import has no siblings to fetch — e.g. Rollup/Vite `output.inlineDynamicImports: true` (or a single-entry lib build with code splitting disabled). This is what attempt 2 did ("single self-contained chunk (7.2 MB)" per `console-403-windows.txt`), and it is the correct fix for a plugin that can only guarantee one shipped file. (Alternative: ship and serve *all* emitted chunks — but for a lib-only plugin bundle, one file is the robust choice, and the hashed sibling names make "remember to ship them all" fragile across builds.)

---

## 2. Incident 2 — the exact guard flaw behind the Windows 403

Evidence:

- `console-403-windows.txt`: `GET /dsh-attach-input/resources/mermaid-chunk.js 403`, route log shows the guard branch fired (`"path escapes the plugin lib"`) "for a path that is plainly inside the lib directory."
- `ci-note.md` debugging print on the production host:
  - `LIB_DIR   = "E:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib"`
  - `realpath  = "e:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\mermaid-chunk.js"`
  - Note the drive-letter case: the guard's constant is **uppercase `E:`**, the realpath is **lowercase `e:`**.
- `chunk-route.ts`, second containment check:

```
file = normalize(realpathSync(abs))
if (!file.startsWith(LIB_DIR + sep)) { res.writeHead(403).end('path escapes the plugin lib'); return }
```

Precise mechanism (per-API, per-platform):

- `normalize()`/`join()` are **pure string normalizers**: on win32 they resolve `.`/`..` and separators but preserve the drive-letter case exactly as written in the input. `LIB_DIR` comes from `normalize(fileURLToPath(new URL('.', import.meta.url)))`; on that host the module URL carried `E:`, so `LIB_DIR` keeps uppercase `E:\dsh\…`.
- `fs.realpathSync()` on Windows resolves the path through the filesystem (also resolving symlinks/junctions), and the case it returns is the case **as stored on the volume / retrieved from the filesystem** — on that Windows Server 2022 host it came back as lowercase `e:\dsh\…`. On Linux this cannot happen: POSIX paths are case-sensitive and ext4 preserves exactly the case that was created, so `realpathSync` output matches the input's case character-for-character.
- `String.prototype.startsWith` is a byte-exact comparison: `"e:\…".startsWith("E:\…" + "\")` is `false` on Windows, `true` on every Linux box. Hence the guard only misfires on Windows hosts where realpath's stored case differs from the URL's case — matching the maintainer's matrix in `ci-note.md` exactly (Linux green; Win11 laptop on `C:\` happened to agree in case; production `E:` vs `e:` → 403 on every chunk GET).
- The same flaw affects the *first* check (`abs.startsWith(LIB_DIR + sep)`) only in principle — it survives because both `LIB_DIR` and `join(LIB_DIR, rel)` derive from the same string, so their case always agrees.

So this is not "Windows paths are unreliable"; it is a **case-sensitive prefix comparison applied to a case-insensitive filesystem**, compounded by comparing a raw input path against a filesystem-resolved (realpath) path.

---

## 3. Fix direction for the guard + the other serving requirement

Fix — stop comparing strings with `startsWith`; use `path.relative` and realpath **both** sides:

```
const LIB_REAL = normalize(realpathSync(LIB_DIR))            // resolve symlinked lib dir, once at startup
const inside = (candidate) => {
  const rel = relative(LIB_REAL, candidate)
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))
}
```

- `path.relative` is the containment primitive the platform owns: on win32 it is **case-insensitive** (so `e:\…` is contained under an `E:\…` base), and it returns a result that states exactly how the candidate sits under the base; a `'..'-`prefixed or absolute result means escape. On POSIX it is case-sensitive, which is correct there. One comparison, robust on both platforms — no platform forks.
- Applying `realpathSync` to the *base* (`LIB_REAL`) as well as to the candidate makes the comparison realpath-vs-realpath, so symlink/junction redirections of the lib directory can neither produce a false escape nor a false pass when the base itself is a symlink.
- Keep rejecting an empty `rel`, traversal (`..`), and non-`.m?js` extensions before touching the filesystem; `join` + `relative` still neutralizes encoded/decoded traversal attempts, and the existing 404-on-`realpathSync`-throw branch remains the missing-file path.

Other serving requirement for a dynamic `import()` to work at all: the route must serve the response with a **JavaScript MIME type** (`text/javascript` / `application/javascript`). ES module scripts are fetched in strict MIME mode — a correct-looking 200 served as `text/plain` (or a generic type) is refused by the browser as a module-load error, surfacing as the same "Failed to fetch dynamically imported module". The route already does this correctly (`'content-type': 'application/javascript; charset=utf-8'` in `chunk-route.ts`) and must keep doing so. Implicitly the chunk must also be served same-origin (it is, under the host's own `/dsh-attach-input/resources` prefix), since cross-origin module fetches additionally require CORS.

---

## 4. Incident 3 — why BOTH Ctrl+scroll handlers fire, and the ownership rule

Symptom: in the new fullscreen zoom modal, Ctrl+scroll resizes the diagram **and** the pane's font size.

Mechanism — event propagation semantics, not browser flakiness:

- A `wheel` event dispatched on a node inside the modal does not stop at the modal's listener. It propagates along the composed path (bubbling through the modal's ancestors to any pane-level listener registered on the markdown pane, a portal root, `document`/`window`; or through them in the capture phase if such a listener used `capture: true`). Unless a listener calls `stopPropagation()`, **every** listener on the path runs; registration order only decides sequence, never exclusivity — there is no built-in "the modal handled it, others back off" default.
- Neither handler claims ownership: the modal's handler scales the diagram; the pane's pre-existing handler only tests `ctrlKey` + `deltaY` and does not know the gesture started inside an overlay, so it also zooms text. Neither calls `preventDefault()`, so the browser's own Ctrl+wheel page zoom can fire on top — multiple responders, one gesture.

Ownership rule that fixes it: **the topmost (innermost overlay) surface owns the gesture; every other listener on the path must yield.** Concretely:

1. The modal's wheel handler registers with `{ passive: false }`, calls `event.preventDefault()` (suppressing browser page zoom) and `event.stopPropagation()` so no ancestor handler sees the gesture.
2. Every other Ctrl+wheel consumer (the pane's font-size handler) checks the composed path before acting: `if (event.composedPath().some(n => n === modal || modal.contains(n))) return` — it ignores any event whose target lives inside an overlay it does not own. This holds regardless of registration order, capture vs. bubble, or future overlays.

---

## 5. Regression tests that would have caught incidents 1–3

**Incident 1 (sibling-chunk 404) — bundler output contract test:**

- Build the lib bundle in CI and assert the emit plan: exactly one JS artifact, and the built file contains **no static import specifiers pointing at sibling chunks** (no `./pie-…-HASH.js`-style relative chunk imports). Any dependency-graph change that silently re-enables splitting fails the build, not production.
- Route-level test (the general version): for every static import specifier found in any served file, GET it from the route and assert 200 — the test that would have turned `console-split-chunks.txt`'s 404s into a red CI run.

**Incident 2 (Windows 403 guard) — route guard unit tests, table-driven over platform path shapes:**

- Containment passes: same-case path (`E:\lib\mermaid-chunk.js`), **case-mismatched drive** (`e:\lib\…` resolved against an `E:\` base — the exact production pair printed in `ci-note.md`), symlinked lib dir resolved via `realpathSync`, nested path (`lib/vendor/a.js`).
- Containment rejects: URL-encoded traversal (`..%2F..%2F`), post-decode `..\` traversal, absolute `rel`, non-`.js` extension (404 branch), missing file (404 branch, not 403).
- Assert headers and methods: `content-type` starts with `text/javascript` or `application/javascript` (strict module MIME), and non-GET → 405.
- Running this suite on win32 and POSIX CI legs (or mocking `path`/`fs` platform behavior for the case-mismatch case) would have caught the case-sensitivity hole before production rollout.

**Incident 3 (double zoom) — interaction/DOM tests:**

- Dispatch a `ctrlKey: true` `wheel` event on a node inside the modal; assert the diagram scale changed **and the pane's font-size is unchanged**, and that `preventDefault` was called (page zoom suppressed).
- Same dispatch with the modal closed; assert the pane font-size changes (the ownership check must not over-block).
- Order-independence: register the pane handler before *and* after the modal handler, and once with `capture: true` — assertions must hold in all registrations, pinning the composed-path ownership rule rather than accidental listener order.

---

## Root causes, one line each

1. Default code splitting emitted hashed sibling chunks the package never shipped; the dynamic entry 200'd but its import graph 404'd → fix by building one self-contained chunk (`inlineDynamicImports`).
2. `file.startsWith(LIB_DIR + sep)` compared a `realpathSync()` result (on Windows the drive letter comes back in volume-stored case, `e:`) against a URL-derived constant (`E:`) — a case-sensitive string compare on a case-insensitive filesystem → fix with `path.relative` from a realpath'd base, case-insensitive on win32 and correct on POSIX.
3. `wheel` events keep propagating after the modal's handler runs, so all listeners on the composed path fire → topmost overlay owns the gesture (`passive: false` + `preventDefault` + `stopPropagation`); all other Ctrl+wheel handlers yield via a `composedPath()` check.
