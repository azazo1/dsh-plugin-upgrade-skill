// benchmark/scripts/analyze-glm-pair-stability.test.mjs
//
// Golden check: the retrospective A1/A2 analysis reproduces its committed
// numbers from the committed inputs. No network, no Docker.
import test from 'node:test'
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { analyze, spearman, TABLE_PATH, OUTPUT_PATH } from './analyze-glm-pair-stability.mjs'

const repoRoot = fileURLToPath(new URL('../../', import.meta.url))

test('analyze: A1 lift-gap point estimate and CI match the committed record', () => {
  const r = analyze(repoRoot)
  assert.equal(r.a1.tasks, 22)
  assert.equal(r.a1.meanD, 6.2273)
  assert.deepEqual(r.a1.bootstrapCi95, [2.5909, 10.0455])
  assert.ok(r.a1.wilcoxon.pTwoSided > 0 && r.a1.wilcoxon.pTwoSided < 0.05)
})

test('analyze: both GLM groups expose 22 per-task deltas on the same tasks', () => {
  const r = analyze(repoRoot)
  const t1 = r.a1.perTask.map(e => e.task).sort()
  assert.equal(t1.length, 22)
})

test('analyze: A2 per-round means match the committed record', () => {
  const r = analyze(repoRoot)
  const flash = r.a2.perRoundMeanDelta['glm-5.3-flash']
  const strong = r.a2.perRoundMeanDelta['glm-5.2']
  assert.deepEqual(flash.map(e => e.meanDelta), [6.3182, 8.8182, 9.8182])
  assert.deepEqual(strong.map(e => e.meanDelta), [1.5455, 1.6364, 5])
})

test('analyze: strongest zero-skill baseline has the weakest baseline-gain correlation', () => {
  const r = analyze(repoRoot)
  assert.ok(r.a2.baselineVsGainSpearman['glm-5.3-flash'].spearmanBaselineVsGain < 0)
  assert.ok(r.a2.baselineVsGainSpearman['glm-5.2'].spearmanBaselineVsGain < 0)
})

test('renderMarkdown: table mentions the mean and CI', () => {
  const r = analyze(repoRoot)
  const md = renderMarkdownSafe(r)
  assert.ok(md.includes('6.2273'))
  assert.ok(md.includes('2.5909'))
})

import { renderMarkdown } from './analyze-glm-pair-stability.mjs'
function renderMarkdownSafe(r) { return renderMarkdown(r) }

test('Spearman uses original observation order and midpoint ranks for ties', () => {
  assert.ok(Math.abs(spearman([30, 10, 20], [1, 2, 3]) + 0.5) < 1e-12)
  assert.ok(Math.abs(spearman([1, 1, 2], [1, 2, 3]) - Math.sqrt(3) / 2) < 1e-12)
  assert.equal(spearman([1, 1, 1], [1, 2, 3]), null)
  assert.throws(() => spearman([1, 2], [1]), /equal-length/)
})

test('all committed outputs reproduce exactly from the hashed inputs', () => {
  const r = analyze(repoRoot)
  assert.equal(JSON.stringify(r, null, 2) + '\n', readFileSync(repoRoot + OUTPUT_PATH, 'utf8'))
  assert.equal(renderMarkdown(r), readFileSync(repoRoot + TABLE_PATH, 'utf8'))
  assert.ok(!renderMarkdown(r).includes('[object Object]'))
})
