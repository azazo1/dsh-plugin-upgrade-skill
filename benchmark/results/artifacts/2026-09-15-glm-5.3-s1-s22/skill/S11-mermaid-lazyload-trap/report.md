# S11 · Mermaid Lazy-Load Trap — Diagnosis Report

Task: read-only diagnosis of three rollout incidents in `@org/dsh-attach-input` v0.4.0
(community Web plugin, lib-only bundle) after adding lazily-imported mermaid rendering.
Mode: A · inspect (skill `plugin-upgrade`). No files outside the designated output
directory were written; the fixture was not modified.

Evidence reviewed: `fixture/chunk-route.ts`, `fixture/console-split-chunks.txt`,
`fixture/console-403-windows.txt`, `fixture/ci-note.md`.

---

## 1 · Incident 1 — why the split-chunk approach failed

**Observed:** the browser fetched `mermaid-chunk.js` itself fine (200, 8.1 kB), then
404'd on `src-BfvxrPJe.js` and `pie-WAS4IAKB-CQHCQWWM.js`, and the whole
`import()` rejected with `TypeError: Failed to fetch dynamically imported module`.
The fixture's `ls` note is decisive: the sibling files named in the chunk's import
statements were **not shipped** in `lib/`.

**Mechanism.** With default bundler code-splitting, the lazily-imported entry is *not*
self-contained: `mermaid-chunk.js` contains static module imports (ESM `import "."
` statements, or a chunk-loading map for `rollup`/`vite`/`esbuild` split output)
pointing at sibling chunk files emitted next to it. A dynamic `import()` of a chunk
loads the chunk **and then resolves its entire static import graph**; any sibling in
that graph that cannot be fetched (404) fails the module instantiation, and the browser
surfaces it as a failure of the *originally imported* module URL — hence "Failed to
fetch dynamically imported module: …/mermaid-chunk.js" even though that URL returned
200. 8.1 kB for mermaid is the tell: it is the thin entry of a ~100-file graph, and
only the entry was packaged (the package `files`/publish list shipped the documented
entry, not the 97 hash-named siblings).

**Build-side fix.** Make the lazy chunk a **single self-contained file** with *no*
sibling imports, so that a working dynamic import requires exactly one shipped file:

- Rollup/Vite: `output.inlineDynamicImports: true` (single-entry) or force
  `manualChunks` so everything reachable from the mermaid entry lands in one chunk;
  verify the emitted file has **zero** relative `import` statements.
- esbuild: bundle without `--splitting` (splitting is opt-in there).

(Shipping all 98 hashed chunks is theoretically possible but fragile for a lib-served
plugin — hash-named files must all survive packaging, publishing, and the route's
extension guard — so single-file is the robust fix, which is what attempt 2 correctly
moved to.)

## 2 · Incident 2 — the exact flaw in the containment guard

**Observed:** 403 "path escapes the plugin lib" for a file plainly inside `lib/`,
only on the production Windows host. The CI note's debug print is the smoking gun:

    LIB_DIR   = "E:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib"
    realpath  = "e:\dsh\...\lib\mermaid-chunk.js"

**Flaw: a case-sensitive `startsWith` string comparison applied to Windows paths whose
drive-letter casing differs between the two producers of the strings.**

Walk the guard:

1. `LIB_DIR` is derived from `fileURLToPath(new URL('.', import.meta.url))` — on
   Windows this yields the drive letter as it appears in the module URL, here
   uppercase `E:`.
2. First guard: `abs = normalize(join(LIB_DIR, rel))` then
   `abs.startsWith(LIB_DIR + sep)`. `abs` is *built from* `LIB_DIR`, so this check
   can never fail for a syntactically in-range `rel` — it only rejects
   `..`-style escapes by string prefix. It passes.
3. Second guard: `file = normalize(realpathSync(abs))`. Node's `realpathSync` on
   Windows goes through libuv, which canonicalizes the path against the OS (volume
   name / final path), and returns the **lowercase drive letter** `e:` here. The
   subsequent `file.startsWith(LIB_DIR + sep)` is an exact, case-sensitive string
   comparison: `"e:\dsh\…"` vs `"E:\dsh\…" ` → mismatch → 403.

**Why the matrix split the way it did (platform/API behavior, not folklore):**

- **Linux:** paths are case-sensitive and `realpathSync` returns the same bytes that
  `fileURLToPath` produced (there is no drive-letter concept and no case
  canonicalization), so both `startsWith` checks pass deterministically.
- **Windows laptop (C:\, "lowercase c: in some tooling"):** on that machine the two
  strings happened to agree in case — e.g. the profile was launched via a path whose
  URL form already carried `c:`, or node_modules sat behind a junction whose realpath
  happened to match — so the equality was accidental, not guaranteed.
- **Windows Server 2022, DSH on E:\:** uppercase `E:` from the URL-derived
  `LIB_DIR` vs lowercase `e:` from `realpathSync` → every GET takes the 403 branch.

So the guard conflates *string identity* with *filesystem identity*. On Windows the
same file legitimately has multiple string spellings (case-insensitive NTFS, drive
letter case is not significant, plus optional 8.3 short names and junctions), and two
different Node APIs legitimately return different spellings.

## 3 · Fix direction for the guard + the other serving requirement

**Robust containment comparison.** Put *both* sides through the same canonicalizer and
compare structurally instead of by raw prefix:

1. Canonicalize the root once at registration time, not per request:
   `const LIB_REAL = realpathSync(LIB_DIR)`.
