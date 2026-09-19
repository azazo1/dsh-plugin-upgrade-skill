# Naming Compatibility & Registry Status Judgment — S5-negative-naming

## 0. Scope, method, and evidence base

- **Reviewed read-only** (no file under the fixture was created, modified, or deleted):
  - `fixture/package.json` (5 lines)
  - `fixture/dsh-plugin.naming.json` (17 lines)
  - `fixture/README.md` (6 lines — fixture-provided context describing the intended judgment rules for this declaration)
- **No registry query was performed or was possible.** The brief is closed-book and offline; there is no local registry snapshot, no network access, and no lookup tool in scope. Consequently, per the brief's own rule, nothing below is claimed to be "reserved" or "globally available". All global-uniqueness questions are reported as **unknown / not checked**.
- **No reproduction environment was built** and nothing was installed, executed, or migrated; this is a static judgment only.
- The naming policy referenced by the manifest (`policy: "dsh-plugin-naming/v1"`, `dsh-plugin.naming.json:3`) is **not included in the fixture**. Where a verdict depends on the policy text, I say so rather than guessing its clauses. The fixture README states the four intended judgment surfaces, and I use it as fixture-internal context, flagged as such.

## 1. Internal consistency checks (local, deterministic)

These can be decided from the files alone:

- `package.json:2` name `dsh-greet` **matches** `dsh-plugin.naming.json:4` `packageName: "dsh-greet"`. Consistent.
- `dsh-plugin.naming.json:4` is internally coherent: `namespace: "acme"` + `name: "greet"` → `coordinate: "acme/greet"`. The coordinate is exactly `namespace/name`. Consistent.
- `package.json:4` `"private": true` — per the fixture README this is the repository's "test material, do not publish" discipline, not part of the naming judgment. It is noted here only because a real publish attempt with `private: true` would be blocked at the package-manager level; that is a publishing-mechanics observation, not a naming verdict.

## 2. Per-surface verdicts

Verdict vocabulary (from the brief): **compatibility error** / **collision recommendation** / **needs registry context** / **unknown**.

### 2.1 Plugin name — `greet` (short name), coordinate `acme/greet` (`dsh-plugin.naming.json:4,6`)

**Verdict: no compatibility error found in the local declaration; global availability = unknown (needs registry context).**

Reasoning: the short name `greet` is the plugin's *official* short name, and the fixture README states it is valid — i.e., lack of a prefix on the official short name is not a violation; prefixes on derived identifiers are collision-avoidance recommendations, not hard requirements. I have no policy text to independently confirm this, so the precise statement is: **nothing in the fixture shows `greet` to be a compatibility error**, and per the fixture's own context it is intended to be valid. Whether the coordinate `acme/greet` is taken, reserved, or squatted in the real registry **cannot be determined from the given information** — that requires an online registry query.

### 2.2 Loader ID — `acme-greet` (`dsh-plugin.naming.json:7`)

**Verdict: no local defect; registry status unknown.**

Reasoning: the ID carries the `acme-` namespace prefix, which is the recommended collision-avoidance shape. Locally there is nothing to flag. Whether `acme-greet` collides with an existing loader ID in the registry is **not determinable offline** → needs registry context before publishing.

### 2.3 Service name — `search` (`dsh-plugin.naming.json:8`)

**Verdict: collision recommendation (warning) — not a compatibility error.**

Reasoning: `search` is an **unprefixed, highly generic** service name. Unlike the official plugin short name (§2.1), a *service* name is a derived identifier that other plugins may also declare, and `search` is exactly the kind of word multiple plugins will pick. The fixture README confirms the intended reading: this is a **warning, not an error**. Recommendation: rename to a prefixed form (e.g., following the same `acme-` / `acme-greet-` pattern used by the loader ID and commands) before publishing. Whether a concrete collision already exists in the registry is **unknown / not checked**.

### 2.4 Tool name — `acme_greet_hi` (`dsh-plugin.naming.json:9`)

**Verdict: no local defect; registry status unknown.**

Reasoning: carries the `acme_greet_` prefix, matching the collision-avoidance convention (note: snake_case here vs kebab-case for commands — both are prefixed; whether the policy mandates one separator style per surface **cannot be determined without the policy text**, and I do not flag it as an error on suspicion alone). Global uniqueness: not checked.

### 2.5 Command name — `acme-greet-hi` (`dsh-plugin.naming.json:10`)

**Verdict: no local defect; registry status unknown.**

