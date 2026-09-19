// paper/scripts/validate-task-annotations.test.mjs
//
// Focused tests for the task-annotation pipeline validator: synthetic git
// repositories for pin/determinism checks, pure objects for the leakage
// guard, and CSV fixtures for annotator/adjudication rules. Zero model
// calls, zero network.
import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildPacket, renderPacket } from './generate-task-annotation-packet.mjs'
import { ADJUDICATION_COLUMNS, ANNOTATOR_COLUMNS, LEAKAGE_PATTERNS, leakageFailures, validateAdjudicationCsv, validateAnnotatorCsv, validateInventoryGit, validateInventoryShape, validatePacket, validateTaskAnnotations } from './validate-task-annotations.mjs'

const REPO_ROOT = resolve(dirname(dirname(dirname(fileURLToPath(import.meta.url)))))
const TASK_IDS = ['H1-plane-trap', 'M2-optional-dep-trap', 'S9-composer-coordinate-trap']

// ── synthetic repo fixture (3 tasks) ─────────────────────────────────────────

function initRepo() {
  const root = mkdtempSync(join(tmpdir(), 'ta-'))
  execFileSync('git', ['init', '-q', '-b', 'main'], { cwd: root })
  execFileSync('git', ['config', 'user.email', 't@e.c'], { cwd: root })
  execFileSync('git', ['config', 'user.name', 'T'], { cwd: root })
  return root
}

function write(root, rel, content = 'placeholder') {
  mkdirSync(dirname(join(root, rel)), { recursive: true })
  writeFileSync(join(root, rel), content)
}

function commitAll(root, message) {
  execFileSync('git', ['add', '-A'], { cwd: root })
  execFileSync('git', ['commit', '-q', '-m', message], { cwd: root })
  return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim()
}

function gitOut(root, args) {
  return execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim()
}

function buildRepo() {
  const root = initRepo()
  write(root, 'skills/plugin-upgrade/SKILL.md')
  write(root, 'skills/plugin-upgrade/references/README.md')
  write(root, 'skills/plugin-upgrade/references/v0.1.2-alpha.2.md', [
    '- DSH-0.1.2-A1-01 · First card',
    '  continuation detail',
    '- DSH-0.1.2-A1-02 · Second card',
  ].join('\n'))
  commitAll(root, 'skill freeze')
  const modes = { 'H1-plane-trap': 'Hands-on', 'M2-optional-dep-trap': 'Hands-on', 'S9-composer-coordinate-trap': 'Static' }
  const table = ['| Task | Type | What it tests |', '|---|---|---|',
    ...TASK_IDS.map((id) => `| ${id} | ${modes[id]} | description of ${id} |`),
  ].join('\n')
  write(root, 'benchmark/README.md', `The 3 plugin-upgrade tasks measure.\n\n${table}\n`)
  for (const id of TASK_IDS) {
    write(root, `benchmark/tasks/${id}/task.toml`, [
      'schema_version = "1.4"',
      '[task]',
      `name = "dsh-plugin-upgrade/${id}"`,
      'version = "1.1.0"',
      `description = "Migration task ${id}"`,
      'keywords = ["dsh", "plugin-migration"]',
      '',
      '[metadata]',
      'difficulty = "hard"',
      'category = "programming"',
      'execution_contract = "BENCHMARK-AUTH-v1"',
    ].join('\n'))
    write(root, `benchmark/tasks/${id}/instruction.md`, `# ${id}\n\nMigrate the fixture for ${id}.\n`)
    write(root, `benchmark/tasks/${id}/README.md`, [
      `# ${id} · synthetic`,
      '',
      `The agent migrates ${id}.`,
      '',
      '- **Environment**: node:24 + git.',
      '- **Verifier**: the judge checks the fix.',
    ].join('\n'))
    write(root, `benchmark/tasks/${id}/environment/fixture/index.js`, 'module.exports = 1\n')
  }
  const commit = commitAll(root, 'tasks')
  return { root, commit, modes }
}

function syntheticInventory(root, commit, overrides = {}) {
  const tasks = TASK_IDS.map((id) => ({
    id,
    interactionMode: overrides.mode?.[id] ?? (id.startsWith('S') ? 'Static' : 'Hands-on'),
    treeSha: gitOut(root, ['rev-parse', `${commit}:benchmark/tasks/${id}`]),
  }))
  return {
    schemaVersion: 1,
    id: 'task-annotation-v1-inventory',
    inventoryStatus: 'pre-freeze-main56',
    inventoryCommit: commit,
    annotationStatus: 'not-started',
    taskCount: 3,
    ...overrides.extra,
    tasks: overrides.tasks ?? tasks,
  }
}

