# S5 · Naming Four-State Judgment Report (Read-Only)

Task: pre-publish judgment of a community plugin's naming compatibility and registry status.
Fixture: `dsh-plugin.naming.json`, `package.json`, `README.md` (read-only; nothing under the fixture was modified).
Mode: Mode A-style read-only inspection (plugin-upgrade skill). No reproduction environment built, no dependencies installed, no network/registry queries performed — this is a closed-book brief.

## Four states used

- **compatibility error** — the name violates a syntactic/structural rule of the naming policy itself; would fail regardless of registry state.
- **collision recommendation** — syntactically valid but namespace-risky; recommend prefixing/scoping to reduce collision likelihood (not an error).
- **needs registry context** — validity depends on who else registered/uses the name (shared channels, well-known identifiers); cannot be judged offline.
- **unknown** — no offline evidence available; honest not-checked status (never reported as "reserved" or "globally available").

## Inputs recorded

- `dsh-plugin.naming.json`: schemaVersion 1, policy `dsh-plugin-naming/v1`; plugin coordinate `acme/greet`, packageName `dsh-greet`.
- Declared names: pluginNames `["greet"]`; loaderIds `["acme-greet"]`; services `["search"]`; tools `["acme_greet_hi"]`; commands `["acme-greet-hi"]`; skills `["greet"]`; skillProviders `["acme-greet-filesystem"]`; events `["web-search/ready"]`; settingsNamespaces `["acme-greet"]`; routes `[{"kind":"exact","path":"/api/plugins/acme-greet/hi"}]`.
- `package.json`: name `dsh-greet`, version 0.1.0, `private: true`.

## Per-surface judgment

| Surface | Declared value | Verdict | Reasoning |
|---|---|---|---|
| Plugin short name | `greet` | **No compatibility error** (naming-valid) | The official short name `greet` is valid under the policy; a bare short name is not an error. Adding a namespace prefix would only be a **collision recommendation**, not a requirement. |
| Plugin coordinate | `acme/greet` | No compatibility error | Namespaced coordinate is well-formed (namespace `acme` + short name `greet`); consistent with the packageName and loader id below. |
| Package name | `dsh-greet` | No compatibility error; registry availability **unknown** | Matches the declared `packageName`. Whether the npm name `dsh-greet` is taken cannot be determined without a registry query — not checked. |
| Loader id | `acme-greet` | No compatibility error | Namespaced-prefixed, consistent with the coordinate `acme/greet`; collision with another `acme-*` plugin would be a registry question — not checked. |
| Service name | `search` | **Collision recommendation** (warning, not an error) | The unprefixed service name `search` is generic and highly collision-prone against other plugins (and host/web search services). Syntactically acceptable — this is a warning, not a compatibility error. Recommend a prefixed name such as `acme-greet/search` or `acme.search`. |
| Event name | `web-search/ready` | **Needs registry context** (shared channel; informational) | `web-search/ready` reads as a shared/cross-plugin channel name (web-search namespace), not a plugin-private event. Whether emitting on this channel is appropriate depends on which plugin/host owns the `web-search` namespace — not decidable offline. Informational, not an error by itself. |
| Tool name | `acme_greet_hi` | No compatibility error | Prefixed (`acme_greet_`), namespaced, unlikely to collide. |
| Command name | `acme-greet-hi` | No compatibility error | Prefixed consistently with the loader id and coordinate. |
| Skill name | `greet` | No compatibility error; collision recommendation for registry availability | A bare skill name `greet` is valid as declared; whether another published plugin already registers the skill `greet` is a registry question — **unknown, not checked**. |
| Skill provider | `acme-greet-filesystem` | No compatibility error | Fully prefixed; low collision risk (registry availability still not checked). |
| Settings namespace | `acme-greet` | No compatibility error | Prefixed, matches loader id and coordinate. |
| Route | `/api/plugins/acme-greet/hi` (exact) | No compatibility error | Sits under the plugin-scoped `/api/plugins/<loader-id>/` segment, so the namespacing convention is respected; conflict beyond the plugin's own scope would require registry knowledge — not checked. |

## Registry status (negative capability — no findings ≠ no problems)

- **No online registry query was performed** (prohibited by the closed-book brief). Therefore:
  - npm availability of `dsh-greet`: **unknown / not checked**.
  - Availability of coordinate `acme/greet`, loader id `acme-greet`, and every short name (`greet`, `search`): **unknown / not checked**.
- I explicitly do **not** claim any name is "reserved" or "globally available". Absence of offline findings says nothing about registry occupancy; every registry-dependent question above must stay "unknown" until a live registry query is done at publish time.
- `package.json` carries `private: true`, which would block an accidental `npm publish`; before publishing this flag must be removed deliberately — noted, not changed (read-only review).

## Summary

- Compatibility errors: **0** across all surfaces.
- Collision recommendations: **1** — the unprefixed service name `search` (warning; recommend prefixing).
- Needs registry context: **1** — the event `web-search/ready` as a shared channel (informational).
- Registry availability of every name: **unknown / not checked** — no reserved or available claims made.

## Blockers / residual risk

- No blocker to this read-only judgment. Residual risk: all registry-occupancy questions remain open by design; re-run this judgment with a live registry query before publishing.
