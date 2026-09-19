# H26 Reference Solution

## Reference Changes

See [solution/plugin/](plugin/) (expected judge score 100). The **only** class of change is
in `package.json` — the plugin self-description the host uses to register an installed
package as a plugin:

- `main: "index.js"` — the entry the host loads;
- `exports` map — resolvable module surface;
- the `dsh` block — the plugin's own declaration to the host.

`index.js` is untouched (it was already correct for 0.1.2-alpha.2).

## Core Point (In One Sentence)

**Installing a package and registering a plugin are two different layers.** `dsh plugin add`
succeeds at the dependency layer (the package lands in the profile), but the host only
registers an entry when the package carries its plugin self-description (`main` / `exports`
/ the `dsh` block) — with those fields absent the entry never appears in
`dsh plugin list`, no matter how many times you reinstall.

## Why the trap works

The in-source memo nudges toward a flaky-install story ("reinstall / clear the store");
the install indeed "succeeds" every time, which makes the reinstall theory feel confirmed.
The real defect never was in the install layer.

## Verification (in-container, isolated profile)

```
dsh plugin --profile bench-h26-notlisted-trap add /app/fixture   # ok
dsh plugin --profile bench-h26-notlisted-trap list               # entry now present
dsh --profile bench-h26-notlisted-trap 'ping'                    # MISSING_CREDENTIAL → alive
```

## Report contents the judge credits

- the two layers named separately (dependency installation vs. plugin registration);
- the cause pinned on the missing manifest fields (main/exports/dsh), not the host;
- reinstall explicitly ruled out as a fix.
