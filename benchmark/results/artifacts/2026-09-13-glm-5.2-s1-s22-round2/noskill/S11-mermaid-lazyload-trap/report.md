# S11 - Mermaid Lazy-Load Trap - Diagnosis Report

Task: derive root causes for three rollout incidents of the lazily-imported mermaid chunk in @org/dsh-attach-input v0.4.0, from the static evidence pack (host route source, two console captures, CI note). Read-only analysis; no code was changed.

## 1. Incident 1 - why the split-chunk approach failed

Evidence (console-split-chunks.txt): the entry chunk mermaid-chunk.js loads with 200, then src-BfvxrPJe.js and pie-WAS4IAKB-CQHCQWWM.js return 404, and the import() promise rejects with "Failed to fetch dynamically imported module". The trailing note is decisive: the shipped lib/ contained mermaid-chunk.js but **the sibling files listed in its import statements were not shipped with the package**.

Mechanism. A dynamically imported chunk is not self-contained under default bundler code-splitting. The entry chunk itself contains import statements (import "./src-BfvxrPJe.js", import "./pie-HASH.js") for the pieces the splitter carved off (shared modules and per-diagram renderers like pie). The browser resolves those specifiers **relative to the entry chunk's URL** (under .../resources/) and fetches them as module scripts. Two things follow:

- The failure mode is *delayed*: the initial fetch of the entry succeeds, so any test that only checks "chunk reachable = 200" passes. The import() only rejects after the browser has parsed the entry and issued the sibling fetches that 404 - hence "Failed to fetch dynamically imported module" pointing at the *entry* URL, which is misleading in the console.
- Serving was never the problem in attempt 1: the route can only serve what exists. The hashed siblings were never in the published lib-only bundle - typically the package files list / .npmignore shipped only the hand-listed entry outputs, or the packaging step copied just the main chunk.

Build-side fix. Eliminate sibling chunks for this lazy boundary so one URL is the whole feature:

- Rollup/Vite: build the mermaid lazy entry with output.inlineDynamicImports = true (Vite: a dedicated config with build.rollupOptions.output.inlineDynamicImports, legal only with a single entry), producing the single self-contained chunk - exactly what attempt 2 did.
- Alternatively keep splitting but treat *all* emitted assets as publishable: add the hashed chunk pattern to the package files list and copy the full build output into the shipped lib. This stays fragile for a lib-only bundle (hash churn, easy to under-ship), so the single-file option is the robust choice.

## 2. Incident 2 - the exact flaw in the containment guard (403 on Windows, green on Linux)

Evidence (chunk-route.ts): the handler guards twice, once on the lexically joined path and once on realpathSync. The CI note's production printout is the smoking gun:

    LIB_DIR   = "E:\dsh\profiles\web\node_modules\@org\dsh-attach-input\lib"
    realpath  = "e:\dsh\...\lib\mermaid-chunk.js"

Mechanism. fileURLToPath(new URL('.', import.meta.url)) returns the drive letter **as it appears in the module URL** - uppercase E: here. On Windows, fs.realpathSync resolves through the Win32 API, which canonicalizes the drive letter to **lowercase** - Node commonly returns e:\... regardless of the input's drive-letter casing (Win32 does not guarantee drive-letter case preservation; the laptop row's "lowercase c: in some tooling" is the same phenomenon in the opposite direction). The second guard

    if (!file.startsWith(LIB_DIR + sep)) -> 403

is a **case-sensitive string prefix comparison**. "e:\dsh\...".startsWith("E:\dsh\...") is false, so every legitimate chunk GET on that host falls into the "path escapes the plugin lib" branch - matching the route log line quoted in console-403-windows.txt.

Why the matrix splits the way it does:

- Linux CI (green): on POSIX, realpathSync only resolves symlinks and preserves the exact character case; LIB_DIR was derived from the same tree, so the prefix matches. No symlinks in the container, so realpath equals the input.
- Laptop, Windows, DSH on C: (green): case coincidence. URL-derived LIB_DIR and the realpath result happened to carry the *same* drive-letter case on that machine (note the "lowercase c:" hint - both sides plausibly came out lowercase), so the string prefix matched.
- Production, Windows Server, E: (broken): URL-derived LIB_DIR uppercase E: vs realpath-normalized lowercase e: -> prefix test fails -> 403 on every chunk.

So the flaw is precisely: **a case-sensitive startsWith containment check applied to two path strings produced by APIs with different drive-letter/case canonicalization on Windows** (fileURLToPath echoes the URL; realpathSync re-canonicalizes via Win32). It is not "Windows paths are unreliable" - both APIs returned *correct* paths; only their case normalization differs, and the comparison is case-sensitive where the filesystem is not.

## 3. Fix direction for the guard, plus the other serving requirement

Robust containment comparison. Do not compare raw strings; use path.relative:

    const rel = relative(LIB_DIR, file)
    if (rel === '' || rel.startsWith('..') || isAbsolute(rel)) -> 403

path.win32.relative performs a case-insensitive same-drive comparison internally (Node lowercases both operands for Windows comparisons), so E:\... vs e:\... yields "mermaid-chunk.js", not a ".." escape; on POSIX it stays strictly case-sensitive, matching the filesystem. The isAbsolute(rel) check covers cross-drive references (Z:\other), which relative returns verbatim; the empty-string check rejects the lib dir itself. If a string compare must be kept, lowercase both sides explicitly on win32 - but relative is the platform-correct idiomatic form. Apply the same comparison to both the lexical check and the post-realpath check (keep the realpath check: it defeats symlink escapes).

