// benchmark/scripts/validate-temporal-holdout-execution.test.mjs
//
// Synthetic-repository tests for the temporal-holdout execution protocol
// validator and the deterministic schedule generator. No network, no model
// calls: each test builds a minimal git repository in mkdtemp with a freeze
// commit, a task-source commit, and a definition commit carrying the split +
// protocol, then asserts the validator accepts or rejects mutations.
import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { generateSlots, renderSchedule, sequenceFor } from './generate-temporal-holdout-schedule.mjs'
import { validateExecutionProtocol } from './validate-temporal-holdout-execution.mjs'

const MODEL_A = 'deepseek/deepseek-v4-flash'
const MODEL_B = 'openai/gpt-5.6-luna'
const TASKS = ['H4-tsbuildinfo-trap', 'H7-locale-trap', 'H13-ghost-host-trap', 'M3-session-projection', 'M4-peer-prerelease-range', 'S8-release-routing-trap', 'H20-session-events-ledger', 'H21-question-answerer-waterfall', 'M13-repository-plugins-removal', 'M14-service-renames-0812']

function initRepo() {
  const root = mkdtempSync(join(tmpdir(), 't2exec-test-'))
  execFileSync('git', ['init', '-q', '-b', 'main'], { cwd: root })
  execFileSync('git', ['config', 'user.email', 'test@example.com'], { cwd: root })
  execFileSync('git', ['config', 'user.name', 'Test'], { cwd: root })
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

/** Build the standard synthetic repo: freeze skill → 10 pinned tasks → split+protocol+schedule at main. */
function buildRepo(overrides = {}) {
  const root = initRepo()
  write(root, 'skills/plugin-upgrade/SKILL.md')
  write(root, 'skills/plugin-upgrade/references/rollup-0.1.2.md')
  const freeze = commitAll(root, 'freeze')
  const skillTree = gitOut(root, ['rev-parse', `${freeze}:skills/plugin-upgrade`])
  const skillBlob = gitOut(root, ['rev-parse', `${freeze}:skills/plugin-upgrade/SKILL.md`])
  for (const task of TASKS) {
    write(root, `benchmark/tasks/${task}/task.toml`, `id = "${task}"\n`)
    write(root, `benchmark/tasks/${task}/instruction.md`, `# ${task}\ninstruction for ${task}\n`)
  }
  const taskSource = commitAll(root, 'tasks')
  const taskTrees = {}
  for (const task of TASKS) taskTrees[task] = gitOut(root, ['rev-parse', `${taskSource}:benchmark/tasks/${task}`])
  const split = {
    schemaVersion: 1, id: 'temporal-holdout-v1', kind: 'distillation-time-holdout',
    definitionCommitPolicy: 'synthetic', freeze: { commit: freeze, commitDate: 'x', skillPath: 'skills/plugin-upgrade', skillTree, skillEntryBlob: skillBlob },
    candidateInventoryCommit: taskSource, candidateInventoryCommitDate: 'x', candidateInventoryNote: 'synthetic',
    eligibilityPolicy: {}, candidates: [], primaryTasks: TASKS,
  }
  write(root, 'benchmark/holdouts/temporal-holdout-v1.json', JSON.stringify(split, null, 2))
  const definition = commitAll(root, 'definition')
  const protocol = baseProtocol({ definition, freeze, skillTree, skillBlob, taskSource, taskTrees })
  Object.assign(protocol, overrides.protocol ?? {})
  write(root, 'benchmark/holdouts/temporal-holdout-execution-v1.json', JSON.stringify(protocol, null, 2))
  write(root, 'benchmark/holdouts/temporal-holdout-execution-v1.schedule.json', overrides.scheduleText ?? renderSchedule(protocol))
  const scheduleCommit = commitAll(root, 'schedule+protocol')
  return { root, freeze, skillTree, skillBlob, taskSource, taskTrees, definition, protocol, scheduleCommit }
}

function baseProtocol({ definition, freeze, skillTree, skillBlob, taskSource, taskTrees }) {
  return {
    schemaVersion: 1,
    id: 'temporal-holdout-execution-v1',
    kind: 'preregistered-execution-protocol',
    status: 'preregistered',
    modelCallsMadeDuringPreregistration: 0,
    selectionDefinitionCommit: definition,
    skillSourceCommit: freeze,
    skillTree,
    skillEntryBlob: skillBlob,
    skillPath: 'skills/plugin-upgrade',
    taskSourceCommit: taskSource,
    tasks: TASKS.map((id) => ({ id, pinnedTree: taskTrees[id] })),
    models: [MODEL_A, MODEL_B],
    modelResolutionPolicy: { requestedIds: [MODEL_A, MODEL_B], dryResolution: 'synthetic', mismatchPolicy: 'synthetic' },
    agent: 'terminus-2',
    reasoning: 'high',
    concurrency: 1,
    attemptsPerCell: 3,
    conditions: ['frozen-skill', 'no-injected-skill'],
    logicalSlots: 120,
    scheduleSeed: 'temporal-holdout-v1-t2-2026-09',
    scheduleFile: 'benchmark/holdouts/temporal-holdout-execution-v1.schedule.json',
    timeoutPolicy: { agent: '3x', verifier: 'pinned', mutation: 'frozen' },
    networkPolicy: {
      taskContainerOutbound: 'disabled — technical enforcement',
      formalHostRequirements: 'Linux; macOS Docker Desktop is NOT an acceptable no-network authority',
      canary: 'a model-free canary must run inside a task container',
      canaryFailure: 'HARD STOP — zero formal model slots are executed until the enforcement is fixed and re-canaried',
    },
    replacementPolicy: { rules: 'infra-only, at most one replacement, artifacts retained' },
    artifactPolicy: { noTmpOnly: '/tmp-only and ephemeral CI-only retention are prohibited', manifests: 'SHA-256 manifest per trial and aggregate' },
    activationPolicy: { status: 'not-measured' },
    analysisPolicy: {
      unit: 'per-model',
      bootstrap: { unit: 'task (paired task deltas, not individual trials)', replicates: 10000, seed: '20260907' },
      wilcoxon: { type: 'two-sided Wilcoxon signed-rank', zeroHandling: 'zeros retained, midpoint ranks' },
      retainedGain: { definition: 'holdoutDelta / referenceDelta', fallback: 'retainedGain = not-estimable-yet until such a reference exists; earlier networked calibrations (e.g. H21) are context, never the denominator' },
    },
    midRunMutationPolicy: { rule: 'abort + v2' },
  }
}

function run(protocol, root) {
  return validateExecutionProtocol(protocol, root)
}

const SCHEDULE_REL = 'benchmark/holdouts/temporal-holdout-execution-v1.schedule.json'
function readSchedule(repo) {
  return JSON.parse(readFileSync(join(repo.root, SCHEDULE_REL), 'utf8'))
}
function writeSchedule(repo, schedule) {
  writeFileSync(join(repo.root, SCHEDULE_REL), JSON.stringify(schedule, null, 2))
}

test('valid protocol + schedule validates', () => {
  const repo = buildRepo()
  assert.deepEqual(run(repo.protocol, repo.root), [])
})

test('schedule generator is byte-deterministic', () => {
  const repo = buildRepo()
  assert.equal(renderSchedule(repo.protocol), renderSchedule(repo.protocol))
  assert.equal(renderSchedule(repo.protocol), readFileSync(join(repo.root, 'benchmark/holdouts/temporal-holdout-execution-v1.schedule.json'), 'utf8'))
})

test('sequenceFor is stable and balanced', () => {
  const seq = sequenceFor('temporal-holdout-v1-t2-2026-09', MODEL_A, TASKS[0])
  assert.equal(seq.sequence, sequenceFor('temporal-holdout-v1-t2-2026-09', MODEL_A, TASKS[0]).sequence)
  assert.ok(['ABBAAB', 'BAABBA'].includes(seq.sequence))
  const counts = { A: 0, B: 0 }
  for (const ch of seq.sequence) counts[ch] += 1
  assert.deepEqual(counts, { A: 3, B: 3 })
})

test('wrong definition SHA fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.selectionDefinitionCommit = '0'.repeat(40)
  assert.ok(run(def, repo.root).some((f) => f.includes('selectionDefinitionCommit')))
})

