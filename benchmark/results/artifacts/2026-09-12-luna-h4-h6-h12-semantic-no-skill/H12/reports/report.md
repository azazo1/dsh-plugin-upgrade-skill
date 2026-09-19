## Root Cause

The migration shape is not correct for dsh 0.1.2-alpha.2. A unary Remote call normally fulfills with a `RemoteResult`; an application-level failure is represented by a fulfilled result with `ok: false`, not by a rejected promise. Therefore the `catch` block is not the ordinary `RemoteError` handling path, and `result.value` is not valid until `result.ok` has been checked.

`RemoteError` describes the error payload crossing the protocol boundary. It is not evidence that JavaScript threw a `RemoteError` instance locally, so the error must be read from `result.error` on the failed result.

## Problems in the Current Code

- `return result.value` assumes success without checking `result.ok`. On a failed result, `value` is absent or not meaningful; the code silently returns an invalid success value instead of handling `result.error`.
- The `gateway/cancelled` and `session/not-found` branches in `catch` do not handle ordinary Remote failures, because those failures resolve normally and never enter `catch`.
- `instanceof RemoteError` is the wrong discriminator across a serialized Remote boundary. The consumer should discriminate the result with `result.ok`, then inspect `result.error.code`.
- The fallback in `catch` retries every actual rejection, including assembly, validation, serialization, transport/dispatch, or programming failures that should remain visible. It can hide defects and recurse indefinitely.
- The object method's name does not create a lexical `renameSession` binding for its body. The retry callback can consequently raise `ReferenceError`; the corrected version declares a local function and returns it.

## Corrected Implementation

```ts
import type { Context } from '@deepseek-ai/cordis'

export const name = 'h12-remote-result-boundary-fixture'

export function apply(ctx: Context) {
  ctx.slots.inject('session-rename-helper', () => {
    async function renameSession(sessionId: string, title: string) {
      const result = await ctx.remote.session.rename({ sessionId, title })

      if (result.ok) {
        return result.value
      }

      if (result.error.code === 'gateway/cancelled') {
        return retry(() => renameSession(sessionId, title))
      }

      if (result.error.code === 'session/not-found') {
        return null
      }

      // Unknown application-level Remote failures are not retryable by default.
      throw result.error
    }

    return { renameSession }
  })
}

function retry<T>(operation: () => T): T {
  // Production code should schedule a bounded retry with suitable backoff.
  return operation()
}
```

## RemoteResult Control Flow

`await ctx.remote.session.rename(...)` first waits for the Remote invocation promise. When the invocation produces a protocol response, the promise fulfills with one discriminated result:

- `ok: true` means the operation succeeded, and `value` is the returned value. This is the only branch in which `result.value` should be read.
- `ok: false` means the operation failed at the Remote/application level, and `error` contains the typed, protocol-shaped error. This is the branch in which `result.error.code` should be inspected; `result.value` is not a success value there.

Thus cancellation and not-found handling belong after the `ok` check. They are result branches, not exception branches. The error-code vocabulary in the fixture is already in the required namespaced form and does not need migration here.

## Reject Boundary

`catch` around the `await` can see only a rejected invocation promise: a failure that prevents the client from producing a `RemoteResult`. Depending on the client machinery, that boundary includes local request assembly or validation, argument/codec or serialization failures, an invalid/missing remote binding, and infrastructure or dispatch failures that cannot be represented by the protocol response.

It cannot see a normal Remote handler/application failure encoded as `{ ok: false, error: ... }`. The corrected helper has no catch so those genuine rejects naturally propagate to its caller. If a caller adds a catch, it must classify only documented rejection types and must not treat every caught value as a retryable `RemoteError`.

## Error Boundary

There are two distinct error boundaries: the Remote protocol boundary, where a handled Remote failure becomes `result.error`, and the JavaScript promise boundary, where invocation machinery may reject. A `RemoteError` type or serialized error object does not guarantee a matching local prototype, so `instanceof RemoteError` is not a reliable cross-boundary test.

The safe order is: test `result.ok`, return `result.value` only for `true`, inspect `result.error.code` only for `false`, and rethrow or explicitly handle actual rejected promises according to their documented cause. Retry policy should be an explicit allowlist for known transient result codes such as `gateway/cancelled`, not a blanket catch-all.
