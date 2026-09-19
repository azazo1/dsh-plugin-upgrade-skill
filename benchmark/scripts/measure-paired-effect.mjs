// benchmark/scripts/measure-paired-effect.mjs
//
// Deterministic paired-effect statistics for the completed skill-vs-noskill
// experiments: five main groups along the capability axis plus one
// sensitivity group. Task-level pairing follows the preregistered
// analysisPolicy in benchmark/holdouts/temporal-holdout-execution-v1.json:
//
//   - glm-5.3-flash and glm-5.2 (S1–S22, 3 rounds per arm): per-task median of
//     the 3 rounds per condition, delta = skillMedian − noskillMedian.
//   - qwen3.8-27b (56 tasks, 3 attempts per arm): per-task mean of the scored
//     rewards per condition, rescaled by 100.
//   - deepseek-v4-flash (23 tasks, 3 runs per arm): per-task median of the raw
//     run rewards per condition (H8 with-skill has 2 runs), rescaled by 100.
//   - gpt-5.6-terra (21 of 22 tasks) and gpt-5.6-luna (18 tasks): single-shot
//     per-task pairing, rescaled by 100; no per-task median exists. luna is a
//     SENSITIVITY group (contaminated no-skill arm) and never enters the
//     paper's main table.
//   NO-REWARD trials (null rewards, verifier-excluded tasks) are anomalies,
//   never zeros — the same semantics as summarize-runs.mjs; counts and
//   excluded tasks are reported per group. The 2026-09-01 groups read only
//   the extracted paired-scores.json files (see their PROVENANCE.md), never
//   the markdown reports.
//
// Inference:
//   1. Paired bootstrap over task deltas (resampling unit = task), 10000
//      replicates, mulberry32 PRNG seeded 20260907, statistic = mean delta,
//      95% percentile CI: lo = sorted[floor(0.025 * B)], hi = sorted[ceil(0.975 * B) - 1]
//      with B = 10000 (0-based indices 250 and 9749).
//   2. Two-sided Wilcoxon signed-rank test. DEVIATION from the preregistered
//      zeroHandling ("zeros are retained"): zeros are EXCLUDED here, the
//      standard textbook convention; the zero count is reported as nZero.
//      Ties receive midpoint ranks, the tie-corrected normal approximation
//      with continuity correction is used, output is z and the two-sided p.
//
// Validation (hard failures, non-zero exit):
//   - glm groups: 22 records per round file, task sets identical across the 3
//     rounds and equal to the canonical S1–S22 set; per-task median totals
//     must equal 1711/1915 (glm-5.3-flash) and 2053/2120 (glm-5.2).
//   - qwen: 56 unique tasks, each arm has exactly 3 reward slots with every
//     entry null or a number in [0, 1] and at least one scored reward; the
//     trial-weighted scored means must match 0.4494 (no-skill) / 0.4160
//     (with-skill) within 1e-3.
//   - paired-scores groups (deepseek/terra/luna): unique tasks, arms are a
//     reward in [0, 1], an array of 1-3 run rewards, or null (null requires an
//     exclusion reason); per-task arm totals must match the source reports
//     (16.09/18.55 within 0.0051, 14.93/16.75, 12.42/15.15).
//
// Usage (from anywhere; paths resolve against the repo root):
//   node benchmark/scripts/measure-paired-effect.mjs           # write + print summary
//   node benchmark/scripts/measure-paired-effect.mjs --check   # byte-compare, no write
//
// Output (committed to the repo):
//   benchmark/results/paired-effect-stats.json — fixed key order, no
//   timestamps; the same inputs always produce byte-identical output.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const MAX_DECIMALS = 4

export const PRNG_ALGORITHM = 'mulberry32'
export const BOOTSTRAP_SEED = 20260907
export const BOOTSTRAP_REPLICATES = 10000

