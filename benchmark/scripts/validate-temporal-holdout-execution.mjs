// benchmark/scripts/validate-temporal-holdout-execution.mjs
//
// Deterministic validator for the preregistered temporal-holdout execution
// protocol (benchmark/holdouts/temporal-holdout-execution-v1.json) and its
// committed schedule. Enforces the frozen scientific pins against local git
// objects and the complete structural policy of the preregistration:
//
//   - selectionDefinitionCommit exists and is an ancestor of the local main;
//   - skill freeze commit/tree/blob and task source commit match git exactly;
//   - the ten task IDs equal temporal-holdout-v1.primaryTasks exactly AS
//     COMMITTED at the pinned selectionDefinitionCommit (never the living
//     working tree), with no duplicates, and every pinned task tree resolves
//     at the task source commit;
//   - exactly 2 models with the exact preregistered IDs, 2 conditions with
//     the exact names, attemptsPerCell 3, concurrency 1, logicalSlots 120;
//   - the committed schedule regenerates byte-identically from the protocol
//     and the fixed seed (determinism), each model/task/condition cell holds
//     exactly attempts 1..3, and each model/task group is a balanced
//     ABBAAB/BAABBA interleave with the seed-derived digest;
//   - policy completeness: network policy requires technical outbound
//     enforcement with a pre-run canary and forbids macOS Docker as the
//     authority; artifact policy forbids /tmp-only retention and requires
//     SHA-256 manifests; activation status is not-measured; bootstrap
//     replicates/seed fixed; Wilcoxon policy and zero handling exist;
//     replacement policy exists; timeout policy exists; retained-gain
//     compatibility rule exists.
//
// Usage: node benchmark/scripts/validate-temporal-holdout-execution.mjs [repo-root]
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { generateSlots, sequenceFor } from './generate-temporal-holdout-schedule.mjs'

export const FAILURE_PREFIX = '[temporal-holdout-execution]'
const FULL_SHA_RE = /^[0-9a-f]{40}$/

function git(repoRoot, args, { allowFailure = false } = {}) {
  try {
    return execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  } catch (error) {
    if (allowFailure) return null
    throw new Error(`git ${args.join(' ')} failed: ${String(error.stderr ?? error.message).trim()}`)
  }
}

function commitResolvable(repoRoot, sha) {
  return git(repoRoot, ['cat-file', '-e', `${sha}^{commit}`], { allowFailure: true }) !== null
}

function isAncestor(repoRoot, maybeAncestor, commit) {
  return git(repoRoot, ['merge-base', '--is-ancestor', maybeAncestor, commit], { allowFailure: true }) !== null
}

function treeOf(repoRoot, spec) {
  return git(repoRoot, ['rev-parse', spec], { allowFailure: true })
}

