# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Diagnostic Report

Evidence pack: `environment/fixture/` (read-only) — release of `@dsh-external/dsh-file-trace` v0.3.7/v0.3.8, 2026-09-05.

---

## 1. Phantom self-update root cause (v0.3.7 badge "新版本 v0.3.7 可用")

**Where the compared version constant comes from: build time, not runtime.**
The shipped client bundle contains, verbatim (`client-bundle-excerpt.js`):

```js
/** The running plugin version (from package.json at build time). */
export const PLUGIN_VERSION = "0.3.6";
```

with the comment that "tsdown inlined this constant from package.json WHEN THE BUNDLE WAS BUILT — it is not read dynamically at runtime." So the running browser code hard-codes `0.3.6`, baked in at build time.

**The operation-order mistake.** `release-log.md` (v0.3.7) shows:

1. 16:22 `pnpm run build` — client bundle emitted (build ran while `package.json` still said 0.3.6)
2. 16:23 bump `package.json` version 0.3.6 → 0.3.7 — **version bumped AFTER the build**
3. 16:24 `git commit` (includes the already-built `lib/client.js`) and `git tag v0.3.7`

The tag therefore ships a bundle whose baked constant is still `0.3.6`. The self-update check then runs `newerTag("v0.3.7")` against `PLUGIN_VERSION = "0.3.6"` → `compareSemver("0.3.7","0.3.6") > 0` → returns `v0.3.7` → the badge "新版本 v0.3.7 可用" renders on the just-released v0.3.7 itself. The plugin is not lying about what it fetched; it is lying about what it is.

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows all three mirrors (origin / public / omdsh) list `refs/tags/v0.3.7` at the identical SHA `748b5e56e41ca4dc22da1631569fb29d8ae0b99d` (and v0.3.8 at `d887deb0...`). The remote data is perfectly consistent — the update check correctly found tag v0.3.7 on every mirror. The defect is entirely local: the constant inside the shipped artifact. No amount of mirror or tag verification can detect a stale constant baked into the bundle at build time.

**Corrected release order** (as already adopted for v0.3.8 per the release log: "bump FIRST, then build"): edit → **bump `package.json` first** → typecheck/tests → **build** (so tsdown inlines the new version) → commit built `lib/` → tag → push mirrors → verify tag SHAs.

**Check that would have caught it before pushing:** after building, grep the emitted bundle for the baked constant — e.g. `grep -E 'PLUGIN_VERSION = "' lib/client.js` must equal `package.json`'s `version` field; fail the release if they differ. This is one of the checklist items added in §5.

---

## 2. Client vs host plane update asymmetry (client toggle visible, host route still 404)

**Where each half loads and when.**

