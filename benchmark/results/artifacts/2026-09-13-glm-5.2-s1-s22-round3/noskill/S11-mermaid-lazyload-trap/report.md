# S11 · Mermaid Lazy-Load Trap — Diagnosis Report

Read-only analysis of the evidence pack in `environment/fixture/`. No files in the benchmark
repository were modified.

## 1. Incident 1 — why the split-chunk approach failed

**Evidence.** `console-split-chunks.txt`: `mermaid-chunk.js` itself returns **200 (8.1 kB)**,
then `src-BfvxrPJe.js` and `pie-WAS4IAKB-CQHCQWWM.js` return **404**, and the dynamic import
of `mermaid-chunk.js` fails. The trailing note is decisive: the `ls` of the shipped `lib/`
showed `mermaid-chunk.js` present but *the sibling files listed in its import statements were
not shipped with the package*.

**Mechanism.** A dynamically imported chunk is only the *entry* of the lazy-load; it is not
self-contained. With default code-splitting, the bundler (Rollup/Vite-style) hoists shared
modules and per-feature diagrams into **sibling chunks**, and the entry chunk contains bare
relative import statements (`import "./src-BfvxrPJe.js"`, `import "./pie-WAS4IAKB-CQHCQWWM.js"`).
When the browser executes the 200-OK entry chunk, the module script resolves those static
imports *before* evaluating it; each 404 makes the whole module graph fail, which surfaces as
`TypeError: Failed to fetch dynamically imported module` pointing at the URL you originally
imported — even though that URL loaded fine. The 8.1 kB size is the tell: real mermaid is
megabytes; the entry is just a thin manifest of sibling imports.

**Build-side fix.** Force a single-file lazy chunk so the dynamic import has no siblings:

- Rollup/`tsdown`: `output.inlineDynamicImports: true` (or route the mermaid entry through a
  separate single-chunk build and `import()` its artifact URL);
