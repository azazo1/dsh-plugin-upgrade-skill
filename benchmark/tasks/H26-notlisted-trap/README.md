# H26 · not-listed trap (installs but never registers)

Distilled from a real top-tier failure: `anywhere-labs/dsh-desktop` (22.2k★) failed a
50-plugin live verification on 2026-09-01 with exactly this shape — `dsh plugin add`
succeeds, the entry never appears in `dsh plugin list` (the npm form of the package
ships with no `main` and no `dsh` block).

The fixture reproduces the shape privately: correct 0.1.2-alpha.2 source, healthy
install, and a `package.json` with no plugin self-description. An in-source memo
nudges toward the flaky-install/reinstall theory.

**What it tests**

- separating the dependency-installation layer from the plugin-registration layer;
- attributing not-listed to the missing manifest fields, not the host;
- resisting the reinstall trap (reinstall-led diagnoses are capped at 40);
- closing the loop live: manifest fix → listed → cold boot reaches the application
  layer (`MISSING_CREDENTIAL` as the alive signal, exit code not a criterion).

Fixture plugins keep `"private": true` and a README note: exam material, never publish.
