// benchmark/scripts/measure-paired-effect.test.mjs
//
// Pure-function tests plus an end-to-end golden check against the three real
// experiment inputs committed in this repository. No network, no Docker.
import test from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import {
  median,
  mulberry32,
  pairedBootstrap,
  wilcoxonSignedRank,
  standardNormalCdf,
  measure,
  renderJson,
  BOOTSTRAP_SEED,
  BOOTSTRAP_REPLICATES,
  GLM_TASKS,
} from './measure-paired-effect.mjs'

const repoRoot = fileURLToPath(new URL('../../', import.meta.url))

test('median: odd, even, and empty inputs', () => {
  assert.equal(median([3, 1, 2]), 2)
  assert.equal(median([1, 2, 3, 4]), 2.5)
  assert.equal(median([5]), 5)
  assert.equal(median([]), null)
  // input array is not mutated
  const input = [3, 1, 2]
  median(input)
  assert.deepEqual(input, [3, 1, 2])
})

test('mulberry32: deterministic stream from the same seed', () => {
  const a = mulberry32(20260907)
  const b = mulberry32(20260907)
  for (let i = 0; i < 100; i += 1) assert.equal(a(), b())
  const c = mulberry32(1)
  const value = c()
  assert.ok(value >= 0 && value < 1)
})

test('standardNormalCdf: known reference points', () => {
  assert.ok(Math.abs(standardNormalCdf(0) - 0.5) < 1e-7)
  assert.ok(Math.abs(standardNormalCdf(1.96) - 0.9750021) < 1e-6)
  assert.ok(Math.abs(standardNormalCdf(-1.96) - 0.0249979) < 1e-6)
})

test('pairedBootstrap: same seed reproduces the identical interval', () => {
  const deltas = [5, -2, 0, 8, 1, 3, -4, 2, 0, 6]
  const first = pairedBootstrap(deltas)
  const second = pairedBootstrap(deltas)
  assert.deepEqual(first, second)
  assert.equal(first.replicates, BOOTSTRAP_REPLICATES)
  assert.ok(first.ci95[0] <= second.ci95[1])
})

test('pairedBootstrap: small golden case (replicates=100, seed=42)', () => {
  const result = pairedBootstrap([1, 2, 3], { replicates: 100, seed: 42 })
  assert.deepEqual(result, { replicates: 100, ci95: [1, 3] })
})

test('pairedBootstrap: rejects empty input', () => {
  assert.throws(() => pairedBootstrap([]), /at least one delta/)
})

// Hand-computed: deltas 1..4 have ranks 1..4, W+ = 10, n = 4,
// mu = 5, var = 4·5·9/24 = 7.5, z = (10 − 5 − 0.5)/√7.5 = 1.6432, p ≈ 0.1003.
test('wilcoxonSignedRank: hand-computed example without ties or zeros', () => {
  const result = wilcoxonSignedRank([1, 2, 3, 4])
  assert.equal(result.n, 4)
  assert.equal(result.nZero, 0)
  assert.equal(result.wPlus, 10)
  assert.ok(Math.abs(result.z - 1.6432) < 1e-4, `z=${result.z}`)
  assert.ok(Math.abs(result.pTwoSided - 0.1003) < 1e-4, `p=${result.pTwoSided}`)
})

// Hand-computed: the zero is excluded (nZero = 1, n = 3); |Δ| = [2, 2, 5] gets
// midpoint ranks [1.5, 1.5, 3]; W+ = 1.5 + 3 = 4.5; mu = 3; the tie group of 2
// corrects the variance to (3·4·7 − (2³−2)/2)/24 = 81/24 = 3.375;
// z = (4.5 − 3 − 0.5)/√3.375 = 0.5443, p ≈ 0.5862.
test('wilcoxonSignedRank: zeros excluded and ties get midpoint ranks', () => {
  const result = wilcoxonSignedRank([0, 2, -2, 5])
  assert.equal(result.n, 3)
  assert.equal(result.nZero, 1)
  assert.equal(result.wPlus, 4.5)
  assert.ok(Math.abs(result.z - 0.5443) < 1e-4, `z=${result.z}`)
  assert.ok(Math.abs(result.pTwoSided - 0.5862) < 1e-4, `p=${result.pTwoSided}`)
})

