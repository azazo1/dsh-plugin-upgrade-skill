# H6 remote error-flow migration report

## Scope and evidence

This is a read-only assessment of `/app/fixture`.

- `package.json` declares `@deepseek-ai/dsh-typert-protocol` at `0.1.2-alpha.2`.
- `src/remote-usage.ts` still compares `result.error.code` with the legacy literals
  `'cancelled'` and `'internal'`.
- The same source uses `result.error instanceof RemoteError` and returns from a
  catch-all `catch`, so both an error object that crosses a realm boundary and any
  unrelated thrown value are treated as success.
- `README.md` independently identifies all three behaviors as the migration trap.

The source comment is therefore contradicted by the fixture's own migration note;
it is not evidence that the legacy literals remain valid.

## Required flow

1. If `rename` resolves with `result.ok === true`, finish normally.
2. If it resolves with `result.ok === false`, classify the returned error by its
   protocol `code` (the wire/data discriminator). Do not classify it with
   `instanceof RemoteError`; constructor identity is not reliable across realms
   or duplicated package copies.
3. Handle the branches as follows:

   - **Cancel:** recognize the canonical alpha.2 cancel code and return normally.
     Cancellation is the one expected, non-failure terminal branch.
   - **Internal:** recognize the canonical alpha.2 internal code, retain the
     remote error and propagate it (or pass it to the application's explicit
     error boundary). It must not be returned as if the rename succeeded. Any
     retry decision belongs to a deliberate higher-level policy.
   - **Unknown/unrecognized code:** use a safe default branch that preserves the
     received code and message, records appropriate diagnostics, and propagates
     the remote failure. Never treat an unknown code as cancellation or as a
     successful rename.
4. For an exception thrown by the remote call or by the handling code, remove the
   silent `return`. Either omit the catch or add context/diagnostics and rethrow
   the original value (preserving its cause). An unexpected exception is not an
   unsuccessful `Result` branch and must remain observable to the caller.

In implementation terms, the old `instanceof` fallback should be removed, and
the old literals must not be retained as accepted alpha.2 cases. A code-based
`switch`/mapping with an explicit default is the appropriate shape. If a runtime
structural guard is needed, check that the error is non-null and has a string
`code`; do not use constructor identity as the guard.

## Verification matrix

Verification should cover all of these cases:

| Case | Expected outcome |
|---|---|
| Successful result | Resolves normally. |
| Canonical alpha.2 cancel code | Resolves normally as an intentional cancellation. |
| Canonical alpha.2 internal code | Fails observably with the remote error; it is not reported as success. |
| Canonical alpha.2 unknown code | Fails observably while preserving the unknown code/message. |
| An unrecognized/future code | Takes the same safe unknown-code fallback, not cancel/internal handling. |
| Legacy `'cancelled'` and `'internal'` literals | Negative controls: they must not be assumed to be the alpha.2 canonical values. |
| A cross-realm or otherwise structurally equivalent remote error | Classification still follows `code`; it must not depend on `instanceof`. |
| An unexpected thrown exception | Rejects/propagates (with optional diagnostics), rather than resolving `void`. |

The fixture does **not** include the alpha.2 package source, type declarations,
lockfile, or API documentation. Consequently, the exact alpha.2 string literals
for the cancel, internal, and unknown cases are **unconfirmed** from the allowed
evidence. They must be taken from the public `0.1.2-alpha.2` protocol definition
when implementing the change; this report deliberately does not guess them.

## Bottom line

The community comment should be rejected as a trap. Migrate classification to
the alpha.2 wire-code values, cover cancel/internal/unknown plus an unrecognized
fallback, remove the cross-realm `instanceof` dependency, and make internal,
unknown, and unexpected exceptions observable instead of silently successful.
