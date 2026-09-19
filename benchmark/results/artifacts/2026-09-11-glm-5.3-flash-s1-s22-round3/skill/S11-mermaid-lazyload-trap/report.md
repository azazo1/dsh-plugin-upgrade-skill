# S11 · Mermaid Lazy-Load Trap — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.4.0 (lib-only bundle, lazily-imported mermaid chunk served by a host prefix route).
Evidence inspected (read-only fixture): `chunk-route.ts`, `console-split-chunks.txt`, `console-403-windows.txt`, `ci-note.md`, `README.md`.

---

## 1. Incident 1 — split chunks: sibling imports 404

**Evidence.** `console-split-chunks.txt`: `mermaid-chunk.js` loads with **200 (8.1 kB)**, then `src-BfvxrPJe.js` → 404 and `pie-WAS4IAKB-CQHCQWWM.js` → 404, followed by `TypeError: Failed to fetch dynamically imported module` and the code-block fallback. The note in the same file: "`mermaid-chunk.js` WAS present; the sibling files listed in its import statements were NOT shipped with the package."

**Root cause.** With default bundler code-splitting, a dynamically imported entry is not one artifact: the bundler emits the entry chunk **plus sibling chunks** shared with (or split out of) it, and the entry chunk keeps static `import`/`import()` statements referencing those siblings **relative to its own URL** (e.g. `./pie-WAS4IAKB-CQHCQWWM.js`). The packager shipped only the mermaid entry into `lib/`, so the browser resolved those relative imports against `/dsh-attach-input/resources/mermaid-chunk.js`'s URL, requested the siblings from the same route, and got 404s. A dynamic `import()` fails atomically: any module in its graph failing to fetch rejects the whole import — hence the fallback even though the entry itself returned 200.

**Build-side fix.** Produce a **single self-contained chunk** for the lazy entry: `output.inlineDynamicImports: true` (Rollup) / Vite lib-mode or `manualChunks` pinning everything mermaid needs into one file, so no relative sibling imports remain. Equivalently (and as a regression guard), ship *every* emitted chunk of that entry graph in `lib/` and verify the graph closes. Attempt 2 correctly took the single-file route (7.2 MB chunk per `console-403-windows.txt`).

## 2. Incident 2 — Windows-only 403: case-sensitive containment guard

**Evidence.** `console-403-windows.txt`: `GET .../resources/mermaid-chunk.js → 403`, "the route log shows the guard branch fired ('path escapes the plugin lib') — for a path that is plainly inside the lib directory." `ci-note.md` prints the decisive debug output on the production host:

- `LIB_DIR  = "E:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib"` (uppercase **E:**, from `normalize(fileURLToPath(new URL('.', import.meta.url)))`)
- `realpath = "e:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\mermaid-chunk.js"` (lowercase **e:**)