test('wilcoxonSignedRank: all-zero deltas yield null statistics', () => {
  const result = wilcoxonSignedRank([0, 0, 0])
  assert.equal(result.n, 0)
  assert.equal(result.nZero, 3)
  assert.equal(result.z, null)
  assert.equal(result.pTwoSided, null)
})

// Golden end-to-end values, produced by the first verified run of
// `node benchmark/scripts/measure-paired-effect.mjs` on the committed inputs
// and frozen here so any statistical or data drift fails loudly. Main groups
// are ordered along the capability axis: qwen, deepseek, terra, glm-5.3-flash,
// glm-5.2; luna is the sensitivity group and comes last.
test('golden: group order and flags', () => {
  const report = measure(repoRoot)
  assert.deepEqual(
    report.groups.map((group) => group.label),
    ['qwen3.8-27b', 'deepseek-v4-flash', 'gpt-5.6-terra', 'glm-5.3-flash', 'glm-5.2', 'gpt-5.6-luna'],
  )
  assert.deepEqual(report.groups.map((group) => group.sensitivity), [false, false, false, false, false, true])
})

test('golden: qwen3.8-27b × 56 tasks (one unscored no-skill trial)', () => {
  const report = measure(repoRoot)
  const group = report.groups.find((entry) => entry.label === 'qwen3.8-27b')
  assert.equal(group.tasks, 56)
  assert.equal(group.unscoredTrials, 1)
  assert.equal(group.protocol, '3 scored, mean')
  assert.equal(group.inputs.length, 1)
  assert.equal(group.meanNoskill, 44.6726)
  assert.equal(group.meanSkill, 41.6012)
  assert.equal(group.meanDelta, -3.0714)
  assert.equal(group.medianDelta, 0)
  assert.deepEqual(group.bootstrap.ci95, [-8.125, 1.994])
  assert.equal(group.wilcoxon.z, -1.3496)
  assert.equal(group.wilcoxon.pTwoSided, 0.1771)
  assert.equal(group.nZero, 31)
  // H8-fire-drill has the single unscored trial: no-skill mean of [0, 0] = 0.
  const h8 = group.perTask.find((row) => row.task === 'H8-fire-drill')
  assert.equal(h8.noskill, 0)
})

test('golden: deepseek-v4-flash × 23 tasks (H8 with-skill has 2 runs)', () => {
  const report = measure(repoRoot)
  const group = report.groups.find((entry) => entry.label === 'deepseek-v4-flash')
  assert.equal(group.tasks, 23)
  assert.equal(group.unscoredTrials, 1)
  assert.equal(group.protocol, '3-run median')
  assert.equal(group.meanNoskill, 69.9565)
  assert.equal(group.meanSkill, 80.6304)
  assert.equal(group.meanDelta, 10.6739)
  assert.deepEqual(group.bootstrap.ci95, [0.4783, 22.1087])
  assert.equal(group.wilcoxon.z, 1.6416)
  assert.equal(group.wilcoxon.pTwoSided, 0.1007)
  assert.equal(group.nZero, 13)
  // H8 two-run median: mean of 0.60 and 0.79 = 0.695, ×100.
  const h8 = group.perTask.find((row) => row.task === 'H8-fire-drill')
  assert.equal(h8.skill, 69.5)
  assert.equal(h8.noskill, 20)
})

test('golden: gpt-5.6-terra × 21 tasks (H8 excluded on both arms)', () => {
  const report = measure(repoRoot)
  const group = report.groups.find((entry) => entry.label === 'gpt-5.6-terra')
  assert.equal(group.tasks, 21)
  assert.equal(group.protocol, 'single-shot')
  assert.equal(group.excludedTasks.length, 1)
  assert.equal(group.excludedTasks[0].task, 'H8-fire-drill')
  assert.equal(group.meanNoskill, 71.0952)
  assert.equal(group.meanSkill, 79.7619)
  assert.equal(group.meanDelta, 8.6667)
  assert.deepEqual(group.bootstrap.ci95, [-4.2857, 21.619])
  assert.equal(group.wilcoxon.z, 1.1853)
  assert.equal(group.wilcoxon.pTwoSided, 0.2359)
  assert.equal(group.nZero, 14)
})