test('wrong freeze commit fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.skillSourceCommit = '0'.repeat(40)
  assert.ok(run(def, repo.root).some((f) => f.includes('skillSourceCommit') || f.includes('skillTree')))
})

test('wrong skill tree SHA fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.skillTree = '0'.repeat(40)
  assert.ok(run(def, repo.root).some((f) => f.includes('skillTree')))
})

test('wrong skill entry blob fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.skillEntryBlob = '0'.repeat(40)
  assert.ok(run(def, repo.root).some((f) => f.includes('skillEntryBlob')))
})

test('wrong task source commit fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.taskSourceCommit = '0'.repeat(40)
  assert.ok(run(def, repo.root).some((f) => f.includes('taskSourceCommit')))
})

test('missing task fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.tasks = def.tasks.slice(0, 9)
  assert.ok(run(def, repo.root).some((f) => f.includes('exactly 10')))
})

test('extra task fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.tasks.push({ id: 'H25-session-seed-boundary-trap', pinnedTree: repo.taskTrees[TASKS[0]] })
  assert.ok(run(def, repo.root).some((f) => f.includes('exactly 10') || f.includes('primaryTasks')))
})

test('duplicate task fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.tasks[9] = { ...def.tasks[0] }
  assert.ok(run(def, repo.root).some((f) => f.includes('duplicate task')))
})

