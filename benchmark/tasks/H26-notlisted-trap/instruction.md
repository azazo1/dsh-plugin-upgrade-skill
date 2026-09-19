# H26 · The Package That Installs But Never Registers

## Unattended Evaluation Authorization (BENCHMARK-AUTH-v1)

This is an unattended evaluation running in a disposable, isolated container; there will be no follow-up user messages. This task statement itself is the user's explicit authorization and confirmation for the solution and execution needed to complete the task: perform the necessary analysis and planning on your own, and proceed with execution immediately once the plan is formed — do not pause to wait for "confirmation", and do not ask the user follow-up questions. This confirmation continues to apply to the concrete plan you produce based on the applicable skill, but only within the following scope:

- You may read `/app/fixture/`, local in-container documentation, and local tools; you may modify `/app/fixture/` directly, and write the designated report under `/app/agent-output/H26-notlisted-trap/` as specified by the task;
- You may create throwaway local verification profiles and temporary files, and run local tests, builds, and dsh commands;
- You may not modify the skill, the verifier, or the reference solution; you may not publish, push, access external services, or alter resources outside the container;
- If you cannot complete the task, state the blocker honestly, but do not stop merely because another round of confirmation is missing.

A teammate reports: "I installed our plugin and dsh said it succeeded, but it never shows up in `dsh plugin list`. Must be a host bug — I tried reinstalling twice, same thing."

The plugin sits at `/app/fixture/` (host-plane, already written against the 0.1.2-alpha.2 API — the source itself is fine). The host `dsh 0.1.2-alpha.2` is installed globally, `pnpm` is available, and the fixture is git-committed as the baseline.

1. **Diagnose** — reproduce the symptom in an isolated profile (`dsh plugin add` succeeds; the entry never appears in the list). Figure out what is actually missing and why a reinstall cannot fix it. Write the diagnosis to `/app/agent-output/H26-notlisted-trap/diagnosis.md`, naming the exact missing pieces and the two distinct layers involved (dependency installation vs. plugin registration).
2. **Fix** — edit the files under `/app/fixture/` directly so the plugin registers and activates on `dsh 0.1.2-alpha.2`.
3. **Verify** — in a fresh isolated profile: `dsh plugin add` succeeds, the entry **appears in the list**, and a cold boot reaches the host application layer (a headless boot without an API key failing with `MISSING_CREDENTIAL` after the plugin tree loads is the expected alive signal; exit code is not a criterion). Record the evidence under `/app/agent-output/H26-notlisted-trap/smoke.md`.

The trap: the source code is not the problem, and neither is the install. There is exactly one class of fix that works — find it.
