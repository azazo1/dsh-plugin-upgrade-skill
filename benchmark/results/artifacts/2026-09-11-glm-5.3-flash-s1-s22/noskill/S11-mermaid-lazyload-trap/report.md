# S11 · Mermaid Lazy-Load Trap — Diagnostic Report

Evidence pack: `fixture/README.md`, `fixture/chunk-route.ts`, `fixture/ci-note.md`, `fixture/console-403-windows.txt`, `fixture/console-split-chunks.txt`.

---

## 1. Incident 1 — why the split-chunk approach failed

**What happened.** The bundler's default code-splitting emitted the mermaid entry as
`mermaid-chunk.js` plus 97 sibling chunks. `console-split-chunks.txt` shows the pattern:

```
GET .../resources/mermaid-chunk.js         200  (8.1 kB)
GET .../resources/src-BfvxrPJe.js          404
GET .../resources/pie-WAS4IAKB-CQHCQWWM.js 404
```

and the `ls` note: `mermaid-chunk.js WAS present; the sibling files listed in its import
statements were NOT shipped with the package.`

**What breaks.** A dynamically imported chunk is not self-contained. Vite/Rollup-style
splitting hoists shared modules (`src-BfvxrPJe.js`) and lazy per-diagram modules
(`pie-WAS4IAKB…`) into sibling chunks that the entry chunk references with *relative static
imports* executed at module evaluation time. The browser's module loader resolves each relative
specifier against the entry chunk's URL and fetches it. So serving the entry chunk alone is not
enough: loading `mermaid-chunk.js` immediately requests its siblings, any missing sibling is a
404, and the browser rejects the whole dynamic `import()` with `TypeError: Failed to fetch
dynamically imported module` — which the plugin catches and falls back to a plain code block.
The pack also confirms the sibling requests never even matched the package: only the entry
chunk was published, so the split graph was unrecoverable at runtime by construction.

**Build-side fix.** For a lazily-imported third-party library shipped as a lib-only plugin
bundle, build it as ONE self-contained chunk: set the bundler to inline all dynamic/static
chunks of that entry (`output.inlineDynamicImports: true` in Rollup/Vite, or an equivalent
single-file / no-manual-chunks config for the mermaid entry). Then `mermaid-chunk.js` has no
relative sibling imports and a single served file is sufficient. (If splitting must stay, the
alternative is to ship *every* emitted chunk in the package's `files`/lib dir — but for one
lazy vendor library, single-file output is the correct, simpler fix, which is exactly what
attempt 2 did.)

---

## 2. Incident 2 — the exact guard flaw producing 403 on Windows

The route's containment guard in `chunk-route.ts` is:

```ts
file = normalize(realpathSync(abs))
if (!file.startsWith(LIB_DIR + sep)) { res.writeHead(403).end('path escapes the plugin lib'); return }
```

It compares the **realpath of the requested file** against the **non-realpath'd `LIB_DIR`**,
with a **case-sensitive** `String.prototype.startsWith`.

**The mechanism.** On Windows, `fs.realpathSync` (via `fs.realpath.native`/GetFinalPathNameByHandle
semantics) returns the path with the *canonical on-disk casing of the drive letter* — it returns
**lowercase** drive letters on NTFS regardless of how you spelled the input path. `path.normalize`
does not change letter casing, and `LIB_DIR` here was built from `fileURLToPath(import.meta.url)`,
which preserves the casing as loaded (uppercase `E:`). So on the production host:

- `LIB_DIR`  = `"E:\\dsh\\profiles\\web\\node_modules\\@org\\dsh-attach-input\\lib"` (uppercase `E:`)
- `realpath` = `"e:\\dsh\\profiles\\web\\node_modules\\@org\\dsh-attach-input\\lib\\mermaid-chunk.js"` (lowercase `e:`)

