# S11 · Mermaid Lazy-Load Trap — Diagnosis Report

Plugin: `@org/dsh-attach-input` v0.4.0 (lib-only bundle), community Web plugin.
Evidence: `fixture/chunk-route.ts`, `fixture/console-split-chunks.txt`,
`fixture/console-403-windows.txt`, `fixture/ci-note.md` (read-only; unmodified).
Method: plugin-upgrade skill, Mode A (read-only inspection) — no writes outside this report.

---

## 1 · Incident 1 — why the split-chunk attempt failed

**Root cause: a dynamically imported chunk is not self-contained.** When the bundler
applies default code-splitting to `import('./mermaid')`, it emits the requested entry
chunk (`mermaid-chunk.js`, 8.1 kB — mostly the loader/glue) plus the modules of the
dependency graph as *sibling* chunks (`src-BfvxrPJe.js`, `pie-WAS4IAKB-CQHCQWWM.js`, …).
The browser fetches the entry chunk successfully (200), then parses it and issues ES-module
imports for its static dependencies *relative to the chunk's own URL*. Those sibling files
were never shipped with the lib-only package (the fixture `ls` confirms: only
`mermaid-chunk.js` was present), so every sibling request 404s. When any import in a
module graph fails, the whole dynamic `import()` rejects with
`TypeError: Failed to fetch dynamically imported module` — hence the fallback to a code
block even though the chunk the code requested returned 200.

This is pure bundler/ESM semantics, not a serving bug: the import graph must be complete
at the serving root, and content-hashed sibling names mean "ship just the entry file"
can never work with default splitting.

**Build-side fix:** make the lazily imported entry a *single self-contained chunk*:

- configure the bundler to disable code-splitting for that dynamic entry — esbuild
  `--splitting=false` (or a separate build pass for the mermaid entry without
  `splitting`), Rollup `output.inlineDynamicImports: true` (single-entry) or
  `output.manualChunks` forcing all mermaid-scoped modules into one named chunk; or
- equivalently, guarantee completeness at packaging time: include **every** emitted
  `.js` asset of the chunk graph in the published `files`/lib dir, not just the entry
  (fragile with hashed names — the single-chunk option is the robust one).

(Attempt 2 in the fixture took exactly this single-file direction; that part was correct.)

## 2 · Incident 2 — the exact flaw in the containment guard

The guard that fires is the **second** one:

```ts
file = normalize(realpathSync(abs))
if (!file.startsWith(LIB_DIR + sep)) { res.writeHead(403).end('path escapes the plugin lib'); return }
```

The flaw is an **ordinal, case-sensitive string prefix comparison between a
non-realpath'd \`LIB_DIR\` and a realpath'd file path, on a platform where the two
APIs disagree about drive-letter casing.**

Precisely, per the production debug print in `ci-note.md`:

- `LIB_DIR` comes from `fileURLToPath(new URL('.', import.meta.url))` →
  `"E:\\dsh\\profiles\\web\\node_modules\\@org\\dsh-attach-input\\lib"`
  — it inherits the drive-letter casing of the module URL, i.e. of however the app was
  launched (uppercase `E:\\` here).
