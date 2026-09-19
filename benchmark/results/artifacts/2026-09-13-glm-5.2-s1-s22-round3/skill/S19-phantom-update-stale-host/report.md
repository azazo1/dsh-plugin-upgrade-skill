# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Report

Read-only diagnosis (skill mode A · inspect). Evidence: the v0.3.7/v0.3.8 release session
of `@dsh-external/dsh-file-trace` as captured in the fixture pack. No file in the fixture
was modified; no install, migration, or release was executed.

---

## 1. Phantom self-update root cause (v0.3.7 badge "新版本 v0.3.7 可用")

**Where the compared constant comes from.** The shipped `lib/client.js` (verbatim in
`client-bundle-excerpt.js`) contains:

```js
export const PLUGIN_VERSION = "0.3.6";
```

tsdown **inlined** this constant from `package.json` **at build time**; it is not read
dynamically at runtime. The self-update check runs `git ls-remote --tags` (no auth) at
runtime, picks the highest `vX.Y.Z`, and shows the badge when `latest > PLUGIN_VERSION`.

**The operation-order mistake** (from `release-log.md`):

1. 16:22 `pnpm run build` — client bundle emitted
2. 16:23 bump `package.json` 0.3.6 → 0.3.7   ← **bumped AFTER the build**
3. 16:24 commit (including the already-built `lib/client.js`) and tag `v0.3.7`

So the artifact committed and tagged as v0.3.7 still carries the *old* baked constant
`"0.3.6"`. At runtime the badge comparison is `newerTag("v0.3.7")` vs `PLUGIN_VERSION
"0.3.6"` → `0.3.7 > 0.3.6` → the freshly released plugin announces an update to itself.

**Why mirror/tag integrity is irrelevant.** The badge does not compare what is *deployed*
against what is *published*; it compares a **build-time baked string inside the served
bundle** against the **live mirror tag list**. `git-tags.txt` shows all three mirrors
(origin/public/omdsh) list `v0.3.7` and `v0.3.8` at identical SHAs — the publication side
is perfectly consistent. The inconsistency is entirely on the artifact side: the tag name
says 0.3.7 while the bytes inside the bundle say 0.3.6. Verifying the tag SHA on every
mirror verifies only *which* bytes were published, not *what version string those bytes
claim*. No amount of mirror or SHA checking can catch a constant that was frozen before
the bump.

**Corrected release order:**

1. bump `package.json` (and any install refs) **first**;
2. then `pnpm run build` so the bundler inlines the new version;
3. commit, tag, push, verify mirror tag SHAs.

(The maintainer in fact corrected exactly this for v0.3.8: bump FIRST, then build; the
v0.3.7 tag had to be amend-rebuilt and force-moved on all mirrors.)

**The check that would have caught it before pushing:** after the build and before
committing/tagging, grep the shipped bundle for the baked constant and compare it to the
manifest:

```sh
grep -o 'PLUGIN_VERSION = "[^"]*"' lib/client.js   # must equal package.json version
# or generically:
grep -r "$(jq -r .version package.json)" lib/      # the new version string MUST appear
```

If the bundle's baked version ≠ `package.json` version (or the new version string is
absent from `lib/`), abort the release and rebuild. A one-line CI/release-script
assertion of "shipped bundle version == manifest version" turns this class of failure
into a hard stop.

---

## 2. Client vs host plane update asymmetry (SVG toggle visible, asset route 404s)

**Where each half's code is loaded.** A DSH plugin with a Web Client half ships two
independently loaded artifacts:

- **Client half (`lib/client.js`)** — fetched by the **browser**. A page reload (or the
  client re-fetch/HMR path) re-requests the client bundle, so the *new* v0.3.8 client code
  — including the new SVG render toggle — reached the browser without restarting
  anything. The evidence confirms this: the toggle was visible and clickable at probe
  time.
- **Host half (`lib/index.js`)** — required/loaded by the **DSH host Node.js process at
  plugin activation (boot time)**. Its effects — here, the asset route's extension →
  content-type whitelist registration — are bound when the host starts the plugin. The
  session had **not restarted the host** since before the SVG whitelist change, so the
  *running* host process still executes the *old* whitelist, which lacks `svg`.

**How the probes pin the staleness to the running host, not the release:**
three independent observations, and only one model fits all of them:

| Observation | Implication |
|---|---|
| PNG probe → 200 `image/png` | The asset **route itself is alive and registered** — the 404 is not a missing route or a dead plugin; it is the route's own extension whitelist rejecting `svg`. |
| SVG probe → 404 "unsupported image type" | The whitelist the route consults **does not contain `svg`** — i.e. the executing code predates the SVG support. |
| Shipped `lib/index.js` on disk **does** whitelist `svg: 'image/svg+xml'` (`lib-index-excerpt.js`) | The *released artifact* is correct. |