Other serving requirement for import() to work at all. The response must carry a **JavaScript MIME type** - Content-Type: application/javascript (or text/javascript). Dynamic imports are module scripts, subject to strict MIME checking: the browser refuses to execute a module whose Content-Type is not a JS type regardless of status or body, so a generic file server or a missing header makes the import() fail even with a 200. The route already sets this header, so it satisfies the requirement - but it is a hard prerequisite that the regression tests must assert. (The route is same-origin with the page, so no CORS headers are needed; a cross-origin chunk host would additionally require proper CORS.)

## 4. Incident 3 - both Ctrl+scroll handlers firing under the zoom modal

Mechanism. The wheel event does not belong to either handler - it is a single DOM event that **bubbles** from the target (the diagram inside the modal) up through the modal subtree to the pane and beyond. Both listeners sit high in the tree (the pane's font-size handler on the pane/window; the plugin's zoom handler on the modal or window), both are non-passive listeners keyed on the same wheel + ctrlKey gesture, and neither calls stopPropagation(). The browser delivers the one event to every matching listener along the propagation path in registration order, so both run: the modal zooms the diagram *and* the pane's Ctrl+wheel font-size logic also fires. One gesture, two owners, no arbitration - a shared-event ownership failure, not a browser bug.

Ownership rule that fixes it. The DOM node that owns a gesture is the innermost interested ancestor, and ownership must be *exclusive while its surface is active*:

- The fullscreen zoom modal is an overlay covering the pane; while open, the modal **owns** Ctrl+wheel within its subtree. Its handler is registered on the modal element (not window), calls event.preventDefault() (stopping the browser's own Ctrl+zoom) and event.stopPropagation() so the event never reaches the pane's listener.
- Defensively, the pane's font-size handler must also check provenance: ignore any wheel event whose target / composedPath() lies inside an open overlay (e.g. target.closest('[data-fullscreen-overlay]')), or that is already defaultPrevented. Belt-and-braces matters because either half may ship before the other.
- The strictest form registers the modal handler in the **capture** phase on the modal root and stops propagation there, guaranteeing the pane listener never sees the event regardless of registration order on shared ancestors.

## 5. Regression tests that would have caught incidents 1-3

Incident 1 - under-shipped sibling chunks.
- Artifact-completeness build gate: after building, parse every emitted .js in the publish set for static/dynamic import specifiers and asset URLs; assert each relative specifier resolves to a file present in the **published** file list (npm pack --dry-run / files projection), not just in the build dir. Fails attempt 1 because src-BfvxrPJe.js etc. are imported but absent from the tarball.
- Serving test: start the real route against the packaged lib and request every emitted specifier URL; assert 200 and a JS MIME type. Attempt 1's pie-WAS4IAKB-CQHCQWWM.js 404 fails it.
- End-to-end render test: load a page containing a mermaid fence against the packaged build; assert an svg is rendered and the plugin's "fell back to code block" flag is **not** emitted. This is the only test that catches the delayed failure mode directly.

Incident 2 - case-mismatch 403.
- Guard unit tests with injected paths: run the containment predicate against the pair (LIB_DIR = "E:\dsh\...\lib", realpath = "e:\dsh\...\lib\mermaid-chunk.js") plus the lower/lower and upper/upper variants; assert "inside" in all three. The current startsWith implementation fails the mixed-case pair on any OS - the test is platform-independent and would have failed in Linux CI too.
- Traversal tests: "..%2f..%2fsecret.js" URL encoding, absolute-specifier injection, and a symlink pointing outside lib must still yield 403/404 after the fix (guards against over-correcting into permissiveness).
- Cross-platform route test: exercise the route end-to-end on a Linux **and** a Windows runner, asserting 200 + application/javascript for a file physically inside lib, ideally with a fixture forcing drive-letter case divergence between the URL-derived and realpath-derived strings.

Incident 3 - double wheel handling.
- Event-isolation test: mount the pane (with a Ctrl+wheel font-size spy) plus the open zoom modal; dispatch one WheelEvent with ctrlKey = true on a node inside the modal. Assert the modal zoom spy fired exactly once, event.defaultPrevented is true, and the pane font-size spy did **not** fire. Attempt 3's code fails this (both spies fire).
- Ordering-independence variant: register the pane listener after the modal listener (or attach both to window) and re-run - the ownership rule (modal-subtree handler + stopPropagation, or capture-phase) must hold regardless of registration order.
- Closed-modal regression: with the modal closed, Ctrl+wheel on the pane still resizes the font (ensures the ownership transfer did not break the pane's own gesture).

## Summary of fixes

| Incident | Root cause | Fix |
|---|---|---|
| 1 | Split chunks import siblings by relative URL; siblings never shipped in the lib-only package; import() rejects after sibling 404s | Single self-contained chunk (inlineDynamicImports) or ship+serve *all* emitted assets; add artifact-completeness build gate |
| 2 | Case-sensitive startsWith(LIB_DIR + sep) vs realpathSync lowercase drive-letter canonicalization on Windows (E: vs e:); Linux/laptop passed by case coincidence | Containment via path.relative (+ ".." / isAbsolute / empty checks), case-correct per platform; keep the realpath check |
| 3 | One bubbling Ctrl+wheel event reaches two non-passive high-level listeners; no exclusivity | Innermost-active-surface ownership: modal-attached (capture) handler with preventDefault + stopPropagation; pane handler ignores events originating in an open overlay |

No blockers were encountered; all analysis derives from the read-only fixture.
