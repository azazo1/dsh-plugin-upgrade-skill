# S15 — vanishing dock chips

## Root cause

The pre-existing crash is the `busy` reference in
`AttachmentChips`:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy
```

`busy` is a state variable local to `AttachButton`; it is not a binding in
`AttachmentChips`, nor is it passed in as a prop. When JavaScript evaluates
the expression in the chip's remove-button props, resolving `busy` therefore
throws `ReferenceError: busy is not defined`.

This is conditional on a chip being rendered. With no matching occurrences,
line 23 returns `null` before the `map` callback runs, so the button props and
the bad expression are never constructed. With an occurrence present, the
expression is reached for each chip. The `||` also hid the defect: if
`(props.input?.phase ?? 'plain') !== 'plain'` is true, JavaScript short-
circuiting never evaluates `busy`. It is only when the phase is `plain` (or
missing and therefore defaulted to `plain`) that the left side is false and
the free identifier is looked up. This explains why earlier execution could
leave the defect latent even though the bad source line was already in
v0.2.10.

The failure is at render time, before a user can click the x button. The dock
is an `InputZone` slot entry. The framework's slot error boundary catches the
render exception and unmounts that entry, so the entire dock disappears; it
does not merely disable or break the remove button. The attach button is a
different slot/component and remains mounted. The boundary exposes no UI
error, so the only visible diagnostic is the `ReferenceError` in the browser
console.

## Feature-diff bisection

The update date and the fact that the same component was edited make the
hover-preview additions a plausible suspect, but do not establish that they
caused this failure. The useful bisection is:

1. Render the v0.2.10 component in a small harness with a matching
   occurrence, a `plain` (or omitted) phase, a record, and an error boundary.
   It reproduces the boundary capture at the pre-existing `busy` expression.
2. Remove the hover hunk, then re-add it in one logical piece or by smaller
   pieces. Record both the boundary capture and the console stack/source
   location at each step. If the baseline already fails at `busy`, the
   hover code exposed or coincided with an already latent bug; it did not
   create that particular failure. A genuinely new preview crash would have
   a passing baseline and would appear only when its hunk is re-added, with a
   stack pointing into the new preview code.

The empty-state mount is not a valid bisection: it returns at the early
`occurrences.length === 0` check and never reaches either render-time path.

There is also a separate scope defect in the literal `feature.diff` that
should be verified against the actual shipped patch: its added

```js
const imageItem = status !== 'missing'
  ? record?.items.find(...)
  : undefined;
```

appears before the `map` callback, while `status` and `record` are declared
inside that callback. If that hunk was shipped exactly as shown, it produces
an earlier, independent `ReferenceError` (`status is not defined`) whenever
an occurrence exists. The console stack and the rollback/re-add bisect
separate that new defect from the pre-existing `busy` crash. In either case,
the source must be scoped and tested rather than attributing every failure
to the feature merely because it was released recently.

## Fix and hardening

Remove the dangling `|| busy` from `AttachmentChips`, or deliberately scope
the state by passing a `busy` value into the component (or owning equivalent
state there). For the preview implementation, compute `record`, `status`,
and `imageItem` inside the per-occurrence callback. The relevant shape is:

```js
const imageItem = status !== 'missing'
  ? (record?.items ?? []).find(item => isImagePath(item.path))
  : undefined;
```

The `record?.items ?? []` pattern is cheap insurance for an absent record or
absent items collection; `record?.items.find(...)` only protects the record,
not a null/undefined `items` value. Likewise, a DOM event target is not
guaranteed to be an Element. Use an optional-chained closest lookup, such as
`event.target?.closest?.('.remove')`, before treating it as a matched remove
button. These defensive reads are especially inexpensive in slot components,
where one malformed optional datum otherwise removes the whole slot entry.

## Regression that should have blocked release

Add a render smoke with a real matching occurrence, not just the empty state:

```js
it('renders a pending chip without an error-boundary capture', () => {
  const onBoundaryError = vi.fn();
  render(
    <ErrorBoundary onError={onBoundaryError}>
      <AttachmentDock
        input={{
          phase: 'plain',
          occurrences: [{
            occurrenceId: 'o1', source: SOURCE, ref: 'r1', label: 'shot.png'
          }]
        }}
        remove={vi.fn()}
      />
    </ErrorBoundary>
  );

  expect(document.querySelector('.dock .chip')).not.toBeNull();
  expect(onBoundaryError).not.toHaveBeenCalled();
});
```

The harness must seed `records` with `r1` (and, for the preview path, a
representative `items` array) and use the same slot/error-boundary wrapper as
the plugin. The important part is that the occurrence is present and the
phase makes the old right-hand side evaluate. An empty-state assertion alone
would pass while testing only the early return.

## Release-process lesson

`node --check` is a parser check. It can confirm balanced JavaScript and
valid syntax, but unresolved lexical names and unsafe property access are
runtime failures; it neither mounts the component nor evaluates its props.
That is particularly easy to miss in a lib-only plugin with no host
application test run.

The minimum viable pre-ship check is a runtime import/render smoke of every
slot-rendering entry, using representative data-present states (including at
least one pending occurrence and, for this feature, an image record), wrapped
in an error boundary and asserting that no capture occurs and the expected
chip is present. Keep the empty-state case as a second check, but it cannot
replace the data-present render. This tiny harness, in addition to the syntax
check, would have caught the free identifier before publishing v0.2.11.