function shapeFailures(protocol, file) {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  if (protocol === null || typeof protocol !== 'object' || Array.isArray(protocol)) { fail('protocol must be a JSON object'); return failures }
  if (protocol.schemaVersion !== 1) fail(`schemaVersion must be 1, got ${JSON.stringify(protocol.schemaVersion)}`)
  if (protocol.id !== 'temporal-holdout-execution-v1') fail(`id must be temporal-holdout-execution-v1, got ${JSON.stringify(protocol.id)}`)
  if (protocol.modelCallsMadeDuringPreregistration !== 0) fail('modelCallsMadeDuringPreregistration must be 0')
  for (const field of ['selectionDefinitionCommit', 'skillSourceCommit', 'skillTree', 'skillEntryBlob', 'taskSourceCommit', 'tasks', 'models', 'modelResolutionPolicy', 'agent', 'reasoning', 'attemptsPerCell', 'concurrency', 'conditions', 'logicalSlots', 'scheduleSeed', 'scheduleFile', 'timeoutPolicy', 'networkPolicy', 'replacementPolicy', 'artifactPolicy', 'activationPolicy', 'analysisPolicy', 'midRunMutationPolicy']) {
    if (protocol[field] === undefined) fail(`missing required field: ${field}`)
  }
  if (typeof protocol.selectionDefinitionCommit !== 'string' || !FULL_SHA_RE.test(protocol.selectionDefinitionCommit)) fail('selectionDefinitionCommit must be a full 40-char SHA')
  if (typeof protocol.skillSourceCommit !== 'string' || !FULL_SHA_RE.test(protocol.skillSourceCommit)) fail('skillSourceCommit must be a full 40-char SHA')
  if (typeof protocol.taskSourceCommit !== 'string' || !FULL_SHA_RE.test(protocol.taskSourceCommit)) fail('taskSourceCommit must be a full 40-char SHA')
  if (typeof protocol.skillTree !== 'string' || !FULL_SHA_RE.test(protocol.skillTree)) fail('skillTree must be a full 40-char SHA')
  if (typeof protocol.skillEntryBlob !== 'string' || !FULL_SHA_RE.test(protocol.skillEntryBlob)) fail('skillEntryBlob must be a full 40-char SHA')
  if (!Array.isArray(protocol.tasks) || protocol.tasks.length !== 10) fail(`tasks must be exactly 10 entries, got ${Array.isArray(protocol.tasks) ? protocol.tasks.length : 'not an array'}`)
  const seenTasks = new Set()
  for (const task of protocol.tasks ?? []) {
    if (typeof task?.id !== 'string' || task.id === '') { fail('task entry with empty id'); continue }
    if (seenTasks.has(task.id)) fail(`duplicate task: ${task.id}`)
    seenTasks.add(task.id)
    if (typeof task.pinnedTree !== 'string' || !FULL_SHA_RE.test(task.pinnedTree)) fail(`task ${task.id}: pinnedTree must be a full 40-char SHA`)
  }
  if (!Array.isArray(protocol.models) || protocol.models.length !== 2) fail('models must be exactly 2 entries')
  const seenModels = new Set()
  for (const model of protocol.models ?? []) {
    if (typeof model !== 'string' || model === '') { fail('model entry empty'); continue }
    if (seenModels.has(model)) fail(`duplicate model: ${model}`)
    seenModels.add(model)
  }
  for (const expected of ['deepseek/deepseek-v4-flash', 'openai/gpt-5.6-luna']) {
    if (!seenModels.has(expected)) fail(`models must contain the preregistered id ${expected}`)
  }
  const resolution = protocol.modelResolutionPolicy
  if (resolution === undefined || !Array.isArray(resolution.requestedIds) || JSON.stringify([...resolution.requestedIds].sort()) !== JSON.stringify([...protocol.models ?? []].sort())) {
    fail('modelResolutionPolicy.requestedIds must equal the protocol models exactly')
  }
  if (resolution === undefined || typeof resolution.dryResolution !== 'string' || resolution.dryResolution === '') {
    fail('modelResolutionPolicy must record an explicit dry-run resolution outcome')
  }
  if (resolution === undefined || typeof resolution.mismatchPolicy !== 'string' || resolution.mismatchPolicy === '') {
    fail('modelResolutionPolicy must record an explicit mismatch policy')
  }
  if (protocol.agent !== 'terminus-2') fail(`agent must be terminus-2, got ${JSON.stringify(protocol.agent)}`)
  if (protocol.reasoning !== 'high') fail(`reasoning must be high, got ${JSON.stringify(protocol.reasoning)}`)
  if (protocol.attemptsPerCell !== 3) fail(`attemptsPerCell must be 3, got ${JSON.stringify(protocol.attemptsPerCell)}`)
  if (protocol.concurrency !== 1) fail(`concurrency must be 1, got ${JSON.stringify(protocol.concurrency)}`)
  if (!Array.isArray(protocol.conditions) || protocol.conditions.length !== 2) fail('conditions must be exactly 2 entries')
  const condSet = new Set(protocol.conditions ?? [])
  for (const expected of ['frozen-skill', 'no-injected-skill']) {
    if (!condSet.has(expected)) fail(`conditions must contain ${expected}`)
  }
  if (protocol.logicalSlots !== 120) fail(`logicalSlots must be 120, got ${JSON.stringify(protocol.logicalSlots)}`)
  if (typeof protocol.scheduleSeed !== 'string' || protocol.scheduleSeed === '') fail('scheduleSeed must be a non-empty string')
  if (protocol.scheduleFile !== 'benchmark/holdouts/temporal-holdout-execution-v1.schedule.json') fail(`scheduleFile must point at the committed schedule, got ${JSON.stringify(protocol.scheduleFile)}`)
  // policy completeness
  const network = protocol.networkPolicy
  if (network === undefined || typeof network.taskContainerOutbound !== 'string' || !network.taskContainerOutbound.startsWith('disabled')) fail('networkPolicy must require disabled task-container outbound traffic')
  if (network === undefined || typeof network.canary !== 'string' || !/model-free/.test(network.canary)) fail('networkPolicy must require a model-free pre-run canary')
  if (network === undefined || network.canaryFailure !== 'HARD STOP — zero formal model slots are executed until the enforcement is fixed and re-canaried') fail('networkPolicy canaryFailure must hard-stop')
  if (network === undefined || !/macOS Docker Desktop is NOT an acceptable/.test(network.formalHostRequirements ?? '')) fail('networkPolicy must forbid macOS Docker Desktop as the no-network authority')
  const artifacts = protocol.artifactPolicy
  if (artifacts === undefined || !/\/tmp-only|ephemeral CI-only/.test(artifacts.noTmpOnly ?? '')) fail('artifactPolicy must forbid /tmp-only and ephemeral CI-only retention')
  if (artifacts === undefined || !/SHA-256 manifest/.test(artifacts.manifests ?? '')) fail('artifactPolicy must require SHA-256 manifests')
  if (protocol.activationPolicy?.status !== 'not-measured') fail('activationPolicy.status must be not-measured')
  const analysis = protocol.analysisPolicy
  if (analysis?.bootstrap?.replicates !== 10000) fail('bootstrap replicates must be pinned at 10000')
  if (analysis?.bootstrap?.seed !== '20260907') fail('bootstrap seed must be pinned at 20260907')
  if (analysis?.bootstrap?.unit !== 'task (paired task deltas, not individual trials)') fail('bootstrap unit must be the task')
  if (analysis?.wilcoxon?.type !== 'two-sided Wilcoxon signed-rank') fail('Wilcoxon policy must be two-sided')
  if (analysis?.wilcoxon?.zeroHandling === undefined || analysis?.wilcoxon?.zeroHandling === '') fail('Wilcoxon zero handling must be pre-registered')
  if (protocol.replacementPolicy?.rules === undefined) fail('replacement policy must exist with explicit rules')
  if (protocol.timeoutPolicy?.agent === undefined) fail('timeout policy must exist')
  if (protocol.analysisPolicy?.retainedGain?.definition !== 'holdoutDelta / referenceDelta') fail('retained-gain rule must define holdoutDelta / referenceDelta')
  if (protocol.analysisPolicy?.retainedGain?.fallback !== 'retainedGain = not-estimable-yet until such a reference exists; earlier networked calibrations (e.g. H21) are context, never the denominator') fail('retained-gain fallback rule must exist')
  return failures
}

