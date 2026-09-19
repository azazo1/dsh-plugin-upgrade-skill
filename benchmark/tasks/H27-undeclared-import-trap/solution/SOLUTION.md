# H27 Reference Solution

## Reference Changes

See [solution/plugin/](plugin/) (expected judge score 100). The **only** change:
`peerDependencies` gains `"@deepseek-ai/dsh-llm": "^0.1.2-alpha.1"`.
`index.js` is untouched.

## Core Point (In One Sentence)

**An import without a declaration is a load-time bomb**: the install layer
fetches only what `package.json` declares, so the package was never there for
the loader — and in 0.1.2 the host no longer provides packages implicitly.

## Why the trap works

The memo suggests a try/catch-and-degrade "fix"; it silences the crash by
dropping the capability, which the judge caps at 40. The honest fix is one
declaration line.