export const GLM_TASKS = [
  'S1-static-scan',
  'S2-negative-scan',
  'S3-snapshot-migration',
  'S4-legacy-client-imports',
  'S5-negative-naming',
  'S6-corridor-net-state',
  'S7-unpublished-cohort',
  'S8-release-routing-trap',
  'S9-composer-coordinate-trap',
  'S10-paste-rename-and-version-chip',
  'S11-mermaid-lazyload-trap',
  'S12-global-upgrade-ebusy-trap',
  'S13-peer-range-vs-runtime',
  'S14-link-install-lock-trap',
  'S15-slot-error-boundary-crash',
  'S16-self-host-upgrade-trap',
  'S17-external-ui-plugin-onboarding-trap',
  'S18-terminal-sprite-render-trap',
  'S19-phantom-update-stale-host',
  'S20-msvc-flock-trap',
  'S21-resource-service-unavailable-trap',
  'S22-duplicate-insert-boot-crash-trap',
]

const GLM_GROUPS = [
  {
    label: 'glm-5.3-flash',
    design: 'S1-S22 × 3 rounds per arm, per-task median',
    protocol: '3-round median',
    dirs: [
      'benchmark/results/artifacts/2026-09-11-glm-5.3-flash-s1-s22',
      'benchmark/results/artifacts/2026-09-11-glm-5.3-flash-s1-s22-round2',
      'benchmark/results/artifacts/2026-09-11-glm-5.3-flash-s1-s22-round3',
    ],
    expectedMedianTotals: [1711, 1915], // [noskill, skill]
  },
  {
    label: 'glm-5.2',
    design: 'S1-S22 × 3 rounds per arm, per-task median',
    protocol: '3-round median',
    dirs: [
      'benchmark/results/artifacts/2026-09-13-glm-5.2-s1-s22',
      'benchmark/results/artifacts/2026-09-13-glm-5.2-s1-s22-round2',
      'benchmark/results/artifacts/2026-09-13-glm-5.2-s1-s22-round3',
    ],
    expectedMedianTotals: [2053, 2120],
  },
]

const QWEN_GROUP = {
  label: 'qwen3.8-27b',
  design: '56 tasks × 3 attempts per arm, per-task mean of scored rewards × 100',
  protocol: '3 scored, mean',
  file: 'benchmark/results/validation-report-2026-09-11-codex-qwen3.8-27b-medium-paired.json',
  expectedTrialMeans: { 'no-skill': 0.4494, 'with-skill': 0.4160 },
  tolerance: 1e-3,
}

// Groups whose per-task scores were extracted from report tables into
// machine-readable paired-scores.json files (see each directory's
// PROVENANCE.md). The script reads only the extracted JSON, never the report.
const DEEPSEEK_GROUP = {
  label: 'deepseek-v4-flash',
  design: '23 tasks × 3 runs per arm, per-task median (terminus-2 harness, legacy keyword verifiers)',
  protocol: '3-run median',
  file: 'benchmark/results/artifacts/2026-09-01-terminus2-deepseek-v4-flash/paired-scores.json',
  expectedMedianTotals: [16.09, 18.55], // [noskill, skill], report values
  // H8 with-skill has 2 runs; the report rounds its 0.695 two-run median to 0.70 (see PROVENANCE.md)
  totalsTolerance: 0.0051,
}

const TERRA_GROUP = {
  label: 'gpt-5.6-terra',
  design: '21 of 22 tasks, single attempt per arm (H8 excluded: verifier timeout on both arms)',
  protocol: 'single-shot',
  file: 'benchmark/results/artifacts/2026-09-01-codex-gpt-5.6-terra/paired-scores.json',
  expectedMedianTotals: [14.93, 16.75],
  totalsTolerance: 1e-6,
}

const LUNA_GROUP = {
  label: 'gpt-5.6-luna',
  design: '18 tasks, single attempt per arm (H8 not in the 2026-09-01 snapshot)',
  protocol: 'single-shot',
  file: 'benchmark/results/artifacts/2026-09-01-codex-gpt-5.6-luna/paired-scores.json',
  expectedMedianTotals: [12.42, 15.15],
  totalsTolerance: 1e-6,
  sensitivity: true,
  contamination: 'no-skill arm is not a literal zero-skill run: the H2/H3 trajectories read the Codex-native plugin-creator skill; the decontaminated 16-task no-skill subset (10.42/16 = 0.6513) is diagnostic only',
}

