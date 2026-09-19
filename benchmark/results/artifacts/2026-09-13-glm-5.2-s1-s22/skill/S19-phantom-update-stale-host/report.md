# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Read-Only Diagnosis

Task: S19-phantom-update-stale-host (plugin-upgrade skill, Mode A · read-only inspection)
Evidence pack: `benchmark/tasks/S19-phantom-update-stale-host/environment/fixture/` (read-only, unmodified).
All three symptoms were diagnosed from the fixture evidence alone; no migrations, installs, or
writes outside the report directory were performed.

---

## 1. Phantom self-update root cause — a build-time version constant meeting a bump-after-build order

**Where the compared constant comes from.** The shipped client bundle's own update check is
verbatim in `client-bundle-excerpt.js`:

```js
/** The running plugin version (from package.json at build time). */
export const PLUGIN_VERSION = "0.3.6";
```

`PLUGIN_VERSION` is **inlined by tsdown from `package.json` at build time** — it is a frozen
string literal baked into `lib/client.js`, not something read dynamically at runtime. At runtime
the check does `git ls-remote --tags` (no auth) against the mirrors, picks the highest `vX.Y.Z`,
and shows the badge when `compareSemver(latestTag, PLUGIN_VERSION) > 0`.

**The operation-order mistake.** `release-log.md` records the fatal sequence for v0.3.7:

1. 16:22 `pnpm run build` — client bundle emitted **while package.json still said 0.3.6**
2. 16:23 bump version 0.3.6 → 0.3.7 — **after** the build
3. 16:24 commit (including the already-built `lib/client.js`) and tag `v0.3.7`

So the artifact that was committed and tagged carries `PLUGIN_VERSION = "0.3.6"`. When the
browser fetched the freshly released v0.3.7 bundle, that bundle compared its baked `"0.3.6"`
against the newest mirror tag `v0.3.7` → `newerTag("v0.3.7")` returned `"v0.3.7"` →
the drawer announced 「新版本 v0.3.7 可用」 — the plugin advertising an update **to itself**. The
badge is not wrong from the bundle's point of view: the code actually running in the browser
genuinely is "0.3.6"; only the tag/mirror metadata says 0.3.7. Artifact identity and release
metadata diverged.

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows all three mirrors (origin /
public / omdsh) list `v0.3.7 → 748b5e5…` and `v0.3.8 → d887deb…` with identical SHAs. The
verification the maintainer ran (`git ls-remote` SHA check) proves the *distribution* channel is
consistent — every mirror serves the same bytes of the same commit. But those bytes are exactly the
problem: the committed bundle itself contains the stale constant. Tag-SHA verification is a
transport-integrity check; it cannot detect that the artifact's content was produced from the wrong
package.json state. No mirror lag, no cache, no partial push — the defect was sealed inside the
commit before any push happened.

**Corrected release order** (already applied for v0.3.8 per the release log):

1. make source changes, tests green;
2. **bump `package.json` version FIRST**;
3. `pnpm run clean && pnpm run build` (clean first — also guards against incremental-build
   stale output, per migration-hygiene §1);
4. commit + tag;
5. push mirrors; verify tag SHAs (still worth doing — it catches the other failure class).

**The check that would have caught it before pushing:** grep the shipped bundle for the baked
constant and assert it equals the new version, e.g.
`grep 'PLUGIN_VERSION = "0.3.7"' lib/client.js` (or extracting and comparing the emitted
constant) as a mandatory pre-tag/pre-push step — a one-line CI gate. A release that cannot show its
own new version string inside its own artifact must not be tagged.

---

## 2. Client vs host plane update asymmetry — why the new UI renders but the new route 404s

**Where each half's code is loaded and when.** DSH plugins of this shape ship two artifacts, and
they become effective through different mechanisms (skill reference migration-hygiene §3):

- **Client half (`lib/client.js`)**: fetched by the browser on page load / hard refresh with
  no-cache semantics; the bundle re-registers its slots/UI on every load. The new SVG render
  toggle appearing in the browser is direct proof this plane refreshed.
- **Host half (`lib/index.js`)**: loaded and `apply()`-ed once at **host boot**. The asset
  route and its `CONTENT_TYPES` extension whitelist are registered at that moment — the route
  handler closure captures the whitelist object that existed when the process started. Replacing
  the file on disk does nothing to the already-registered route.