and the matrix: Linux CI green, Windows 11 laptop green, Windows Server 2022 (DSH on `E:\`) broken.

**Exact mechanism.** The guard in `chunk-route.ts` does a **byte-exact string prefix comparison** after `file = normalize(realpathSync(abs))`: `if (!file.startsWith(LIB_DIR + sep)) → 403`.

On Windows, `path.normalize` preserves the drive-letter case of the string it is given; it does not canonicalize case. `realpathSync` resolves to the **on-disk canonical case** of each path component — on the production volume the DSH tree is recorded with a lowercase `e:`, while `import.meta.url` (i.e., how Node was given the module path at boot) carries uppercase `E:`. So on Windows the two APIs can return the *same directory with different drive-letter case*; `"e:\...".startsWith("E:\...")` is `false` (JS string comparison is case-sensitive), and the guard rejects a legitimately contained file with 403. The laptop passed only by coincidence — there, both strings happened to use the same case. On Linux, paths are case-sensitive, the two APIs always agree byte-for-byte, and the guard is accidentally correct.

## 3. Fix direction for the guard + one other serving requirement

**Comparison fix.** Replace the raw `startsWith` with a **relative-path containment check that is case-insensitive on `win32`**:

    import { relative, isAbsolute } from 'node:path'
    function contains(dir, candidate) {
      const rel = relative(dir, candidate)
      return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel)
    }
    // on win32, compare lowercased inputs: relative(dir.toLowerCase(), candidate.toLowerCase())

Why robust on both platforms: `path.relative` expresses containment structurally instead of textually (a child yields a relative path that neither escapes via `..` nor is absolute); lowercasing the inputs on `win32` only absorbs the case-insensitive filesystem, where two casings of one path denote the same file. Alternatively, canonicalize the *directory* too — compare `realpathSync(abs)` against `realpathSync(LIB_DIR)` — so both sides get the same on-disk casing. Apply the same fix to both guard sites (the pre-realpath `abs` check and the post-realpath check). Traversal rejection must keep working — `relative` still yields a leading `..` for escapes, so `../secret.js` → 403 on both platforms.

**Other serving requirement.** The route must serve the chunk with a **JavaScript MIME type** (`Content-Type: text/javascript` or `application/javascript`). Module scripts loaded via dynamic `import()` are subject to strict MIME checking in the browser; a 200 served as `text/plain` (or the prefix route being shadowed by another handler) is refused before execution. The excerpt already sets `'application/javascript; charset=utf-8'` — this must be preserved, and the route must actually win registration for the prefix.

## 4. Incident 3 — Ctrl+scroll resizes both the diagram and the pane font

**Root cause.** The zoom modal's wheel handler and the reading pane's font-size wheel handler are both active for the same gesture. The modal is rendered inside the pane's DOM tree (or both listeners are registered on a common ancestor such as `window`), so the browser dispatches the single `wheel` event to the innermost target first and then **bubbles it to every listener on the ancestor chain** — the pane's handler receives the same event after the modal's. Neither handler calls `event.stopPropagation()`/`stopImmediatePropagation()` (and passive registration would make `preventDefault` unavailable anyway), so one Ctrl+scroll applies the modal's zoom *and* the pane's font scaling. Registration order does not save you: bubbling delivers the event to both regardless.

**Ownership rule.** **One owner per gesture.** When the fullscreen modal is open, the modal owns the wheel gesture exclusively: its handler claims the event with `event.preventDefault()` + `event.stopPropagation()` (non-passive, on the modal root or capture phase), or — equivalently and more explicitly — the pane's font-size handler is gated on `modalOpen === false`. When the modal is closed, the pane owns the gesture. Rule to encode: an overlay surface that consumes a gesture must cancel its propagation to ambient handlers, and ambient handlers must check whether an owning overlay is active.

## 5. Regression tests that would have caught incidents 1–3

1. **Chunk-graph closure test (incident 1).** After `build`, statically scan every emitted `lib/*.js` chunk's `import`/`import()` specifiers and assert each resolves to a file that exists in the shipped package (fail on `./src-*.js` / `./pie-*.js` siblings absent from `lib/`). Also assert exactly one self-contained mermaid chunk (`inlineDynamicImports` held). This runs before packaging and would have failed attempt 1.
2. **Route guard platform-matrix test (incident 2).** Unit-test the containment helper with the exact production divergence: `LIB_DIR = 'E:\\...\\lib'` vs candidate realpath `'e:\\...\\lib\\mermaid-chunk.js'` → must be contained (HTTP 200, via a mocked `realpathSync` or by creating the file on a case-insensitive temp volume). Pair with negative cases: `rel = '../secret.js'` → 403, non-JS extension → 404, POST → 405. Run the suite on both Linux and Windows CI so the drive-case mismatch is exercised natively, not only simulated.
3. **Serving-contract test (item 3).** Integration test that boots the route and asserts a GET of the chunk returns 200 with `content-type: application/javascript` (or `text/javascript`) — the strict-MIME precondition for any dynamic import.
4. **Gesture-ownership test (incident 3).** Component test: mount pane + modal; dispatch a Ctrl+wheel `WheelEvent` on the open modal and assert (a) diagram zoom changed and (b) pane font-size unchanged; dispatch again with the modal closed and assert pane font-size changes. This fails on the current code (both mutate) and pins the ownership rule.
5. **Fallback-metrics assertion (incidents 1–2).** Assert the "mermaid chunk fell back to code block" log/counter stays at zero in a happy-path render test, so any chunk-fetch regression surfaces in CI rather than as a silent plain-code fallback in production.

---

**Summary of fixes:** (1) bundle the lazy mermaid entry with `inlineDynamicImports` / ship the whole chunk graph; (2) replace both `startsWith` guards with a structural `path.relative` containment check, case-insensitive on `win32` (or realpath both sides); (3) keep the JS `Content-Type` and route precedence; (4) make the open modal the exclusive owner of the Ctrl+wheel gesture (`preventDefault` + `stopPropagation`, or gate the pane handler on modal state); (5) add the chunk-graph, guard-matrix, MIME, and gesture-ownership tests above.
