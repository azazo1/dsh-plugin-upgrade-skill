// paper/scripts/measure-task-annotation-agreement.test.mjs
//
// Agreement metric fixtures: ARI (identical / renamed / singleton-vs-one /
// known value), pairwise co-clustering, Cohen's kappa (perfect / partial /
// degenerate → null, never a fabricated 0), disagreement generation, and the
// incomplete-status contract. Zero model calls, zero network.
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  UNRESOLVED,
  adjustedRandIndex,
  cohensKappa,
  comparablePairs,
  computeDisagreements,
  labelsFromCsv,
  measureAnnotations,
  pairwiseCoClusteringAgreement,
  parseCsv,
  rawAgreement,
} from './measure-task-annotation-agreement.mjs'

/** rows([task, family, trap], ...) → Map */
function rows(...entries) {
  const map = new Map()
  for (const [task, family, trap] of entries) map.set(task, { familyId: family, trapType: trap })
  return map
}

// ── ARI fixtures ─────────────────────────────────────────────────────────────

test('ARI: identical clustering = 1', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f2', 'none'])
  const b = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f2', 'none'])
  assert.equal(adjustedRandIndex(a, b), 1)
})

test('ARI: same clustering with renamed labels = 1', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f2', 'none'])
  const b = rows(['t1', 'beta', 'none'], ['t2', 'beta', 'none'], ['t3', 'alpha', 'none'])
  assert.equal(adjustedRandIndex(a, b), 1)
})

test('ARI: singleton clustering vs one big cluster = 0', () => {
  const ids = ['t1', 't2', 't3', 't4', 't5']
  const a = rows(...ids.map((id) => [id, `solo-${id}`, 'none']))
  const b = rows(...ids.map((id) => [id, 'one', 'none']))
  assert.equal(adjustedRandIndex(a, b), 0)
})

test('ARI: known small fixture value (A=[1,1,2], B=[1,2,2] → -0.5)', () => {
  const a = rows(['t1', '1', 'none'], ['t2', '1', 'none'], ['t3', '2', 'none'])
  const b = rows(['t1', '1', 'none'], ['t2', '2', 'none'], ['t3', '2', 'none'])
  assert.ok(Math.abs(adjustedRandIndex(a, b) - (-0.5)) < 1e-12)
})

// ── pairwise co-clustering fixtures ──────────────────────────────────────────

test('pairwise co-clustering: full agreement = 1', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f2', 'none'])
  const b = rows(['t1', 'x', 'none'], ['t2', 'x', 'none'], ['t3', 'y', 'none'])
  assert.equal(pairwiseCoClusteringAgreement(a, b), 1)
})

test('pairwise co-clustering: split clustering over 4 tasks = 1/3', () => {
  // A: {t1,t2},{t3},{t4}; B: {t1,t3},{t2},{t4} → pairs (t1,t2):A=1,B=0 ✗
  // (t1,t3):A=0,B=1 ✗ (t1,t4):A=0,B=0 ✓ (t2,t3):A=0,B=0 ✓
  // (t2,t4):A=0,B=0 ✓ (t3,t4):A=0,B=0 ✓ → 4/6
  const a = rows(['t1', 'a1', 'none'], ['t2', 'a1', 'none'], ['t3', 'a2', 'none'], ['t4', 'a3', 'none'])
  const b = rows(['t1', 'b1', 'none'], ['t2', 'b2', 'none'], ['t3', 'b1', 'none'], ['t4', 'b3', 'none'])
  assert.ok(Math.abs(pairwiseCoClusteringAgreement(a, b) - 4 / 6) < 1e-12)
})

test('pairwise co-clustering: unresolved tasks excluded from pairs but retained', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', UNRESOLVED, 'other'])
  const b = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f9', 'other'])
  // only the pair (t1,t2) is comparable: both say same → 1
  assert.equal(pairwiseCoClusteringAgreement(a, b), 1)
  assert.equal(comparablePairs(a, b).length, 1)
})

// ── trap-type agreement fixtures ─────────────────────────────────────────────

test('trap raw agreement: perfect = 1', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'stale-artifact'])
  const b = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'stale-artifact'])
  assert.equal(rawAgreement(a, b, 'trapType'), 1)
})

test('trap raw agreement: one of two = 0.5', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'stale-artifact'])
  const b = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'runtime-state'])
  assert.equal(rawAgreement(a, b, 'trapType'), 0.5)
})

test('trap kappa: perfect = 1', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f1', 'multi-failure'])
  const b = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f1', 'multi-failure'])
  assert.equal(cohensKappa(a, b, 'trapType'), 1)
})

test('trap kappa: known partial fixture (A=[x,y,y], B=[y,x,y] → -0.5)', () => {
  // p0 = 1/3 (only t3 agrees); marginals P(x)=1/3, P(y)=2/3 on both sides
  // → pe = 1/9 + 4/9 = 5/9 → kappa = (1/3 - 5/9)/(1 - 5/9) = -0.5
  const a = rows(['t1', 'f1', 'x'], ['t2', 'f1', 'y'], ['t3', 'f1', 'y'])
  const b = rows(['t1', 'f1', 'y'], ['t2', 'f1', 'x'], ['t3', 'f1', 'y'])
  assert.ok(Math.abs(cohensKappa(a, b, 'trapType') - (-0.5)) < 1e-12)
})