2. Per request, after `realpathSync(abs)`, use `path.relative(LIB_REAL, file)` and
   reject when the result is empty, starts with `..`, or `path.isAbsolute()`:

   ```js
   const rel = relative(LIB_REAL, file)
   if (rel === '' || rel.startsWith('..') || isAbsolute(rel)) { 403 }
   ```

   The win32 `path` module already performs case-insensitive drive/case-insensitive
   comparisons, so `relative()` yields `''`-prefixed in-root results regardless of
   `E:` vs `e:`; on POSIX it behaves exactly like the prefix check. (Equivalent
   alternative: `startsWith` after lowercasing both strings on win32 — but
   `path.relative` is the idiomatic, separator- and case-correct form.) Because the
   realpath step already resolved symlinks/junctions, this also defeats
   symlink-escape; keep the pre-realpath check only as a fast syntactic filter.

**Other serving requirement for `import()` to work at all:** the response must carry a
**JavaScript MIME type** (`text/javascript` / `application/javascript`) — module
scripts are refused by the browser on a wrong or missing `Content-Type` (this route
already sets it; it must survive any refactor). Additionally, module fetches cannot
survive interactive auth prompts or cross-origin redirects, so the route must answer
same-origin GETs directly with 200 + JS MIME, never a redirect chain. Both belong in
the route's contract tests.

## 4 · Incident 3 — why both handlers fire on one Ctrl+scroll

**Mechanism.** `wheel` is a bubbling DOM event; Ctrl+wheel is simultaneously the
app's font-size gesture. The plugin attached its zoom listener on the fullscreen modal
(a DOM subtree inside the pane whose font-size handler lives on the pane or an
ancestor/`window`). One Ctrl+scroll over the diagram dispatches a *single* event that
propagates through both registered listeners (inner modal target → bubbles to pane),
and neither handler consults the other, so both effects apply: diagram zoom **and**
pane font resize. Listener registration order is irrelevant — they are on different
nodes of one propagation path.

**Ownership rule.** For any given UI state, exactly one component owns a gesture: the
component that visually owns the region under the cursor consumes the event there.
Concretely: while the fullscreen zoom modal is open, the modal is the owner — its
`wheel` listener on the modal root must call `event.stopPropagation()` (registered
in the capture or target phase on the modal container so it runs before anything on
ancestors), optionally `preventDefault()` to also suppress browser page-zoom; the
pane-level Ctrl+wheel font handler must be inert while the modal is open (guard on
"modal open" state, or suspend/re-register the pane listener via `ctx.effect()`
cleanup when the modal mounts). Never rely on which listener happens to be registered
first.

## 5 · Regression tests that would have caught each incident

**Incident 1 — chunk self-containment / packaging test (build gate):**
- After `pnpm build`, scan every emitted lazy chunk in `lib/` for static import
  specifiers (`import … from "./…"`, `import("./…")`, and bundler chunk-loading
  maps) and assert each referenced file exists in `lib/` — fails when siblings are
  missing from the package.
- Stronger packaging check: run `npm pack --dry-run` and assert the tarball file list
  equals the emitted `lib/` file set (catches `files`/publish-list drift that
  shipped the entry but not the 97 siblings). Assert the mermaid chunk contains zero
  *relative* sibling imports once `inlineDynamicImports` is on.

**Incident 2 — route containment + MIME tests (host unit tests, run on both POSIX and
Windows, with a forced case-mismatch case so it fails everywhere):**
- Serve a real file under a `LIB_DIR`/realpath pair whose strings differ only in
  drive-letter case (mock `realpathSync` to return `e:\…` against `LIB_DIR =
  E:\…`, or a temp-dir fixture with mixed-case directories) → expect **200**, not 403.
- Escape cases stay rejected: `/…/resources/..%2F..%2F..%2Fetc%2Fpasswd`-style and
  symlink/junction-out-of-root requests → 403; non-`.js` → 404; non-GET → 405.
- Response contract: `Content-Type` is a JavaScript MIME type and the body is the
  file bytes (needed for `import()` at all).

**Incident 3 — gesture-ownership test (Web Client, jsdom/Playwright):**
- Open the mermaid fullscreen modal, dispatch one Ctrl+`wheel` event on the diagram,
  assert: modal zoom applied **and** a spy on the pane font-size handler was **not**
  invoked (equivalently, pane font-size CSS unchanged).
- Inverse: with modal closed, same event on the pane resizes font and does not touch
  the modal.

---

## Summary table

| Incident | Root cause | Fix |
|---|---|---|
| 1 · sibling 404s | default code-splitting made the lazy entry non-self-contained; siblings not shipped; `import()` fails on any missing graph edge | single self-contained chunk (`inlineDynamicInputs`/no splitting); packaging test |
| 2 · Windows 403 | case-sensitive `startsWith` on `realpathSync` output vs URL-derived `LIB_DIR`; Windows drive-letter case differs (`E:` vs `e:`), Linux identical | realpath the root once; `path.relative` containment (case-aware on win32); cross-case route tests |
| 3 · double Ctrl+scroll | one bubbling `wheel` event reaches both modal and pane listeners on the propagation path | single gesture owner: modal consumes (`stopPropagation`/`preventDefault`), pane handler suspended while modal open |

**Pending/residual risk (honest notes):** the exact libuv/Windows realpath drive-letter
behavior was derived from the fixture's own debug print (`e:` vs `E:`), which is the
authoritative observed evidence; no Windows host was available in this read-only run to
re-execute it. The route excerpt is labeled "excerpt", so registration/lifecycle
correctness (e.g. `ctx.effect` disposal) was assumed, not verified.