function syntheticPacket(inventory, repoRoot, mutate) {
  const packet = buildPacket(inventory, repoRoot)
  return mutate ? mutate(packet) : packet
}

// ── inventory shape tests ────────────────────────────────────────────────────

function validInventoryShape() {
  return {
    schemaVersion: 1,
    id: 'task-annotation-v1-inventory',
    inventoryStatus: 'pre-freeze-main56',
    inventoryCommit: 'a'.repeat(40),
    annotationStatus: 'not-started',
    tasks: Array.from({ length: 56 }, (_, i) => ({
      id: `T${String(i + 1).padStart(2, '0')}`,
      interactionMode: 'Static',
      treeSha: 'b'.repeat(40),
    })),
  }
}

test('valid inventory shape passes', () => {
  assert.deepEqual(validateInventoryShape(validInventoryShape()), [])
})

test('missing task fails (55 of 56)', () => {
  const inv = validInventoryShape()
  inv.tasks = inv.tasks.slice(0, 55)
  assert.ok(validateInventoryShape(inv).some((f) => f.includes('exactly 56')))
})

test('extra task fails (57 of 56)', () => {
  const inv = validInventoryShape()
  inv.tasks.push({ id: 'T57', interactionMode: 'Static', treeSha: 'c'.repeat(40) })
  assert.ok(validateInventoryShape(inv).some((f) => f.includes('exactly 56')))
})

test('duplicate task fails', () => {
  const inv = validInventoryShape()
  inv.tasks[10] = { ...inv.tasks[0] }
  assert.ok(validateInventoryShape(inv).some((f) => f.includes('duplicate task')))
})

test('invalid interaction mode fails', () => {
  const inv = validInventoryShape()
  inv.tasks[0].interactionMode = 'Interactive'
  assert.ok(validateInventoryShape(inv).some((f) => f.includes('interactionMode')))
})

test('unsorted task order fails', () => {
  const inv = validInventoryShape()
  inv.tasks = [inv.tasks[5], ...inv.tasks.slice(0, 5), ...inv.tasks.slice(6)]
  assert.ok(validateInventoryShape(inv).some((f) => f.includes('lexical order')))
})

test('wrong inventoryStatus fails', () => {
  const inv = validInventoryShape()
  inv.inventoryStatus = 'frozen-main56'
  assert.ok(validateInventoryShape(inv).some((f) => f.includes('pre-freeze-main56')))
})

// ── git-level pin tests (synthetic repo) ─────────────────────────────────────

test('inventory matches git pins at the commit', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  assert.deepEqual(validateInventoryGit(inv, root), [])
})

test('changed pinned inventory (treeSha drift) rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  inv.tasks[0].treeSha = '0'.repeat(40)
  assert.ok(validateInventoryGit(inv, root).some((f) => f.includes('treeSha mismatch')))
})

test('prefix-derived mode mismatch rejected (S task recorded Hands-on)', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  inv.tasks.find((t) => t.id === 'S9-composer-coordinate-trap').interactionMode = 'Hands-on'
  const failures = validateInventoryGit(inv, root)
  assert.ok(failures.some((f) => f.includes('does not match the pinned registry Type')))
})

test('mode is read from the registry, not the prefix (H task recorded Static is fine when the registry says Static)', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit, { mode: { 'H1-plane-trap': 'Static' } })
  // regenerate the README to say Static for H1 so the recorded value matches
  write(root, 'benchmark/README.md', [
    '| Task | Type | What it tests |', '|---|---|---|',
    '| H1-plane-trap | Static | description of H1-plane-trap |',
    '| M2-optional-dep-trap | Hands-on | description of M2-optional-dep-trap |',
    '| S9-composer-coordinate-trap | Static | description of S9-composer-coordinate-trap |',
  ].join('\n'))
  execFileSync('git', ['add', '-A'], { cwd: root })
  execFileSync('git', ['commit', '-q', '-m', 'flip type'], { cwd: root })
  const newCommit = gitOut(root, ['rev-parse', 'HEAD'])
  inv.inventoryCommit = newCommit
  inv.tasks.forEach((t) => { t.treeSha = gitOut(root, ['rev-parse', `${newCommit}:benchmark/tasks/${t.id}`]) })
  assert.deepEqual(validateInventoryGit(inv, root), [])
})