test('trap kappa: all-same-category is degenerate → null (never a fabricated 0)', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f1', 'none'])
  const b = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', 'f1', 'none'])
  assert.equal(cohensKappa(a, b, 'trapType'), null)
})

test('trap kappa: perfect disagreement with single category each → null, not 0', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'])
  const b = rows(['t1', 'f1', 'multi-failure'], ['t2', 'f1', 'multi-failure'])
  assert.equal(cohensKappa(a, b, 'trapType'), null)
})

test('trap kappa: missing labels excluded; single shared category → null', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', ''], ['t3', 'f1', 'none'])
  const b = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'stale-artifact'], ['t3', 'f1', 'none'])
  // t2 has no shared label; shared t1/t3 both 'none' → raw agreement 1,
  // kappa degenerate (one category, no variance) → null, never 0
  assert.equal(rawAgreement(a, b, 'trapType'), 1)
  assert.equal(cohensKappa(a, b, 'trapType'), null)
})

// ── disagreement generation ──────────────────────────────────────────────────

test('disagreements: family mismatch, trap mismatch, unresolved-vs-resolved all listed', () => {
  const a = rows(['t1', 'f1', 'none'], ['t2', 'f1', 'none'], ['t3', UNRESOLVED, 'other'])
  const b = rows(['t1', 'f9', 'none'], ['t2', 'f1', 'stale-artifact'], ['t3', 'f9', 'other'])
  const disagreements = computeDisagreements(a, b)
  const family = disagreements.filter((d) => d.dimension === 'incident_family').map((d) => d.taskId).sort()
  const trap = disagreements.filter((d) => d.dimension === 'trap_type').map((d) => d.taskId)
  assert.deepEqual(family, ['t1', 't3'])
  assert.deepEqual(trap, ['t2'])
})

test('disagreements: unresolved tasks are retained, not dropped', () => {
  const a = rows(['t1', UNRESOLVED, 'none'])
  const b = rows(['t1', 'f1', 'none'])
  const disagreements = computeDisagreements(a, b)
  assert.equal(disagreements.length, 1)
  assert.equal(disagreements[0].dimension, 'incident_family')
})

// ── incomplete-status contract ───────────────────────────────────────────────

const INVENTORY = { tasks: [{ id: 't1' }, { id: 't2' }, { id: 't3' }] }

function csvFromRows(rowsText) {
  return `# annotator_id: human\n# independence_declaration: yes\ntask_id,incident_family_id,family_short_name,observable_trap_type,family_evidence,rationale,confidence,difficulty\n${rowsText}\n`
}

test('measure: missing B submission → status incomplete, no metrics', () => {
  const result = measureAnnotations({
    inventory: INVENTORY,
    annotatorAText: csvFromRows('t1,f1,n,none,e,r,high,\nt2,f1,n,none,e,r,high,\nt3,f2,n,multi-failure,e,r,high,\n'),
    annotatorBText: '',
  })
  assert.equal(result.status, 'incomplete')
  assert.equal(result.incidentFamily, undefined)
  assert.equal(result.trapType, undefined)
})

test('measure: both submissions → complete with metrics + disagreements', () => {
  const a = csvFromRows('t1,f1,n,stale-artifact,e,r,high,\nt2,f1,n,none,e,r,high,\nt3,f2,n,none,e,r,high,\n')
  const b = csvFromRows('t1,f1,n,stale-artifact,e,r,high,\nt2,f1,n,none,e,r,high,\nt3,f2,n,none,e,r,high,\n')
  const result = measureAnnotations({ inventory: INVENTORY, annotatorAText: a, annotatorBText: b })
  assert.equal(result.status, 'complete')
  assert.equal(result.incidentFamily.adjustedRandIndex, 1)
  assert.equal(result.trapType.cohensKappa, 1)
  assert.deepEqual(result.disagreements, [])
})

test('measure: inventoryCount reported even when incomplete', () => {
  const result = measureAnnotations({ inventory: INVENTORY, annotatorAText: '', annotatorBText: '' })
  assert.equal(result.status, 'incomplete')
  assert.equal(result.inventoryCount, 3)
})

// ── CSV parser sanity ────────────────────────────────────────────────────────

test('parseCsv: quoted commas and metadata comments', () => {
  const { comments, rows } = parseCsv('# annotator_id: a1\n"x","a,b","c"\n')
  assert.equal(comments[0], '# annotator_id: a1')
  assert.deepEqual(rows[0], ['x', 'a,b', 'c'])
})

test('labelsFromCsv: empty template → null (not started)', () => {
  const text = '# annotator_id: <fill>\ntask_id,incident_family_id,family_short_name,observable_trap_type,family_evidence,rationale,confidence,difficulty\nt1,,,,,,,\n'
  assert.equal(labelsFromCsv(text, {}), null)
})