test('changed pinned task tree fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.tasks[0].pinnedTree = repo.taskTrees[TASKS[1]]
  assert.ok(run(def, repo.root).some((f) => f.includes('pinnedTree mismatch')))
})

test('wrong model fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.models = ['openai/gpt-5.6-luna', 'anthropic/claude-opus-4-1']
  assert.ok(run(def, repo.root).some((f) => f.includes('models must contain')))
})

test('third model fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.models = [MODEL_A, MODEL_B, 'openai/gpt-5.6-terra']
  assert.ok(run(def, repo.root).some((f) => f.includes('models must be exactly 2')))
})

test('wrong condition fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.conditions = ['frozen-skill', 'generic-migration']
  assert.ok(run(def, repo.root).some((f) => f.includes('conditions must contain')))
})

test('2 attempts fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.attemptsPerCell = 2
  assert.ok(run(def, repo.root).some((f) => f.includes('attemptsPerCell')))
})

test('4 attempts fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.attemptsPerCell = 4
  assert.ok(run(def, repo.root).some((f) => f.includes('attemptsPerCell')))
})

test('missing slot fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  const schedule = readSchedule(repo)
  schedule.slots = schedule.slots.slice(1)
  writeSchedule(repo, schedule)
  assert.ok(run(def, repo.root).some((f) => f.includes('120') || f.includes('deterministic regeneration')))
})

test('duplicate slot fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  const schedule = readSchedule(repo)
  schedule.slots[1] = { ...schedule.slots[0] }
  writeSchedule(repo, schedule)
  assert.ok(run(def, repo.root).some((f) => f.includes('duplicate slot') || f.includes('deterministic regeneration')))
})

test('bad attempt number fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  const schedule = readSchedule(repo)
  schedule.slots[0].attempt = 4
  writeSchedule(repo, schedule)
  assert.ok(run(def, repo.root).some((f) => f.includes('bad attempt')))
})

test('unbalanced schedule fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  const schedule = readSchedule(repo)
  schedule.slots[0].condition = 'frozen-skill' // breaks the seed-derived sequence
  writeSchedule(repo, schedule)
  assert.ok(run(def, repo.root).some((f) => f.includes('observed sequence')))
})

test('non-deterministic schedule fails (generation metadata drift)', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  const schedule = readSchedule(repo)
  schedule.generation.slotCount = 119
  writeSchedule(repo, schedule)
  assert.ok(run(def, repo.root).some((f) => f.includes('generation metadata') || f.includes('deterministic regeneration')))
})

test('current-main task source cannot satisfy the pin (drift guard)', () => {
  const repo = buildRepo()
  // simulate living-main drift: edit a task AFTER the task source commit
  write(repo.root, 'benchmark/tasks/H4-tsbuildinfo-trap/instruction.md', 'drifted content')
  commitAll(repo.root, 'living drift')
  const def = JSON.parse(JSON.stringify(repo.protocol))
  // the recorded pinnedTree still matches the PINNED commit, so this stays valid —
  // the pin is immune to living drift; assert the validator still passes.
  assert.deepEqual(run(def, repo.root), [])
})

