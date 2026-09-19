# S11 · Mermaid Lazy-Load Trap — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.4.0 (community Web plugin, lib-only bundle). Evidence inspected read-only from the fixture pack: `README.md`, `chunk-route.ts`, `console-split-chunks.txt`, `console-403-windows.txt`, `ci-note.md`. No fixture file was modified; no migrations or installs were run. Diagnosis follows the plugin-upgrade skill's read-only inspection posture (Mode A): root causes derived from primary evidence, fixes proposed but not applied.

## 1. Incident 1 — why default code-splitting broke the lazy import

**Evidence.** `console-split-chunks.txt`: `mermaid-chunk.js` loaded with **200** (8.1 kB), then `GET .../resources/src-BfvxrPJe.js 404` and `GET .../resources/pie-WAS4IAKB-CQHCQWWM.js 404`, followed by `TypeError: Failed to fetch dynamically imported module` and the plugin's own `fell back to code block` log. The captured `ls` note says it directly: "mermaid-chunk.js WAS present; the sibling files listed in its import statements were NOT shipped with the package."

**Root cause.** With bundler-default code-splitting, a dynamically imported entry is not one file: the bundler emits the entry chunk **plus shared/sibling chunks** for any module graph the mermaid entry shares with other code (mermaid internally uses further dynamic imports per diagram type — hence `pie-WAS4IAKB.js`). Each emitted chunk contains static `import` statements referencing its hashed siblings. A browser executes a dynamic `import()` by fetching the entry and then resolving **every** static import in it; any missing sibling fails the whole module graph, so the top-level `import()` rejects even though the entry file itself was served with 200. The maintainer shipped a lib-only bundle (one file), so 97 sibling chunks simply never existed on disk — the route was never the problem in attempt 1; the 404s are genuine "file not shipped" failures.

**Build-side fix.** Emit the mermaid lazy-load target as a **single self-contained chunk**: build it as its own bundler entry (or use `output.inlineDynamicImports` for that entry / a `manualChunks` config that forces everything reachable from the mermaid entry into one file), so the emitted artifact has no runtime-relative imports to siblings. This is exactly what attempt 2 did (a 7.2 MB single chunk per `console-403-windows.txt`), which is the correct direction. Regression-proof it by asserting post-build that the chunk contains no relative import specifiers pointing at files outside the emitted output (see §5).

## 2. Incident 2 — the exact guard flaw behind the Windows 403

**Evidence.** `console-403-windows.txt`: `GET /dsh-attach-input/resources/mermaid-chunk.js 403`, and the route log shows the guard branch fired ("path escapes the plugin lib") "for a path that is plainly inside the lib directory." `ci-note.md` gives the decisive debugging print from the production host:

```
LIB_DIR   = "E:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib"
realpath  = "e:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\mermaid-chunk.js"
```

Note the drive letters: `E:` vs `e:`.

**Mechanism, precisely.** The guard in `chunk-route.ts` is:

```ts
const abs = normalize(join(LIB_DIR, rel))
if (!abs.startsWith(LIB_DIR + sep)) { ... 403 ... }
file = normalize(realpathSync(abs))
if (!file.startsWith(LIB_DIR + sep)) { ... 403 ... }
```

Two Windows behaviors combine:

- `fileURLToPath(new URL('.', import.meta.url))` + `normalize` preserve the **casing as written in the module URL** — here the uppercase `E:\` from how DSH was installed on the production host. `path.win32.normalize` never changes letter case.
- `fs.realpathSync` on Windows resolves through the OS, and **Win32 path resolution is case-insensitive but case-preserving, returning the canonical stored casing of the path components** — on that host the resolver reports a lowercase drive letter, yielding `e:\...`. The maintainer's own CI note corroborates that this is environment-dependent: the laptop shows "lowercase c:\ in some tooling".

The containment check is a **case-sensitive** `String.prototype.startsWith`. On Linux, ext4 paths are byte-comparably case-sensitive and both sides of the comparison derive from the same source, so the prefix always matches (CI green). On the Windows Server 2022 production host, `"e:\\dsh\\...".startsWith("E:\\dsh\\..." + sep)` is `false` purely because of the drive-letter case mismatch, so a file inside the lib directory is rejected as "escaping" it. On the laptop both spellings happened to agree, which is why the bug looked environment-flaky rather than deterministic — "Windows paths are unreliable" is the wrong takeaway; the string comparison is what is unreliable.

## 3. Fix direction for the guard, plus the other serving requirement

**Guard fix.** Replace the raw `startsWith` prefix checks with a containment test built on `path.relative`, which delegates case-sensitivity to the platform implementation (`path.win32.relative` compares Windows path components case-insensitively — drive letters included — while `path.posix.relative` stays case-sensitive, correct for Linux):

```ts
function insideLib(candidate: string): boolean {
  const rel = relative(LIB_DIR, candidate)
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))
}
```

Apply it to the `realpathSync` result (keeping the realpath step — it is what defeats symlink/junction escape and `..` traversal via canonicalization, and its `ENOENT` → 404 mapping is already correct). Why robust on both platforms: `path.relative` produces `..` segments for anything outside the base and an empty/relative result for anything inside; on Windows its internal comparison folds case, so `e:\...` vs `E:\...` no longer false-positives; on Linux nothing changes because POSIX paths are genuinely case-sensitive. (Lowercasing both sides before `startsWith` would also fix this instance, but `path.relative` is the platform-idiomatic containment primitive and handles mixed separators cleanly.)

**Other serving requirement for a dynamic `import()` to work at all.** The response must be delivered **same-origin with a JavaScript MIME type** — module scripts are strictly blocked when served as `text/plain`/octet-stream. `chunk-route.ts` already sends `content-type: application/javascript; charset=utf-8`; that header must be preserved, and the route must be reachable on the same origin as the page (`127.0.0.1:3080`, as in the captures) since ES module imports get no CORS slack. Relatedly, with a single un-hashed 7.2 MB chunk, serve it with sane cache semantics (e.g. `no-cache` or a versioned URL) so a plugin upgrade cannot leave browsers executing a stale chunk — a failed dynamic import is cached per document and manifests exactly like the fallback log line in both incidents.

## 4. Incident 3 — why BOTH Ctrl+scroll handlers fire, and the ownership rule

**Evidence.** Brief item 3: in the new fullscreen zoom modal, Ctrl+scroll resizes the diagram **and** the pane font size simultaneously. The modal is an overlay inside the same document as the markdown reading pane (not a separate window), so one wheel-event dispatch path serves both.

**Mechanism.** Ctrl+wheel zoom handlers are conventionally attached at container/window level with `{ passive: true }`. The reading pane's font-size zoom handler is such a listener on the pane/window ancestor; the modal's diagram-zoom handler is another, on or inside the overlay. Wheel events **bubble** from the event target inside the modal up through the overlay to the shared ancestors, so one gesture reaches both listeners: the modal handler zooms the diagram, and the bubbled event then hits the ancestor pane handler which zooms the font. Neither handler cancels the event, so both effects apply to a single scroll. (Dispatch order is DOM order — target-phase modal handler first, then bubbling ancestors — but both run regardless of registration order because nothing stops propagation.)

**Ownership rule.** The **topmost interactive surface owns the gesture**: while the fullscreen modal is open, the ctrl+wheel gesture belongs exclusively to the modal. Concretely:

- The modal's ctrl+wheel handler calls `event.preventDefault()` and `event.stopPropagation()` (or `stopImmediatePropagation()` if other handlers sit on the same node) so the bubbling pane handler never sees the gesture. The modal's handler must be the non-passive one; `passive` pane handlers cannot preventDefault anyway, which is exactly why cancellation belongs at the modal.
- Symmetrically, the pane's font-zoom handler must ignore events whose target is inside the open modal (`if (modal.contains(event.target)) return`), as defense for capture-phase or window-level handlers that bypass bubbling.

One owner per gesture, decided by z-order/containment — never "both listeners do their thing".

## 5. Regression tests that would have caught incidents 1–3 before release

1. **Incident 1 — bundle self-containment test (build gate).** After the bundler runs, assert over the emitted mermaid chunk: (a) every static/dynamic import specifier inside it resolves to a file present in the shipped `lib/` output (resolve-and-stat pass), and (b) no bare relative specifiers to hashed siblings like `./pie-*.js` remain. This fails the build exactly when default code-splitting leaks siblings the lib-only package will not ship. Complement with a Node smoke test that `await import('./lib/mermaid-chunk.js')` loads standalone from the packed tarball.
2. **Incident 2 — route containment guard tests (host route unit tests).** Against the real handler: (a) a legitimate `GET .../mermaid-chunk.js` returns 200 + `application/javascript` **even when the realpath casing differs from `LIB_DIR` casing** — on Windows this exercises the real drive-letter behavior; on Linux CI, stub `realpathSync` to return a case-variant path to pin the same contract; (b) traversal attempts (`GET .../resources/..%2F..%2Fpackage.json`, encoded backslashes) still return 403/404 — proving the fix did not loosen containment; (c) non-GET → 405 and missing file → 404 stay intact. Case (a) reproduces today's 403 and would have caught the regression in CI via the casing stub.
3. **Incident 3 — event-ownership tests (client/DOM tests).** In a jsdom/happy-dom render of the reading pane with the modal open: dispatch a `WheelEvent` with `ctrlKey: true` on an element inside the modal and assert (a) the diagram zoom scale changed and (b) the pane font-size did **not** change. With the modal closed, the same dispatch must change the pane font size. Also spy-assert the modal handler calls `preventDefault()`/`stopPropagation()`, pinning the ownership rule rather than an implementation coincidence.

## Summary

| Incident | Root cause | Fix |
|---|---|---|
| 1 · split chunks | Default code-splitting emitted sibling chunks the lib-only package never shipped; dynamic `import()` fails whole-graph on any missing sibling (404s on `pie-*.js`, `src-*.js`) | Emit one self-contained chunk (`inlineDynamicImports`/single entry) + build gate asserting emitted imports resolve inside the shipped output |
| 2 · Windows 403 | Guard compares `realpathSync` output against `LIB_DIR` with case-sensitive `startsWith`; Windows realpath canonicalizes drive-letter casing (`E:` vs `e:`), Linux paths match by construction | Containment via `path.relative(LIB_DIR, realpath)` (case-folds on win32, case-sensitive on posix); keep realpath traversal defense; preserve JS MIME type |
| 3 · double zoom | Modal and pane font-zoom ctrl+wheel handlers both receive the same bubbling event; neither claims it | Topmost-surface ownership: modal handler `preventDefault()` + `stopPropagation()`; pane handler skips targets inside the open modal |
