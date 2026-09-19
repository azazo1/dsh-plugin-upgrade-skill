# S11 · Mermaid Lazy-Load Trap — Diagnosis Report

Evidence: `chunk-route.ts`, `console-split-chunks.txt`, `console-403-windows.txt`, `ci-note.md` (read-only fixture).

---

## 1. Incident 1 — why the split-chunk approach failed

**What happened.** The bundler was allowed to apply its default code-splitting to the lazily-imported mermaid entry. That emits not one file but a *chunk graph*: `mermaid-chunk.js` plus 97 hashed sibling chunks (`src-BfvxrPJe.js`, `pie-WAS4IAKB-CQHCQWLM.js`, …). At runtime the browser resolves each sibling import **relative to the importing chunk's URL** (`/dsh-attach-input/resources/…`). The package shipped only `mermaid-chunk.js` — the console capture confirms the sibling files "were NOT shipped with the package" — so every sibling import 404s, the module graph fails to instantiate, and `import()` rejects with `Failed to fetch dynamically imported module` even though the *first* GET returned 200.

**Root cause (bundler semantics).** Dynamic `import()` does not mean "one file". With splitting on, the entry chunk contains bare relative specifiers for its sibling chunks; those references are resolved by the *browser* at runtime, not inlined by the bundler at build time. A lazily-imported chunk is only self-contained if the build inlines its whole dependency graph. Shipping just the entry chunk of a split graph is always broken; and a route whose allowlist is a `.m?js` regex would additionally 404 any non-JS emitted assets (CSS, fonts) the graph pulls in.

**Build-side fix.** Make the lazy chunk genuinely single-file:
- Rollup/Vite: `output.inlineDynamicImports: true` for the mermaid entry (or `manualChunks` collapsing to one chunk — the point is exactly one emitted JS file with zero sibling import statements);
- or ship the *entire* `dist` output (all 98 chunks) and serve any file under it. The second attempt's "one self-contained 7.2 MB chunk" is the correct shape; the failure there was the route, not the bundling.

A build assertion should verify whichever invariant is chosen (see §5).

---

## 2. Incident 2 — the exact flaw in the containment guard

The guard is:

```ts
file = normalize(realpathSync(abs))
if (!file.startsWith(LIB_DIR + sep)) { 403 }
```

This is a **case-sensitive string prefix comparison between two strings that come from different casing authorities**:

- `LIB_DIR` is derived from `fileURLToPath(new URL('.', import.meta.url))` + `normalize`. Its drive-letter casing is whatever the loader/URL encoded — here `E:\dsh\…` (uppercase).
- `realpathSync(abs)` returns the **kernel-truth canonical path**. On Windows, the final-path-name API underneath `realpathSync` canonicalizes the drive letter from the volume device object, which routinely comes back **lowercase**: the debug print in `ci-note.md` shows `realpath = "e:\dsh\…\mermaid-chunk.js"` while `LIB_DIR = "E:\dsh\…\lib"`.

`"e:\dsh\…".startsWith("E:\dsh\…")` is `false` → 403 on a path that is plainly inside the lib dir. NTFS is case-insensitive, so the filesystem happily opened the file; only the *string* comparison failed.

