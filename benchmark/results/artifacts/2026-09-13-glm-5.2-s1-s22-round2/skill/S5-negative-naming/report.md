# S5 · Naming Four-State Judgment Report (Read-Only Review)

## Scope and method

- Fixture reviewed read-only: `package.json`, `dsh-plugin.naming.json` (schema `dsh-plugin-naming/v1`), plus fixture `README.md`. No file under the fixture (or anywhere in the benchmark repository) was modified.
- Mode A (inspect) per the plugin-upgrade skill: read-only investigation, report, stop. No reproduction environment was built, no dependencies installed, no network/registry query performed.
- This is a closed-book review: no online registry was queried, so **no "reserved" or "globally available" claim is made anywhere below**. Registry availability for every externally-visible identifier is reported as **unknown / not checked**.

Judgment states used: **compatibility error** (violates a naming rule/format), **collision recommendation** (valid but likely to collide; prefixing recommended), **needs registry context** (cannot be judged locally), **unknown**.

## Surface-by-surface verdicts

| Surface | Declared value | Verdict | Reasoning |
|---|---|---|---|
| Plugin short name | `greet` | **No compatibility error** (valid) | The official short name is unprefixed by design and format-valid. A prefix is only a collision *recommendation*, never an error. See also registry status below. |
| Plugin coordinate | `acme/greet` | No error; **collision recommendation for the bare short name** | The `namespace/name` coordinate is namespaced and well-formed. Uniqueness of `greet` among community short names is not locally verifiable. |
| Package name (`package.json`) | `dsh-greet` | **Needs registry context / unknown** | Unscoped, generic `dsh-` package on a public registry. Cannot check npm occupancy offline; may already be taken or squatted. Do not claim availability. Note `private: true` currently blocks accidental publish (fixture README states this is intentional). |
| Loader id | `acme-greet` | No error | Prefixed with the namespace; low collision risk by construction. Registry-wide uniqueness still unverified (unknown), but local judgment is clean. |
| Service name | `search` | **Collision recommendation (warning, not error)** | Cordis service names resolve in a single global in-process registry. `search` is a maximally generic, unprefixed name that a DSH host or another plugin (e.g. the built-in web-search capability) may already provide or later provide. Recommend `acme-greet/search` or `acme.search`-style prefixing. This is a collision risk, not a format/compat error. |
| Tool name | `acme_greet_hi` | No error | Namespaced with underscore prefix; matches tool-name format expectations. |
| Command name | `acme-greet-hi` | No error | Namespaced kebab-case; low collision risk. |
| Skill name | `greet` | **Collision recommendation** | Skill names live in a shared per-session catalog alongside other plugins' skills and built-in skills. The bare `greet` is generic and likely to collide (or be confused) with other plugins exposing a greeting skill. Recommend `acme-greet` or similar prefixed id. |
| Skill provider | `acme-greet-filesystem` | No error | Namespaced; well-formed. |
| Event name | `web-search/ready` | **Informational / shared channel — needs context (not an error)** | The `web-search` namespace is a shared/cross-plugin channel concept, not owned by this plugin. Declaring an event under it is allowed (shared channel, informational), but the plugin must not assume ownership of that channel; compatibility depends on the actual event contract published by the owning capability. Flag for awareness rather than blocking. |
| Settings namespace | `acme-greet` | No error | Namespaced; matches loader id. |
| Route | `/api/plugins/acme-greet/hi` (exact) | No error | Sits under the plugin-namespaced `/api/plugins/acme-greet/` prefix; exact-match and namespaced, so no cross-plugin route collision is expected locally. |

## Registry status (negative capability / honesty section)

- **No online registry query was performed** (closed-book brief; no external services). Therefore the npm availability of `dsh-greet`, the reservation status of the `acme` namespace, the uniqueness of the short name `greet`, and any prior use of `search`/`greet`/`web-search/ready` by other community plugins are all **unknown / not checked**.
- "No findings" above must not be read as "no problems": every *no error* verdict is a local format/collision judgment only, and several surfaces (package name, plugin short name, namespace) additionally require a registry check before publishing. Treat those as **unknown** for availability purposes.

## Summary of actionable items before publish

1. **Service `search`**: rename to a namespaced id (collision recommendation, warning-level).
2. **Skill `greet`**: prefix it (collision recommendation).
3. **Event `web-search/ready`**: confirm the shared-channel contract with the `web-search` capability owner; informational.
4. **Registry checks** (cannot be done here): package `dsh-greet` availability, `acme` namespace reservation, short-name `greet` uniqueness — all currently unknown.
5. Remove `private: true` only at actual publish time (intentional guard per fixture README).

## Constraints honored

- Fixture and benchmark repository untouched; output written only to the designated report directory.
- No reproduction environment built, no installs, no network access, no lifecycle scripts run.
