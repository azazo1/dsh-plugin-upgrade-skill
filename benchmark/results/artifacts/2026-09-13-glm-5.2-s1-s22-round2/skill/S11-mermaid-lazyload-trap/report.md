# S11 · Mermaid Lazy-Load Trap — Diagnosis Report

Task: read-only diagnosis of three rollout incidents in `@org/dsh-attach-input` v0.4.0
(lib-only bundle) after adding mermaid rendering as a lazily-imported chunk served by a new
host prefix route. Mode A (inspect) per the plugin-upgrade skill: no files under the fixture
were touched; no builds, installs, or migrations were executed.

Evidence reviewed: `fixture/chunk-route.ts`, `fixture/console-split-chunks.txt`,
`fixture/console-403-windows.txt`, `fixture/ci-note.md`.

---

## 1 · Incident 1 — why default code-splitting broke the dynamic import

**Observed:** `mermaid-chunk.js` itself loads (200, 8.1 kB), then sibling imports
(`src-BfvxrPJe.js`, `pie-WAS4IAKB-CQHCQWWM.js`, …) 404, and the whole `import()`
rejects with `TypeError: Failed to fetch dynamically imported module`. The fixture's own
`ls` note confirms it: the sibling files listed in the chunk's import statements were **not
shipped with the package**.

**Mechanism.** A dynamically imported ES module is not executable on its own. When the
bundler applies default code-splitting, the "entry" chunk it emits for the lazy import
contains *static* `import` statements pointing at the sibling chunks the splitter carved
out (shared modules like `src-*.js`, per-diagram renderers like `pie-*.js` — mermaid alone
produces ~100 of them). The browser's module loader must resolve and fetch **every** static
import of the chunk before it can instantiate the module graph; a single 404 anywhere in that
graph makes the entire `import()` promise reject — the error names the entry URL even though
the failing requests are the siblings. Because the plugin is published as a lib-only bundle,
the packaging step shipped the one file it knew about and silently dropped the 97 hashed
siblings the splitter had generated alongside it. (Hashed filenames also make this fragile
even if they *were* shipped: any mismatch between the built file list and the packed file
list fails only at runtime.)

**Build-side fix.** Make the lazy chunk self-contained so it has **zero sibling imports**:

- With Rollup/Vite: build the mermaid entry with `output.inlineDynamicImports: true`
  (single-entry, no splitting), or `manualChunks` collapsed so everything lands in one file;
- With esbuild: `splitting: false` (default) plus `--bundle` and `format=esm`, with mermaid
  marked non-external;
- Verify by construction: the emitted chunk's only external references are bare
  `node:` builtins at most, and no `import "./<hash>.js"` statements remain.

The alternative — shipping and serving all 98 chunks — also works but couples the route, the
packager, and the bundler's hash churn; the single-file chunk is the robust choice for a
lib-only plugin.

---

## 2 · Incident 2 — the exact guard flaw behind the Windows 403

**Observed:** every chunk GET returns 403 with the log showing the *realpath* containment
branch fired, for a path plainly inside the lib dir. The debugging print in `ci-note.md`
is the smoking gun:

    LIB_DIR   = "E:\dsh\...\lib"                          ← uppercase E
    realpath  = "e:\dsh\...\lib\mermaid-chunk.js"        ← lowercase e

**Mechanism — what each API returns on each platform.**

- `new URL('.', import.meta.url)` → `fileURLToPath` → `normalize` produces `LIB_DIR`
  with the **drive-letter casing the module URL was spelled with** — here `E:\`.
- `fs.realpathSync` does not "return the input normalized": it resolves the path through
  the OS's canonical device/object naming. On Linux it returns the same string modulo
  symlinks (the filesystem is case-sensitive, so casing cannot drift — CI passes). On
  **Windows**, which is case-*insensitive* but case-*preserving*, libuv's realpath resolves
  the drive letter to whatever casing the mounted volume object reports — `e:\` on the
  production host — and may also normalize short (8.3) name components to their long forms.
  So `abs.startsWith(LIB_DIR + sep)` succeeded (both are `E:`-spelled string joins of the
  same literals), but the *second* check `realpathSync(abs).startsWith(LIB_DIR + sep)`
  compares `"e:\..." .startsWith("E:\...")` — **a byte-wise, case-sensitive string
  comparison between two spellings of the same case-insensitive path** — and fails.

The platform matrix in `ci-note.md` matches exactly: Linux CI green (case-sensitive, no
drift); the maintainer's laptop green *because* "lowercase c:\ in some tooling" — there the
module URL and the realpath happened to agree on casing; production on `E:\` broke because
they disagreed. "Windows paths are unreliable" is folklore; the precise statement is:
**on Windows, two APIs can return different drive-letter (and component) casings for the
same file, and `String.prototype.startsWith` is a case-sensitive containment test.**

---

## 3 · Fix direction for the guard + the other serving requirement

**Guard fix.** Do containment with `path.relative`, not `startsWith`:

```js
import { relative, isAbsolute } from 'node:path'
const LIB_ROOT = realpathSync(LIB_DIR) // resolve once at startup, same API as the file check

