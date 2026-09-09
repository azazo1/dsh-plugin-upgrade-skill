# Do Migration Skills Actually Help? A Community-Grounded Benchmark for Skill-Guided Framework Migration

Review and experiment planning (Chinese): [review](REVIEW-2026-09-08.zh.md) · [paper TODO](GAP-ANALYSIS.zh.md), updated 2026-09-08.

[中文说明](README.zh.md)

This work-in-progress paper now plans a fresh **56-task × two-configuration × four-condition × one-trial evaluation (448 runs)**; see the [execution plan](../docs/superpowers/plans/2026-09-08-paper-56-task-rerun.md). A subset of K tasks will be fixed before formal outcomes are seen and receive two additional trials in every cell (16K extra runs), reported separately for stability. Generated tables still describe the **23-task historical snapshot** until the new 56-task inventory passes quality control and is frozen. Historical scores will not enter the new main table, and the full pool is not claimed to be independently unseen. Empirical conclusions remain pending.

The [experiment and exposure audit](audit/README.zh.md) covers 22 submitted reports and 56 current task definitions. Neither inventory count establishes the size of an independent test set.

## Directory structure

- `latex/` — LaTeX source of the report
  - `acl_latex.tex` — main file (title, authors, abstract, full section skeleton; based on the latest official template)
  - `acl.sty` / `acl_natbib.bst` — official ACL style (acl-org/acl-style-files master, 2026-06)
  - `custom.bib` — bibliography (five versioned arXiv records checked; broader literature review remains pending)
  - `formatting.md` — official formatting guidelines
  - `acl_lualatex.tex` — XeLaTeX / LuaLaTeX template (unused)
- `word/`, `archive/` — official Word template and legacy templates (unused, kept as shipped with the style package)

## Build

```bash
cd latex
pdflatex acl_latex && bibtex acl_latex && pdflatex acl_latex && pdflatex acl_latex
```

For [Overleaf](https://www.overleaf.com/), upload `latex/` and `generated/` together, preserve their relative paths, and select `latex/acl_latex.tex` as the main document. The document currently uses `review` mode (with line numbers).

## Historical generated benchmark metadata

The existing historical task metadata is **generated, never hand-written**. Switching the main table to the planned 56-task snapshot is a freeze-stage task; the old snapshot stays immutable:

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

## Writing status

- [x] Rewrite abstract, introduction and contributions around three research questions.
- [x] Replace unsupported positive findings with explicit evidence status and planned analyses.
- [x] Use generated frozen task counts; distinguish prefixes from interaction modes.
- [x] Create report and development-exposure ledgers (initial audit, not a certified split).
- [x] Replace five active bibliography stubs with checked records; preserve old leads in `audit/`.
- [ ] Archive available historical artifacts; complete new protocol hashes, incident grouping and provenance.
- [ ] Validate graders independently and regrade both conditions consistently.
- [ ] Freeze and run the 56-task single-trial four-condition study and preselected stability repeats; holdout and clean/trap are extensions.
- [ ] Complete remaining figures, measured results, appendices, and full related-work review.

## Related resources

- Benchmark tasks and graders: `../benchmark/`
- Skill corpus: `../skills/`
- Official style source: [acl-org/acl-style-files](https://github.com/acl-org/acl-style-files)