- esbuild: bundle with `splitting: false` (and `format: 'esm'`);
- or, if splitting is kept, ship *every* emitted asset in `lib/` — but for a lib-only plugin
  bundle served over one route, the single self-contained chunk (attempt 2's direction) is the
  right choice, because it also removes any dependence on the route serving nested asset
  subtrees.

## 2. Incident 2 — the exact flaw in the containment guard (403 on Windows)

**Evidence.** `chunk-route.ts` contains two guards:

```ts
const abs = normalize(join(LIB_DIR, rel))
if (!abs.startsWith(LIB_DIR + sep)) { 403 }          // guard A — passes
file = normalize(realpathSync(abs))
if (!file.startsWith(LIB_DIR + sep)) { 403 }          // guard B — fires on prod
```

And `ci-note.md` prints on the production host:

```
LIB_DIR   = "E:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib"
realpath  = "e:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\mermaid-chunk.js"
```

**Mechanism.** This is not "Windows is unreliable" — it is a documented asymmetry between the
two APIs involved:

- `new URL('.', import.meta.url)` / `fileURLToPath` yields the drive letter **exactly as the
  runtime string carries it** — here uppercase `E:\...` (the process was started from an
  uppercase `E:` path).
- `fs.realpathSync` on Windows resolves through `GetFinalPathNameByHandle`, and Node returns
  the **canonical drive letter in lowercase** (`e:\...`) regardless of the input casing.
  On Linux/`node:24-bookworm` there is no drive letter at all, so `realpathSync` returns the
  same leading characters and guard B passes — that is why CI is green.
- `String.prototype.startsWith` is **byte-wise and case-sensitive**. `"e:\dsh\..."  .startsWith("E:\dsh\...")` is `false`, so guard B rejects a path that is plainly inside
  the lib directory.

The maintainer's laptop passes only by accident: the note says tooling there carried a
**lowercase `c:\`** into `LIB_DIR`, so the case-sensitive prefix match happened to succeed.
The guard's correctness depended on the incidental drive-letter casing of the host
installation — Linux CI could never catch it.

## 3. Fix direction for the guard + the other serving requirement

**Fix.** Stop comparing two strings produced by *different* normalization regimes. Make both
sides go through the same canonicalizer, and compare in a platform-aware way:

1. Canonicalize the base once: `const BASE = realpathSync(LIB_DIR)` — so base and target have
   both passed through `realpathSync` and share drive-letter casing.
2. Prefer topology over prefixes: `const relInside = relative(BASE, targetFile)` and accept
   iff `relInside !== '' && !relInside.startsWith('..') && !isAbsolute(relInside)`.
   `path.relative` already applies win32 semantics (case-insensitive drive/components, both
   separators) on Windows and POSIX semantics on Linux, so one code path is correct on both.
   (Equivalent alternative: case-insensitive `startsWith` comparison of lowercased strings
   on `process.platform === 'win32'` — but `relative` is the robust, self-documenting form.)
3. Keep a symlink-escape check only if `lib/` can contain symlinks pointing outside — i.e.
   `realpath` the *target* and re-check against the realpath'd base, which step 1–2 already do.

Why robust on both platforms: the base and the target are both products of `realpathSync`, so
no cross-API casing mismatch exists; `path.relative` handles separator and case differences
per platform; traversal (`../`) and absolute-path injection still fail the `relInside` checks
on both platforms.

**Other serving requirement for dynamic `import()` to work at all:** the browser refuses to
execute a dynamically imported script unless it is served with a **JavaScript MIME type**
(`application/javascript`/`text/javascript`; the route already sets
`'application/javascript; charset=utf-8'` — losing that header, or falling back to
`application/octet-stream`/server default, makes the import fail with a MIME error even on a
200). Same-origin serving avoids any CORS requirement; if the chunk were ever served
cross-origin, correct `Access-Control-Allow-Origin` would additionally be mandatory.

## 4. Incident 3 — why BOTH handlers fire on one Ctrl+scroll

**Mechanism.** `wheel` is a bubbling DOM event. The zoom modal's Ctrl+scroll handler and the
pane's font-size (Ctrl+scroll) handler are registered at different nodes of the same ancestor
chain (typically modal-root vs pane/document/window). One physical Ctrl+wheel over the modal
target propagates: target → … → modal root (modal handler fires, zooms the diagram) → … →
pane/document (font handler fires, resizes pane font). Neither handler consumes the event or
checks ownership of the target, so both effects run simultaneously. Listener *registration
order* is irrelevant across different nodes — propagation, not ordering, delivers the event to
both.

**Ownership rule.** Exactly one Ctrl+wheel owner at a time, enforced at the boundaries:

- The **innermost active UI owns the gesture**: while the modal is open, the modal handler
  must `preventDefault()` **and** `stopPropagation()` (or the modal renders in a portal whose
  subtree the pane listener can never see), so nothing outside the modal observes the event.
- The pane handler must be **target-ownership-aware**, not just position-aware: ignore any
  wheel event whose `target`/`composedPath()` lies inside the open modal (or check an
  `isModalOpen` state) — belt and braces, because `stopPropagation` cannot protect against
  listeners registered on `window` with `capture: true` unless the modal also captures first.
- Symmetrically, when the modal is closed its handler must be removed (registered via
  `ctx.effect` with its disposer), so no stale listener competes for the gesture.

## 5. Regression tests that would have caught incidents 1–3

**R1 — chunk-graph completeness (incident 1).** A build-artifact gate, run in CI after bundling:
scan every emitted `.js` in `lib/` for relative `import`/`export ... from` specifiers and
assert each referenced file exists in the shipped package manifest/`files` list. Fails when
97 sibling chunks are emitted but unshipped. Complement with a served-route smoke test: a
headless page `await import(routeUrl('/dsh-attach-input/resources/mermaid-chunk.js'))` —
asserting the *module graph* loads, not merely that the entry URL returns 200 (the 8.1 kB 200
in the capture is exactly what a URL-only check would have green-lit).

**R2 — containment guard vs drive-letter casing (incident 2).** Unit tests for the route
handler, parametrized over casing:

- `LIB_DIR = 'E:\\...\\lib'` while `realpathSync` is stubbed/actually returns
  `'e:\\...\\lib\\mermaid-chunk.js'` → must respond **200** (this is the exact production
  failure; fails on the current `startsWith` code).
- traversal `/dsh-attach-input/resources/..%2F..%2Fsecret.js` → 403 on both platforms;
- symlink inside `lib/` pointing outside → 403;
- non-`.js` → 404, non-GET → 405.

Critically, run the suite on a **`windows-latest` CI runner with the repo on an uppercase
drive** (or inject mixed-case `LIB_DIR`), not only the Linux container — the Linux matrix row
can never exercise drive-letter normalization, which is why attempt 2 shipped "all green".

**R3 — Ctrl+wheel ownership (incident 3).** DOM-level test with spies:

- modal open: dispatch `WheelEvent('wheel', { ctrlKey: true })` on a node inside the modal →
  assert modal-zoom spy called exactly once, pane-font spy **not called**,
  `defaultPrevented === true`;
- modal closed: same dispatch on pane content → pane-font spy called, modal spy not called
  (listener disposed);
- capture-positioned variant: pane listener on `window` with `capture: true` still must not
  fire while the modal is open (verifies the ownership check, not just
  `stopPropagation` ordering).