test('missing task at the commit rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  inv.tasks.push({ id: 'X99-ghost', interactionMode: 'Static', treeSha: 'e'.repeat(40) })
  assert.ok(validateInventoryGit(inv, root).some((f) => f.includes('task list does not equal git')))
})

test('unresolvable inventoryCommit rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  inv.inventoryCommit = 'f'.repeat(40)
  assert.ok(validateInventoryGit(inv, root).some((f) => f.includes('not resolvable')))
})

// ── packet + determinism + leakage tests ─────────────────────────────────────

test('packet validates against a synthetic repo (deterministic regeneration)', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  assert.deepEqual(validatePacket(inv, packet, root), [])
})

test('packet drift from deterministic regeneration rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].instruction += '\n(drifted)'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('deterministic regeneration')))
})

test('packet interactionMode must equal inventory', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].interactionMode = 'Static'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('interactionMode')))
})

test('packet must not carry task.toml difficulty (deferred to P1)', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].taskToml.difficulty = 'hard'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('difficulty')))
})

test('outcome path leakage rejected (benchmark/results/)', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].instruction += '\nsee benchmark/results/validation-report-2026-09-01.md'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('results-path')))
})

test('reward field leakage rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].reward = 1.0
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('forbidden outcome field name')))
})

test('score field leakage rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].score = 100
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('forbidden outcome field name')))
})

test('benign "meaning" does not false-positive the mean-reward guard', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].instruction += '\nThe meaning of the migration is lost when cards are ignored.'
  assert.deepEqual(leakageFailures(packet), [])
})

test('result report phrase rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].instruction += '\nexpected reward 1.0 on the oracle.'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('expected-reward')))
})

test('model identity rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].instruction += '\nrun with gpt-5.6-luna.'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('model-id')))
})

test('holdout verdict vocabulary rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].instruction += '\nthis task is clean-holdout.'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('holdout-verdict')))
})

test('condition vocabulary rejected', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const packet = syntheticPacket(inv, root)
  packet.tasks[0].instruction += '\ncompare the no-injected-skill arm.'
  assert.ok(validatePacket(inv, packet, root).some((f) => f.includes('condition-name')))
})

test('renderPacket is byte-stable', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  assert.equal(renderPacket(inv, root), renderPacket(inv, root))
})

// ── annotator CSV tests ──────────────────────────────────────────────────────

const FILLED = { family: 'session-event-ledger-removal', short: 'Session.events ledger removal', trap: 'silent-contract-drift', evidence: 'alpha.4 removed Session.events', rationale: 'same upstream contract change', confidence: 'high' }

function annotatorCsv(rows, meta = {}) {
  const comments = [
    '# annotator_id: ' + (meta.annotator_id ?? '<fill>'),
    '# started_at: ' + (meta.started_at ?? '<fill ISO-8601>'),
    '# finished_at: ' + (meta.finished_at ?? '<fill ISO-8601>'),
    '# independence_declaration: ' + (meta.declaration ?? '<fill>'),
  ].join('\n')
  const body = rows.map((r) => {
    const row = r ?? [r?.task ?? '', '', '', '', '', '', '', '']
    return [row[0] ?? '', row[1] ?? '', row[2] ?? '', row[3] ?? '', row[4] ?? '', row[5] ?? '', row[6] ?? '', row[7] ?? ''].join(',')
  }).join('\n')
  return `${comments}\n${ANNOTATOR_COLUMNS.join(',')}\n${body}\n`
}

test('all-blank template is not-started and valid', () => {
  const text = annotatorCsv(TASK_IDS.map((id) => [id]))
  const result = validateAnnotatorCsv(text, TASK_IDS, { role: 'A' }, 'templates/annotator-a.csv')
  assert.deepEqual(result.failures, [])
  assert.equal(result.anyFilled, false)
})

test('annotator incomplete (missing family) fails', () => {
  const rows = TASK_IDS.map((id) => [id])
  rows[0] = ['H1-plane-trap', '', 'X', 'none', 'ev', 'why', 'high', '']
  const result = validateAnnotatorCsv(annotatorCsv(rows), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('incomplete row')))
})

