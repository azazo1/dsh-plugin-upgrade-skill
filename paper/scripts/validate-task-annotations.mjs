// paper/scripts/validate-task-annotations.mjs
//
// Deterministic validator for the T5 incident-family task-annotation
// pipeline (paper/audit/task-annotation-v1/). Enforces:
//
//   A. inventory integrity   — inventoryStatus pre-freeze-main56, full-SHA
//      inventoryCommit resolvable in git, and the task list EXACTLY equal to
//      git ls-tree <inventoryCommit>:benchmark/tasks/ (no missing / extra /
//      duplicate); per-task treeSha pin verified; interactionMode machine-
//      re-derived from the pinned benchmark/README.md Type column (never the
//      ID prefix);
//   B. packet integrity      — task set/order/pins equal the inventory, the
//      committed packet regenerates byte-identically (determinism), and the
//      leakage guard holds: no benchmark/results/ paths, no outcome/model/
//      condition/holdout-verdict vocabulary, no outcome field names, and no
//      task.toml difficulty key (difficulty is deferred to P1);
//   C. annotator rules       — templates cover the inventory exactly; an
//      all-blank template is status not-started (valid in this PR), any
//      partially filled template is incomplete (invalid); filled rows need
//      valid trap types, confidence, rationale, family-name consistency,
//      unresolved rules, and the independence declaration;
//   D. adjudication rules    — a third party only (id distinct from both
//      annotators); only disagreement rows may be adjudicated; choice A|B|new
//      with reasons; adjudication before annotations is invalid;
//   E. consensus prohibition — consensus.csv must not exist until
//      adjudication completes; this pipeline never fabricates consensus.
//
// No model calls, no network. Usage:
//   node paper/scripts/validate-task-annotations.mjs [repo-root]
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { extractMarkdownTable } from '../../benchmark/scripts/validate-task-registry.mjs'
import { buildPacket } from './generate-task-annotation-packet.mjs'
import { CONFIDENCES, TRAP_TYPES, UNRESOLVED, computeDisagreements, csvMetadata, labelsFromCsv, parseCsv } from './measure-task-annotation-agreement.mjs'

export const FAILURE_PREFIX = '[task-annotation]'
const FULL_SHA_RE = /^[0-9a-f]{40}$/
export const ANNOTATOR_COLUMNS = ['task_id', 'incident_family_id', 'family_short_name', 'observable_trap_type', 'family_evidence', 'rationale', 'confidence', 'difficulty']
export const ADJUDICATION_COLUMNS = ['task_id', 'dimension', 'choice', 'chosen_family_id', 'chosen_trap_type', 'adjudication_reason']

function git(repoRoot, args, { allowFailure = false } = {}) {
  try {
    return execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  } catch (error) {
    if (allowFailure) return null
    throw new Error(`git ${args.join(' ')} failed: ${String(error.stderr ?? error.message).trim()}`)
  }
}

export function listTasksAt(repoRoot, commit) {
  return (git(repoRoot, ['ls-tree', '--name-only', `${commit}:benchmark/tasks/`], { allowFailure: true }) ?? '')
    .split('\n').filter(Boolean).sort()
}

/** Leakage guard: forbid outcome/model/condition/holdout vocabulary and
 *  outcome field names anywhere in the packet. Token-aware phrase patterns
 *  only — the word "meaning" must never false-positive, and the judge
 *  contract's own tier language (e.g. "caps the score at 20") is preserved
 *  because it describes the grading contract, not a measured outcome. */
