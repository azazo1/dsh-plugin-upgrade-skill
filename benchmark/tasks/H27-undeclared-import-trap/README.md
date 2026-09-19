# H27 · undeclared-import trap (installs, lists, crashes on load)

Distilled from the most common real failure shape in our 50-plugin live
verification (2026-09-01): six top-100 plugins died at load with
module-resolution errors while install and listing passed — an import whose
dependency was never declared (the old host provided some packages implicitly;
0.1.2 does not).

The fixture reproduces the shape: a correct 0.1.2 entry whose `index.js`
imports `@deepseek-ai/dsh-llm` (ContentBlock's new home) with no matching
declaration, plus an in-source memo nudging toward try/catch-and-degrade.

**What it tests**

- pinning the failing import and the `ERR_MODULE_NOT_FOUND` evidence;
- attributing the crash to the undeclared dependency (not the host, not the code);
- understanding why install never fetched it (declarations drive installs);
- the accepted fix is declaring the dependency — swallowing the import is the
  trap and caps the score at 40;
- closing the loop live: add → listed → cold boot reaches the application layer.

Fixture plugins keep `"private": true` and a never-publish note: exam material.