function gitFailures(protocol, repoRoot, file) {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  const definition = protocol.selectionDefinitionCommit
  if (!commitResolvable(repoRoot, definition)) {
    fail(`selectionDefinitionCommit ${definition} not resolvable locally`)
    return failures
  }
  const mainSha = git(repoRoot, ['rev-parse', '--verify', 'origin/main'], { allowFailure: true })
    ?? git(repoRoot, ['rev-parse', '--verify', 'main'], { allowFailure: true })
  if (mainSha !== null && !isAncestor(repoRoot, definition, mainSha)) {
    fail(`selectionDefinitionCommit is not an ancestor of main (${mainSha?.slice(0, 12)})`)
  }
  // split authority: the protocol's ten tasks must equal v1.primaryTasks
  // exactly, read at the PINNED definition commit — never from the living
  // working tree, so a later amendment of the split file on main cannot
  // break validation of this immutable preregistration
  const splitText = git(repoRoot, ['show', `${definition}:benchmark/holdouts/temporal-holdout-v1.json`], { allowFailure: true })
  if (splitText === null) {
    fail('temporal-holdout-v1.json missing at selectionDefinitionCommit')
  } else {
    const split = JSON.parse(splitText)
    const primary = [...split.primaryTasks].sort()
    const protocolTasks = protocol.tasks.map((task) => task.id).sort()
    if (JSON.stringify(primary) !== JSON.stringify(protocolTasks)) {
      fail(`protocol tasks must equal temporal-holdout-v1.primaryTasks exactly: split [${primary.join(', ')}] vs protocol [${protocolTasks.join(', ')}]`)
    }
    if (split.freeze.commit !== protocol.skillSourceCommit) fail('skillSourceCommit must equal the split freeze.commit')
  }
  // skill freeze pin
  const skillTree = treeOf(repoRoot, `${protocol.skillSourceCommit}:skills/plugin-upgrade`)
  if (skillTree !== protocol.skillTree) fail(`skillTree mismatch: recorded ${protocol.skillTree}, git says ${skillTree}`)
  const entryBlob = treeOf(repoRoot, `${protocol.skillSourceCommit}:skills/plugin-upgrade/SKILL.md`)
  if (entryBlob !== protocol.skillEntryBlob) fail(`skillEntryBlob mismatch: recorded ${protocol.skillEntryBlob}, git says ${entryBlob}`)
  // task source pins
  if (!commitResolvable(repoRoot, protocol.taskSourceCommit)) {
    fail(`taskSourceCommit ${protocol.taskSourceCommit} not resolvable locally`)
  } else {
    for (const task of protocol.tasks) {
      const tree = treeOf(repoRoot, `${protocol.taskSourceCommit}:benchmark/tasks/${task.id}`)
      if (tree === null) {
        fail(`task ${task.id} does not exist at taskSourceCommit`)
      } else if (tree !== task.pinnedTree) {
        fail(`task ${task.id} pinnedTree mismatch: recorded ${task.pinnedTree}, git says ${tree}`)
      }
    }
  }
  return failures
}