test('annotator B incomplete fails', () => {
  const rows = TASK_IDS.map((id) => [id])
  rows[2] = ['S9-composer-coordinate-trap', 'family-x', '', 'none', 'ev', 'why', 'medium', '']
  const result = validateAnnotatorCsv(annotatorCsv(rows), TASK_IDS, { role: 'B' }, 'b.csv')
  assert.ok(result.failures.some((f) => f.includes('incomplete row')))
})

test('filled rows require the independence declaration', () => {
  const rows = TASK_IDS.map((id) => [id, FILLED.family, FILLED.short, FILLED.trap, FILLED.evidence, FILLED.rationale, FILLED.confidence, ''])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'human-x', started_at: '2026-09-10', finished_at: '2026-09-10' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('independence declaration')))
})

test('fully filled consistent annotator passes', () => {
  const rows = TASK_IDS.map((id) => [id, FILLED.family, FILLED.short, FILLED.trap, FILLED.evidence, FILLED.rationale, FILLED.confidence, ''])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'human-x', started_at: '2026-09-10', finished_at: '2026-09-10', declaration: 'I confirm...' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.deepEqual(result.failures, [])
})

test('missing rationale fails', () => {
  const rows = TASK_IDS.map((id) => [id, FILLED.family, FILLED.short, FILLED.trap, FILLED.evidence, '', FILLED.confidence, ''])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'h', started_at: 's', finished_at: 'f', declaration: 'd' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('incomplete row')))
})

test('invalid confidence fails', () => {
  const rows = TASK_IDS.map((id) => [id, FILLED.family, FILLED.short, FILLED.trap, FILLED.evidence, FILLED.rationale, 'very-sure', ''])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'h', started_at: 's', finished_at: 'f', declaration: 'd' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('confidence')))
})

test('invalid trap type fails', () => {
  const rows = TASK_IDS.map((id) => [id, FILLED.family, FILLED.short, 'tricky', FILLED.evidence, FILLED.rationale, FILLED.confidence, ''])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'h', started_at: 's', finished_at: 'f', declaration: 'd' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('not in the fixed vocabulary')))
})

test('inconsistent family short name fails', () => {
  const rows = TASK_IDS.map((id) => [id, 'family-x', id === TASK_IDS[0] ? 'name-one' : 'name-two', 'none', 'ev', 'why', 'high', ''])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'h', started_at: 's', finished_at: 'f', declaration: 'd' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('must be consistent per annotator')))
})

test('unresolved family requires low confidence and is retained', () => {
  const rows = TASK_IDS.map((id) => [id, 'unresolved', 'unresolved', 'none', 'no shared evidence', 'cannot link to an incident', 'high', ''])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'h', started_at: 's', finished_at: 'f', declaration: 'd' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('unresolved family requires confidence=low')))
})

test('difficulty must stay blank in v1', () => {
  const rows = TASK_IDS.map((id) => [id, FILLED.family, FILLED.short, FILLED.trap, FILLED.evidence, FILLED.rationale, FILLED.confidence, 'easy'])
  const result = validateAnnotatorCsv(annotatorCsv(rows, { annotator_id: 'h', started_at: 's', finished_at: 'f', declaration: 'd' }), TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('deferred to P1')))
})

test('template rows must equal the inventory exactly', () => {
  const text = annotatorCsv(TASK_IDS.slice(0, 2).map((id) => [id]))
  const result = validateAnnotatorCsv(text, TASK_IDS, { role: 'A' }, 'a.csv')
  assert.ok(result.failures.some((f) => f.includes('task_id rows must equal the inventory exactly')))
})

// ── adjudication CSV tests ───────────────────────────────────────────────────

function adjudicationCsv(rows, meta = {}) {
  const comments = [
    '# adjudicator_id: ' + (meta.adjudicator_id ?? '<fill>'),
    '# independence_declaration: ' + (meta.declaration ?? '<fill>'),
  ].join('\n')
  const body = rows.map((r) => r.join(',')).join('\n')
  return `${comments}\n${ADJUDICATION_COLUMNS.join(',')}\n${body}\n`
}

const DISAGREEMENTS = [{ taskId: 'H1-plane-trap', dimension: 'incident_family', annotatorA: 'fam-x', annotatorB: 'fam-y' }]

test('empty adjudication template is valid', () => {
  const failures = validateAdjudicationCsv(adjudicationCsv([]), { annotatorA: { annotator_id: 'a' }, annotatorB: { annotator_id: 'b' } }, DISAGREEMENTS)
  assert.deepEqual(failures, [])
})