**How the probes pin the staleness to the running host process, not the release.** Three
independent observations (`asset-route-probe.txt`, `lib-index-excerpt.js`):

1. PNG probe → `200 image/png`: the route itself is alive and served by the plugin — this is
   not a missing route, a dead plugin, or a composition problem;
2. SVG probe → `404 "unsupported image type"`: the exact failure mode of the *old* whitelist
   (which lacked `svg`) rejecting the extension — the error string is the whitelist's own
   rejection message;
3. the **disk** copy of the shipped `lib/index.js` at v0.3.8 **does** contain
   `svg: 'image/svg+xml'`.

Old-type 200 + new-type 404 + disk artifact containing the new entry is a complete triangulation:
the *code on disk* is correct, the *route in the running process* predates the change. The release
is fine; the process is stale. The release log confirms it: "a host restart had NOT been performed
in this session".

**What makes a host-plane change effective — and why "plugins hot-update" doesn't hold here.**
Host-half changes take effect only when the dsh host process restarts and re-`apply()`s the
plugin, re-registering the route with the new whitelist. The usual "client plugins hot-update on
refresh" mental rule covers **only the client plane**; the host plane is boot-time-registered and
immutable within a process lifetime. This incident is precisely the case where that rule fails:
both halves shipped together, one plane visibly refreshed, and the asymmetry manufactured a
half-working feature. (Same class as the DSH-0.1.5-A1-20 lesson: an in-place upgrade can serve a
fresh client combo against a stale host; a host restart reconciles them.) The fix here is simply:
restart the host, re-probe — SVG must return `200 image/svg+xml`. No code change needed.

---

## 3. Broken-image attribution — upstream session-payload corruption, not the traced file

**Where the corruption happened.** `session-log-excerpt.txt` gives the full decomposition:

- the **source file on disk** is well-formed XML (XmlDocument load: no error), lines 232–247 intact;
- the **session log's stored read-result text** at payload line 232 is
  `…stroke="#dde6ea" stro` **+** line 247's tail `0 0,1 821,730…` — source lines 233–247
  are missing entirely, and the splice lands on the shared prefix `"stro"` (the `stroke-width…`
  of line 232 meeting the `0 0,1` arc-flag run of line 247). The stored text is not
  well-formed (「Specification mandates value for attribute stro0」);
- the read tool's TYPE result delivered to the caller was clean, and **a re-read of the same region
  came back clean** (non-deterministic).

The plugin renders from the session payload (the persisted model-visible result block). That text
was produced by the **result-text assembly layer upstream of the plugin** — the read tool's
text assembly / persistence path — and was already corrupted when the session log recorded it. The
plugin received exactly what the log stored; the log received something the disk never contained.
Corruption window: between the tool's clean in-memory result and the session-log write. It is
non-deterministic (clean re-read), consistent with a race/concurrency bug in result-text
assembly, not with any property of the file.

**Why the plugin must treat the session payload as untrusted rendering input.** The payload
crosses a durable boundary (session log → later consumer) and has now been *observed* to diverge
from the bytes on disk. Feeding it straight into an SVG renderer produced the broken image; in
general, unvalidated markup from a persisted channel is also an injection surface. The disk file
is the ground truth; the payload is a possibly-stale, possibly-corrupt copy.

**Why editing or "repairing" the traced file would have been the wrong move.** The traced file was
never broken — every check of the source (XmlDocument load, the separate clean read, the disk
excerpt) confirms it. "Fixing" the .svg would (a) destroy the evidence proving the upstream bug,
(b) mutate a user file the plugin does not own, and (c) leave the real defect live to corrupt the
next session's payload. The correct response is to render defensively (§4) and **report the
upstream result-text-corruption bug** with the decoded log frames as evidence (§5), not to paper
over it at either end.

---

## 4. Defensive render chain for the SVG preview

Ordered render-source chain, each level justified:

1. **Disk-bytes asset route first.** `GET /<plugin>/asset?path=…` streams the file's raw bytes
   from disk at render time — it bypasses the session-payload channel entirely, so the §3
   corruption class cannot reach it, and it always reflects the file's current state (a re-trace
   renders the current bytes, not a stale snapshot). It is the ground-truth source; use it
   whenever the route can serve the path (host restarted so the whitelist covers `svg`, file
   within workspace scope).

2. **Session payload only after an XML well-formedness check.** When the asset route cannot serve
   the file (out of scope, host route unavailable, historical trace whose file moved), fall back
   to the payload text — but first parse it with `DOMParser` (`image/svg+xml` mode) and
   reject on `parsererror`. Justification: §3 proved this input can be corrupt; the splice
   produced `attribute stro0`, exactly what a well-formedness gate catches. A payload that
   fails the gate is *evidence of upstream corruption*, not a rendering problem — surface it as
   such.

3. **Sandboxed iframe as the last render fallback.** Render the (validated) SVG inside a
   `<iframe sandbox>` (no `allow-scripts`, served from a blob/srcdoc with no same-origin
   access). Justification: even well-formed SVG is active content — `<script>`, event-handler
   attributes, and external references are live in an inline render. The sandbox blocks scripts
   while SMIL animations (`<animate>` etc.) still run, since those are declarative and do not
   need script permission — preserving preview fidelity without its risk.

4. **Explicit error state instead of a silent broken image.** Each failure level (route 404,
   `parsererror`, sandbox load failure) must render a visible, distinguishable error card
   ("asset route unavailable — host restart required", "payload failed XML validation — possible
   session-log corruption, please re-read", …). Justification: the incident's user-visible symptom
   was a mute broken image that could have pointed at three unrelated causes; explicit states make
   the next diagnosis instant and stop the user from blaming (or "fixing") the source file.

---

## 5. Forensics method + prevention

**Frame-by-frame session-log decoding.** The session log is a concatenated-Zstandard generation
file: each frame is independently zstd-compressed and concatenated (monotonic `SCHEMA_VERSION`
framing and per-session locking per the corridor cards). Recovery procedure:

1. work on a **copy** (read-only evidence discipline; never hand-write or edit session logs);
2. iterate the container byte stream: zstd skippable-frame-aware splitting, or simpler — decode
   each zstd member with a streaming decoder (`StreamDecoder` / `zstd -d` accepting
   concatenated members) which yields per-frame boundaries;
3. for each decoded frame, locate the read-result event for the target file (seq ordering;
   `Session.events`/`eventAt` semantics post-alpha.4), and extract the stored result text;
4. diff the stored text against a fresh line-numbered disk read — the §3 splice (payload 232 =
   source 232-head + source 247-tail at prefix `"stro"`, lines 233–247 absent) is then a
   mechanical, reproducible fact rather than an anecdote;
5. the non-determinism (clean re-read) is itself evidence: re-run the read in the same session and
   compare the two stored payloads.

**Release-checklist items this incident adds:**

- **Version-bump-before-build**: bump `package.json` → `clean` → `build` → commit →
  tag → push, in that order, always. (Adopted for v0.3.8 already.)
- **Grep the shipped bundle for the baked constant**: assert
  `PLUGIN_VERSION = "<new version>"` literally appears in the emitted `lib/client.js` before
  tagging; fail the release otherwise.
- **Per-mirror tag SHA verification**: keep `git ls-remote --tags` on every mirror after push
  (origin/public/omdsh) — it did not catch this class, but it catches the mirror-lag/partial-push
  class; the checklist needs both.
- **Plane-aware validation**: after any release touching `lib/index.js`, restart the host and
  probe the new host behavior (SVG → 200 `image/svg+xml`), not just a browser refresh;
  client-plane refresh alone proves nothing about host-plane routes.
- **Report the upstream text-corruption bug** (result-text assembly splicing lines at a shared
  prefix, non-deterministic, clean on re-read) with the decoded log frames attached — do not add
  payload "repair" logic in the plugin; the defensive render chain (§4) contains it, the upstream
  fix eliminates it.

---

## Skill-mode note

Executed as **Mode A · inspect** (read-only): investigation and report only; no configuration,
dependency, or source writes anywhere, and nothing inside the fixture or benchmark repository was
touched. Pre-existing failures: not collected (no baseline build/test run — outside the read-only
scope and not required by the brief).
