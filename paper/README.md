# Evaluating Agent Skills for Version-Specific Plugin Migration

Current manuscript: **A Retrospective Study** (17 September 2026). The paper targets software-maintenance readers, with JSS as the intended first venue; it is a generic single-column review draft, not a certified publisher template.

The inverted-U hypothesis is no longer a main claim or a completion criterion. No new solver or API judge calls were made. Historical configurations remain descriptive; the archived Flash S16 comparison is the focal case. The bounded, non-blind review initially used AI assistance; the authors subsequently reported human checking by contributing plugin authors.

See the [Chinese project guide](README.zh.md), [current stopping plan](INVERTED-U-WORKPLAN.zh.md), [claim/evidence map](audit/claim-evidence-20260917.md), and [submission package](submission/README.zh.md).

Build with `tectonic --outdir output/pdf paper/latex/acl_latex.tex`. Check the new summary with `node paper/scripts/summarize-submission-evidence.mjs --check`. The legacy LaTeX filename is retained for compatibility. Author declarations and the publisher's current submission requirements require final author confirmation.

The complete contract-stratified analysis covers all 64 reports and 328 recorded decisions; it is separate from targeted semantic review. Human follow-up is author-reported without a separate item-level scoring dataset. Run `npm run check:paper-contracts` and `npm run check:paper-glm53` for offline checks.

The revised narrative centers the focal comparison and contract-level inspection. Historical and supplementary configurations are retained in Appendix B. Proposed maintenance checks are distinguished from empirically evaluated interventions.