// ── Deterministic PRNG and statistics ─────────────────────────────────────────

// mulberry32: 32-bit state counter PRNG, public domain reference implementation.
export function mulberry32(seed) {
  let a = seed >>> 0
  return function next() {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function median(values) {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 1) return sorted[middle]
  return (sorted[middle - 1] + sorted[middle]) / 2
}

export function round4(value) {
  return Number(value.toFixed(MAX_DECIMALS))
}

// Abramowitz–Stegun 7.1.26 erf approximation (|error| ≤ 1.5e-7); deterministic.
function erf(x) {
  const sign = x < 0 ? -1 : 1
  const ax = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * ax)
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax)
  return sign * y
}

export function standardNormalCdf(z) {
  return 0.5 * (1 + erf(z / Math.SQRT2))
}

export function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

// Paired bootstrap: resample task deltas with replacement; statistic = mean.
export function pairedBootstrap(deltas, { replicates = BOOTSTRAP_REPLICATES, seed = BOOTSTRAP_SEED } = {}) {
  if (deltas.length === 0) throw new Error('pairedBootstrap requires at least one delta')
  const rand = mulberry32(seed)
  const means = new Array(replicates)
  for (let r = 0; r < replicates; r += 1) {
    let sum = 0
    for (let i = 0; i < deltas.length; i += 1) {
      sum += deltas[Math.floor(rand() * deltas.length)]
    }
    means[r] = sum / deltas.length
  }
  means.sort((a, b) => a - b)
  return {
    replicates,
    ci95: [means[Math.floor(0.025 * replicates)], means[Math.ceil(0.975 * replicates) - 1]],
  }
}

// Two-sided Wilcoxon signed-rank test. Zeros are excluded (reported as nZero),
// ties receive midpoint ranks, and the tie-corrected normal approximation with
// continuity correction is used. See the header comment for the deviation from
// the preregistered zero-retention policy.
export function wilcoxonSignedRank(deltas) {
  const nonzero = deltas.filter((delta) => delta !== 0)
  const nZero = deltas.length - nonzero.length
  const n = nonzero.length
  if (n === 0) return { n: 0, nZero, wPlus: 0, z: null, pTwoSided: null }
  const abs = nonzero.map((delta) => Math.abs(delta))
  const order = [...abs.keys()].sort((a, b) => abs[a] - abs[b])
  const ranks = new Array(n)
  const tieSizes = []
  let i = 0
  while (i < n) {
    let j = i
    while (j + 1 < n && abs[order[j + 1]] === abs[order[i]]) j += 1
    const midpoint = (i + j) / 2 + 1
    for (let k = i; k <= j; k += 1) ranks[order[k]] = midpoint
    if (j > i) tieSizes.push(j - i + 1)
    i = j + 1
  }
  let wPlus = 0
  for (let k = 0; k < n; k += 1) {
    if (nonzero[k] > 0) wPlus += ranks[k]
  }
  const mu = (n * (n + 1)) / 4
  const tieSum = tieSizes.reduce((sum, t) => sum + (t ** 3 - t), 0)
  const variance = (n * (n + 1) * (2 * n + 1) - tieSum / 2) / 24
  const diff = wPlus - mu
  const z = (diff - Math.sign(diff) * 0.5) / Math.sqrt(variance)
  return { n, nZero, wPlus, z, pTwoSided: 2 * (1 - standardNormalCdf(Math.abs(z))) }
}

// ── Loading and validation ─────────────────────────────────────────────────────