- `fs.realpathSync()` on Windows resolves through the final-path API
  (\`GetFinalPathNameByHandle\`-style \`\\\\?\\\` normalization). Windows path
  semantics are case-insensitive but case-preserving, and the final path's drive-letter
  casing is normalized independently of the input string — on this host it returns the
  lowercase volume form `"e:\\dsh\\…\\lib\\mermaid-chunk.js"`.
- \`String.prototype.startsWith\` is a case-*sensitive* ordinal comparison:
  \`"e:\\…" .startsWith("E:\\…")\` is \`false\`, so a path that is plainly inside
  the lib dir is classified as "path escapes the plugin lib" → 403 on every chunk GET.

Why the matrix looked like folklore:

- **Linux CI green:** Linux has no drive letters, and on a case-sensitive fs
  \`realpathSync\` returns the same on-disk casing both sides already agree with
  (both strings originate from the same \`import.meta.url\` ancestry), so the ordinal
  prefix match holds.
- **Windows laptop (C:\\, "lowercase c:\\ in some tooling") green:** by accident —
  there the launch path's drive casing happened to match what \`realpathSync\`
  normalized to, so the comparison succeeded. Same code, coincidence of casing.
- **Production (E:\\, uppercase) red:** casing mismatch — the only variable that
  actually changed.

So the mechanism is: \`fileURLToPath\`/\`import.meta.url\` preserve the caller's
drive-letter casing; \`realpathSync\` on Windows canonicalizes it; a case-sensitive
prefix compare then fails. Nothing about "Windows paths being unreliable".

(A latent second bug of the same shape: \`LIB_DIR\` itself is never realpath'd, so any
junction/symlink inside \`node_modules\` — e.g. pnpm links — would break the guard on
*any* platform once \`realpathSync(abs)\` resolves through the link. Fixing the
comparison must address this too.)

## 3 · Fix direction for the guard + one other serving requirement

**Robust containment comparison:**

1. Canonicalize **both** sides symmetrically: \`const realLib = realpathSync(LIB_DIR)\`
   and \`const realFile = realpathSync(abs)\` (one \`realpath\`, not one side raw).
2. Compare with \`path.relative(realLib, realFile)\` and require a *stayed-inside*
   result: non-empty, not starting with \`..\`, and not absolute:
   \`const rel = relative(realLib, realFile); if (!rel || rel.startsWith('..') || isAbsolute(rel)) → 403\`.
   \`path.relative\` already applies platform-appropriate separator handling.
3. Because \`path.relative\` on Windows is still case-*sensitive* in Node, apply the
   platform's own comparison rule to the boundary: either case-fold both real paths when
   \`process.platform === 'win32'\` (or \`win32\`-vs-\`posix\` path module
   detection), or do the prefix check with a case-insensitive comparator on Windows.

Why robust on both platforms: both operands pass through the same canonicalization
(\`realpath\` twice), so symlink/junction indirection cancels; \`path.relative\`
replaces literal prefix string matching with graph-inside semantics; and explicit
case-folding on Windows matches the OS's own case-insensitive-but-preserving semantics,
so drive-letter casing (E:\\ vs e:\\) can never reject a contained file — while on
Linux the comparison stays exact, keeping true escapes rejected.

**One other serving requirement:** the response must carry a **JavaScript MIME type**
(`application/javascript` / `text/javascript`, with charset). Browsers apply strict
MIME checking to module scripts: a dynamic `import()` of a URL served as
`text/plain`, `application/octet-stream`, or without `Content-Type` is refused
("Failed to load module script: expected a JavaScript module script but the server
responded with a MIME type of …"). (Same-origin serving, as here, is the other baseline;
CORS headers would additionally be required only if the chunk were served
cross-origin.)

## 4 · Incident 3 — why both handlers fire on one Ctrl+scroll, and the ownership rule

Mechanism: `wheel` is a bubbling DOM event. The plugin attaches its zoom handler on the
fullscreen modal element, while the pane's font-size handler is attached to an *ancestor*
(or `window`/document). One physical Ctrl+scroll produces one `WheelEvent` with
`ctrlKey: true`; it dispatches at the modal target and propagates (bubble phase, and on
many setups the pane listener is also registered non-\`{passive:true}\`) to the pane's
listener. Neither handler marks the event as consumed — `preventDefault()` suppresses
the browser's default page-zoom but does *not* stop other listeners; only
\`stopPropagation()/stopImmediatePropagation()\` (or simply not being reached) does.
Also note: if either listener was registered as passive (wheel listeners default to
passive on root targets), it could not even call \`preventDefault\`. Result: the modal
zooms the diagram *and* the pane resizes its font from the same event.

**Ownership rule: the innermost/topmost active consumer owns the gesture, exactly one
handler may act per event, and the owner must terminate propagation.**

Concretely:

- the fullscreen modal's zoom handler registers in the **capture or target phase with
  \`{ passive: false }\`; when it handles a ctrl+wheel it calls
  \`event.preventDefault()\` *and* \`event.stopPropagation()\`** so no ancestor
  ever sees it; and/or
- the outer pane's ctrl+wheel font handler must **yield to descendants that claim the
  gesture**: before acting, check \`event.composedPath()\` / target containment
  against any open overlay (or a shared "zoom-owned" registry/flag the modal sets while
  open) and no-op if the event originated inside the modal.

The rule is ownership-with-explicit-handoff (one gesture → one owner), not "call
preventDefault harder": canceling the browser default never cancels other application
listeners.

## 5 · Regression tests that would have caught each incident

**Incident 1 — chunk-graph completeness (build/packaging test, runs in CI on any OS):**

- Static graph check: after \`build\`, parse the emitted \`mermaid-chunk.js\` for
  relative \`import … from "./…"\` / \`import("./…")\` specifiers and assert every
  referenced file exists in the packaged lib dir (and in the npm pack file list via
  \`npm pack --dry-run\` / \`files\` glob assertion). Fails immediately when the
  bundler emits unshipped siblings.
- Behavioral check: serve the *packed* artifact directory with the same route on a local
  port, then in a headless browser \`await import('http://127.0.0.1:PORT/…/mermaid-chunk.js')\`
  and render one \`\`\`mermaid\`\`\` fence; assert no network 404 and no
  "Failed to fetch dynamically imported module". Or (cheaper) \`node --input-type=module\`
  importing the file URL from the pack tarball.

**Incident 2 — containment guard unit tests (platform-parametrized):**

- Case-mismatch drive-letter test (the exact production signature): on Windows, register
  the route with a hand-built \`LIB_DIR\` whose drive letter is uppercase while the
  on-disk realpath canonicalizes to lowercase (and vice versa); request
  \`/…/resources/mermaid-chunk.js\` and assert **200 + correct body**, not 403. Keep a
  paired escape case (\`/../escape\`, absolute \`C:\\windows\`, encoded
  \`%2e%2e\`) asserting 403 — proving the fix did not weaken containment.
- Symmetric-realpath test: put the lib dir behind a junction/symlink (as pnpm does) and
  assert contained requests still pass on Linux and macOS.
- Route-level integration test: boot the real route handler against a temp lib tree and
  assert status codes (200 contained, 404 missing/non-js, 403 escape, 405 non-GET,
  and \`Content-Type: application/javascript\` on 200s). Run the matrix on
  `windows-latest` **with an explicitly case-flipped drive reference**, which is what
  the maintainer's laptop was silently missing.

**Incident 3 — gesture-ownership component test:**

- Mount the modal over the pane with spies on both handlers; dispatch
  \`new WheelEvent('wheel', { ctrlKey: true, deltaY: -100, bubbles: true, cancelable: true })\`
  on a node inside the modal; assert **modal zoom spy called exactly once and pane
  font-size spy not called** (and \`event.defaultPrevented === true\`).
- Inverse case: wheel outside the modal → pane handler called, modal handler not.
- Assert the modal's listener is registered \`{ passive: false }\` (e.g. via
  \`cancelable\` handling in the test) so \`preventDefault\` is effective in
  production browsers' passive-by-default wheel listeners.

---

## Status summary (skill report format)

- **pre-existing / baseline:** not collected (Mode A read-only inspection of a static
  fixture; no builds or tests were run, per the task's no-execution boundary).
- **Completed:** root-cause analysis of incidents 1–3 from the evidence pack; fix
  directions (single self-contained chunk; symmetric realpath + \`path.relative\` +
  platform-aware case comparison for the guard; JS MIME requirement; capture-phase
  non-passive owner + \`stopPropagation\` / composedPath yield rule); regression-test
  plan per incident.
- **Skipped:** none of the four evidence files was unused; no runtime verification was
  possible (fixture is static and read-only by design).
- **Pending/residual risk:** the exact bundler used by \`@org/dsh-attach-input\` is
  not in the evidence, so the single-chunk config is named per-tool (esbuild/Rollup)
  rather than as a ready patch; the drive-letter normalization Node applies can vary by
  how the volume is referenced, so the Windows case-flipped CI job is the decisive guard.
- **Recommendations:** serve plugin chunks under a host-provided static-resource seam
  (if the DSH host offers one) instead of a hand-rolled containment route; add the
  packed-artifact import test to the release checklist for any lazily imported code.
