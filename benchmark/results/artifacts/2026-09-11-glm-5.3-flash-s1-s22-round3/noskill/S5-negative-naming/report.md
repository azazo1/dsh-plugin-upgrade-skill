# S5 · Naming Four-State Judgment Report

**Subject:** community plugin `dsh-greet` / `acme/greet` (read-only review of the evidence pack: `package.json`, `dsh-plugin.naming.json`, `README.md`).
**Method:** static inspection of the fixture only. No registry was queried and no environment was built or executed. Every statement below is grounded in the fixture files; anything not decidable from them is reported as **unknown / not checked**.

Verdict vocabulary (per the brief): **compatibility error** (violates a naming rule and will break), **collision recommendation** (legal but likely to collide with other namespaces; a recommendation, not a defect), **needs registry context** (correctness depends on information only a registry/registry policy can provide), **unknown** (cannot be judged from the pack).

---

## 1. Per-surface verdicts

### 1.1 Plugin name — `greet` (pluginNames) → **collision recommendation**
- Legal as a bare plugin name, and prefixing conventions are per-namespace guidance. The coordinate `acme/greet` (`namespace: "acme"`, `name: "greet"`) is the disambiguating form, so there is no compatibility error here.
- However, a bare short name like `greet` is a highly generic token; other community authors can declare the same short name under their own namespaces. Recommendation only: prefer consumers to address the plugin via the namespaced coordinate `acme/greet` and keep the short `greet` unadvertised as a global identifier. This does not block publishing.

### 1.2 Loader id — `acme-greet` (loaderIds) → **OK (no finding); registry context still applies globally**
- Consistent with the coordinate: namespace + name joined by `-`. It is properly prefixed with the author's namespace `acme`, so it is self-disambiguating and does not require a judgment beyond format consistency with `plugin.coordinate`, which it satisfies.