function sha256Of(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function loadJson(path) {
  if (!existsSync(path)) throw new Error(`input file not found: ${path}`)
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch (error) {
    throw new Error(`input file is not valid JSON: ${path} (${error.message})`)
  }
}

function validateGlmAggregate(parsed, path) {
  if (!Array.isArray(parsed)) throw new Error(`${path}: expected a JSON array of task records`)
  if (parsed.length !== GLM_TASKS.length) {
    throw new Error(`${path}: expected ${GLM_TASKS.length} task records, got ${parsed.length}`)
  }
  const seen = new Set()
  for (const record of parsed) {
    if (record === null || typeof record !== 'object' || Array.isArray(record)) {
      throw new Error(`${path}: task record is not an object: ${JSON.stringify(record)}`)
    }
    const { task, method, noskill, skill } = record
    if (typeof task !== 'string' || task === '') throw new Error(`${path}: record has no task name`)
    if (seen.has(task)) throw new Error(`${path}: duplicate task "${task}"`)
    seen.add(task)
    if (typeof method !== 'string' || method === '') throw new Error(`${path}: task "${task}" has no method`)
    for (const [field, value] of [['noskill', noskill], ['skill', skill]]) {
      if (typeof value !== 'number' || Number.isNaN(value) || value < 0 || value > 100) {
        throw new Error(`${path}: task "${task}" has malformed ${field} score ${JSON.stringify(value)} (must be a number in [0, 100])`)
      }
    }
  }
  return seen
}

function loadGlmGroup(repoRoot, spec) {
  const inputs = []
  const rounds = []
  const taskSets = []
  for (const dir of spec.dirs) {
    const rel = `${dir}/aggregate.json`
    const abs = join(repoRoot, rel)
    const parsed = loadJson(abs)
    taskSets.push(validateGlmAggregate(parsed, rel))
    rounds.push(parsed)
    inputs.push({ path: rel, sha256: sha256Of(abs) })
  }
  const expected = new Set(GLM_TASKS)
  for (const [index, taskSet] of taskSets.entries()) {
    if (taskSet.size !== expected.size || [...taskSet].some((task) => !expected.has(task))) {
      throw new Error(`${spec.label} round ${index + 1}: task set differs from the canonical S1–S22 set`)
    }
  }
  const byTask = new Map()
  for (const [roundIndex, records] of rounds.entries()) {
    for (const record of records) {
      if (!byTask.has(record.task)) byTask.set(record.task, [])
      byTask.get(record.task)[roundIndex] = record
    }
  }
  const perTask = []
  for (const task of GLM_TASKS) {
    const cells = byTask.get(task)
    const noskill = median(cells.map((cell) => cell.noskill))
    const skill = median(cells.map((cell) => cell.skill))
    perTask.push({ task, noskill, skill, delta: round4(skill - noskill) })
  }
  const totals = [
    perTask.reduce((sum, row) => sum + row.noskill, 0),
    perTask.reduce((sum, row) => sum + row.skill, 0),
  ]
  if (totals[0] !== spec.expectedMedianTotals[0] || totals[1] !== spec.expectedMedianTotals[1]) {
    throw new Error(`${spec.label}: per-task median totals ${totals[0]}/${totals[1]} do not match the expected ${spec.expectedMedianTotals[0]}/${spec.expectedMedianTotals[1]}`)
  }
  return { label: spec.label, design: spec.design, protocol: spec.protocol, scale: 'rubric points (0-100)', inputs, perTask, unscoredTrials: 0, excludedTasks: [], sensitivity: false, contamination: null }
}

function loadQwenGroup(repoRoot, spec) {
  const abs = join(repoRoot, spec.file)
  const parsed = loadJson(abs)
  if (parsed === null || typeof parsed !== 'object' || !Array.isArray(parsed.per_task)) {
    throw new Error(`${spec.file}: expected a report object with a "per_task" array`)
  }
  const perTaskRaw = parsed.per_task
  if (perTaskRaw.length !== 56) {
    throw new Error(`${spec.file}: expected 56 per_task entries, got ${perTaskRaw.length}`)
  }
  const seen = new Set()
  let unscoredTrials = 0
  const scored = { 'no-skill': [], 'with-skill': [] }
  const perTask = []
  for (const entry of perTaskRaw) {
    if (entry === null || typeof entry !== 'object' || typeof entry.task !== 'string' || entry.task === '') {
      throw new Error(`${spec.file}: per_task entry has no task name`)
    }
    if (seen.has(entry.task)) throw new Error(`${spec.file}: duplicate task "${entry.task}"`)
    seen.add(entry.task)
    const arms = {}
    for (const arm of ['no-skill', 'with-skill']) {
      const rewards = entry[arm]?.rewards
      if (!Array.isArray(rewards) || rewards.length !== 3) {
        throw new Error(`${spec.file}: task "${entry.task}" arm "${arm}" must have exactly 3 reward slots, got ${JSON.stringify(rewards)}`)
      }
      const valid = []
      for (const reward of rewards) {
        if (reward === null) {
          unscoredTrials += 1 // no-reward trial: anomaly, never a zero
          continue
        }
        if (typeof reward !== 'number' || Number.isNaN(reward) || reward < 0 || reward > 1) {
          throw new Error(`${spec.file}: task "${entry.task}" arm "${arm}" has malformed reward ${JSON.stringify(reward)} (must be null or a number in [0, 1])`)
        }
        valid.push(reward)
      }
      if (valid.length === 0) {
        throw new Error(`${spec.file}: task "${entry.task}" arm "${arm}" has no scored reward; a paired delta cannot be computed (never treat no-reward as 0)`)
      }
      scored[arm].push(...valid)
      arms[arm] = mean(valid)
    }
    perTask.push({
      task: entry.task,
      noskill: round4(arms['no-skill'] * 100),
      skill: round4(arms['with-skill'] * 100),
      delta: round4((arms['with-skill'] - arms['no-skill']) * 100),
    })
  }
  for (const arm of ['no-skill', 'with-skill']) {
    const trialMean = mean(scored[arm])
    if (Math.abs(trialMean - spec.expectedTrialMeans[arm]) > spec.tolerance) {
      throw new Error(`${spec.label}: trial-weighted ${arm} mean ${round4(trialMean)} differs from the expected ${spec.expectedTrialMeans[arm]} by more than ${spec.tolerance}`)
    }
  }
  return {
    label: spec.label,
    design: spec.design,
    protocol: spec.protocol,
    scale: 'percent (reward mean × 100)',
    inputs: [{ path: spec.file, sha256: sha256Of(abs) }],
    perTask,
    unscoredTrials,
    excludedTasks: [],
    sensitivity: false,
    contamination: null,
  }
}

// Load a group from an extracted paired-scores.json (deepseek/terra/luna).
// Arms are either a single reward (single-shot) or an array of 2-3 raw run
// rewards (per-task median); null arms mark verifier-excluded tasks.
function loadPairedScoresGroup(repoRoot, spec) {
  const abs = join(repoRoot, spec.file)
  const parsed = loadJson(abs)
  if (parsed === null || typeof parsed !== 'object' || !Array.isArray(parsed.tasks)) {
    throw new Error(`${spec.file}: expected an object with a "tasks" array`)
  }
  const seen = new Set()
  const perTask = []
  const excludedTasks = []
  let unscoredTrials = 0
  const armValues = { noskill: [], skill: [] }
  for (const entry of parsed.tasks) {
    if (entry === null || typeof entry !== 'object' || typeof entry.task !== 'string' || entry.task === '') {
      throw new Error(`${spec.file}: task entry has no task name`)
    }
    if (seen.has(entry.task)) throw new Error(`${spec.file}: duplicate task "${entry.task}"`)
    seen.add(entry.task)
    const arms = {}
    let excluded = false
    for (const arm of ['noskill', 'skill']) {
      const value = entry[arm]
      if (value === null || value === undefined) {
        excluded = true
        continue
      }
      if (typeof value === 'number') {
        if (Number.isNaN(value) || value < 0 || value > 1) {
          throw new Error(`${spec.file}: task "${entry.task}" arm "${arm}" has malformed reward ${JSON.stringify(value)} (must be in [0, 1])`)
        }
        arms[arm] = value
      } else if (Array.isArray(value) && value.length >= 1 && value.length <= 3) {
        for (const run of value) {
          if (typeof run !== 'number' || Number.isNaN(run) || run < 0 || run > 1) {
            throw new Error(`${spec.file}: task "${entry.task}" arm "${arm}" has malformed run reward ${JSON.stringify(run)} (must be in [0, 1])`)
          }
        }
        unscoredTrials += 3 - value.length
        arms[arm] = median(value)
      } else {
        throw new Error(`${spec.file}: task "${entry.task}" arm "${arm}" must be a reward, an array of 1-3 run rewards, or null, got ${JSON.stringify(value)}`)
      }
    }
    if (excluded) {
      if (typeof entry.excluded !== 'string' || entry.excluded === '') {
        throw new Error(`${spec.file}: task "${entry.task}" has a null arm but no "excluded" reason`)
      }
      excludedTasks.push({ task: entry.task, reason: entry.excluded })
      continue
    }
    armValues.noskill.push(arms.noskill)
    armValues.skill.push(arms.skill)
    perTask.push({
      task: entry.task,
      noskill: round4(arms.noskill * 100),
      skill: round4(arms.skill * 100),
      delta: round4((arms.skill - arms.noskill) * 100),
    })
  }
  const totals = [
    armValues.noskill.reduce((sum, value) => sum + value, 0),
    armValues.skill.reduce((sum, value) => sum + value, 0),
  ]
  for (const [index, arm] of [[0, 'noskill'], [1, 'skill']]) {
    if (Math.abs(totals[index] - spec.expectedMedianTotals[index]) > spec.totalsTolerance) {
      throw new Error(`${spec.label}: per-task ${arm} total ${round4(totals[index])} differs from the report value ${spec.expectedMedianTotals[index]} by more than ${spec.totalsTolerance}`)
    }
  }
  return {
    label: spec.label,
    design: spec.design,
    protocol: spec.protocol,
    scale: 'percent (reward × 100)',
    inputs: [{ path: spec.file, sha256: sha256Of(abs) }],
    perTask,
    unscoredTrials,
    excludedTasks,
    sensitivity: spec.sensitivity === true,
    contamination: spec.contamination ?? null,
  }
}

// ── Analysis entry ────────────────────────────────────────────────────────────

function analyzeGroup(loaded) {
  const deltas = loaded.perTask.map((row) => row.delta)
  const bootstrap = pairedBootstrap(deltas)
  const wilcoxon = wilcoxonSignedRank(deltas)
  return {
    label: loaded.label,
    design: loaded.design,
    protocol: loaded.protocol,
    scale: loaded.scale,
    sensitivity: loaded.sensitivity,
    contamination: loaded.contamination,
    tasks: loaded.perTask.length,
    unscoredTrials: loaded.unscoredTrials,
    excludedTasks: loaded.excludedTasks,
    inputs: loaded.inputs,
    perTask: loaded.perTask,
    meanNoskill: round4(mean(loaded.perTask.map((row) => row.noskill))),
    meanSkill: round4(mean(loaded.perTask.map((row) => row.skill))),
    meanDelta: round4(mean(deltas)),
    medianDelta: round4(median(deltas)),
    positiveDeltas: deltas.filter((delta) => delta > 0).length,
    negativeDeltas: deltas.filter((delta) => delta < 0).length,
    nZero: wilcoxon.nZero,
    bootstrap: { replicates: bootstrap.replicates, ci95: bootstrap.ci95.map(round4) },
    wilcoxon: {
      n: wilcoxon.n,
      wPlus: wilcoxon.wPlus,
      z: round4(wilcoxon.z),
      pTwoSided: round4(wilcoxon.pTwoSided),
    },
  }
}

export function measure(repoRoot) {
  // Main groups ordered along the capability axis (weakest first); the
  // sensitivity group (luna, contaminated no-skill arm) is appended last and
  // never enters the paper's main table.
  const groups = [
    loadQwenGroup(repoRoot, QWEN_GROUP),
    loadPairedScoresGroup(repoRoot, DEEPSEEK_GROUP),
    loadPairedScoresGroup(repoRoot, TERRA_GROUP),
    ...GLM_GROUPS.map((spec) => loadGlmGroup(repoRoot, spec)),
    loadPairedScoresGroup(repoRoot, LUNA_GROUP),
  ].map(analyzeGroup)
  return {
    schemaVersion: 1,
    id: 'paired-effect-stats-v1',
    prng: PRNG_ALGORITHM,
    seed: BOOTSTRAP_SEED,
    bootstrapReplicates: BOOTSTRAP_REPLICATES,
    method: 'task-level paired deltas; glm groups use the per-task median of 3 rounds per condition, qwen3.8-27b uses the per-task mean of scored rewards per condition rescaled by 100; bootstrap resamples task deltas (95% percentile CI); Wilcoxon signed-rank is two-sided with midpoint ranks, tie-corrected normal approximation, and continuity correction',
    zeroHandling: 'zero deltas are EXCLUDED from the Wilcoxon test and reported as nZero; the preregistered policy (benchmark/holdouts/temporal-holdout-execution-v1.json) retains zeros, so this implementation deviates on zero handling and reports the count explicitly',
    groups,
  }
}

// ── Renderers ─────────────────────────────────────────────────────────────────

export function renderJson(report) {
  return `${JSON.stringify(report, null, 2)}\n`
}

function fmt(value) {
  if (value === null || value === undefined) return '—'
  return String(round4(value))
}

export function renderMarkdown(report) {
  const lines = []
  lines.push('# Paired-effect statistics')
  lines.push('')
  lines.push(`PRNG ${report.prng} (seed ${report.seed}), ${report.bootstrapReplicates} bootstrap replicates. ${report.method}.`)
  lines.push('')
  lines.push('| Group | Tasks | Protocol | Mean noskill | Mean skill | Mean Δ | Median Δ | 95% CI (bootstrap) | Wilcoxon z | p (two-sided) | nZero |')
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
  for (const group of report.groups) {
    const ci = `[${fmt(group.bootstrap.ci95[0])}, ${fmt(group.bootstrap.ci95[1])}]`
    const label = group.sensitivity ? `${group.label} (sensitivity)` : group.label
    lines.push(`| ${label} | ${group.tasks} | ${group.protocol} | ${fmt(group.meanNoskill)} | ${fmt(group.meanSkill)} | ${fmt(group.meanDelta)} | ${fmt(group.medianDelta)} | ${ci} | ${fmt(group.wilcoxon.z)} | ${fmt(group.wilcoxon.pTwoSided)} | ${group.nZero} |`)
  }
  lines.push('')
  return lines.join('\n')
}

// ── CLI ───────────────────────────────────────────────────────────────────────

export const OUTPUT_PATH = 'benchmark/results/paired-effect-stats.json'

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (isMain) {
  const args = process.argv.slice(2)
  const check = args.includes('--check')
  if (args.some((arg) => arg !== '--check')) {
    console.error('usage: node benchmark/scripts/measure-paired-effect.mjs [--check]')
    process.exit(2)
  }
  const repoRoot = fileURLToPath(new URL('../../', import.meta.url))
  let report
  try {
    report = measure(repoRoot)
  } catch (error) {
    console.error(`[measure-paired-effect] ${error.message}`)
    process.exit(1)
  }
  const content = renderJson(report)
  const target = join(repoRoot, OUTPUT_PATH)
  if (check) {
    if (!existsSync(target)) {
      console.error(`missing output file: ${OUTPUT_PATH}`)
      console.error('Run: npm run measure:benchmark-paired')
      process.exit(1)
    }
    if (readFileSync(target, 'utf8') !== content) {
      console.error(`out of date: ${OUTPUT_PATH}`)
      console.error('Run: npm run measure:benchmark-paired')
      process.exit(1)
    }
    console.log(`${OUTPUT_PATH} is up to date (${report.groups.length} groups, seed ${report.seed})`)
    process.exit(0)
  }
  writeFileSync(target, content)
  process.stdout.write(`${renderMarkdown(report)}\n`)
  console.log(`wrote ${OUTPUT_PATH} (${report.groups.length} groups, seed ${report.seed})`)
}