export const LEAKAGE_PATTERNS = [
  { id: 'results-path', pattern: /benchmark\/results\//i, reason: 'source report paths' },
  { id: 'reward-path', pattern: /reward\.txt/i, reason: 'verifier reward path' },
  { id: 'expected-reward', pattern: /expected\s+reward/i, reason: 'expected reward outcome' },
  { id: 'reward-number', pattern: /0–1\s+reward|reward\s+[0-9]/i, reason: 'reward number' },
  { id: 'mean-reward', pattern: /\bmean\s+reward\b/i, reason: 'mean reward outcome' },
  { id: 'median-reward', pattern: /\bmedian\s+reward\b/i, reason: 'median reward outcome' },
  { id: 'oracle-score-line', pattern: /reference\s+answer\s+must\s+score/i, reason: 'oracle score claim' },
  { id: 'condition-name', pattern: /\bwith-skill\b|\bno-skill\b|\bno-injected-skill\b/i, reason: 'experiment condition vocabulary' },
  { id: 'activation-rate', pattern: /\bactivation\s*rate\b/i, reason: 'activation measurement' },
  { id: 'skill-delta', pattern: /\bskill\s*delta\b/i, reason: 'skill delta measurement' },
  { id: 'model-id', pattern: /\bcodex\b|\bterminus\b|\bclaude\b|gpt-5\.6|deepseek-v4/i, reason: 'model identity' },
  { id: 'holdout-verdict', pattern: /\bclean-holdout\b|\bknowledge_holdout_v1\b|\bprovisional_role\b|\bineligible\b|\bmixed\b/i, reason: 'exposure-ledger / holdout verdict vocabulary' },
]
export const FORBIDDEN_KEY_PATTERN = /reward|score|delta|activation/i

export function leakageFailures(packet, file = 'packet/tasks.json') {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  // structural field-name guard
  const walk = (value, path) => {
    if (Array.isArray(value)) { for (const item of value) walk(item, path); return }
    if (value !== null && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        if (FORBIDDEN_KEY_PATTERN.test(key)) fail(`forbidden outcome field name at ${path}.${key}`)
        walk(child, `${path}.${key}`)
      }
    }
  }
  walk(packet, '$')
  // textual token guard over the serialized packet
  const text = JSON.stringify(packet)
  for (const { id, pattern, reason } of LEAKAGE_PATTERNS) {
    const match = pattern.exec(text)
    if (match) fail(`leakage guard hit ${id} (${reason}): ...${text.slice(Math.max(0, match.index - 40), match.index + 60).replaceAll('\n', ' ')}...`)
  }
  return failures
}

export function validateInventoryShape(inventory, file = 'inventory.json') {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  if (inventory === null || typeof inventory !== 'object' || Array.isArray(inventory)) { fail('inventory must be a JSON object'); return failures }
  if (inventory.schemaVersion !== 1) fail('schemaVersion must be 1')
  if (inventory.id !== 'task-annotation-v1-inventory') fail('id must be task-annotation-v1-inventory')
  if (inventory.inventoryStatus !== 'pre-freeze-main56') fail(`inventoryStatus must be pre-freeze-main56, got ${JSON.stringify(inventory.inventoryStatus)}`)
  if (typeof inventory.inventoryCommit !== 'string' || !FULL_SHA_RE.test(inventory.inventoryCommit)) fail('inventoryCommit must be a full 40-char SHA')
  if (!['not-started', 'in-progress', 'single-pass-incomplete', 'complete'].includes(inventory.annotationStatus)) fail(`annotationStatus invalid: ${JSON.stringify(inventory.annotationStatus)}`)
  if (!Array.isArray(inventory.tasks) || inventory.tasks.length !== 56) fail(`tasks must be exactly 56 entries, got ${Array.isArray(inventory.tasks) ? inventory.tasks.length : 'not an array'}`)
  const seen = new Set()
  const ids = []
  for (const task of inventory.tasks ?? []) {
    if (typeof task?.id !== 'string' || task.id === '') { fail('task entry with empty id'); continue }
    if (seen.has(task.id)) fail(`duplicate task: ${task.id}`)
    seen.add(task.id)
    ids.push(task.id)
    if (!['Static', 'Hands-on'].includes(task.interactionMode)) fail(`task ${task.id}: interactionMode must be Static or Hands-on, got ${JSON.stringify(task.interactionMode)}`)
    if (typeof task.treeSha !== 'string' || !FULL_SHA_RE.test(task.treeSha)) fail(`task ${task.id}: treeSha must be a full 40-char SHA`)
  }
  const sorted = [...ids].sort()
  if (JSON.stringify(ids) !== JSON.stringify(sorted)) fail('tasks must be in lexical order by id')
  return failures
}

export function validateInventoryGit(inventory, repoRoot, file = 'inventory.json') {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  const commit = inventory.inventoryCommit
  if (!FULL_SHA_RE.test(commit ?? '')) return failures
  if (git(repoRoot, ['cat-file', '-e', `${commit}^{commit}`], { allowFailure: true }) === null) {
    fail(`inventoryCommit ${commit} not resolvable locally`)
    return failures
  }
  const actual = listTasksAt(repoRoot, commit)
  const recorded = inventory.tasks.map((task) => task.id)
  if (JSON.stringify(actual) !== JSON.stringify(recorded)) {
    fail(`task list does not equal git at inventoryCommit: recorded ${recorded.length} vs git ${actual.length}`)
  }
  const readme = git(repoRoot, ['show', `${commit}:benchmark/README.md`], { allowFailure: true })
  const typeMap = {}
  if (readme !== null) {
    for (const row of extractMarkdownTable(readme) ?? []) typeMap[row[0]] = row[1]
  }
  for (const task of inventory.tasks) {
    const tree = git(repoRoot, ['rev-parse', `${commit}:benchmark/tasks/${task.id}`], { allowFailure: true })
    if (tree !== task.treeSha) fail(`task ${task.id}: treeSha mismatch (recorded ${task.treeSha}, git ${tree})`)
    const expectedMode = typeMap[task.id]
    if (expectedMode !== undefined && expectedMode !== task.interactionMode) {
      fail(`task ${task.id}: interactionMode ${task.interactionMode} does not match the pinned registry Type ${expectedMode}`)
    } else if (expectedMode === undefined) {
      fail(`task ${task.id}: missing from the pinned benchmark/README.md task table`)
    }
  }
  return failures
}

