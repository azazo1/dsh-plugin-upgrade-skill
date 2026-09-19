# S19 Diagnostic Report — The Phantom Update, the Stale Host Half, and the Corrupted Payload

Plugin: `@dsh-external/dsh-file-trace` (v0.3.7 markdown fix; v0.3.8 SVG render preview). All findings are grounded in the read-only evidence pack (`release-log.md`, `client-bundle-excerpt.js`, `asset-route-probe.txt`, `lib-index-excerpt.js`, `git-tags.txt`, `session-log-excerpt.txt`, `package.json`, `README.md`).

## 1. Phantom self-update root cause (released v0.3.7 announces "新版本 v0.3.7 可用" against itself)

**Where the compared version constant comes from — build time, not runtime.** The shipped bundle excerpt (`client-bundle-excerpt.js`) states verbatim:

> `export const PLUGIN_VERSION = "0.3.6";`
> `// tsdown inlined this constant from package.json WHEN THE BUNDLE WAS BUILT — it is not read dynamically at runtime.`

The update check compares `compareSemver(latestTag, PLUGIN_VERSION) > 0`. So the running client believes it is **0.3.6** because the bundle was compiled before the version bump.

**The actual operation-order mistake.** `release-log.md` records the exact sequence for v0.3.7:

1. 16:22 `pnpm run build` — "← build ran here"
2. 16:23 "bump `package.json` version 0.3.6 → 0.3.7 — ← version bumped AFTER the build"

The build therefore baked `0.3.6` into the artifact that was tagged and pushed as v0.3.7. The self-update check fetched the mirror tags (`git-tags.txt`: all three mirrors list `v0.3.7` and `v0.3.8` with identical SHAs) and picked the highest tag `v0.3.7`; since `compareSemver("v0.3.7", "0.3.6") > 0`, `newerTag("v0.3.7")` returned `"v0.3.7"` and the badge rendered on the very release that already contains it. The release log itself prescribes the fix: "the rebuild order was corrected for v0.3.8 (bump FIRST, then build)."

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows the tag SHA `748b5e5...` for v0.3.7 identical across origin/public/omdsh — the release log confirms "`git ls-remote` verified the tag SHA on all three". Distribution was perfect; the *content* committed was wrong (a bundle with a stale baked constant). No mirror, auth, or tampering problem can produce or fix this symptom — the badge is correct arithmetic over a stale constant.

**Corrected release order and the catching check.**

- Order: bump `package.json` **first**, then `pnpm run build`, then commit (with the freshly built `lib/client.js`), tag, push, verify tag SHAs.
- Pre-push check: grep the shipped bundle for the baked constant — e.g. `grep -o 'PLUGIN_VERSION = "[^"]*"' lib/client.js` must output the value just written to `package.json` (here `0.3.7`; the shipped artifact had `0.3.6`, which would have failed). Equivalently, fail the release if the emitted bundle does not contain the manifest version string.

## 2. Client vs host plane update asymmetry (new toggle visible, yet the SVG route 404s)

**Where each half is loaded and when.**

- *Client half:* served from the built `lib/client.js` and re-fetched by the browser; a page refresh/reload loads the new bundle. Evidence: after the v0.3.8 push "the client UI showed the new render toggle" and `release-log.md` notes "the client half was confirmed refreshed: the new toggle button was rendered by the browser."
- *Host half:* route registration and its `CONTENT_TYPES` whitelist are loaded **once at host boot** into the long-running DSH process. Updating files on disk (or re-linking the repo) does nothing to the already-registered route.

**How the probes pin the staleness to the RUNNING host process.** `asset-route-probe.txt` (executed after the browser was confirmed refreshed, host NOT restarted):

- PNG probe → `200 OK, content-type: image/png` — the route handler is alive and serving; the route is not missing.
- SVG probe → `404 "unsupported image type"` — a whitelist rejection from the running handler.
- Disk: `lib-index-excerpt.js` (shipped host half at tag v0.3.8) verbatim contains `svg: 'image/svg+xml'` in `CONTENT_TYPES`.

Three facts together: route alive (200 PNG) + svg rejected (404) + disk whitelist includes svg ⇒ the executing handler holds the **pre-change** whitelist. The release content is correct; the running host process predates it. The release-log notes exactly this: "a host restart had NOT been performed in this session."

**What makes a host-plane change effective.** A host restart, so boot-time route registration re-runs against the new `lib/index.js`. This is the one case where the usual "plugins hot-update" rule does not hold: hot update refreshes client bundles on reload, but host-side code (routes, whitelists, handlers) lives in the already-booted process and only reloads when the host itself does.

## 3. Broken-image attribution (traced SVG renders broken; source is fine)

**Where the corruption happened.** `session-log-excerpt.txt` shows:

- Stored read-result text at line 232: `<circle r="98" fill="none" stroke="#dde6ea" stro0,1 821,730" fill="none" ...` — a splice of source line 232 up to the shared prefix `"stro"` with the tail of source line 247 (`"0 0,1 821,730"`, the arc flags); source lines 233–247 are absent from the payload.
- The source file on disk is clean: line 232 `<circle r="98" ... stroke-width="6.5"/>`, ..., line 247 `<path d="M 587,730 A 122,122 0 0,1 821,730" ...`.
- Verdicts: "source file: well-formed (System.Xml XmlDocument load: no error)"; "log payload: NOT well-formed — error on line 233 at column 54: Specification mandates value for attribute stro0".
- The excerpt pins the layer: "The read tool's TYPE result delivered to the caller was clean; the corrupted text is the model-visible result block persisted into the session log, i.e. **the corruption happened in the result-text assembly, upstream of the plugin**." A re-read afterwards "came back clean (non-deterministic)" — a flaky upstream defect, not a property of the file.

**Why the plugin must treat the session payload as untrusted rendering input.** The payload the plugin receives (or reconstructs from the log) is not guaranteed to equal the file bytes: the upstream assembly layer has been observed to splice lines non-deterministically. Render input must therefore be validated (XML well-formedness) regardless of provenance, with a fallback to authoritative disk bytes.

**Why editing/repairing the traced file would have been wrong.** The file on disk is well-formed — "repairing" it would corrupt a good asset to match a corrupted copy, hiding the real defect. The wrong text exists only in the session log; the correct actions were to re-read (which came back clean) and report the upstream result-text-assembly bug. Papering over it in the plugin would also mask future, genuinely different corruptions.

## 4. Defensive render chain for the SVG preview

Render-source order, each level justified:

1. **Disk-bytes asset route first.** The file on disk is the authoritative artifact; the asset route serves exact bytes (the PNG 200 proves the route works once the host is restarted with the svg whitelist). Using disk bytes bypasses any session-log corruption by construction.
2. **Session payload only after an XML well-formedness check (DOMParser / `parsererror`).** The session log is a legitimate but untrusted fallback source (item 3 proved it can be spliced). `DOMParser` + checking for a `parsererror` element turns "is this the file?" into a cheap, decisive test; the corrupted payload here fails with "Specification mandates value for attribute stro0" and is rejected before rendering.
3. **Sandboxed iframe as the last render fallback.** An `<iframe sandbox>` (no `allow-scripts`) blocks embedded `<script>` while SMIL animations still run, so decorative traced artwork animates safely even when the SVG comes from a less-trusted path. Sandboxing is essential because an SVG document can carry scripts.
4. **Explicit error state instead of a silent broken image.** If all sources fail validation, show a typed error ("SVG failed well-formedness check; re-read the file") rather than a blank/broken glyph. The evidence shows how easily a broken image is misread as a file defect — an explicit state names the actual failing layer and prevents the wrong repair.

## 5. Forensics method + prevention checklist

**Decoding the session log frame-by-frame.** The session log is a concatenated-Zstandard generation file: a sequence of independently compressed zstd frames concatenated back-to-back. Decode it by reading the byte stream and decompressing frames sequentially (a streaming zstd decoder, or a framing pass that finds each frame boundary and decompresses per frame), then project each decoded event to text. That is exactly how `session-log-excerpt.txt` was produced — it recovers the *exact stored* read-result text (with the `stro0,1 821,730` splice), which — compared against the clean disk file and an XML well-formedness verdict on both — converts "the image looks broken" into a located, reproducible upstream bug with byte-level evidence. The clean re-read plus the non-determinism note completes the attribution.

**Release-checklist items this incident adds:**

1. **Version-bump-before-build**: `package.json` bump is step 1; `pnpm run build` only afterwards (the v0.3.8 correction recorded in `release-log.md`).
2. **Grep the shipped bundle for the baked constant**: assert `PLUGIN_VERSION = "0.3.7"` (the newly bumped value) appears in the emitted `lib/client.js` before commit/tag; fail the release otherwise. This would have caught the v0.3.7 phantom badge (`0.3.6` was baked in).
3. **Per-mirror tag SHA verification**: `git ls-remote --tags` on origin/public/omdsh, all SHAs identical (`git-tags.txt` pattern) — necessary but never sufficient on its own (it passed on the broken v0.3.7).
4. **Host-plane changes require a host restart**: after shipping host-half changes (routes/whitelists), restart the host and re-probe (PNG 200 *and* SVG 200) before declaring the feature live.
5. **Report upstream text-corruption instead of papering over it**: when a render defect traces to a spliced session payload with a well-formed source file, file the bug against the result-text assembly layer, validate payload input in the plugin, and never "fix" the healthy source file to match corrupted stored text.
