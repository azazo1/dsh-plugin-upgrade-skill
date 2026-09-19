# When Does a Migration Skill Help?

Current subtitle: **A Retrospective Study of Version-Pinned Plugin Migration**.

The September 15 revision retains the inverted-U shape of absolute gains as an exploratory observation across heterogeneous historical configurations. It does not establish a capability effect. The benchmark and retrospective paired analysis are the contributions; the unexecuted source-matched protocol is in the appendix.

The single active work plan is [Inverted-U work recommendations](INVERTED-U-WORKPLAN.zh.md): analyze existing data and audit output grades first, then decide whether a matched three-configuration experiment is worthwhile. Superseded plans have been removed. The [revision record](audit/REVISION-2026-09-15-retrospective.zh.md) describes completed edits.

[中文说明](README.zh.md)

## Directory structure

- `latex/` — LaTeX source of the report
  - `acl_latex.tex` — main file (title, authors, abstract, full section skeleton; based on the latest official template)
  - `acl.sty` / `acl_natbib.bst` — official ACL style (acl-org/acl-style-files master, 2026-06)
  - `custom.bib` — active bibliography; full related-work review remains pending
  - `formatting.md` — official formatting guidelines

## Build

```bash
cd latex
pdflatex acl_latex && bibtex acl_latex && pdflatex acl_latex && pdflatex acl_latex
```

For [Overleaf](https://www.overleaf.com/), upload `latex/` and `generated/` together, preserve their relative paths, and select `latex/acl_latex.tex` as the main document. The document currently uses `review` mode (with line numbers).

## Historical generated benchmark metadata

The existing historical task metadata is **generated, never hand-written**. The historical snapshot stays immutable; no switch to a future study is planned by this cleanup:

- **Source of truth**: one frozen evaluation snapshot, `benchmark/snapshots/2026-09-01-main-23.json` (currently 23 tasks, 3 runs per task, `per-task-median` aggregation, 2 conditions).
- The generator (`paper/scripts/generate-benchmark-table.mjs`) reads every task row, registry Type (`Static` / `Hands-on`), and description from **git objects at the snapshot's pinned benchmark commit** — never from the current checkout. Tasks added to the living benchmark after the pinned commit do not change the paper metadata of this experiment.
- The living benchmark is **not** the paper's evaluation set. Paper experiments are always pinned to an explicit snapshot; there is no "latest snapshot" behavior.

Generated files (committed, do not edit by hand):

- `paper/generated/benchmark-metadata.tex` — deterministic macros (`\BenchmarkTaskCount`, `\BenchmarkStaticCount` / `\BenchmarkHandsOnCount`, ID-prefix counts `\BenchmarkPrefixSCount` / `\BenchmarkPrefixMCount` / `\BenchmarkPrefixHCount`, pinned benchmark/skill commits, runs-per-task, aggregation, condition count). Prefix counts and registry interaction Type are kept as **two separate dimensions** (H4/H6 are registry-Static despite the H prefix).
- `paper/generated/task-pool-table.tex` — the `Task | Type | What it tests` table (`\input` into the appendix).

Regenerate (from the repo root):

```bash
npm run generate:paper-benchmark
npm run check:paper-benchmark   # CI gate: fails if the committed files drift
```

`check:paper-benchmark` and the generator unit tests run as part of `npm test`, so a snapshot/metadata drift turns CI red. The generator is deterministic: the same snapshot plus the same local git objects always produces byte-identical files (no timestamps, no host paths), and a snapshot whose pinned commit is missing locally is a hard error rather than a fallback to current `main`.

## Generated results table (main result)

The paper's main result table is **generated, never hand-written**:

- **Source of truth**: `benchmark/results/paired-effect-stats.json`, produced by `benchmark/scripts/measure-paired-effect.mjs` (task-level paired deltas, mulberry32 seed 20260907, 10000 bootstrap replicates, two-sided Wilcoxon; input-file SHA-256s embedded).
- `paper/generated/paired-effect-table.tex` (five main model points) and `paper/generated/paired-effect-sensitivity-table.tex` (contaminated luna group) are rendered from that JSON by `paper/scripts/generate-paired-effect-table.mjs` and `\input` into the Results section and the sensitivity appendix.

Regenerate / verify (from the repo root):

```bash
npm run measure:benchmark-paired   # recompute stats + write the JSON
npm run generate:paper-paired      # render the .tex from the JSON
npm run check:paper-paired         # CI gate: byte-exact drift check for both
npm run test:benchmark-paired      # unit + golden tests for the statistics
```

## Current status

The manuscript retains the inverted-U as an exploratory observation; the unexecuted four-condition design is in the appendix. Statistics are reproducible and the working PDF has been compiled and inspected. Grade validation, robustness analyses, and submission preparation remain outstanding; tasks are maintained only in the [work plan](INVERTED-U-WORKPLAN.zh.md).

## Related resources

- Benchmark tasks and graders: `../benchmark/`
- Skill corpus: `../skills/`
- Official style source: [acl-org/acl-style-files](https://github.com/acl-org/acl-style-files)