Reasoning: properly prefixed with `acme-greet-`. No local issue. Registry collision: unknown.

### 2.6 Skill name — `greet` (`dsh-plugin.naming.json:11`)

**Verdict: unknown / needs registry context (possible collision recommendation; cannot be firmly classified from the given information).**

Reasoning: `greet` appears a second time, here as a *skill* name rather than the plugin's official short name. The fixture README's "valid unprefixed" statement covers the **official short name** surface; it does not explicitly cover the skill-name surface. Two readings are possible: (a) skill names follow the same rule as the plugin short name and `greet` is valid; (b) skill names are derived identifiers like services, in which case an unprefixed generic `greet` would warrant the same collision recommendation as `search` (§2.3). **Which reading is correct cannot be determined from the given information** — it requires the `dsh-plugin-naming/v1` policy text and/or registry context. The restrained verdict is therefore "unknown", with a note that if skills behave like services, the same prefixing recommendation applies.

### 2.7 Skill provider — `acme-greet-filesystem` (`dsh-plugin.naming.json:12`)

**Verdict: no local defect; registry status unknown.**

Reasoning: fully prefixed and descriptive. No local issue. Registry collision: unknown.

### 2.8 Event name — `web-search/ready` (`dsh-plugin.naming.json:13`)

**Verdict: informational — shared channel; not an error, but its ownership semantics need registry/host context.**

Reasoning: the event's namespace segment is `web-search`, **not** this plugin's own namespace `acme`/`acme-greet`. That pattern indicates a **shared channel** — a lifecycle/topic event defined by the host or by another plugin domain, which this plugin subscribes to or re-emits on. The fixture README confirms the intended classification: informational. Two honest caveats: (1) I cannot verify from the fixture whether `web-search/ready` actually exists as a published channel or is well-formed per policy — that needs host/registry context; (2) if this plugin *declares* (rather than consumes) this event, publishing into another domain's namespace would deserve a second look — the manifest alone does not disambiguate declare-vs-consume.

### 2.9 Settings namespace — `acme-greet` (`dsh-plugin.naming.json:14`)

**Verdict: no local defect; registry status unknown.**

Reasoning: properly prefixed, consistent with the loader ID. No local issue.

### 2.10 Route — `exact /api/plugins/acme-greet/hi` (`dsh-plugin.naming.json:15`)

**Verdict: no local defect (collision-unlikely by construction); registry/host mount status unknown.**

Reasoning: the route is an **exact** (not prefix/wildcard) match and is path-scoped under `/api/plugins/acme-greet/`, i.e., it lives inside the plugin's own prefixed subtree — structurally the route-analog of a prefixed identifier, so a local collision is unlikely by construction. Remaining unknowns that only host/registry context can answer: whether the host actually mounts plugin routes under `/api/plugins/<id>/`, and whether another plugin already occupies this exact path.

## 3. Overall judgment

- **Compatibility errors: none found in the local declaration.** This is a statement about the two fixture files only. It is *not* a claim that the plugin is clear to publish: per the brief, "no findings ≠ no problems" — none of the surfaces has been checked against the live registry, so global availability of every name above is **unknown / not checked**.
- **One collision recommendation:** the unprefixed generic service name `search` (§2.3) should be prefixed before publishing. Warning level, not blocking.
- **One informational note:** `web-search/ready` is a shared channel outside the plugin's own namespace (§2.8).
- **One unresolved classification:** skill name `greet` (§2.6) — needs the naming-policy text and/or registry context to classify firmly.
- **Registry status of all surfaces: unknown.** No online registry query was possible in this closed-book, offline review; I explicitly do not claim any name is "reserved" or "globally available".

## 4. What would be needed to close the unknowns (procedure, not performed)

1. Obtain the text of naming policy `dsh-plugin-naming/v1` (referenced at `dsh-plugin.naming.json:3` but not shipped in the fixture) to confirm: whether unprefixed skill names are governed like the official short name or like services, and whether separator style (snake_case vs kebab-case) is normative per surface.
2. Run an online registry query for each declared identifier (coordinate `acme/greet`, loader ID, service, tool, command, skill, skill provider, event, settings namespace, route) to convert every "unknown" into "available / collision / reserved".
3. Confirm against host documentation whether declaring an event in a foreign namespace (`web-search/ready`) denotes subscription or ownership.
4. Only after 1–3: flip `private: true` if publishing is actually intended (noted as repository discipline, outside this judgment's scope).
