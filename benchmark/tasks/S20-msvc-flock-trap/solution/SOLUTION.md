# S20 Reference Solution

## Reference Changes

See [solution/report.md](report.md) (expected judge score 100). The task is
read-only: the only artifact is the diagnosis report.

## Core Point (In One Sentence)

An install blocker whose obvious cause (a native build) is not the real
requirement: the module is statically imported so it must load, but Windows
never executes its `flock` path (named kernel semaphore instead) — so the
least-invasive fix is a pnpm patch that skips the native build on Windows and
provides a pure-JS fallback, not Visual Studio and not an upstream change.

## Boundaries

- The judge checks the report only; the fixture must remain unchanged
  (read-only discipline).
- Two caps mirror the traps: relying on installing Visual Studio caps at 50;
  relying on `--ignore-scripts` alone caps at 40.
- The finding is carded as DSH-0.1.3-A1-03 (single-host Windows field report).