test('golden: glm-5.3-flash × S1–S22', () => {
  const report = measure(repoRoot)
  const group = report.groups.find((entry) => entry.label === 'glm-5.3-flash')
  assert.equal(group.tasks, 22)
  assert.equal(group.unscoredTrials, 0)
  assert.equal(group.inputs.length, 3)
  assert.equal(group.meanNoskill, 77.7727)
  assert.equal(group.meanSkill, 87.0455)
  assert.equal(group.meanDelta, 9.2727)
  assert.equal(group.medianDelta, 0)
  assert.deepEqual(group.bootstrap.ci95, [3.9545, 16.0909])
  assert.equal(group.wilcoxon.z, 2.772)
  assert.equal(group.wilcoxon.pTwoSided, 0.0056)
  assert.equal(group.nZero, 12)
})

test('golden: glm-5.2 × S1–S22', () => {
  const report = measure(repoRoot)
  const group = report.groups.find((entry) => entry.label === 'glm-5.2')
  assert.equal(group.tasks, 22)
  assert.equal(group.meanNoskill, 93.3182)
  assert.equal(group.meanSkill, 96.3636)
  assert.equal(group.meanDelta, 3.0455)
  assert.equal(group.medianDelta, 0)
  assert.deepEqual(group.bootstrap.ci95, [0, 7.1818])
  assert.equal(group.wilcoxon.z, 1.484)
  assert.equal(group.wilcoxon.pTwoSided, 0.1378)
  assert.equal(group.nZero, 16)
})

test('golden: gpt-5.6-luna sensitivity group (contamination recorded)', () => {
  const report = measure(repoRoot)
  const group = report.groups.find((entry) => entry.label === 'gpt-5.6-luna')
  assert.equal(group.sensitivity, true)
  assert.match(group.contamination, /plugin-creator/)
  assert.equal(group.tasks, 18)
  assert.equal(group.protocol, 'single-shot')
  assert.equal(group.meanNoskill, 69)
  assert.equal(group.meanSkill, 84.1667)
  assert.equal(group.meanDelta, 15.1667)
  assert.deepEqual(group.bootstrap.ci95, [3.7778, 29.6111])
  assert.equal(group.wilcoxon.z, 2.1129)
  assert.equal(group.wilcoxon.pTwoSided, 0.0346)
  assert.equal(group.nZero, 11)
})

test('golden: glm per-task order follows the canonical S1–S22 list', () => {
  const report = measure(repoRoot)
  for (const label of ['glm-5.3-flash', 'glm-5.2']) {
    const group = report.groups.find((entry) => entry.label === label)
    assert.deepEqual(group.perTask.map((row) => row.task), GLM_TASKS)
  }
})

test('report metadata and byte determinism', () => {
  const report = measure(repoRoot)
  assert.equal(report.schemaVersion, 1)
  assert.equal(report.prng, 'mulberry32')
  assert.equal(report.seed, BOOTSTRAP_SEED)
  assert.equal(report.bootstrapReplicates, BOOTSTRAP_REPLICATES)
  assert.match(report.zeroHandling, /EXCLUDED/)
  assert.match(report.method, /task-level paired deltas/)
  const first = renderJson(measure(repoRoot))
  const second = renderJson(measure(repoRoot))
  assert.equal(first, second)
  assert.ok(first.endsWith('\n'))
  // no timestamps anywhere in the output
  assert.doesNotMatch(first, /\d{4}-\d{2}-\d{2}T/)
})

test('every input file carries a 64-hex sha256', () => {
  const report = measure(repoRoot)
  for (const group of report.groups) {
    for (const input of group.inputs) {
      assert.match(input.sha256, /^[0-9a-f]{64}$/)
      assert.ok(input.path.startsWith('benchmark/results/'))
    }
  }
})