**Why the matrix split the way it did:**
- **Linux CI green:** `realpathSync` on Linux returns the same bytes (no case dimension; `normalize` already canonicalized `.` segments), so the prefix comparison succeeds.
- **Laptop green:** DSH on `C:\` with "lowercase `c:\` in some tooling" — `LIB_DIR` happened to be built from a lowercase-c URL, matching realpath's lowercase output, so the comparison accidentally passed.
- **Production broken:** DSH on `E:\` with an uppercase URL-derived `LIB_DIR` vs lowercase realpath drive letter — mismatch on every request.

So it is not "Windows is unreliable"; it is *two APIs with different casing authorities compared byte-wise*, and the platforms/machines differ only in whether the two authorities happen to agree.

---

## 3. Fix direction for the guard + the other serving requirement

**Fix the comparison.**
1. **Realpath both sides**: compute `realpathSync(LIB_DIR)` once at registration, then compare the resolved file against that base. Both strings then come from the same authority (the kernel), eliminating the URL-casing divergence at the drive letter and any symlink/junction aliases under the lib dir.
2. **Compare structurally, not by string prefix**: use `path.relative(realBase, file)` and reject when the result starts with `..` or is absolute. `path.win32.relative` performs case-insensitive segment matching, so residual casing differences still resolve to a clean relative path on Windows while Linux keeps exact behavior. Prefix concatenation (`LIB_DIR + sep`) also has classic edge cases (trailing separators, exact-equal paths) that `relative` avoids.

Both together give a guard that is robust on Linux and Windows regardless of drive-letter casing.

**Other serving requirement for `import()` to work at all:** module scripts are **MIME-strict** — the browser refuses to execute a dynamically imported module unless the response `Content-Type` is a JavaScript MIME type (`text/javascript`, `application/javascript`, …). The route does set `application/javascript; charset=utf-8` and must keep doing so (a bare 200, or a generic `application/octet-stream`, fails instantiation with the same `TypeError`). If the chunk were ever served cross-origin, CORS headers would additionally be required; on this same-origin prefix route the MIME type is the operative requirement. (Relatedly, the `.m?js` allowlist means any non-JS asset the chunk graph references would 404 — moot for a truly single-file chunk, but a latent trap otherwise.)

---

## 4. Incident 3 — why both handlers fire on one Ctrl+scroll

`wheel` is a bubbling DOM event. The zoom modal's listener and the pane's font-size listener are attached to *different nodes in the same propagation path* (modal content → … → pane → document). Unless the modal's handler stops propagation, the event continues to propagate to the pane's listener, so one physical Ctrl+scroll is delivered twice: once as diagram zoom, once as pane font-size change. Registering the modal listener with `{ passive: true }` (common for wheel) makes it worse: `preventDefault()` is then impossible, so even the "handled" signal other handlers could check is absent. Ordering nuance: if the pane listens on `document`/`window` in the *capture* phase, it fires even before the modal's bubble-phase handler — so merely calling `stopPropagation()` in a bubble-phase modal listener is not sufficient either.

**Ownership rule: exactly one component owns a gesture.** The innermost component that acts on Ctrl+wheel (the modal) must, in a listener registered with `{ capture: true, passive: false }` on the modal root:
1. call `event.preventDefault()` (marks the gesture consumed, also stops browser page-zoom), and
2. call `event.stopPropagation()` (capture phase ⇒ the event never reaches any ancestor listener, bubble or capture).

Dually, the pane's handler must respect ownership: bail out when `event.defaultPrevented` is already `true`, or when `event.target` is inside the modal (`modal.contains(event.target)`). One writer per gesture; every other listener is a reader that defers.

---

## 5. Regression tests that would have caught incidents 1–3

**Incident 1 — chunk-graph completeness (build artifact test):**
- After build, parse the shipped `lib/mermaid-chunk.js` for relative `import` specifiers (or read the bundler's manifest) and assert every referenced file exists in the shipped package directory — fails when siblings are emitted but not shipped. Equivalently, assert the invariant directly: the lazy entry emits exactly one JS file (`readdir` of dist contains no `*-<hash>.js` siblings when `inlineDynamicImports` is the contract).
- E2E/page test: load a page with one mermaid fence and assert the rendered diagram exists (not the code-block fallback) and that no request under `/dsh-attach-input/resources/` returned 404. This is the direct reproduction of `console-split-chunks.txt`.

**Incident 2 — route containment guard (host unit tests against the real route handler):**
- **Case-authority test (the missing one):** request an in-bounds file while `LIB_DIR`'s drive-letter casing differs from `realpathSync`'s output; assert **200**. Deterministic on any OS by stubbing `realpathSync` to return lowercased drive letters (reproducing the production print), or by casing-mismatched fixtures on win32. The old code 403s — this test fails pre-fix.
- **Containment tests:** `..%2f..%2fsecret.js`, absolute-path smuggling, encoded backslashes, a symlink inside lib pointing outside (must 403 after realpath), non-GET → 405, non-`.js` → 404, missing file → 404.
- **MIME test:** assert the 200 response carries `content-type: application/javascript`.
- Run the suite on both `windows-latest` and `ubuntu-latest` CI; the casing test is what turns "maintainer laptop green, production red" into a red build.

**Incident 3 — gesture ownership (client/DOM test):**
- Mount the markdown pane with the zoom modal open; `dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, bubbles: true, cancelable: true }))` on an element inside the modal. Assert the pane's font-size handler spy was **not** called (or font size unchanged) and the diagram zoom callback ran exactly once. Pre-fix code fails: both spies fire.
- Variant: pane listener attached to `document` in capture phase, to pin the `capture: true` half of the fix; plus a `defaultPrevented` assertion to pin the `passive: false` requirement.

---

## Summary of fixes

| Incident | Root cause | Fix |
|---|---|---|
| 1 | Split chunk graph: entry chunk references sibling chunks resolved at runtime by the browser; siblings never shipped | `inlineDynamicImports` / single-file bundle (or ship+serve the whole graph); build assertion on emitted files |
| 2 | Case-sensitive `startsWith` between URL-derived `LIB_DIR` (E:\) and `realpathSync` output (lowercase e:\ from the Windows kernel); platforms differ only in whether the authorities agree | Compare `path.relative(realpathSync(LIB_DIR), file)` and reject `..`/absolute; realpath both sides; `relative` is case-insensitive on win32 |
| 3 | `wheel` bubbles; modal and pane listeners both on the propagation path; passive/capture misregistration | One owner per gesture: modal handles Ctrl+wheel with `{capture, passive:false}` + `preventDefault` + `stopPropagation`; other handlers defer to `defaultPrevented`/containment |
