// paper/scripts/measure-task-annotation-agreement.mjs
//
// Deterministic agreement measurement for the T5 task annotation
// (paper/audit/task-annotation-v1/). Reads the two independent annotator
// templates plus the optional third-party adjudication file and reports:
//
//   - incident family: pairwise co-clustering agreement (primary; family ids
//     are arbitrary slugs, so raw label equality is meaningless) and the
//     label-permutation-invariant Adjusted Rand Index (secondary);
//   - observable trap type: raw agreement + Cohen's kappa over the fixed
//     categorical vocabulary (kappa is null/NA — never a fabricated 0 —
//     when the category distribution makes it undefined);
//   - the disagreement list that a third-party adjudicator works from.
//
// When any required submission is missing the output has status "incomplete"
// and NO pseudo-metrics are computed. No model calls, no network, no
// reward/result data anywhere in this pipeline.
//
// Usage: node paper/scripts/measure-task-annotation-agreement.mjs [repo-root]
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export const UNRESOLVED = 'unresolved'
export const TRAP_TYPES = ['none', 'misleading-guidance', 'pre-existing-failure', 'stale-artifact', 'runtime-state', 'silent-contract-drift', 'multi-failure', 'other']
export const CONFIDENCES = ['high', 'medium', 'low']

/** Minimal CSV parser: quoted fields with \" escapes, # comment lines
 *  collected separately, CRLF tolerant. */
export function parseCsv(text) {
  const comments = []
  const rows = []
  for (const rawLine of String(text).replaceAll('\r\n', '\n').split('\n')) {
    if (rawLine.trim() === '') continue
    if (rawLine.trimStart().startsWith('#')) { comments.push(rawLine.trimStart()); continue }
    const fields = []
    let field = ''
    let inQuotes = false
    for (let i = 0; i < rawLine.length; i += 1) {
      const ch = rawLine[i]
      if (inQuotes) {
        if (ch === '"') {
          if (rawLine[i + 1] === '"') { field += '"'; i += 1 } else { inQuotes = false }
        } else { field += ch }
      } else if (ch === '"') { inQuotes = true } else if (ch === ',') { fields.push(field); field = '' } else { field += ch }
    }
    fields.push(field)
    rows.push(fields.map((f) => f.trim()))
  }
  return { comments, rows }
}

/** Extract `# key: value` metadata from CSV comment lines. */
export function csvMetadata(comments) {
  const meta = {}
  for (const line of comments) {
    const match = /^#\s*([A-Za-z_]+)\s*:\s*(.*)$/.exec(line)
    if (match) meta[match[1]] = match[2].trim()
  }
  return meta
}

/** Convert annotation rows (arrays) into per-task label maps.
 *  Empty (not-started) CSVs yield null. */
export function labelsFromCsv(text, { familyCol, shortCol, trapCol }) {
  const { rows } = parseCsv(text)
  const dataRows = rows.slice(1) // drop header
  const map = new Map()
  let anyFilled = false
  for (const row of dataRows) {
    if (row.length < 7) continue
    const [taskId, familyId, , trapType] = row
    const filled = familyId !== '' || trapType !== ''
    anyFilled = anyFilled || filled
    map.set(taskId, { familyId, trapType })
  }
  return anyFilled ? map : null
}

/** Task pairs where A and B both resolved a family label (unresolved tasks
 *  are excluded from co-clustering metrics but retained and reported). */
export function comparablePairs(rowsA, rowsB) {
  const pairs = []
  for (const [taskA, labelA] of rowsA) {
    if (labelA.familyId === '' || labelA.familyId === UNRESOLVED) continue
    for (const [taskB, labelB] of rowsB) {
      if (labelB.familyId === '' || labelB.familyId === UNRESOLVED) continue
      if (taskA === taskB) continue
      if (rowsA.get(taskB)?.familyId === '' || rowsA.get(taskB)?.familyId === UNRESOLVED) continue
      if (rowsB.get(taskA)?.familyId === '' || rowsB.get(taskA)?.familyId === UNRESOLVED) continue
      if (taskA < taskB) pairs.push([taskA, taskB])
    }
  }
  return pairs
}