### 1.3 Package name — `dsh-greet` (packageName, and `package.json` `"name": "dsh-greet"`) → **collision recommendation (strong), partially needs registry context**
- The `dsh-` prefix is conventionally the official/core prefix in this ecosystem (the harness's own packages are `dsh-*` / `@deepseek-ai/dsh-*`). A community package claiming `dsh-greet` invites confusion with first-party packages and risks colliding with a future official `dsh-greet`.
- Whether the exact npm name `dsh-greet` is taken, or whether a registry/package-policy reserves the `dsh-*` prefix for official packages, cannot be decided offline. Without an online registry query I do **not** claim the name is free or reserved — recorded as **not checked**.
- Recommendation: rename to a namespace-owned package name (e.g. `acme-dsh-greet`, `dsh-plugin-acme-greet`, or whatever scheme the registry policy prescribes) — but the concrete compliant scheme itself is unknown without the registry policy.

### 1.4 Service name — `search` (services) → **collision recommendation (warning-level), not a compatibility error**
- `search` is fully unprefixed — no `acme` namespace marker at all. If service names share a flat per-process registry, any other plugin declaring `search` collides, and a generic English word maximizes that probability.
- Per the brief's grading intent (and the fixture README, which names "the unprefixed service `search` is a warning not an error"), this is a **warning/collision recommendation**: it is syntactically acceptable and will load, but it is poor hygiene. Recommendation: rename to `acme-greet-search` or similar so the namespace travels with the service name.

### 1.5 Tool name — `acme_greet_hi` (tools) → **OK**
- Correctly namespace-prefixed (`acme_greet_`), unique, self-disambiguating. No compatibility error, no meaningful collision risk attributable to this declaration.

### 1.6 Command name — `acme-greet-hi` (commands) → **OK**
- Fully namespace-prefixed and consistent with the loader id family. No finding.

### 1.7 Skill name — `greet` (skills) → **collision recommendation**
- Bare, unprefixed, and generic — same exposure as the plugin short name. If the skill catalog is flat, any other plugin exposing `greet` conflicts or ambiguates. Legal (not an error), but should be `acme-greet` / `acme-greet-hi` style. Note the internal inconsistency: the skill provider entry (below) is prefixed while the skill itself is not.

### 1.8 Skill provider — `acme-greet-filesystem` (skillProviders) → **collision recommendation / possible compatibility policy question**
- The id is correctly prefixed with `acme-greet`, so it does not collide as itself.
- However, its suffix `filesystem` suggests it may present or override a *filesystem* skill role. If the host treats certain well-known suffixes/roles (e.g. `filesystem`) as builtin-mapped, a community provider claiming that role could shadow or conflict with the builtin `filesystem` capability. Whether such a role reservation exists cannot be confirmed from the pack → the shadowing question is **unknown / needs registry (host capability catalog) context**. As declared, it is at minimum a naming recommendation: avoid mirroring builtin capability names even as suffixes.

### 1.9 Event name — `web-search/ready` (events) → **needs registry context (informational; shared-channel semantics)**
- The `namespace/event` shape is structurally valid, but the namespace chosen is `web-search` — which is not the plugin's own `acme` namespace. Two readings:
  1. **Intentional shared channel**: `web-search/ready` is a common channel other plugins emit/listen on. If so, this is informational: emitting on a shared channel is fine, but the plugin must not assume sole ownership, and payload contracts on shared channels are a compatibility surface the plugin does not control.
  2. **Accidental namespace**: if `web-search` is not an agreed shared channel, the plugin is publishing outside its namespace and should use `acme-greet/ready`.
- Which reading holds depends on whether `web-search/...` is a documented shared namespace in the registry/host event catalog — unverifiable offline. Reported as **needs registry context**, not as an error. I do not claim the channel is reserved or free.

### 1.10 Settings namespace — `acme-greet` (settingsNamespaces) → **OK**
- Matches the loader id; properly scoped to the author's namespace. No finding.

### 1.11 Route — `{ kind: "exact", path: "/api/plugins/acme-greet/hi" }` (routes) → **OK; runtime-uniqueness unknown**
- `kind: "exact"` with a path namespaced under `/api/plugins/acme-greet/` is well-scoped: an exact path (not a wildcard/prefix mount) under the plugin's own segment cannot structurally swallow other plugins' routes. No compatibility error.
- Whether another plugin already registered the identical exact path at runtime is a live-registry question → **not checked**.

### 1.12 `package.json` metadata — `"private": true`, version `0.1.0` → **compatibility-relevant observation, not a naming defect**
- `private: true` prevents npm publishing. The fixture README states this is the repository's "test material, do not publish" discipline, not part of the brief — so it is not judged as a defect. It is noted because a user literally "about to publish" a package with `private: true` would be blocked at `npm publish`; flipping it is a publishing step, not a naming judgment.

---

## 2. Aggregate judgment

- **No compatibility error found** in any declared name: every identifier is syntactically well-formed and the coordinate/loader/settings/route/tool/command family is consistently and correctly `acme`-namespaced.
- **Collision recommendations (4):** bare plugin short name `greet`, bare service name `search`, bare skill name `greet`, and the `dsh-`-prefixed package name `dsh-greet` (the strongest — it appropriates the official prefix family).
- **Needs registry context (2):** the `web-search/ready` event namespace (shared channel vs. out-of-namespace publish) and the `acme-greet-filesystem` skill provider (possible builtin-role shadowing).
- **Unknown / not checked:** npm availability of `dsh-greet`; existence of any official reservation of `dsh-*`, `web-search/*`, or the `filesystem` skill role; runtime route uniqueness. Per requirement 2, and per the fixture README's fourth bullet ("an unqueried registry is unknown"), these are reported as unknown, not as "reserved" or "globally available".

## 3. Consistency note on the declaration itself

The manifest is internally uneven: tools, commands, loader ids, settings, and routes carry the `acme-greet` namespace, while the plugin short name, service, and skill are bare, and the event lives under a foreign `web-search` namespace. This asymmetry (three of ten surfaces unnamespaced or misnamespaced) is the dominant hygiene finding; no individual entry is a hard error.

## 4. Scope and honesty statement

- Fixture read strictly read-only; nothing under the fixture was modified, and no files were written outside the designated report location.
- No registry, network, or reference material was consulted (closed-book); no reproduction environment was built.
- All claims above cite the fixture files (`package.json`, `dsh-plugin.naming.json`, `README.md`); anything beyond them is explicitly marked unknown/not checked.