Disk bytes are new, executing behavior is old ⇒ the discrepancy is in the **process that
has not re-loaded the code**: the running host. If the release were wrong (svg missing
from the shipped whitelist), the disk excerpt could not contain it; if the route were
dead, PNG would 404 too. Only "stale in-memory host code" explains 200-PNG + 404-SVG +
correct-disk simultaneously.

**What makes a host-plane change effective:** reload the host-side plugin code — in
practice, **restart the DSH host process** (or use the runtime's explicit plugin
reload/re-activation path) so the new `lib/index.js` is required and the asset route is
re-registered with the extended `CONTENT_TYPES`. After restart, the SVG probe should
return 200 `image/svg+xml`; that probe pair (PNG 200 / SVG 200) is the acceptance check.

**Why the usual "plugins hot-update" rule fails here:** for *client-half* changes a
browser refresh genuinely suffices — the browser re-fetches the bundle, which is exactly
why the new toggle appeared. That success creates a false generalization ("the update is
live"). But host-half code is resolved at **boot-time activation** in the host process;
nothing in the browser can re-require Node-side modules or re-register host routes. This
incident is precisely the case where the hot-update intuition holds for one plane and
silently fails for the other: **any release that touches the host half must be validated
against the running host process, not against a refreshed browser.** (Cf. the corridor
card DSH-0.1.5-A1-20 in the skill references: a host restart is what self-heals a
serving-roster/combo mismatch — same asymmetry, in-place client refresh vs host restart.)

---

## 3. Broken-image attribution (session-payload corruption, not the traced file)

**Where the corruption happened.** `session-log-excerpt.txt` gives a three-way
triangulation:

- The **source file on disk** is well-formed XML (XmlDocument load: no error), and its
  lines 232–247 read cleanly in a separate read.
- The **session-log payload** for the read result is NOT well-formed, and its shape is a
  **splice**: payload line 232 = source line 232 truncated at the shared prefix `"stro"`
  + the tail of source line 247 (from `"0 0,1 821,730"` onward); source lines 233–247 are
  absent.
- A **re-read** of the same region afterwards returned clean text (non-deterministic).

The corrupted text is the **model-visible result block persisted into the session log** —
i.e. it was produced **upstream of the plugin**, in the read tool's result-text assembly
layer (whatever chunked/assembled the tool result text before it was written to the log).
The plugin's SVG renderer consumed that payload text and, given malformed XML, produced a
broken image. The disk file was never bad.

**Why the plugin must treat the session payload as untrusted rendering input.** The
session-log text is a *derived copy* that crossed several layers (tool output → chunked
assembly → session-log persistence → replay/projection → plugin renderer). Any of those
can corrupt, truncate, or reorder — and this incident is existence proof it does,
non-deterministically. A renderer that assumes "payload text == file bytes" will render
corruption as if it were the author's file, producing silent broken images with no
diagnosis. Untrusted input means: validate before rendering, never silently fall back to
best-effort rendering of malformed markup.

**Why "repairing" the traced file would have been the wrong move.** The disk file is
well-formed; the defect lives in an ephemeral, non-deterministic upstream text-assembly
path. Editing the traced SVG would (a) corrupt a *good* artifact based on a *bad copy*,
(b) destroy the forensic evidence needed to localize the upstream bug, and (c) not fix
anything — the next read could splice again on any file. The correct action is to detect
malformedness, surface an explicit error state, re-read or fall back to a trusted source
(disk bytes via the asset route), and **report the upstream text-corruption bug** rather
than papering over it in data.

---

## 4. Defensive render chain for the SVG preview

Ordered from most-trusted to most-defensive; each level exists because the level above it
has a demonstrated or structural failure mode:

1. **Disk-bytes asset route first.** Request the file through the host asset route
   (`/dsh-file-trace/asset?path=...`), which serves the file's actual bytes from disk
   with a content-type from its whitelist. This bypasses the session-log copy entirely —
   it is the only source that reflects the file as it exists now. (Which is exactly why
   the v0.3.8 host-half whitelist fix matters: this level is unavailable for SVG until
   the host restart registers `svg: 'image/svg+xml'`; the PNG-200/SVG-404 probe pair is
   its acceptance test.)

2. **Session payload only after an XML well-formedness check.** When the asset route is
   unavailable (stale host, non-workspace path, offline replay), the session-payload text
   is usable **only after** parsing with `DOMParser` (`application/xml` / `image/svg+xml`)
   and checking for a `<parsererror>` document element. Rationale: the payload is the
   layer this incident proved corrupt (and non-deterministically so); a splice that lands
   mid-attribute (`stro0,1 821,730 …`) is invisible to string length checks but is caught
   deterministically by any conforming XML parser. If `parsererror` is present, do NOT
   render — go to the error state.

3. **Sandboxed iframe as the last render fallback.** When markup parses clean, render it
   inside a sandboxed `<iframe sandbox>` (no `allow-scripts`): SVG embedded as a
   document can carry `<script>` and event-handler attributes, and a traced file's
   provenance is untrusted; scripts must be blocked. Note the deliberate residual: with
   scripts blocked, **SMIL animations still run** (SMIL is declarative, not
   script-gated) — acceptable for a preview, but worth knowing so animation is not
   mistaken for script execution. The iframe also isolulates CSS/origin effects of the
   rendered SVG from the app DOM.

4. **Explicit error state instead of a silent broken image.** If every source fails
   (route 404 + payload fails `parsererror`), show a visible error ("SVG could not be
   rendered: session payload failed XML validation; source file may be fine — re-read or
   open via asset route"), not a broken-image glyph. Rationale: this incident was only
   diagnosable because a human happened to compare three artifacts; an explicit error
   state turns the next occurrence into a self-describing failure and steers the user to
   the trusted source instead of blaming the file.

Design principle: **trust order = proximity to the file's real bytes**, and **validation
at every trust downgrade**. Level 1 exists because the payload copy is unreliable; level
2's gate exists because level 2's source is the proven-corrupt layer; level 3 exists
because even well-formed SVG is active content; level 4 exists because silent failure
hides upstream bugs.

---

## 5. Forensics method + prevention

**Decoding the session log.** The session log is a **concatenated-Zstandard generation
file**: a sequence of independently zstd-compressed frames (generations) concatenated
tail-to-head/one after another. Recovery procedure:

1. Read the raw generation file and **split it into zstd frames** — scan for zstd magic
   `0x28 B5 2F FD`; each occurrence starts a frame (a naive single-shot `zstd -d` fails
   or silently truncates on concatenated frames; use `zstandard`'s stream reader with
   `read_across_frames=True`, `zstd -d` with `--long`/multipart handling, or decode each
   frame's length and advance).
2. Decompress frame-by-frame; each frame yields its generation's records.
3. Locate the read-result event for the traced SVG (the excerpt places it around payload
   line 232) and extract the **stored text verbatim** — this is the authoritative record
   of what the model actually saw.
4. Compare against (a) the file on disk read separately and (b) a fresh re-read; the
   excerpt's verdict — log payload spliced at shared prefix `"stro"`, lines 233–247
   missing, disk and re-read clean, parse error `"Specification mandates value for
   attribute stro0"` at the splice — is what converts "sometimes the preview breaks"
   from anecdote into **reproducible, localizable evidence**: the corruption is in the
   result-text assembly upstream of the plugin, non-deterministic, and independent of the
   file.

**Release-checklist items this incident adds:**

1. **Version-bump-before-build** — bump `package.json` (and version-bearing docs/refs)
   *before* running the bundler, so build-time-inlined constants (`PLUGIN_VERSION`)
   match the tag being cut. (Corrected order was already applied to v0.3.8.)
2. **Grep the shipped bundle for the baked constant** — post-build, pre-commit assertion
   that the version string inlined into `lib/*.js` equals `package.json`'s version;
   fail the release on mismatch. Generalizes to any define/inlined manifest field.
3. **Per-mirror tag SHA verification** — keep verifying `git ls-remote --tags` SHAs agree
   across all push mirrors (already done here, and necessary — but understand its scope:
   it proves publication consistency, not artifact-internal correctness; it cannot catch
   item 1's failure).
4. **Host-plane restart + probe validation for host-half changes** — any release touching
   `lib/index.js` (routes, services, registration) requires a host restart and a
   behavioral probe of the changed surface (here: SVG asset probe must return 200
   `image/svg+xml` after restart), not merely a refreshed browser.
5. **Report the upstream text-corruption bug** — file the session-log/result-assembly
   splice (with the decoded frame evidence and the clean re-read) against the upstream
   component that assembles read-result text; do not add "repair" heuristics in the
   plugin that mask it. The plugin's correct posture is validate-and-error (§4), plus
   the forensic report upstream.

---

## Summary table

| Symptom | Layer at fault | Root cause | Fix |
|---|---|---|---|
| v0.3.7 shows its own update badge | client bundle artifact | `PLUGIN_VERSION "0.3.6"` baked by a build that ran **before** the version bump; badge compares baked constant vs live mirror tags, so mirror/SHA integrity is irrelevant | bump → build → tag; assert baked version == manifest version before push |
| SVG toggle visible but Render 404s | **running host process** (stale in-memory whitelist), not the release | client half re-fetched by browser; host half's route whitelist fixed only at boot-time activation; host not restarted | restart host; verify SVG probe 200 alongside PNG 200 |
| Broken image from traced SVG | upstream read-result text assembly (session-log payload) | non-deterministic splice at shared prefix `"stro"` in the persisted result text; disk file well-formed; re-read clean | treat payload as untrusted: disk-bytes route → `DOMParser`/`parsererror` gate → sandboxed iframe (scripts blocked, SMIL runs) → explicit error state; report upstream bug |

*Skill posture: Mode A (read-only inspection). No writes outside this report; fixture,
skill, verifier, and reference material untouched.*
