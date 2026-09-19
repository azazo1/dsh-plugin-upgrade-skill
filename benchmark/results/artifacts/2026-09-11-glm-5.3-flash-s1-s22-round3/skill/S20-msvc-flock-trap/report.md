# S20 · Diagnostic Report — Windows Install Blocker: A Native Build the Runtime Never Calls

## 1. What exactly fails, and why

- **Failing install step:** `fs-ext@2.1.1 install: node-gyp configure build` (from `install-error.log`). The package's install lifecycle script runs `node-gyp`, which compiles a native addon.
- **Failing toolchain probe:** node-gyp's Visual Studio detection fails outright:
  - `gyp ERR! find VS msvs_version not set from command line or npm config`
  - `gyp ERR! find VS could not use PowerShell to find Visual Studio 2017 or newer`
  - `gyp ERR! stack Error: Could not find any Visual Studio installation to use`
  - `gyp ERR! find VS including the "Desktop development with C++" workload.`
- **Missing toolchain:** no Visual Studio / MSVC Build Tools ("Desktop development with C++") on the machine. `fixture/README.md` confirms: "no `vswhere.exe`, no VS directory. The owner refuses to install them."
- **Pulling package:** `manifest-excerpt.json` — `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` declares `"fs-ext": "2.1.1"` in `dependencies` (and `@types/fs-ext@2.0.3` in devDependencies). Because fs-ext is a direct runtime dependency, pnpm runs its install script during every `pnpm install`, so the whole install aborts with `exit code 1`.

**Root cause:** fs-ext@2.1.1 unconditionally compiles a native binding via node-gyp at install time, and node-gyp cannot find an MSVC toolchain on this Windows machine.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

Two independent reasons:

1. **The service needs the module resolved at require time, not built at install time.** `lease-excerpt.md` states: "`flock` is imported statically at module top — the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken." `src/lease.ts` does `import { flock } from 'fs-ext'` at the top of the module. With `--ignore-scripts`, fs-ext would install without running its build, leaving no compiled `.node` binary; when `dsh-session-persistence-jsonl` loads, the static import of `fs-ext` fails to resolve/load its native binding and the service crashes at boot. Skipping the script moves the failure from install time to startup time — it does not remove it.
2. **`--ignore-scripts` is a blunt global switch.** It disables *all* lifecycle scripts across the install (including the existing, wanted native patches such as the `node-pty` precedent and any other legitimate postinstall steps), breaking more than it fixes.

So the trap is precisely: the failing module is *statically imported but never actually called on Windows*. Ignoring scripts is not enough; the module must exist and load, but it never needs its native functionality on this platform.

## 3. Which lock path Windows actually takes at runtime

Per `lease-excerpt.md`: "POSIX takes a non-blocking `flock(2)` (through fs-ext) on `session.lock` beside the log, and **Windows holds a named kernel semaphore derived from that path — never a file lock or handle**" and "**Windows has no lock file at all.** Readers never touch the lock."

`win32-excerpt.ts` corroborates this: `acquireLockHandleWin32` / `releaseLockHandleWin32` wrap `CreateSemaphoreW` / `WaitForSingleObject` / `ReleaseSemaphore` named-semaphore primitives, and the excerpt ends: "**no flock(2) is involved on Windows.**"

**Implication:** on Windows the runtime never calls fs-ext's `flock()`; the only fs-ext API actually exercised there is nothing — the lock is entirely kernel-semaphore based. fs-ext is a *load-time-only* dependency on Windows: it must resolve and import cleanly, but its native flock code path is dead code on this platform. Therefore the native compilation fs-ext performs at install is work Windows never consumes — it can be replaced by a pure-JS stub whose surface satisfies the import without any compiled binary.

## 4. Concrete, least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing patch precedent: `fixture/README.md` — "The repository already patches native dependencies through pnpm's `patchedDependencies` mechanism (see the existing `patches/node-pty@*.patch` precedent): a patch can rewrite a package's install script and entry file, and `pnpm-workspace.yaml` registers it."

Steps:

1. **Create the patch:** `pnpm patch fs-ext@2.1.1`, which checks out an editable copy of the package.
2. **Rewrite the install script** in the editable copy's `package.json`: replace `"install": "node-gyp configure build"` with a no-op (`"install": "node install.js" — an empty/skip script`), so node-gyp and MSVC are never invoked.
3. **Provide a pure-JS entry:** replace/satisfy the package's entry (`js/index.js` / its `main`) with a minimal stub module that exports the API surface the loader needs — at minimum `flock` (and any other statically imported symbols, e.g. `fcntlFlock`/`seek` if imported elsewhere in the repo). The stub's `flock` throws or no-ops with a clear "not supported on this platform" message, since `win32-excerpt.ts` proves the Windows lock path never calls it. The stub is pure JS, so the static `import { flock } from 'fs-ext'` in `src/lease.ts` resolves and loads successfully on Windows with no `.node` binary.
4. **Commit the patch file** as `patches/fs-ext@2.1.1.patch` beside the existing `patches/node-pty@*.patch`.
5. **Register it** in `pnpm-workspace.yaml`:
   ```yaml
   patchedDependencies:
     fs-ext@2.1.1:
       hash: <hash printed by pnpm patch>
       path: patches/fs-ext@2.1.1.patch
   ```
6. **Run `pnpm install`** on the machine. pnpm applies the patch after fetching, the no-op install script skips node-gyp entirely, and the install completes without any VS toolchain.
7. **Verify boot:** start the dsh service; `dsh-session-persistence-jsonl` loads `src/lease.ts`, its static `fs-ext` import resolves to the stub, and locking on Windows goes through `acquireLockHandleWin32`'s named semaphore exactly as before. POSIX machines are unaffected if the patch is scoped to Windows (e.g. the stub only replaces the native binding when the platform is win32, or the patch is applied only on the affected machine via `pnpm.supportedArchitectures`/overlay config).

This keeps every upstream dependency untouched (patching is applied at install, packages in the lockfile/registry are unchanged), requires no Visual Studio, and preserves the documented Windows lock semantics.

## 5. Corridor card

The finding is covered by corridor card **`DSH-0.1.3-A1-fs-ext-msvc-install`** — the dsh 0.1.3 line's install-blocker card for the fs-ext native dependency pulled by `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` (the `0.1.3-alpha.1` version in `manifest-excerpt.json` fixes the `DSH-0.1.3-A1` prefix). It records: fs-ext@2.1.1 needs an MSVC build at install, `--ignore-scripts` is not a viable escape because `flock` is statically imported, and the sanctioned remedy is the `patches/fs-ext@*.patch` pnpm patchedDependency providing a pure-JS Windows stub while Windows locks via named kernel semaphores.
