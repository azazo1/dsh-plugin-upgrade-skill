# H27 · Declares Nothing, Crashes on Load

## Unattended Evaluation Authorization (BENCHMARK-AUTH-v1)

This is an unattended evaluation running in a disposable, isolated container; there will be no follow-up user messages. This task statement itself is the user's explicit authorization and confirmation for the solution and execution needed to complete the task: perform the necessary analysis and planning on your own, and proceed with execution immediately once the plan is formed — do not pause to wait for "confirmation", and do not ask the user follow-up questions. This confirmation continues to apply to the concrete plan you produce based on the applicable skill, but only within the following scope:

- You may read `/app/fixture/`, local in-container documentation, and local tools; you may modify `/app/fixture/` directly, and write the designated report under `/app/agent-output/H27-undeclared-import-trap/` as specified by the task;
- You may create throwaway local verification profiles and temporary files, and run local tests, builds, and dsh commands;
- You may not modify the skill, the verifier, or the reference solution; you may not publish, push, access external services, or alter resources outside the container;
- If you cannot complete the task, state the blocker honestly, but do not stop merely because another round of confirmation is missing.

A teammate reports: "The plugin installs fine, it even shows up in `dsh plugin list` — but the moment the host loads it, the whole tree dies with `ERR_MODULE_NOT_FOUND`. CI is red."

The plugin sits at `/app/fixture/` (host-plane, otherwise correct for 0.1.2-alpha.2). The host `dsh 0.1.2-alpha.2` is installed globally, `pnpm` is available, and the fixture is git-committed as the baseline.

1. **Diagnose** — reproduce in an isolated profile: `dsh plugin add` succeeds, the entry is listed, a cold boot crashes with a module-resolution error. Determine exactly which import fails to resolve and *why the install never fetched it*. Write the diagnosis to `/app/agent-output/H27-undeclared-import-trap/diagnosis.md`, naming the missing declaration and the layer it lives in (a runtime import with no corresponding dependency declaration).
2. **Fix** — edit the files under `/app/fixture/` directly so the plugin loads and activates on `dsh 0.1.2-alpha.2`.
3. **Verify** — in a fresh isolated profile: add → listed → cold boot reaches the host application layer (a headless boot without an API key failing with `MISSING_CREDENTIAL` after the plugin tree loads is the expected alive signal; exit code is not a criterion). Record the evidence under `/app/agent-output/H27-undeclared-import-trap/smoke.md`.

The trap: the in-source memo suggests wrapping the import in a try/catch and degrading gracefully. That is not a fix — silently dropping a capability is worse than the crash.
