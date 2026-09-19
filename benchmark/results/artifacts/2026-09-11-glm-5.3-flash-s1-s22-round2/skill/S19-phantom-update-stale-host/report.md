# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Diagnostic Report

Evidence pack: `environment/fixture/` (read-only). Plugin: `@dsh-external/dsh-file-trace` v0.3.7 / v0.3.8.

## 1. Phantom self-update root cause (v0.3.7 badge)

**Finding.** The shipped client bundle announces an update to itself because the version it compares against is a **build-time constant, not a runtime read**, and the release built the bundle **before** bumping `package.json`.

Evidence:

- `client-bundle-excerpt.js` (shipped `lib/client.js` at tag v0.3.7): `export const PLUGIN_VERSION = "0.3.6";` with the note *"tsdown inlined this constant from package.json WHEN THE BUNDLE WAS BUILT — it is not read dynamically at runtime."*
- `release-log.md` v0.3.7 step order: 16:22 `pnpm run build` ("build ran here") → 16:23 bump `0.3.6 → 0.3.7` ("version bumped AFTER the build") → 16:24 commit (which "includes the already-built `lib/client.js`") and tag `v0.3.7` → 16:25 push to three mirrors.
- The self-update check (`newerTag`) compares the highest mirror tag against `PLUGIN_VERSION`: `compareSemver("v0.3.7", "0.3.6") > 0` → true → badge "新版本 v0.3.7 可用" — on the very release that contains the check.

**Operation-order mistake.** Build-then-bump. The bundle was emitted while `package.json` still said 0.3.6, so the released artifact bakes 0.3.6 as its own version while the tag says v0.3.7. The release log records the correction already applied for v0.3.8: "bump FIRST, then build".

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows identical SHAs for `v0.3.7` (`748b5e56…`) and `v0.3.8` (`d887deb0…`) on all three mirrors (origin / public / omdsh); the check fetches exactly those tags. Every mirror serves the same, correctly-tagged commit. The comparison input that is wrong is the **local baked constant** (0.3.6), not the remote "latest" input — verifying tag propagation cannot detect a stale inlined constant.

**Corrected release order.** (1) bump `package.json` → (2) build so the bundler inlines the new version → (3) commit + tag → (4) push to mirrors and verify `git ls-remote` SHAs agree.

**Check that would have caught it.** A pre-push grep of the built artifact for the baked constant: the built `lib/client.js` must contain `PLUGIN_VERSION = "<version from package.json>"` (fail if it still carries the previous version). The plugin-upgrade skill's validation layer 4 ("verify the packed filename and packed manifest both carry that plugin version") is the same discipline extended to the bundle body.

## 2. Client vs host plane update asymmetry (v0.3.8 SVG 404)

**Finding.** The two halves of the plugin load on different schedules:

- **Client half** — the browser fetches the client bundle fresh (page load / refresh), so after the v0.3.8 push the browser executed the new bundle and rendered the new SVG render toggle. `release-log.md`: "the client half was confirmed refreshed: the new toggle button was rendered by the browser."
- **Host half** — routes are registered at **host boot time**, when the plugin's host entry activates. The running host process has held the old `CONTENT_TYPES` map (no `svg` entry) since before the change; pushing new code to disk does not re-run registration.

**Probes pin staleness to the running process, not the release** (`asset-route-probe.txt`):

- PNG probe → `200 OK`, `image/png` — the route handler is alive and served by the running host; this is not a missing route.
- SVG probe → `404 "unsupported image type"` — the extension whitelist in the *running* process rejects `svg`.
- Shipped disk artifact (`lib-index-excerpt.js`, `lib/index.js` at tag v0.3.8) explicitly contains `svg: 'image/svg+xml'`.

Disk is new, route is old ⇒ the process predates the release. `release-log.md` confirms: "a host restart had NOT been performed in this session."