test('/tmp artifact default is rejected', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.artifactPolicy = { noTmpOnly: '', manifests: 'SHA-256' }
  assert.ok(run(def, repo.root).some((f) => f.includes('artifactPolicy')))
})

test('network enabled fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.networkPolicy.taskContainerOutbound = 'allowed'
  assert.ok(run(def, repo.root).some((f) => f.includes('networkPolicy')))
})

test('macOS Docker as authority fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.networkPolicy.formalHostRequirements = 'macOS Docker Desktop acceptable'
  assert.ok(run(def, repo.root).some((f) => f.includes('networkPolicy')))
})

test('concurrency > 1 fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.concurrency = 2
  assert.ok(run(def, repo.root).some((f) => f.includes('concurrency')))
})

test('activation claim fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.activationPolicy = { status: 'skill-opened' }
  assert.ok(run(def, repo.root).some((f) => f.includes('activationPolicy')))
})

test('bootstrap seed drift fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.analysisPolicy.bootstrap.seed = '20270101'
  assert.ok(run(def, repo.root).some((f) => f.includes('bootstrap seed')))
})

test('bootstrap replicates drift fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.analysisPolicy.bootstrap.replicates = 5000
  assert.ok(run(def, repo.root).some((f) => f.includes('bootstrap replicates')))
})

test('missing retry/replacement policy fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  delete def.replacementPolicy
  assert.ok(run(def, repo.root).some((f) => f.includes('replacementPolicy')))
})

test('missing timeout policy fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  delete def.timeoutPolicy
  assert.ok(run(def, repo.root).some((f) => f.includes('timeoutPolicy')))
})

test('missing model resolution policy fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  delete def.modelResolutionPolicy
  assert.ok(run(def, repo.root).some((f) => f.includes('modelResolutionPolicy')))
})

test('bad retained-gain rule fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.analysisPolicy.retainedGain.definition = 'holdoutDelta / anything'
  assert.ok(run(def, repo.root).some((f) => f.includes('retained-gain')))
})

test('protocol/schedule mismatch fails', () => {
  const repo = buildRepo()
  const def = JSON.parse(JSON.stringify(repo.protocol))
  const schedule = readSchedule(repo)
  schedule.executionId = 'other-v1'
  writeSchedule(repo, schedule)
  assert.ok(run(def, repo.root).some((f) => f.includes('executionId')))
})

test('zero model calls declared and enforced', () => {
  const repo = buildRepo()
  assert.equal(repo.protocol.modelCallsMadeDuringPreregistration, 0)
  const def = JSON.parse(JSON.stringify(repo.protocol))
  def.modelCallsMadeDuringPreregistration = 1
  assert.ok(run(def, repo.root).some((f) => f.includes('modelCallsMadeDuringPreregistration')))
})

test('split authority: protocol tasks must equal v1 primaryTasks exactly', () => {
  const repo = buildRepo()
  // rewrite the split with a different primary list at a NEW committed
  // definition and point the protocol at it → mismatch
  const splitPath = join(repo.root, 'benchmark/holdouts/temporal-holdout-v1.json')
  const split = JSON.parse(readFileSync(splitPath, 'utf8'))
  split.primaryTasks = TASKS.slice(0, 9)
  writeFileSync(splitPath, JSON.stringify(split, null, 2))
  const amendedDefinition = commitAll(repo.root, 'amend split definition')
  const def = { ...repo.protocol, selectionDefinitionCommit: amendedDefinition }
  const failures = run(def, repo.root)
  assert.ok(failures.some((f) => f.includes('primaryTasks')))
})

test('split authority reads the pinned definition commit, not the working tree', () => {
  const repo = buildRepo()
  // dirty the working-tree split WITHOUT committing: the preregistration
  // pins the definition commit, so uncommitted drift must not fail it
  const splitPath = join(repo.root, 'benchmark/holdouts/temporal-holdout-v1.json')
  const split = JSON.parse(readFileSync(splitPath, 'utf8'))
  split.primaryTasks = TASKS.slice(0, 9)
  writeFileSync(splitPath, JSON.stringify(split, null, 2))
  assert.deepStrictEqual(run(repo.protocol, repo.root), [])
})