(`ci-note.md` debugging session, verbatim.) `"e:\\…".startsWith("E:\\…")` is `false` — the file
is plainly inside lib, yet the guard fires `403 'path escapes the plugin lib'`, exactly matching
the console capture ("the guard branch fired … for a path that is plainly inside the lib
directory").

**Why Linux passes and why the other Windows machine passed.** POSIX paths are case-sensitive
and `realpathSync` returns the same casing as the input, so prefix comparison holds. On the
maintainer's Windows 11 laptop, `ci-note.md` records DSH "on C:\ (lowercase c:\ in some
tooling)" — there the URL-derived `LIB_DIR` happened to carry the same lowercase `c:` casing the
realpath produced, so the comparison accidentally agreed. Production is `E:\` uppercase vs
realpath's lowercase `e:`. It is not "Windows is unreliable"; it is a case-sensitive string
prefix compared across two APIs with different casing contracts.

---

## 3. Fix direction for the guard, plus the other serving requirement

**Fix.** Compare canonical-to-canonical and compare case-insensitively on win32:

1. Compute the base once, via realpath: `const LIB_BASE = normalize(realpathSync(LIB_DIR))` (with
   a startup fallback to `normalize(LIB_DIR)` if realpath fails). This alone fixes the drive-letter
   case because both sides then come from the same casing authority.
2. Do the prefix check case-insensitively on Windows:
   ```ts
   const samePrefix = (p: string, base: string) =>
     process.platform === 'win32'
       ? p.toLowerCase().startsWith(base.toLowerCase() + sep)
       : p.startsWith(base + sep)
   ```
   This is robust on both platforms: POSIX keeps exact case (case-sensitive comparison is
   required there for correctness against case-sensitive filesystems), and Windows paths are
   case-insensitive by filesystem contract, so folding case cannot merge two genuinely distinct
   locations. Also verify the char after the prefix is `sep` (already done via `+ sep`) so
   `E:\lib-evil` cannot masquerade as `E:\lib`.

**Other serving requirement for dynamic `import()` to work at all.** The chunk must be served
with a JavaScript MIME type — ES module scripts are strictly MIME-checked, and a response with
e.g. `text/plain` (or an empty/wrong type) is refused by the module loader with the same
generic `Failed to fetch dynamically imported module` error. The route already does this
(`'content-type': 'application/javascript; charset=utf-8'`) and this must be preserved through
any guard rewrite; (same-origin serving, which this host prefix route gives, is the other
prerequisite — a cross-origin chunk URL would additionally need CORS).

---

## 4. Incident 3 — why Ctrl+scroll zooms both diagram and pane font

**Why both fire.** The host pane's font-size zoom and the plugin's fullscreen zoom modal both
listen for `wheel` events with `ctrlKey === true` (the browser-standard pinch/zoom gesture) at
overlapping targets (document/window, bubble phase). Listeners on the same event propagation
path all run unless one of them stops propagation — `preventDefault()` only cancels the
browser's *default* action, it does not stop other listeners, and neither handler calls
`stopPropagation()`/`stopImmediatePropagation()`. The event bubbles from the diagram inside the
modal up through the shared ancestors where the host pane listener is attached, so one
Ctrl+scroll invokes the modal's scale handler *and* the pane's font-zoom handler. Ordering may
even be registration-order, but both run regardless of order.

**Ownership rule that fixes it.** Exactly one surface may own a gesture at a time, decided by
event-target containment: while the fullscreen modal is open and the event target is inside the
modal subtree, the modal owns Ctrl+scroll — the plugin handler must consume the event
(`preventDefault()` **and** `stopPropagation()`, or `stopImmediatePropagation()` if the host
listener is attached to the *same* node and would still run). Conversely, when the target is
outside the modal (or the modal is closed), the plugin must not intercept — the host pane keeps
its font zoom. Equivalently, the host side can implement the rule by ignoring Ctrl+wheel whose
target is contained in an open plugin modal. The key property is the containment check +
exclusive consumption, not the specific node.

---

## 5. Regression tests that would have caught incidents 1–3

1. **Split-chunk / missing-sibling (incident 1).** A packaging test that scans the built
   `mermaid-chunk.js` for every relative import specifier and asserts each resolved file exists
   in the shipped lib dir (fails on attempt 1: `src-BfvxrPJe.js`, `pie-WAS4IAKB-CQHCQWWM.js`
   absent). Stronger end-to-end variant: serve the built lib dir from the real route, dynamically
   `import()` the chunk URL in a headless page, and assert it resolves — this catches any missing
   sibling regardless of how the bundler emits it.
2. **Route containment guard casing (incident 2).** Route-level unit test for the guard that
   stubs `realpathSync` to return a path whose drive letter differs in case from `LIB_DIR`
   (the exact `ci-note.md` pair: `E:\\…\\lib` vs `e:\\…\\lib\\mermaid-chunk.js` on
   `process.platform === 'win32'`) and asserts 200, not 403; plus a genuine-escape case
   (`../..` traversal, symlinked path outside lib) asserting 403 still fires on both platforms,
   and a POSIX case-sensitivity check asserting a case-mismatched prefix outside lib is still
   rejected on Linux.
3. **MIME serving.** Assert the chunk route responds `content-type: application/javascript`
   (module-loader requirement) so a guard/serve refactor cannot regress dynamic import.
4. **Gesture ownership (incident 3).** Component/DOM test: render the markdown pane with the
   modal open, spy on the host font-zoom handler, dispatch `new WheelEvent('wheel',
   { ctrlKey: true, deltaY: -100 })` on an element inside the modal, and assert the diagram scale
   changed while the font-size handler was **not** called; then dispatch the same event with the
   modal closed (or on an outside target) and assert the host font zoom still runs. This encodes
   the ownership rule in both directions.