export function validatePacket(inventory, packet, repoRoot, file = 'packet/tasks.json') {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  if (packet === null || typeof packet !== 'object' || Array.isArray(packet)) { fail('packet must be a JSON object'); return failures }
  if (packet.schemaVersion !== 1) fail('packet schemaVersion must be 1')
  if (packet.packetId !== 'task-annotation-v1-packet') fail('packetId must be task-annotation-v1-packet')
  if (packet.inventoryCommit !== inventory.inventoryCommit) fail('packet inventoryCommit must equal the inventory commit')
  if (packet.inventoryStatus !== inventory.inventoryStatus) fail('packet inventoryStatus must equal the inventory status')
  if (packet.taskCount !== inventory.tasks.length) fail(`packet taskCount ${packet.taskCount} != inventory ${inventory.tasks.length}`)
  if (!Array.isArray(packet.tasks) || packet.tasks.length !== inventory.tasks.length) fail('packet tasks must match the inventory count')
  const ids = (packet.tasks ?? []).map((task) => task.taskId)
  const expected = inventory.tasks.map((task) => task.id)
  if (JSON.stringify(ids) !== JSON.stringify(expected)) fail('packet task ids/order must equal the inventory exactly')
  const byId = new Map(inventory.tasks.map((task) => [task.id, task]))
  for (const task of packet.tasks ?? []) {
    const pinned = byId.get(task.taskId)
    if (!pinned) continue
    if (task.interactionMode !== pinned.interactionMode) fail(`task ${task.taskId}: packet interactionMode ${task.interactionMode} != inventory ${pinned.interactionMode}`)
    if (task.taskTreeSha !== pinned.treeSha) fail(`task ${task.taskId}: packet treeSha != inventory pin`)
    if (typeof task.instruction !== 'string' || task.instruction.trim() === '') fail(`task ${task.taskId}: instruction missing or empty`)
    if (typeof task.readme?.summary !== 'string') {
      fail(`task ${task.taskId}: readme summary missing`)
    } else if (task.readme.summary.trim() === '') {
      const hasReadme = git(repoRoot, ['cat-file', '-e', `${inventory.inventoryCommit}:benchmark/tasks/${task.taskId}/README.md`], { allowFailure: true }) !== null
      if (hasReadme) fail(`task ${task.taskId}: readme summary empty although the README exists at inventoryCommit`)
    }
    if (!Array.isArray(task.fixtureFiles) || task.fixtureFiles.some((p) => typeof p !== 'string' || p.includes('..'))) fail(`task ${task.taskId}: fixtureFiles must be safe relative paths`)
    if (typeof task.taskToml?.name !== 'string' || typeof task.taskToml?.version !== 'string') fail(`task ${task.taskId}: taskToml must carry name and version`)
    if (Object.hasOwn(task.taskToml ?? {}, 'difficulty')) fail(`task ${task.taskId}: packet must not carry task.toml difficulty (difficulty is deferred to P1)`)
    if (!Array.isArray(task.referencedCards) || !Array.isArray(task.unresolvedCardRefs)) fail(`task ${task.taskId}: card fields must be arrays`)
  }
  // determinism: the committed packet must regenerate byte-identically
  try {
    const regenerated = buildPacket(inventory, repoRoot)
    if (JSON.stringify(regenerated) !== JSON.stringify(packet)) fail('packet does not match deterministic regeneration')
  } catch (error) {
    fail(`packet regeneration failed: ${error.message}`)
  }
  failures.push(...leakageFailures(packet, file))
  return failures
}

