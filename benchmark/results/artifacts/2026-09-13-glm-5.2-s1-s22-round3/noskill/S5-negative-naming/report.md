# S5 · Naming Four-State Judgment Report (dsh-greet / acme/greet)

**Scope**: read-only review of the fixture `package.json` and `dsh-plugin.naming.json`. No reproduction environment was built; no registry, network, or external service was queried (closed-book brief). Verdict states used: **compatibility error / collision recommendation / needs registry context / unknown**.

## Manifest summary

| Field | Declared value |
|---|---|
| coordinate | `acme/greet` |
| packageName | `dsh-greet` (v0.1.0, `private: true`) |
| pluginNames | `greet` |
| loaderIds | `acme-greet` |
| services | `search` |
| tools | `acme_greet_hi` |
| commands | `acme-greet-hi` |
| skills | `greet` |
| skillProviders | `acme-greet-filesystem` |
| events | `web-search/ready` |
| settingsNamespaces | `acme-greet` |
| routes | exact `/api/plugins/acme-greet/hi` |

## Per-surface verdicts

| # | Surface | Value | Verdict | Reasoning |
|---|---|---|---|---|
| 1 | Plugin name | `greet` | **No compatibility error** — generic short name; collision risk only | A short lowercase name satisfies the naming policy; nothing in the declaration is structurally invalid. However `greet` is a highly generic word likely chosen by other community plugins, so a namespace prefix is a **collision recommendation**, not an error. |
| 2 | Loader ID | `acme-greet` | No compatibility error | Namespaced (`acme-`) and consistent with the coordinate `acme/greet` and packageName `dsh-greet`. Whether another registry entry already claims `acme-greet` is **unknown** (registry not queried). |
| 3 | Service name | `search` | **Collision recommendation (warning, not an error)** | `search` is unprefixed and generic. `search` is a common capability/service name in the wider ecosystem (web-search style plugins commonly expose a `search` service), so co-installing this plugin alongside a search-capability plugin risks a service-name collision at Cordis's flat service registry. It is a recommendation to rename to something like `acme-greet-search` (or drop the service if unused), not a structural incompatibility. |
| 4 | Tool name | `acme_greet_hi` | No compatibility error | Prefixed with the plugin identity (`acme_greet_`), lowercase, underscore-safe. Collision status vs. other registry tools: **unknown / not checked**. |
| 5 | Command name | `acme-greet-hi` | No compatibility error | Prefixed and kebab-case, consistent with loader ID and settings namespace. Registry collision status: **unknown / not checked**. |
| 6 | Skill name | `greet` | **Collision recommendation** | Unprefixed single common word. Skill names are often addressed user-facing; a bare `greet` invites collision with any other greeting plugin's skill. Recommend `acme-greet` or `acme/greet`-derived skill id. Not a structural error. |
| 7 | Skill provider | `acme-greet-filesystem` | No compatibility error | Namespaced and specific. Registry availability: **unknown**. |
| 8 | Event name | `web-search/ready` | **Needs registry context (informational — shared channel)** | The scope segment `web-search` does not belong to this plugin's namespace (`acme-greet`). Publishing an event under a foreign/shared scope means: (a) listeners of the ecosystem's `web-search` channel may receive or miss this event unexpectedly; (b) whether this is intentional (interoperating with an existing `web-search` channel) or a typo cannot be decided from the fixture alone. This is not a compatibility error in itself but requires registry/ecosystem context to classify. |
| 9 | Settings namespace | `acme-greet` | No compatibility error | Namespaced, matches loader ID. Global uniqueness unverified: **unknown**. |
| 10 | Route | exact `/api/plugins/acme-greet/hi` | No compatibility error | Lives under the plugin-namespaced segment `/api/plugins/acme-greet/`, so cross-plugin collision is unlikely by construction. Absolute uniqueness in a deployed router: **unknown / not checked**. |

## Registry status — honest negative findings

- **No online registry query was performed** (closed-book brief; no network). Therefore this report makes **no claim** that any of the above names — `greet`, `acme-greet`, `dsh-greet`, `search`, `acme_greet_hi`, `greet` (skill), `acme-greet-filesystem`, `web-search/ready`, `acme-greet` (settings), or the route — are *reserved*, *taken*, or *globally available*. All registry-side availability is **unknown / not checked**.
- "No findings" above does **not** mean "no problems": the absence of detected errors is bounded by (a) the two fixture files reviewed, (b) no execution of the plugin, and (c) no registry data.

## Additional publish observations

- `package.json` has `private: true`: a package in this state is rejected by npm `publish`. The fixture README states this is the repository's "test material, do not publish" discipline rather than part of the naming brief, so it is recorded as context, not a naming verdict.
- Inconsistency worth noting: the tool uses underscores (`acme_greet_hi`) while the command uses hyphens (`acme-greet-hi`). Both are individually well-formed; symmetry would suggest picking one separator convention per plugin family (style note, not an error).
- The `dsh-plugin.naming.json` schema fields (`schemaVersion: 1`, `policy: dsh-plugin-naming/v1`) are internally consistent with each other; no structural mismatch between the manifest and `package.json` name (`dsh-greet` = declared `packageName`).

## Conclusion

- **Compatibility errors: 0.**
- **Collision recommendations: 2** (unprefixed service `search`; unprefixed skill `greet`).
- **Needs registry context: 1** (event `web-search/ready` under a foreign/shared scope).
- **Registry availability of every name: unknown / not checked** — no reserved-or-available claims are made.