test('adjudication before annotations fails', () => {
  const rows = [['H1-plane-trap', 'incident_family', 'A', '', '', 'A is right']]
  const failures = validateAdjudicationCsv(adjudicationCsv(rows, { adjudicator_id: 'third', declaration: 'd' }), { annotatorA: {}, annotatorB: {} }, null)
  assert.ok(failures.some((f) => f.includes('adjudication rows exist but no annotator disagreements')))
})

test('adjudicating a non-disagreement fails', () => {
  const rows = [['M2-optional-dep-trap', 'incident_family', 'A', '', '', 'A is right']]
  const failures = validateAdjudicationCsv(adjudicationCsv(rows, { adjudicator_id: 'third', declaration: 'd' }), { annotatorA: { annotator_id: 'a' }, annotatorB: { annotator_id: 'b' } }, DISAGREEMENTS)
  assert.ok(failures.some((f) => f.includes('not in the disagreement list')))
})

test('invalid adjudicator choice fails', () => {
  const rows = [['H1-plane-trap', 'incident_family', 'C', '', '', 'both wrong']]
  const failures = validateAdjudicationCsv(adjudicationCsv(rows, { adjudicator_id: 'third', declaration: 'd' }), { annotatorA: { annotator_id: 'a' }, annotatorB: { annotator_id: 'b' } }, DISAGREEMENTS)
  assert.ok(failures.some((f) => f.includes('choice must be A | B | new')))
})

test('choice new requires a chosen label', () => {
  const rows = [['H1-plane-trap', 'incident_family', 'new', '', '', 'neither']]
  const failures = validateAdjudicationCsv(adjudicationCsv(rows, { adjudicator_id: 'third', declaration: 'd' }), { annotatorA: { annotator_id: 'a' }, annotatorB: { annotator_id: 'b' } }, DISAGREEMENTS)
  assert.ok(failures.some((f) => f.includes('requires chosen_family_id')))
})

test('adjudicator must be a third party, not an annotator', () => {
  const rows = [['H1-plane-trap', 'incident_family', 'A', '', '', 'A is right']]
  const failures = validateAdjudicationCsv(adjudicationCsv(rows, { adjudicator_id: 'a', declaration: 'd' }), { annotatorA: { annotator_id: 'a' }, annotatorB: { annotator_id: 'b' } }, DISAGREEMENTS)
  assert.ok(failures.some((f) => f.includes('third party')))
})

test('valid adjudication row passes', () => {
  const rows = [['H1-plane-trap', 'incident_family', 'A', '', '', 'A is right']]
  const failures = validateAdjudicationCsv(adjudicationCsv(rows, { adjudicator_id: 'third', declaration: 'd' }), { annotatorA: { annotator_id: 'a' }, annotatorB: { annotator_id: 'b' } }, DISAGREEMENTS)
  assert.deepEqual(failures, [])
})

// ── full-pipeline integration tests ──────────────────────────────────────────

test('full pipeline: real repo passes end-to-end', () => {
  assert.deepEqual(validateTaskAnnotations(REPO_ROOT), [])
})

test('full pipeline: consensus.csv must not exist (never fabricated)', () => {
  const { root, commit } = buildRepo()
  const inv = syntheticInventory(root, commit)
  const audit = join(root, 'paper', 'audit', 'task-annotation-v1')
  write(root, 'paper/audit/task-annotation-v1/inventory.json', JSON.stringify(inv, null, 2))
  write(root, 'paper/audit/task-annotation-v1/packet/tasks.json', renderPacket(inv, root))
  const blankA = annotatorCsv(TASK_IDS.map((id) => [id]))
  write(root, 'paper/audit/task-annotation-v1/templates/annotator-a.csv', blankA)
  write(root, 'paper/audit/task-annotation-v1/templates/annotator-b.csv', blankA)
  write(root, 'paper/audit/task-annotation-v1/templates/adjudication.csv', adjudicationCsv([]))
  // before consensus exists the mini pipeline reports no consensus failure
  assert.equal(validateTaskAnnotations(root).some((f) => f.includes('consensus')), false)
  writeFileSync(join(audit, 'consensus.csv'), 'task_id,incident_family_id\n')
  const failures = validateTaskAnnotations(root)
  assert.ok(failures.some((f) => f.includes('consensus')))
  assert.ok(failures.some((f) => f.includes('must not be generated')))
})
