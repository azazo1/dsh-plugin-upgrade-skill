## A1 per-task lift difference (d_t = lift_flash − lift_strong, 3-round medians)

| task | 5.3-flash lift | 5.2 lift | d_t |
|---|---:|---:|---:|
| S1-static-scan | 0 | 0 | 0 |
| S10-paste-rename-and-version-chip | 0 | 0 | 0 |
| S11-mermaid-lazyload-trap | 0 | 10 | -10 |
| S12-global-upgrade-ebusy-trap | 0 | 0 | 0 |
| S13-peer-range-vs-runtime | 0 | 0 | 0 |
| S14-link-install-lock-trap | 0 | 0 | 0 |
| S15-slot-error-boundary-crash | 0 | -10 | 10 |
| S16-self-host-upgrade-trap | 0 | 0 | 0 |
| S17-external-ui-plugin-onboarding-trap | 20 | 0 | 20 |
| S18-terminal-sprite-render-trap | 20 | 0 | 20 |
| S19-phantom-update-stale-host | 0 | 0 | 0 |
| S2-negative-scan | 0 | 0 | 0 |
| S20-msvc-flock-trap | 5 | 8 | -3 |
| S21-resource-service-unavailable-trap | 20 | 10 | 10 |
| S22-duplicate-insert-boot-crash-trap | 20 | 0 | 20 |
| S3-snapshot-migration | 10 | 0 | 10 |
| S4-legacy-client-imports | 62 | 37 | 25 |
| S5-negative-naming | 12 | 0 | 12 |
| S6-corridor-net-state | 25 | 12 | 13 |
| S7-unpublished-cohort | 0 | 0 | 0 |
| S8-release-routing-trap | 10 | 0 | 10 |
| S9-composer-coordinate-trap | 0 | 0 | 0 |
| **mean** | | | **6.2273** |
| **95% CI (task bootstrap)** | | | **[2.5909, 10.0455]** |
| **Wilcoxon** | | | **p=0.007988586882083037, n=12** |

## A2 per-round mean delta

- **glm-5.3-flash**: r1=6.3182, round2=8.8182, round3=9.8182
- **glm-5.2**: r1=1.5455, round2=1.6364, round3=5

## leave-one-task-out (A1 mean d_t)

- full-sample mean d_t = 6.2273
- leave-one-out range: 5.3333 (without S4-legacy-client-imports) to 7 (without S11-mermaid-lazyload-trap)

## Repeated-run aggregation sensitivity (task-equally weighted lift)

- glm-5.3-flash: mean over repeats = 8.3182; median per arm over repeats = 9.2727
- glm-5.2: mean over repeats = 2.7273; median per arm over repeats = 3.0455

## baseline vs gain (Spearman rho)

- glm-5.3-flash: rho = -0.742
- glm-5.2: rho = -0.6406

> Retrospective exploratory comparison of historical configurations, not an independent capability ordering or a controlled model effect. Materials, budgets and grading differ between the two GLM runs. Solver and semantic judge share a model family; independent scoring review remains outstanding.
> Mean bootstrap and Wilcoxon are not independent confirmations. Resampling assumes independent tasks; shared source events may make these intervals too narrow. Baseline–gain correlation also contains mathematical coupling (gain subtracts baseline), so it does not establish a ceiling mechanism. This analysis addresses the historical right-side contrast only, not the complete inverted-U shape.