export function validateAnnotatorCsv(text, inventoryIds, { role }, file) {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  const { comments, rows } = parseCsv(text)
  const meta = csvMetadata(comments)
  if (rows.length === 0) { fail('template must have a header row'); return failures }
  const header = rows[0]
  if (JSON.stringify(header) !== JSON.stringify(ANNOTATOR_COLUMNS)) {
    fail(`header mismatch: expected ${ANNOTATOR_COLUMNS.join(',')} got ${header.join(',')}`)
    return failures
  }
  const dataRows = rows.slice(1)
  const rowIds = dataRows.map((row) => row[0])
  if (JSON.stringify(rowIds) !== JSON.stringify(inventoryIds)) {
    fail(`task_id rows must equal the inventory exactly (got ${rowIds.length} rows, inventory has ${inventoryIds.length})`)
  }
  let anyFilled = false
  const familyNames = new Map()
  for (const row of dataRows) {
    const [taskId, familyId, shortName, trapType, evidence, rationale, confidence, difficulty] = row
    const filled = familyId !== '' || shortName !== '' || trapType !== '' || evidence !== '' || rationale !== '' || confidence !== ''
    anyFilled = anyFilled || filled
    if (!filled) {
      if (difficulty !== '') fail(`task ${taskId}: difficulty must be blank in v1 (deferred to P1)` )
      continue
    }
    if (familyId === '' || shortName === '' || trapType === '' || evidence === '' || rationale === '' || confidence === '') {
      fail(`task ${taskId}: incomplete row — annotator ${role} has unfilled required fields`)
    }
    if (familyId !== UNRESOLVED && !/^[a-z0-9][a-z0-9-]*$/.test(familyId)) fail(`task ${taskId}: family_id must be a stable lowercase slug, got ${JSON.stringify(familyId)}`)
    if (!TRAP_TYPES.includes(trapType)) fail(`task ${taskId}: trap type ${JSON.stringify(trapType)} not in the fixed vocabulary`)
    if (!CONFIDENCES.includes(confidence)) fail(`task ${taskId}: confidence ${JSON.stringify(confidence)} must be high|medium|low`)
    if (familyId === UNRESOLVED && confidence !== 'low') fail(`task ${taskId}: unresolved family requires confidence=low`)
    if (familyId !== UNRESOLVED && confidence === 'low' && rationale === '') fail(`task ${taskId}: low confidence requires a rationale`)
    if (difficulty !== '') fail(`task ${taskId}: difficulty must be blank in v1 (deferred to P1)`)
    const known = familyNames.get(familyId)
    if (known !== undefined && known !== shortName) fail(`task ${taskId}: family ${familyId} short name ${JSON.stringify(shortName)} != ${JSON.stringify(known)} (must be consistent per annotator)`)
    familyNames.set(familyId, shortName)
  }
  if (anyFilled) {
    if (meta.annotator_id === undefined || meta.annotator_id === '' || meta.annotator_id === '<fill>') fail(`annotator ${role}: annotator_id must be filled once any row is annotated`)
    if (meta.independence_declaration === undefined || meta.independence_declaration === '' || meta.independence_declaration === '<fill>') fail(`annotator ${role}: independence declaration must be filled once any row is annotated`)
    if (meta.started_at === undefined || meta.finished_at === undefined || /<fill>/.test(meta.started_at + meta.finished_at)) fail(`annotator ${role}: started_at/finished_at must be filled once any row is annotated`)
  }
  return { failures, anyFilled, meta }
}

export function validateAdjudicationCsv(text, annotatorMeta, disagreements, file = 'templates/adjudication.csv') {
  const failures = []
  const fail = (message) => failures.push(`${FAILURE_PREFIX} ${file}: ${message}`)
  const { comments, rows } = parseCsv(text)
  const meta = csvMetadata(comments)
  if (rows.length === 0) { fail('adjudication template must have a header row'); return failures }
  if (JSON.stringify(rows[0]) !== JSON.stringify(ADJUDICATION_COLUMNS)) {
    fail(`header mismatch: expected ${ADJUDICATION_COLUMNS.join(',')} got ${rows[0].join(',')}`)
    return failures
  }
  const dataRows = rows.slice(1).filter((row) => row.some((cell) => cell !== ''))
  if (dataRows.length === 0) return failures
  const { annotatorA: metaA, annotatorB: metaB } = annotatorMeta
  if (!disagreements || disagreements.length === 0) { fail('adjudication rows exist but no annotator disagreements were computed (annotations incomplete or absent)'); return failures }
  if (meta.adjudicator_id === undefined || meta.adjudicator_id === '' || meta.adjudicator_id === '<fill>') fail('adjudicator_id must be filled (third party)')
  if ([metaA?.annotator_id, metaB?.annotator_id].includes(meta.adjudicator_id)) fail('the adjudicator must be a third party: its id must differ from both annotator ids')
  if (meta.adjudicator_id !== undefined && /annotator/i.test(meta.adjudicator_id)) fail('the third party must not be called an annotator')
  const disagreementKeys = new Set(disagreements.map((d) => `${d.taskId}|${d.dimension}`))
  for (const row of dataRows) {
    const [taskId, dimension, choice, chosenFamily, chosenTrap, reason] = row
    if (!disagreementKeys.has(`${taskId}|${dimension}`)) fail(`row ${taskId}/${dimension} is not in the disagreement list`)
    if (!['A', 'B', 'new'].includes(choice)) fail(`row ${taskId}/${dimension}: choice must be A | B | new, got ${JSON.stringify(choice)}`)
    if (choice === 'new' && chosenFamily === '' && chosenTrap === '') fail(`row ${taskId}/${dimension}: choice new requires chosen_family_id and/or chosen_trap_type`)
    if (reason === '') fail(`row ${taskId}/${dimension}: adjudication_reason is required`)
  }
  return failures
}