**What makes a host-plane change effective.** Stop the host and cold-start it (per the skill's global-upgrade discipline: a running host holds file locks; "a browser refresh is not a host stop"). This is the one case where "plugins hot-update" does not hold: the **client** plane hot-updates because the browser re-fetches on reload, but host-plane registrations are created once during plugin activation at boot — a client refresh cannot re-execute host code. The skill's v0.1.5-alpha.1 card records the mirror-image failure mode (stale host serving stale combos; "a host restart self-heals" the mismatch) — same root discipline.

## 3. Broken-image attribution: upstream session-payload corruption

**Finding.** The broken image was not the traced file's fault and not the plugin's render logic's fault — the text stored in the **session log's read-result payload** is corrupted, and the plugin rendered that corrupted payload.

Evidence (`session-log-excerpt.txt`):

- Log payload line 232 is a splice: source line 232 up to `…stroke="#dde6ea" stro` **plus source line 247's tail** `0 0,1 821,730 …`; source lines 233–247 are absent from the payload. The splice lands on the shared prefix "stro".
- The source file on disk is well-formed: *System.Xml XmlDocument load: no error*.
- The log payload is NOT well-formed: *"error on line 233 at column 54: Specification mandates value for attribute stro0"* (attribute `stro0` — literally the two spliced fragments).
- "The read tool's TYPE result delivered to the caller was clean; the corrupted text is the model-visible result block persisted into the session log, i.e. the corruption happened in the **result-text assembly, upstream of the plugin**."
- A re-read of the same region afterwards came back clean — the corruption is non-deterministic, consistent with a transient assembly/read bug, not with file content.

**Why the plugin must treat the session payload as untrusted rendering input.** The payload is a lossy, re-assembled projection of what was read, produced by a different process than the file system; the only authority for the file's bytes is the disk (via the asset route, item 4). Any plugin that renders "the file as seen in the session" is really rendering second-hand text that can be spliced, truncated, or transformed upstream.

**Why "repairing" the traced file would have been wrong.** The file on disk is provably well-formed; the malformed `stro0` attribute exists only in the log. Editing the file would (a) modify correct data, (b) still not fix what the render path consumes if it reads from the session payload, and (c) mask a real upstream bug (result-text assembly corruption) that deserves an upstream bug report. Per the skill's troubleshooting discipline: when local observation conflicts with a primary source, record both and report — never silently patch one side.

## 4. Defensive render chain for the SVG preview

Ordered render-source design, most-trusted first:

1. **Disk-bytes asset route (primary).** The host serves the file's actual bytes with the correct `image/svg+xml` content type (after the host restart from item 2). Justification: the disk is the only authoritative source; the browser's native SVG renderer then handles rendering exactly as for any web image. Availability: PNG 200 proves the route works once the stale whitelist is unloaded.
2. **Session payload, only after XML well-formedness validation (fallback 1).** If the asset route is unavailable, parse the payload text with `DOMParser` (`image/svg+xml` mode) and check for a `parsererror` element before rendering. Justification: item 3 shows the payload can be spliced mid-file; a `parsererror` check deterministically rejects exactly that class of corruption (the spliced payload fails: "Specification mandates value for attribute stro0"), so a corrupted payload produces an error state rather than a broken image. Well-formed payloads may still be *incomplete* (lines 233–247 missing would parse if the splice landed at a tag boundary), so this remains a fallback, never the primary.
3. **Sandboxed iframe (fallback 2 / isolation).** Render whatever source passed validation inside an iframe with `sandbox` (no `allow-scripts`): scripts in a traced/malicious SVG cannot execute, while declarative SMIL animations still run, so preview fidelity is preserved without script execution. Justification: SVG is an active document format; hosting it same-origin in the plugin page would expose the page to embedded script.
4. **Explicit error state (terminal).** If all sources fail validation, render a labeled error ("preview unavailable: source invalid/unreachable"), never a silently broken `<img>`. Justification: the broken image is precisely what made this incident look like a plugin rendering bug; an explicit state names the failing layer (route 404 vs XML `parsererror`) and turns the symptom into a diagnosis.

## 5. Forensics method + prevention checklist

**Decoding the session log.** The log is a **concatenated-Zstandard generation file** (per the evidence README / session-log-excerpt header: "decoded from the session's concatenated-zstd generation file"). Method: read the generation file, split it into its concatenated zstd frames, decompress each frame independently (each frame carries its own magic number `0x28B52FFD` and header, so frames can be walked sequentially without offsets), and reassemble the resulting event frames in sequence order to recover the exact stored text — here, the read-result payload around line 232. That turns the anecdote ("the image renders broken") into evidence: the stored payload itself contains the `stro0` splice, the disk file does not, and the XML validator verdicts pin the corruption to the log layer. This is what allows attributing the bug upstream (result-text assembly in the host) instead of at the plugin or the file — and grounds the upstream bug report.

**Release-checklist items this incident adds:**

1. **Version-bump-before-build** — `package.json` first, then build, then commit/tag/push (already adopted for v0.3.8 per `release-log.md`).
2. **Grep the shipped bundle for the baked constant** — before pushing, assert the built `lib/client.js` contains `PLUGIN_VERSION = "<package.json version>"` and no stale previous version; this is the check that would have caught the 0.3.6 constant inside the v0.3.7 tag.
3. **Per-mirror tag SHA verification** — `git ls-remote --tags` on every mirror (origin / public / omdsh) and require identical SHAs, as done in `git-tags.txt`; this protects the "latest tag" input of the self-update check.
4. **Host-plane changes require a host restart and route probe** — after shipping any host-half change, restart the host and re-probe the changed route (the PNG-200/SVG-404 + disk-whitelist triad is the minimal staleness proof), rather than trusting a refreshed client as evidence of the update.
5. **Treat session payloads as untrusted render input** — validate before rendering (item 4), and never patch files to compensate for log corruption.
6. **Report upstream text-corruption bugs** — file the result-text assembly corruption with the host (with the decoded frame evidence and the deterministic `parsererror` reproduction) instead of papering over it in the plugin; the non-deterministic clean re-read makes reproduction guidance part of the report.
