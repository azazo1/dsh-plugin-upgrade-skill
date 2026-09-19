# S20 · Windows Install Blocker: A Native Build the Runtime Never Calls — Diagnostic Report

Scope: static diagnosis only. The fixture pack at `environment/fixture/` was read; nothing under it was modified. No Visual Studio was installed; no upstream dependency was changed; no network access was used.

Evidence files cited: `install-error.log`, `manifest-excerpt.json`, `lease-excerpt.md`, `win32-excerpt.ts`, `README.md` (all under the fixture pack).

## 1. What exactly fails, and why

- **Failing package / step**: `fs-ext@2.1.1` runs its install script `node-gyp configure build` during `pnpm install` (`install-error.log`: `fs-ext@2.1.1 install: node-gyp configure build`), and the configure step aborts with `gyp ERR! find VS … Error: Could not find any Visual Studio installation to use`. pnpm then fails the whole install: `pnpm: Command failed with exit code 1`, `dsh 退出码: 1`.
- **Missing toolchain**: node-gyp cannot find a Visual Studio C++ toolchain — the log shows `msvs_version not set`, `VCINSTALLDIR not set`, `could not use PowerShell to find Visual Studio 2017 or newer`, and the remedy it prints is "install the latest version of Visual Studio ... including the \"Desktop development with C++\" workload". `fixture/README.md` confirms the machine state: "no Visual Studio / Build Tools installation (no `vswhere.exe`, no VS directory). The owner refuses to install them." Node and pnpm themselves work ("every previous dsh upgrade on this machine installed fine"), so the only broken piece is the MSVC-requiring native compile.
- **Who pulls it in**: `manifest-excerpt.json` — `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` declares `"fs-ext": "2.1.1"` as a (pinned) dependency. The new dsh version introduces this dependency; that is why this machine, which installed every previous upgrade fine, now fails.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

Skipping install scripts only skips the node-gyp build — it does not make the module loadable. `lease-excerpt.md` states: "`flock` is imported statically at module top — the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken." Consequences:

- With `--ignore-scripts`, `fs-ext` would be placed in `node_modules` **without its compiled `build/Release` binary** (fs-ext is a native addon; without the built `.node` file `require('fs-ext')` fails).
- Because `src/lease.ts` imports `flock` **statically at module top**, `@deepseek-ai/dsh-session-persistence-jsonl` (and therefore the dsh boot path that loads session persistence) throws at module resolution/loading time on every platform — the service would not boot. `--ignore-scripts` converts a clean install failure into a later runtime failure.

## 3. Which lock path Windows actually takes, and what it implies

- `lease-excerpt.md`: "POSIX takes a non-blocking `flock(2)` (through fs-ext) on `session.lock` … and **Windows holds a named kernel semaphore derived from that path — never a file lock or handle**" and "**Windows has no lock file at all.**"
- `win32-excerpt.ts` confirms the Windows implementation: `acquireLockHandleWin32 / releaseLockHandleWin32 wrap these named-semaphore primitives (`CreateSemaphoreW`, `WaitForSingleObject`, `ReleaseSemaphore`); **"no flock(2) is involved on Windows."**
- **Implication**: on Windows the `flock` branch is dead code — the compiled `fs-ext` native binary is never used at runtime. The *only* reason Windows needs `fs-ext` to exist is the static top-level `import { flock } from 'fs-ext'` in `lease.ts`, which forces module resolution. So the native build is an install-surface artifact, not a functional Windows requirement: a loadable pure-JS stub of `fs-ext` is functionally sufficient on Windows, while POSIX keeps the real native build.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing patch mechanism, which `fixture/README.md` documents: "The repository already patches native dependencies through pnpm's `patchedDependencies` mechanism (see the existing `patches/node-pty@*.patch` precedent): a patch can rewrite a package's install script and entry file, and `pnpm-workspace.yaml` registers it."

1. **Confirm the platform branch first** (already done in §3): Windows uses `acquireLockHandleWin32` (named semaphore); `flock` is POSIX-only. The native module is dead code on Windows.
2. **Create `patches/fs-ext@2.1.1.patch`** that makes two local edits to the packaged `fs-ext`:
   - **Install script**: rewrite the `install` script so `node-gyp configure build` runs only on non-Windows (e.g. a tiny JS guard: skip the build when `process.platform === 'win32'`). Linux/macOS behavior is unchanged — they still get the real native build.
   - **Entry file**: give the package's JS entry a pure-JS `flock` fallback on Windows that warns once and no-ops (the callback path never errors). This satisfies the static `import { flock } from 'fs-ext'` in `lease.ts` so the module resolves and loads; the export is never called on Windows, so the no-op is unreachable in practice.
3. **Register the patch** in `pnpm-workspace.yaml` under `patchedDependencies` (pin `fs-ext@2.1.1` exactly, matching the manifest's pinned version), and whitelist its (now guarded) build step under pnpm's build-allow configuration (`allowBuilds` / `onlyBuiltDependencies` equivalent for the pnpm version in use).
4. **Re-run `pnpm install`** on the Windows machine.
5. **Verify**:
   - `pnpm install` completes with exit code 0;
   - `require('fs-ext')` loads (no missing `.node` binary) and the `flock` callback path warns once instead of throwing;
   - the dsh service boots — `dsh web --no-open` starts and answers HTTP 200;
   - on a POSIX machine (or CI), confirm the patch leaves the native build intact, so POSIX locking still gets real `flock(2)`.

Explicitly rejected alternatives: installing Visual Studio Build Tools (owner refuses, and unnecessary — the binary is never used on Windows); `--ignore-scripts` alone (breaks module loading, §2); editing/upstreaming the dependency or removing `fs-ext` from the manifest (violates "no upstream changes"; the pinned version would diverge from upstream and POSIX would lose its lock implementation).

## 5. Corridor card

**`DSH-0.1.3-A1-03`** — "Windows install fails on the `fs-ext` native build; the runtime never calls `flock` on Windows" (type: breaking), from the `dsh-v0.1.2-rc.1 → dsh-v0.1.3-alpha.1` corridor reference (`references/v0.1.3-alpha.1.md`). The card matches this fixture exactly: `fs-ext@2.1.1` pinned by `@deepseek-ai/dsh-session-persistence-jsonl`, the `node-gyp`/`gyp ERR! find VS` install failure, the static `flock` import in `src/lease.ts`, the Windows named-semaphore bindings in `src/win32.ts`, and the same pnpm-patch recipe followed in §4 above.