/** Primary incident-family metric: fraction of comparable task pairs where
 *  both annotators agree on same-family vs different-family. */
export function pairwiseCoClusteringAgreement(rowsA, rowsB) {
  const pairs = comparablePairs(rowsA, rowsB)
  if (pairs.length === 0) return null
  let agreeing = 0
  for (const [taskA, taskB] of pairs) {
    const sameA = rowsA.get(taskA).familyId === rowsA.get(taskB).familyId
    const sameB = rowsB.get(taskA).familyId === rowsB.get(taskB).familyId
    if (sameA === sameB) agreeing += 1
  }
  return agreeing / pairs.length
}

/** Label-permutation-invariant Adjusted Rand Index over resolved family
 *  labels. Standard contingency-table formula (Hubert & Arabie 1985). */
export function adjustedRandIndex(rowsA, rowsB) {
  const tasks = [...rowsA.keys()].filter((task) => {
    const a = rowsA.get(task)
    const b = rowsB.get(task)
    return a && b && a.familyId !== '' && a.familyId !== UNRESOLVED && b.familyId !== '' && b.familyId !== UNRESOLVED
  })
  if (tasks.length < 2) return null
  const contingency = new Map()
  const aCounts = new Map()
  const bCounts = new Map()
  for (const task of tasks) {
    const a = rowsA.get(task).familyId
    const b = rowsB.get(task).familyId
    const key = `${a}|||${b}`
    contingency.set(key, (contingency.get(key) ?? 0) + 1)
    aCounts.set(a, (aCounts.get(a) ?? 0) + 1)
    bCounts.set(b, (bCounts.get(b) ?? 0) + 1)
  }
  const choose2 = (n) => (n * (n - 1)) / 2
  let sumNij = 0
  for (const count of contingency.values()) sumNij += choose2(count)
  const sumAi = [...aCounts.values()].reduce((acc, n) => acc + choose2(n), 0)
  const sumBj = [...bCounts.values()].reduce((acc, n) => acc + choose2(n), 0)
  const total = choose2(tasks.length)
  const expectedIndex = (sumAi * sumBj) / total
  const maxIndex = (sumAi + sumBj) / 2
  if (maxIndex - expectedIndex === 0) return null
  return (sumNij - expectedIndex) / (maxIndex - expectedIndex)
}

/** Raw agreement over a fixed categorical dimension. */
export function rawAgreement(rowsA, rowsB, field) {
  const tasks = [...rowsA.keys()].filter((task) => {
    const a = rowsA.get(task)?.[field]
    const b = rowsB.get(task)?.[field]
    return a !== undefined && a !== '' && b !== undefined && b !== ''
  })
  if (tasks.length === 0) return null
  let agreeing = 0
  for (const task of tasks) if (rowsA.get(task)[field] === rowsB.get(task)[field]) agreeing += 1
  return agreeing / tasks.length
}

/** Cohen's kappa; returns null (NA) whenever the category distribution
 *  makes it undefined (e.g. every label in one category). */