/** The full pipeline validation over a repo root. */
export function validateTaskAnnotations(repoRoot) {
  const failures = []
  const root = join(repoRoot, 'paper', 'audit', 'task-annotation-v1')
  const inventory = JSON.parse(readFileSync(join(root, 'inventory.json'), 'utf8'))
  failures.push(...validateInventoryShape(inventory))
  if (failures.length === 0) failures.push(...validateInventoryGit(inventory, repoRoot))
  const packet = JSON.parse(readFileSync(join(root, 'packet', 'tasks.json'), 'utf8'))
  failures.push(...validatePacket(inventory, packet, repoRoot))

  const inventoryIds = inventory.tasks.map((task) => task.id)
  const aResult = validateAnnotatorCsv(readFileSync(join(root, 'templates', 'annotator-a.csv'), 'utf8'), inventoryIds, { role: 'A' }, 'templates/annotator-a.csv')
  const bResult = validateAnnotatorCsv(readFileSync(join(root, 'templates', 'annotator-b.csv'), 'utf8'), inventoryIds, { role: 'B' }, 'templates/annotator-b.csv')
  failures.push(...aResult.failures, ...bResult.failures)

  // disagreements only exist when both annotations exist
  let disagreements = null
  if (aResult.anyFilled && bResult.anyFilled) {
    const rowsA = labelsFromCsv(readFileSync(join(root, 'templates', 'annotator-a.csv'), 'utf8'), {})
    const rowsB = labelsFromCsv(readFileSync(join(root, 'templates', 'annotator-b.csv'), 'utf8'), {})
    disagreements = computeDisagreements(rowsA, rowsB)
  }
  const adjText = readFileSync(join(root, 'templates', 'adjudication.csv'), 'utf8')
  const adjResult = validateAdjudicationCsv(
    adjText,
    { annotatorA: aResult.meta, annotatorB: bResult.meta },
    disagreements,
  )
  failures.push(...adjResult)

  // computed annotation status must match the declared status; "complete"
  // requires both submissions AND adjudication coverage of every
  // disagreement
  const bothFilled = aResult.anyFilled && bResult.anyFilled
  let computed = 'not-started'
  if (!aResult.anyFilled && !bResult.anyFilled) computed = 'not-started'
  else if (!bothFilled) computed = 'single-pass-incomplete'
  else {
    const adjRows = parseCsv(adjText).rows.slice(1).filter((row) => row.some((cell) => cell !== ''))
    const covered = new Set(adjRows.map((row) => `${row[0]}|${row[1]}`))
    const allCovered = (disagreements ?? []).every((d) => covered.has(`${d.taskId}|${d.dimension}`))
    computed = allCovered ? 'complete' : 'in-progress'
  }
  const declared = inventory.annotationStatus
  if (declared !== computed) failures.push(`${FAILURE_PREFIX} inventory.json: annotationStatus ${JSON.stringify(declared)} != computed ${JSON.stringify(computed)}`)

  if (existsSync(join(root, 'consensus.csv'))) {
    failures.push(`${FAILURE_PREFIX} consensus.csv: consensus must not be generated before adjudication completes; this pipeline never fabricates consensus`)
  }
  return failures
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  const repoRoot = process.argv[2] ? resolve(process.argv[2]) : resolve(dirname(dirname(dirname(fileURLToPath(import.meta.url)))))
  const failures = validateTaskAnnotations(repoRoot)
  if (failures.length > 0) {
    console.error(`Task annotation validation failed (${failures.length}):`)
    for (const failure of failures) console.error(`- ${failure}`)
    process.exit(1)
  }
  console.log(`${FAILURE_PREFIX} OK: task-annotation-v1 — pre-freeze-main56 inventory pinned, 56-task packet deterministic and outcome-blind, templates not-started, no consensus fabricated`)
}