function scheduleFailures(protocol, repoRoot, file) {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  const schedulePath = join(repoRoot, protocol.scheduleFile)
  if (!existsSync(schedulePath)) {
    fail(`committed schedule missing: ${schedulePath}`)
    return failures
  }
  const committed = JSON.parse(readFileSync(schedulePath, 'utf8'))
  const { slots, groups, generation } = generateSlots(protocol)
  if (committed.schemaVersion !== 1) fail('schedule schemaVersion must be 1')
  if (committed.executionId !== protocol.id) fail('schedule executionId must match the protocol id')
  if (committed.scheduleSeed !== protocol.scheduleSeed) fail('schedule seed mismatch')
  if (committed.logicalSlots !== 120 || committed.slots.length !== 120) fail('schedule must contain exactly 120 slots')
  // byte-determinism: regeneration must equal the committed slot array
  if (JSON.stringify(committed.slots) !== JSON.stringify(slots)) fail('committed schedule does not match deterministic regeneration')
  if (JSON.stringify(committed.generation) !== JSON.stringify(generation)) fail('schedule generation metadata does not match deterministic regeneration')
  if (JSON.stringify(committed.groups) !== JSON.stringify(groups)) fail('schedule group metadata does not match deterministic regeneration')
  const seenSlotNumbers = new Set()
  const cells = new Map()
  for (const slot of committed.slots) {
    if (seenSlotNumbers.has(slot.slot)) fail(`duplicate slot number ${slot.slot}`)
    seenSlotNumbers.add(slot.slot)
    if (slot.slot < 1 || slot.slot > 120) fail(`slot number out of range: ${slot.slot}`)
    if (!['frozen-skill', 'no-injected-skill'].includes(slot.condition)) fail(`slot ${slot.slot}: unknown condition ${slot.condition}`)
    if (![1, 2, 3].includes(slot.attempt)) fail(`slot ${slot.slot}: bad attempt ${slot.attempt}`)
    const key = `${slot.model}|${slot.task}|${slot.condition}`
    const attempts = cells.get(key) ?? new Set()
    attempts.add(slot.attempt)
    cells.set(key, attempts)
  }
  if (cells.size !== 40) fail(`expected 40 model/task/condition cells, got ${cells.size}`)
  for (const [key, attempts] of cells) {
    if (attempts.size !== 3 || !attempts.has(1) || !attempts.has(2) || !attempts.has(3)) {
      fail(`cell ${key} must have exactly attempts 1..3, got ${[...attempts].sort().join(',')}`)
    }
  }
  // group balance: each model/task group must match its seed-derived sequence
  const groupMap = new Map()
  for (const slot of committed.slots) {
    const key = `${slot.model}|${slot.task}`
    if (!groupMap.has(key)) groupMap.set(key, [])
    groupMap.get(key).push(slot)
  }
  if (groupMap.size !== 20) fail(`expected 20 model/task groups, got ${groupMap.size}`)
  for (const [key, groupSlots] of groupMap) {
    const [model, task] = key.split('|')
    const { sequence } = sequenceFor(protocol.scheduleSeed, model, task)
    const observed = groupSlots.sort((a, b) => a.groupSeq - b.groupSeq).map((slot) => (slot.condition === 'frozen-skill' ? 'A' : 'B')).join('')
    if (observed !== sequence) fail(`group ${key}: observed sequence ${observed} != expected ${sequence}`)
    const perCondition = { 'frozen-skill': 0, 'no-injected-skill': 0 }
    for (const slot of groupSlots) perCondition[slot.condition] += 1
    if (perCondition['frozen-skill'] !== 3 || perCondition['no-injected-skill'] !== 3) fail(`group ${key}: conditions must be 3+3`)
  }
  return failures
}

export function validateExecutionProtocol(protocol, repoRoot, file = 'benchmark/holdouts/temporal-holdout-execution-v1.json') {
  const failures = shapeFailures(protocol, file)
  if (failures.length === 0) {
    failures.push(...gitFailures(protocol, repoRoot, file))
    failures.push(...scheduleFailures(protocol, repoRoot, file))
  }
  return failures
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  const repoRoot = process.argv[2] ? resolve(process.argv[2]) : resolve(dirname(dirname(dirname(fileURLToPath(import.meta.url)))))
  const protocolPath = join(repoRoot, 'benchmark', 'holdouts', 'temporal-holdout-execution-v1.json')
  const protocol = JSON.parse(readFileSync(protocolPath, 'utf8'))
  const failures = validateExecutionProtocol(protocol, repoRoot)
  if (failures.length > 0) {
    console.error(`Temporal-holdout-execution validation failed (${failures.length}):`)
    for (const failure of failures) console.error(`- ${failure}`)
    process.exit(1)
  }
  console.log(`${FAILURE_PREFIX} OK: temporal-holdout-execution-v1 preregistered — 120 logical slots, 10 tasks, 2 models, 2 conditions, deterministic schedule verified`)
}