- **Client half**: the browser re-fetches and evaluates `lib/client.js` per page load / plugin refresh. After the v0.3.8 push, the freshly served bundle contained the new SVG render toggle, and the release log confirms it was "rendered by the browser" — the client plane was refreshed.
- **Host half**: `lib/index.js` registers its routes **once, at host boot time**, when the plugin is loaded into the Node process. A later change on disk is invisible to the already-running process; route registration does not re-run until the host (or the plugin's host process) restarts.

**How the probes pin staleness to the RUNNING host process.** `asset-route-probe.txt`, executed *after* the browser was confirmed refreshed and with "host NOT restarted since before the SVG whitelist change":

- PNG probe → `200 OK / image/png` — the route handler exists and is alive, so the 404 is not a missing route.
- SVG probe → `404 Not Found / "unsupported image type"` — the running process's in-memory `CONTENT_TYPES` whitelist (built before the svg entry existed) rejects `.svg`.
- Yet the shipped, on-disk `lib/index.js` at tag v0.3.8 **does** contain `svg: 'image/svg+xml'` (`lib-index-excerpt.js`, line: `svg: 'image/svg+xml',`).

That triangulation — disk release is correct, live behavior is old, client refresh works — is only consistent with the stale code being the **running host process's in-memory state**, not the release artifacts.

**What makes a host-plane change effective — and why the usual rule breaks.** Client-plane changes take effect on browser reload, so "plugins hot-update" for anything the browser re-fetches. A host-plane change (routes, whitelist, handlers) takes effect only when the host process reloads the plugin — here, a **host restart** was never performed in the session. This is the one case where the hot-update rule does not hold: Node does not re-execute the boot-time registration path just because the files changed on disk, so the fix is simply: restart the host after pushing a host-half change.

---

## 3. Broken-image attribution (spliced session-log payload vs well-formed source file)

**Where the corruption happened: in the read-tool result-text assembly, upstream of the plugin — i.e., in the harness/session layer, not the traced file.** Evidence from `session-log-excerpt.txt`:

- The **source file on disk** is clean: line 232 reads `<circle r="98" fill="none" stroke="#dde6ea" stroke-width="6.5"/>`, and an `System.Xml XmlDocument` load reports **well-formed, no error**.
- The **session log's stored read-result text** is corrupted: line 232 is the source line up to `...stroke="#dde6ea" stro` spliced with line 247's tail `0 0,1 821,730` (from `<path d="M 587,730 A 122,122 0 0,1 821,730" ...`). Source lines 233–247 are absent; the splice lands on the shared prefix "stro" ("stroke-width…" vs line 247's arc-flag "0 0,1"). The XML verdict on the payload: **NOT well-formed — "error on line 233 at column 54: Specification mandates value for attribute stro0"**.
- Crucially, "the read tool's TYPE result delivered to the caller was clean" — the corrupted text is only the **model-visible result block persisted into the session log**. The payload the plugin received from the session was already corrupted before any rendering; a re-read came back clean (the corruption was **non-deterministic**, characteristic of a race/bug in result-text assembly, not of the file).

**Why the plugin must treat the session payload as untrusted rendering input.** The plugin's only render source here was the model/session-visible text, which is an upstream-produced artifact that can be corrupted by a harness bug independent of the actual file. Any content flowing from the session payload is, from the plugin's perspective, attacker-grade and buggy-grade input — it must be validated (well-formedness check) before being fed to the browser, never rendered blindly.

**Why editing/"repairing" the traced file would have been wrong.** The file on disk was well-formed the whole time; the splice exists only inside the session log's stored copy. "Fixing" the file would (a) corrupt a correct asset, (b) silently absorb an upstream harness bug into user data, and (c) not even address the real failure (the next corrupted payload would break again). The correct move is to attribute via forensics (§5) and report the upstream bug.

---

## 4. Defensive render chain for an SVG preview

Ordered render-source strategy, each level justified:

1. **Disk-bytes asset route first.** Fetch the SVG through the host asset route (after host restart, once the `svg: 'image/svg+xml'` whitelist is live) so the bytes come from the authoritative file on disk — the same bytes the user's file is — bypassing the session-payload assembly layer entirely. This avoids the §3 corruption class altogether.
2. **Session payload only after an XML well-formedness check.** If the asset route is unavailable, validate the payload with `DOMParser` and reject on `parsererror` (exactly the check that would have caught this incident's payload: "error on line 233 at column 54"). Only well-formed payloads proceed. This turns a silent broken image into a detectable, attributable failure, and doubles as an SVG-content safety filter.
3. **Sandboxed iframe as the last render fallback.** Render inside a sandboxed iframe (no `allow-scripts`) so embedded `<script>` is blocked while declarative **SMIL animations still run** — preserving legitimate animated SVGs without executing active content.
4. **Explicit error state instead of a silent broken image.** If every source fails validation, show a labeled error ("SVG source failed well-formedness validation; re-fetching from disk") with a retry, rather than an unexplained broken-image glyph. The incident's symptom was precisely a silent broken image that cost a debugging session; an explicit state makes the failing level and reason visible immediately.

---

## 5. Forensics method + prevention

**Session-log forensics.** The session log is a **concatenated-Zstandard generation file**: each frame is independently zstd-compressed. Decode it frame-by-frame — read the frame boundaries from the generation container, zstd-decompress each frame individually, and reassemble the event stream to recover the **exact stored text** (not a re-read, not a paraphrase). That is how `session-log-excerpt.txt` recovered the payload around line 232 and proved the splice exists in the stored result block: payload = source line 232 prefix ("…stro") + source line 247's tail ("0 0,1 821,730"), lines 233–247 missing, with the XML parser pinning the malformed point at line 233 column 54. Combined with the clean disk file, the clean tool TYPE result, and the clean re-read, this converts the anecdote ("render is broken") into layer-attributed evidence: corruption in result-text assembly, upstream of the plugin, non-deterministic.

**Release-checklist items added by this incident:**

1. **Version bump before build** — never build a release bundle before `package.json` carries the release version, so tsdown bakes the right `PLUGIN_VERSION` (v0.3.8 already corrected this order).
2. **Grep the shipped bundle for the baked constant** — after `pnpm run build`, verify `PLUGIN_VERSION = "x.y.z"` in `lib/client.js` equals `package.json`'s version; fail the release otherwise (would have caught the phantom badge).
3. **Per-mirror tag SHA verification** — `git ls-remote --tags` on every mirror (origin/public/omdsh) and diff the SHAs, as done in `git-tags.txt` (all mirrors agreed at `748b5e5…` / `d887deb…`).
4. **Restart the host after any host-half change** — client refresh is not enough; a boot-time-registered route/whitelist only reloads on host restart (the PNG-200/SVG-404 probe pair is the quick discriminator).
5. **Report the upstream text-corruption bug instead of papering over it in the plugin** — file the harness issue with the forensic frame-decoded payload and the well-formedness verdicts attached; do not "repair" the well-formed source file or add plugin-side workarounds that mask a harness-layer defect.
