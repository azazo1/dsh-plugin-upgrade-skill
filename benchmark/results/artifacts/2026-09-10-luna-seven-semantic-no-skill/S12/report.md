# S12 — Global upgrade EBUSY and downgrade trap

## 1. Attempt 1: why `koffi.node` was busy

The lock holder is the dsh web-host process, `node.exe` PID **42432**. The
process listing says that this host loaded `@koromix/koffi` at startup.
`koffi.node` is a native Windows `.node` binary, so Windows keeps the file
open/locked while the host process has the addon loaded. The npm process (PID
23920) therefore cannot copy the old file while replacing it and reports
`EBUSY`.

The browser is only a client of the host. Refreshing a page reloads the SPA in
the browser; it does not terminate or restart PID 42432, so it does not
release the native addon. The lock is released when the dsh host exits (or is
otherwise stopped), not when the page is refreshed. PID 23768 is the agent
worker and PID 23920 is the npm process; neither is the dsh host identified as
holding `koffi.node`.

## 2. Attempt 2: why the version went backward

In this command:

```text
npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
```

`@deepseek-ai/dsh` has no version or tag specifier. npm therefore follows the
package's `latest` dist-tag. At the time of the attempt, the evidence shows:

```text
latest -> 0.1.1-rc.2
next   -> 0.1.1-rc.2
alpha  -> 0.1.2-alpha.5
```

Thus npm deliberately selected `0.1.1-rc.2`; it did not compare the installed
version with available versions and it did not infer that the desired alpha
should be retained or advanced to. Since `0.1.1-rc.2` is older than
`0.1.2-alpha.5`, the successful install was a downgrade. The TUI package being
present in the same command does not make the dsh package inherit the `alpha`
tag.

## 3. Safe Windows upgrade sequence

First stop dsh using its normal stop/exit action. If the captured host is
still running and does not exit cleanly, target that process specifically
(do not kill all `node.exe` processes):

```bat
tasklist /FI "PID eq 42432"
taskkill /PID 42432 /T
tasklist /FI "PID eq 42432"
```

If the normal stop leaves the process alive and `taskkill` reports that it
could not stop it, force only that confirmed dsh-host PID:

```bat
taskkill /PID 42432 /T /F
tasklist /FI "PID eq 42432"
```

Run the install only after the final check shows no PID 42432. Pin the core
package to the requested release while installing the TUI:

```bat
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui
dsh --version
```

The equivalent two-step form, which makes the core-package pin especially
obvious, is:

```bat
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5
npm install -g @deepseek-harness-tui/dsh-tui
dsh --version
```

The expected version check is `0.1.2-alpha.5`. If a particular TUI release
has a documented compatibility constraint, pin that package too using its
documented compatible version, for example:

```bat
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui@<compatible-tui-version>
```

## 4. Prevention for plugin README authors

Plugin installation instructions should not include an unpinned base package:

```text
npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
```

That command silently follows whatever `latest` means in the registry and can
downgrade an installed prerelease. A README should either install only the
plugin, leaving the already-installed core untouched:

```bat
npm install -g @deepseek-harness-tui/dsh-tui
```

or pin the core and the plugin to a tested compatible pair:

```bat
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui@<tested-tui-version>
```

README authors should state the compatibility matrix and use exact versions
for reproducible upgrade instructions. If following a moving channel is
intended, name the channel explicitly (such as `@alpha`) and explain that it
is not an exact-version guarantee; never rely on npm's implicit `latest`.
