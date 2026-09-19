# S19 — The Phantom Update, the Stale Host Half, and the Corrupted Payload

Read-only analysis of the evidence pack for `@dsh-external/dsh-file-trace` v0.3.7/v0.3.8.
No fixture, skill, verifier, or reference material was modified.

## 1. Phantom self-update root cause

**Where the compared constant comes from.** The shipped client bundle contains
`export const PLUGIN_VERSION = "0.3.6";`. As the bundle's own comment states, tsdown
**inlined this constant from `package.json` at build time** — it is a baked build artifact,
not a runtime read of the manifest. The self-update check calls `git ls-remote --tags`
(no auth), picks the highest `vX.Y.Z` tag, and shows the badge when `latest > PLUGIN_VERSION`.

**The operation-order mistake.** `release-log.md` shows the actual sequence for v0.3.7:

1. 16:22 `pnpm run build` ← bundle emitted with `version` still **0.3.6**
2. 16:23 bump `package.json` 0.3.6 → 0.3.7 ← **after** the build
3. 16:24 commit (including the stale `lib/client.js`) and tag `v0.3.7`

So the artifact shipped under tag `v0.3.7` carries `PLUGIN_VERSION = "0.3.6"`. At runtime
the check fetches the tags, sees `v0.3.7` > `0.3.6`, and the freshly released plugin
announces an update to itself: "新版本 v0.3.7 可用".

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows all three mirrors
(origin/public/omdsh) list both tags with identical SHAs, and the tag SHA was verified
everywhere. Integrity was never in question: the *tagged content itself* was wrong. The
corruption is baked into the committed bundle; verifying the SHA of a bad artifact only
proves the bad artifact was faithfully distributed. No attack, no mirror skew, no staleness
on the wire — a pure build-order defect.

**Corrected release order + catch.** Bump `package.json` **before** building, so the
bundle inlines the version it will be tagged with:

1. bump version → 2. build → 3. verify → 4. commit + tag → 5. push mirrors → 6. verify tag SHAs.

The check that would have caught it *before* pushing: **grep the built bundle for the baked
constant** — e.g. `grep -o 'PLUGIN_VERSION = "[^"]*"' lib/client.js` (or simply
`grep '"0.3.7"' lib/client.js`) immediately after the build, asserting it equals the version
about to be tagged. Even simpler and fully general: assert the tagged version string appears
in every built artifact as a release gate. This is exactly what the v0.3.8 re-release did
(bump first, then build), which is why v0.3.8 does not show the badge.

## 2. Client-plane vs host-plane update asymmetry

**Where each half loads.** The two halves of the plugin load at different times through
different mechanisms:

- **Client half** (`lib/client.js`) is fetched by the **browser** and re-fetched/reloaded
  when the client bundle changes — a page/plugin refresh suffices. That is why the new SVG
  render toggle appeared and was clickable after the v0.3.8 push, without any restart.
- **Host half** (`lib/index.js`) is loaded by the **DSH Node process at (re)start**; the
  asset route and its extension whitelist are registered once at plugin activation time.
  A new file on disk does not retroactively change an already-registered route's whitelist
  in the running process.

**How the probes pin staleness to the running host, not the release.** Three independent
observations triangulate it:

1. **PNG probe → 200 `image/png`**: the route handler itself is alive and serving; this is
   not a missing/unregistered route or a dead plugin.
2. **SVG probe → 404 "unsupported image type"**: that exact message is the whitelist's
   rejection path — the *running* whitelist lacks `svg`.
3. **Disk `lib/index.js` at v0.3.8 whitelists `svg: 'image/svg+xml'`**
   (`lib-index-excerpt.js`): the *shipped* code is correct.

If the release were wrong, disk and probe would agree (both reject svg). If the route were
missing, PNG would 404 too. Only one hypothesis fits all three: **the code answering HTTP
is the old host half still resident in the un-restarted process, while the disk and the
browser already run the new halves.** `release-log.md` confirms: host restart was NOT
performed in this session; the whitelist change was made after the host booted.

**What makes a host-plane change effective.** Restart the host process (or otherwise
re-activate the plugin so `apply()` re-registers the route with the new whitelist).
This is the one case where the usual "plugins hot-update (client refresh) is enough" rule
fails: it holds only when the change is confined to the browser-fetched client half. Any
change to host-half code — route registration, whitelists, Services, host handlers —
requires re-loading the host half, i.e. a host restart/re-activation. The evidence pack's
own note makes the plane split explicit: probe "executed AFTER the browser was confirmed
refreshed … host NOT restarted since before the SVG whitelist change."

## 3. Broken-image attribution

The three facts: source file on disk is well-formed XML; the session-log's read-result
text is spliced (payload line 232 = source line 232 up to `...stroke="#dde6ea" stro` +
source line 247's tail from `0 0,1 821,730` onward; source lines 233–247 absent, the splice
landing on the shared prefix `stro`); a re-read of the same region comes back clean.

**Which layer produced the corrupted text.** The corruption exists *only* in the
model-visible result block persisted into the session log — i.e. it happened in the
**read tool's result-text assembly, upstream of the plugin**, between the clean bytes on
disk and the text handed to the caller/model. The plugin's render path consumed that
session payload; the file itself was never bad. The non-deterministic clean re-read
confirms it is a transient assembly bug, not a durable file defect.

