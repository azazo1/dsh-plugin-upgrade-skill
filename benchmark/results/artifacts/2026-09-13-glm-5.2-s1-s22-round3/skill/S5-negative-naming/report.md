# S5 · Naming Four-State Judgment (Read-Only Report)

Task: read-only judgment of a community plugin's naming compatibility and registry status from
`/app/fixture/` (`package.json` + `dsh-plugin.naming.json`). Methodology: plugin-upgrade skill,
Mode A (inspect) discipline — no writes, no environment build, no registry/network queries
(closed-book brief). Fixture was not modified.

## Inputs examined (unchanged)

- `package.json` — `"name": "dsh-greet"`, `"version": "0.1.0"`, `"private": true`.
- `dsh-plugin.naming.json` — `schemaVersion: 1`, policy `dsh-plugin-naming/v1`, coordinate `acme/greet`,
  and declared names across plugin/loader/service/tool/command/skill/skillProvider/event/settings/route surfaces.

## Verdict scale

`compatibility error` / `collision recommendation` / `needs registry context` / `unknown`

## Surface-by-surface judgment

| Surface | Declared value | Verdict | Reasoning |
|---|---|---|---|
| Plugin short name (`pluginNames`) | `greet` | **No compatibility error; registry status unknown** | The short name is syntactically valid under `dsh-plugin-naming/v1`; the namespaced coordinate `acme/greet` is the authoritative identity, so the bare short name raises no compatibility error. A prefix is only a collision *recommendation*, not an error. Whether `acme/greet` (or npm `dsh-greet`) is taken cannot be determined closed-book — see Registry status. |
| Plugin coordinate | `acme/greet` | **Unknown (not checked)** | No online registry query was permitted; reservation/availability is unverified. |
| npm package name (`packageName`) | `dsh-greet` | **Unknown (not checked)** | Consistent between `package.json` and the manifest, and `private: true` currently blocks accidental publish — but npm availability of `dsh-greet` is unverified. |
| Loader IDs | `acme-greet` | **No error; unknown externally** | Prefixed with the plugin's own namespace; loader IDs are host-local, so no compatibility error. Cross-plugin collision inside a user's install cannot be ruled out without the target install — unknown. |
| Services | `search` | **Collision recommendation (warning, not an error)** | Unprefixed, generic, highly likely to collide with other plugins' `search` services in a shared context (the core/web capability already exposes search-shaped services). Recommend `acme-greet/search` or `acme-search`. This is a recommendation; it does not block loading. |
| Tools | `acme_greet_hi` | **No error; registry context needed** | Namespaced by prefix `acme_greet_`, so no self-collision; whether the tool id is free in a given install depends on other plugins — needs registry context. |
| Commands | `acme-greet-hi` | **No error; registry context needed** | Prefixed and specific; collision only checkable against the live command registry. |
| Skills | `greet` | **Collision recommendation** | Unprefixed generic token in a shared skill catalog; recommending a prefixed id (`acme-greet`). Not a compatibility error. |
| Skill providers | `acme-greet-filesystem` | **No error; registry context needed** | Prefixed; provider ids share a registry with other plugins, so availability is install-dependent. |
| Events | `web-search/ready` | **Needs registry context (informational — shared channel)** | The `web-search/` channel prefix suggests a shared/community channel, not a plugin-private event. Emitting on a shared channel is informational here, but whether that channel and payload are actually owned/registered by another plugin cannot be confirmed closed-book — do not treat it as free. |
| Settings namespaces | `acme-greet` | **No error; registry context needed** | Prefixed and specific; only a live settings registry can confirm uniqueness. |
| Route | exact `/api/plugins/acme-greet/hi` | **No error; unknown externally** | Namespaced under `/api/plugins/acme-greet/`, the conventional plugin-scoped segment, so no compatibility error; route uniqueness in a given host is unverified. |

## Registry status — explicit negative statement

**No online registry (community registry or npm) was queried; this is a closed-book review.**
Therefore:

- I do **not** claim `acme/greet`, `dsh-greet`, or any declared service/event/skill/tool/command id is
  "reserved" or "globally available". All external-availability verdicts above are **unknown / not checked**.
- The absence of naming findings in this manifest does **not** mean the names are free: unprefixed generic
  ids (`search`, `greet`) carry concrete collision risk, and even prefixed ids can only be validated against
  the live registry at publish time. "No findings ≠ no problems."
- Pre-publish checklist for the author: query the community registry for the coordinate `acme/greet`,
  the npm name `dsh-greet`, the shared event channel `web-search/`, and each service/skill id; only then
  treat them as available.

## Constraints honored

- Read-only: no file under the fixture (or anywhere in the benchmark repo) was created, modified, or deleted.
- No reproduction environment built, no dependencies installed, no migration performed, no network access.
- Only output written: this report file in the designated output directory.

## Summary of the four graded surfaces

1. Short plugin name `greet`: valid — no compatibility error; prefixing is only a collision recommendation.
2. Unprefixed service `search`: warning (collision recommendation), not an error.
3. Event `web-search/ready`: shared channel — informational / needs registry context.
4. Registry status: unknown — no registry was or could be queried closed-book; no "reserved/available" claim made.