export function cohensKappa(rowsA, rowsB, field) {
  const tasks = [...rowsA.keys()].filter((task) => {
    const a = rowsA.get(task)?.[field]
    const b = rowsB.get(task)?.[field]
    return a !== undefined && a !== '' && b !== undefined && b !== ''
  })
  if (tasks.length < 2) return null
  const categories = new Set()
  for (const task of tasks) {
    categories.add(rowsA.get(task)[field])
    categories.add(rowsB.get(task)[field])
  }
  if (categories.size < 2) return null // degenerate: kappa undefined, never 0
  const countsA = new Map()
  const countsB = new Map()
  let observed = 0
  for (const task of tasks) {
    const aLabel = rowsA.get(task)[field]
    const bLabel = rowsB.get(task)[field]
    if (aLabel === bLabel) observed += 1
    countsA.set(aLabel, (countsA.get(aLabel) ?? 0) + 1)
    countsB.set(bLabel, (countsB.get(bLabel) ?? 0) + 1)
  }
  if (countsA.size < 2 || countsB.size < 2) return null // no within-annotator variance: kappa undefined
  const p0 = observed / tasks.length
  let pe = 0
  for (const category of categories) {
    pe += ((countsA.get(category) ?? 0) / tasks.length) * ((countsB.get(category) ?? 0) / tasks.length)
  }
  if (1 - pe === 0) return null
  return (p0 - pe) / (1 - pe)
}

/** Per-task disagreement list across both dimensions. Unresolved-vs-resolved
 *  family labels count as family disagreements (they must be adjudicated). */
export function computeDisagreements(rowsA, rowsB) {
  const disagreements = []
  for (const task of [...rowsA.keys()].sort()) {
    const a = rowsA.get(task)
    const b = rowsB.get(task)
    if (!b) continue
    const aFamily = a.familyId || UNRESOLVED
    const bFamily = b.familyId || UNRESOLVED
    if (aFamily !== bFamily) {
      disagreements.push({ taskId: task, dimension: 'incident_family', annotatorA: aFamily, annotatorB: bFamily })
    }
    if (a.trapType && b.trapType && a.trapType !== b.trapType) {
      disagreements.push({ taskId: task, dimension: 'trap_type', annotatorA: a.trapType, annotatorB: b.trapType })
    }
  }
  return disagreements
}

/** Full measurement: annotations present → metrics; otherwise status
 *  incomplete with no pseudo-numbers. Pure function of the file texts. */
export function measureAnnotations({ inventory, annotatorAText, annotatorBText }) {
  const rowsA = labelsFromCsv(annotatorAText, {})
  const rowsB = labelsFromCsv(annotatorBText, {})
  const base = {
    status: 'incomplete',
    inventoryCount: inventory.tasks.length,
    annotators: {
      annotatorA: rowsA ? { tasks: rowsA.size } : { tasks: 0, submitted: false },
      annotatorB: rowsB ? { tasks: rowsB.size } : { tasks: 0, submitted: false },
    },
  }
  if (!rowsA || !rowsB) {
    return { ...base, reason: 'annotations missing: both independent submissions are required before any metric is computed' }
  }
  const incidentFamily = {
    pairwiseAgreement: pairwiseCoClusteringAgreement(rowsA, rowsB),
    adjustedRandIndex: adjustedRandIndex(rowsA, rowsB),
  }
  const trapType = {
    rawAgreement: rawAgreement(rowsA, rowsB, 'trapType'),
    cohensKappa: cohensKappa(rowsA, rowsB, 'trapType'),
  }
  return {
    ...base,
    status: 'complete',
    incidentFamily,
    trapType,
    disagreements: computeDisagreements(rowsA, rowsB),
  }
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  const repoRoot = process.argv[2] ? resolve(process.argv[2]) : resolve(dirname(dirname(dirname(fileURLToPath(import.meta.url)))))
  const auditRoot = join(repoRoot, 'paper', 'audit', 'task-annotation-v1')
  const inventory = JSON.parse(readFileSync(join(auditRoot, 'inventory.json'), 'utf8'))
  const read = (rel) => (existsSync(join(auditRoot, rel)) ? readFileSync(join(auditRoot, rel), 'utf8') : '')
  const result = measureAnnotations({
    inventory,
    annotatorAText: read('templates/annotator-a.csv'),
    annotatorBText: read('templates/annotator-b.csv'),
  })
  console.log(JSON.stringify(result, null, 2))
  if (result.status !== 'complete') console.log(`[task-annotation] status: ${result.status} — no metrics computed`)
}