const rel = relative(LIB_ROOT, file /* already realpathSync'd */)
if (rel === '' || rel.startsWith('..') || isAbsolute(rel)) { /* 403 */ }
```

Why robust on both platforms:

- `path.win32.relative` performs **case-insensitive** prefix matching when computing the
  common path (it lowercases for comparison), so `e:\` vs `E:\` still yields a clean
  relative remainder — while `path.posix.relative` on Linux stays an exact case-sensitive
  subtraction, preserving the strictness a case-sensitive filesystem requires. Using
  `relative`+(`..\`/absolute) rejection is the canonical containment idiom and is also
  immune to trailing-separator and `\\?\\`-prefix edge cases that plague `startsWith`.
- Comparing a **realpath'd base against a realpath'd target** additionally removes
  symlink-escape and 8.3-short-name differences on both platforms, which is exactly what the
  (broken) second check was trying to buy.
- Belt-and-braces on Windows: also `toLowerCase()` both sides before any residual string
  comparison; never rely on drive-letter casing stability.

**Other serving requirement for `import()` to work at all:** the route must serve the chunk
with a **JavaScript MIME type** — `Content-Type: application/javascript` (with charset).
A module fetched via dynamic `import()` is executed as a module script; per the HTML spec a
JS MIME type is required, and with `X-Content-Type-Options: nosniff` (which the DSH web
server sets) a wrong/missing type makes the browser refuse execution with exactly the same
"Failed to fetch dynamically imported module" symptom as a 404/403. The current route already
sends it — it must keep doing so for every code path, and the same requirement applies
per-sibling-chunk if splitting is ever re-enabled. (Same-origin serving also avoids any CORS
preflight concern; the route must stay on the host origin.)

---

## 4 · Incident 3 — why both Ctrl+scroll handlers fire under the modal

**Mechanism.** A `wheel` event **bubbles**. The diagram node the user scrolls over sits
inside the fullscreen modal, which itself sits inside the pane whose font-size Ctrl+scroll
zoom listener is attached to an ancestor (or to `window`/`document`). One Ctrl+scroll
therefore travels the *entire* propagation path: the modal's zoom handler fires first at the
inner node, then — unless something stops it — the same event object reaches the pane's
font-size handler on the ancestor. Both effects apply to the same gesture. Listener
*registration order* is irrelevant here: the two handlers are on **different nodes**, so DOM
propagation order (inner → outer) alone decides who runs, and nothing in the code severs the
chain. (If both were on the *same* node, order would be registration order and only
`stopImmediatePropagation` would help.)

**Ownership rule that fixes it.** *The innermost interested UI owns the gesture, and it must
consume it:* while the fullscreen modal is open, its non-passive
(`{ passive: false }` — needed to make `preventDefault` work for wheel) handler on the
modal root calls `event.preventDefault()` **and** `event.stopPropagation()` on Ctrl+scroll,
then removes itself (or re-arms the gate) when the modal closes — via `ctx.effect()-owned
disposers so plugin stop/update also tears it down. Defensively, the pane-level handler must
also *ignore* events not belonging to it: bail out when
`event.composedPath().includes(modalRoot)` (or an "modal open" flag). Do not depend on
z-order, focus, or handler ordering — ownership is asserted by stopping propagation plus an
explicit origin check in the outer handler.

---

## 5 · Regression tests that would have caught each incident pre-release

**Incident 1 — chunk self-containment / packed-completeness (build + e2e):**
1. *Build artifact test:* after building the client bundle, read the emitted
   `mermaid-chunk.js` and extract every static import specifier; assert the set is empty
   (or that every referenced file exists in the output dir **and** in `npm pack --dry-run`'s
   file list — catches "built but not shipped").
2. *Serving e2e:* with the route mounted, request `/resources/mermaid-chunk.js`, walk its
   import specifiers, and GET each through the route expecting 200 — the exact failure mode
   of attempt 1 (siblings 404) fails this test loudly.

**Incident 2 — casing-robust containment (route unit tests):**
1. *Drive-letter case:* mock/stub `realpathSync` (or run on Windows against a path whose
   realpath returns a differently-cased drive, e.g. `e:\` vs `E:\`) and assert
   `GET /resources/mermaid-chunk.js` returns **200**, not 403. A property-style variant:
   for any casing permutation of the drive letter and path segments that the OS accepts, a
   file inside lib must be served.
2. *Traversal still rejected:* `/resources/..%2f..%2fsecret.js`, absolute targets
   (`/resources/E:\other.js`), and symlinked-out files must still yield 403/404 — proving
   the fix widened tolerance without opening escapes.

**Incident 3 — wheel ownership (client component test):**
1. Dispatch a `WheelEvent('wheel', { ctrlKey: true })` on a diagram node inside the open
   modal; assert (spy) the modal's zoom handler ran **and** the pane's font-size handler did
   *not* run, and that `event.defaultPrevented` is true.
2. Symmetric test with the modal closed: the pane handler runs and applies font zoom.
3. Lifecycle test: closing the modal (and plugin stop) removes the modal handler — a later
   Ctrl+scroll reaches only the pane handler.

---

## Summary table

| Incident | Root cause | Fix |
|---|---|---|
| 1 · sibling 404s | Default code-splitting makes the lazy chunk statically import 97 hashed siblings that a lib-only package doesn't ship; one 404 rejects the whole `import()` graph | Build one self-contained chunk (`inlineDynamicImports` / `splitting: false`); assert zero sibling imports |
| 2 · Windows 403 | `realpathSync` on Windows returns OS-canonical casing (`e:\`) while `LIB_DIR` from `import.meta.url` keeps the URL's casing (`E:\`); `startsWith` is a case-sensitive string test | Containment via `relative(base, file)` + `..`/absolute rejection, both sides realpath'd; case-insensitive compare on win32 |
| 3 · double zoom | `wheel` bubbles: modal handler and ancestor pane handler both receive one Ctrl+scroll; nobody stops propagation | Innermost owner consumes the gesture: non-passive handler calls `preventDefault`+`stopPropagation`; outer handler ignores events from inside the modal |

No blockers; all analysis derived from the fixture evidence. No files outside the designated
output directory were written.