**Why the session payload must be treated as untrusted rendering input.** The plugin does
not own that layer; it cannot assume the logged text faithfully mirrors disk. Rendering
payload text directly as SVG means any upstream truncation/splice/encoding fault becomes a
broken image (or worse, a parse-and-execute surface). Untrusted-input validation
(well-formedness check before render) is the plugin's defense, whatever the upstream bug does.

**Why "repairing" the traced file would have been wrong.** The file is well-formed — there
is nothing to repair. Editing it would (a) corrupt a genuinely good file based on a
transient upstream bug, (b) destroy the forensic evidence, and (c) mask the real bug so it
keeps recurring. The correct move is to attribute the corruption upstream, render
defensively, and report the session-log/result-assembly bug — which the fixture itself
concludes: "the corruption happened in the result-text assembly, upstream of the plugin."

## 4. Defensive render chain for SVG preview

Ordered sources, each level justified:

1. **Disk-bytes asset route first.** The asset route streams the file's raw bytes from
   disk with a content-type whitelist — the least-mediated path, bypassing the session-log
   text layer entirely. When the host half is current (post-restart, `svg` whitelisted),
   this serves exactly the bytes that are known well-formed on disk. Prefer it
   unconditionally; it is both the freshest and the most trustworthy source.
2. **Session payload only after an XML well-formedness check.** When the disk source is
   unavailable (404 — e.g. stale host half as in §2, or the file no longer exists), fall
   back to the payload text captured in the session log — but first parse it with
   `DOMParser` (or equivalent) and **reject on `parsererror`**. Per §3 the payload is
   untrusted: a spliced payload fails exactly the check the fixture demonstrates
   ("Specification mandates value for attribute stro0"), converting silent breakage into
   a detectable condition. Only well-formed payload text proceeds to render.
3. **Sandboxed iframe as last render fallback.** SVG can carry scripts; render it inside a
   sandboxed iframe with scripts blocked (`sandbox` without `allow-scripts`, ideally
   opaque-origin) so even adversarial markup cannot execute. SMIL animations still run —
   they are declarative, not script — so legitimate animated previews keep working. This
   isolates rendering of content the plugin cannot fully vouch for.
4. **Explicit error state instead of a silent broken image.** When every source fails
   (route 404 + payload fails the well-formedness gate), show a visible error: which
   sources were tried, why each failed (e.g. "asset route 404 (host half stale — restart
   required)", "session payload not well-formed at line 233"). This turns the §2/§3
   failure modes from mystery broken images into actionable diagnostics, and avoids the
   user mistaking an upstream bug for a bad file.

## 5. Forensics method + prevention

**Decoding the session log.** The session log is a concatenated-Zstandard generation file:
one zstd frame per event/record, concatenated. Frame-by-frame recovery: open the file,
parse the zstd frame boundaries (magic `0x28 B5 2F FD`); decompress each frame
independently (e.g. Node `zstd`/`fzstd`, a streaming decoder that emits per-frame
chunks, or `zstdcat`-style sequential decode with frame offsets tracked); decode each
frame's JSON record; locate the read-result event and extract its stored text verbatim.
That recovers the *exact persisted bytes* — the ground truth that distinguishes
"corrupted in the log" from "corrupted on disk" — which is precisely the evidence
`session-log-excerpt.txt` §1–§4 embodies. Because committed generations are append-only,
the corrupted frame remains available for the upstream bug report even after later clean
re-reads append new events.

**Release-checklist items this incident adds:**

- **Version-bump-before-build**: bump `package.json` before `pnpm run build` so
  build-time-inlined constants carry the to-be-tagged version (v0.3.8's corrected order).
- **Grep the shipped bundle for the baked constant**: post-build gate asserting the new
  version string appears in every built artifact (would have caught v0.3.7's badge before push).
- **Per-mirror tag SHA verification**: keep the existing `git ls-remote` cross-mirror SHA
  check — it correctly rules out mirror skew here, even though it cannot catch content
  baked wrong (know what each check proves).
- **Plane-aware release notes**: client-half changes take effect on refresh; host-half
  changes (route whitelists, Services) require a host restart — state which applies, and
  probe both planes (PNG *and* SVG) before declaring a release live.
- **Report the upstream text-corruption bug** (result-text assembly splicing at a shared
  prefix, non-deterministic) with the decoded log frame as evidence — do not paper over it
  in the plugin by silently retrying reads or "repairing" traced files.

## Verdicts (one line each)

1. Badge: build-time-inlined `PLUGIN_VERSION = "0.3.6"` from a bump-after-build order;
   mirror SHAs prove distribution integrity, not artifact correctness.
2. 404: running host process still has the old whitelist (boot-time registration); disk
   code is correct — restart the host; client-refresh-only does not cover host-plane changes.
3. Broken image: corruption is in the session-log read-result text produced upstream of
   the plugin; the disk file is well-formed and must not be edited.
4. Render chain: disk-bytes route → payload gated on DOMParser well-formedness →
   sandboxed iframe (scripts off, SMIL on) → explicit error state.
5. Prevention: bump-before-build, grep the bundle for the constant, per-mirror SHA check,
   plane-aware probes, and an upstream bug report with the decoded zstd frame.
