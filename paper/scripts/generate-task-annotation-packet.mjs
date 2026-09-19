// paper/scripts/generate-task-annotation-packet.mjs
//
// Deterministic, outcome-blind annotation packet generator for the T5
// incident-family task annotation (paper/audit/task-annotation-v1/).
//
// Reads the pinned inventory (inventory.json) and resolves EVERY source of
// evidence from git objects AT inventoryCommit — never from the living
// checkout, so later edits to tasks/cards on main cannot change an already
// generated packet:
//
//   git show <commit>:benchmark/tasks/<id>/instruction.md     (full text)
//   git show <commit>:benchmark/tasks/<id>/README.md          (summary /
//       environment / verifier paragraphs, outcome-scrubbed)
//   git show <commit>:benchmark/tasks/<id>/task.toml          ([task] name /
//       version / description / keywords + provenance fields)
//   git ls-tree <commit>:benchmark/tasks/<id>/environment/fixture  (paths)
//   git show <commit>:skills/plugin-upgrade/references/*.md   (card texts
//       referenced by the instruction)
//
// Explicitly excluded from the packet (leakage guard, machine-enforced by
// validate-task-annotations.mjs): benchmark/results/, rewards, scores,
// deltas, activation rates, model names, condition scores, exposure-ledger
// columns, holdout verdicts, skill revision SHAs.
//
// Determinism: no timestamps, no host paths, no usernames; task ordering is
// lexical by task id; regeneration is byte-identical.
//
// Usage (from the repo root):
//   node paper/scripts/generate-task-annotation-packet.mjs [--check]
// Writes paper/audit/task-annotation-v1/packet/tasks.json; --check
// regenerates in memory and exits 1 when the committed packet drifts.
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const REPO_FILES = {
  inventory: 'paper/audit/task-annotation-v1/inventory.json',
  packet: 'paper/audit/task-annotation-v1/packet/tasks.json',
}

function git(repoRoot, args, { allowFailure = false } = {}) {
  try {
    return execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  } catch (error) {
    if (allowFailure) return null
    throw new Error(`git ${args.join(' ')} failed: ${String(error.stderr ?? error.message).trim()}`)
  }
}

/** Minimal TOML [task] + provenance extraction for the task.toml shape in
 *  this repository (single-line quoted strings and quoted-string arrays).
 *  Deliberately ignores [metadata].difficulty: difficulty is deferred to P1
 *  and must not anchor annotators. */
export function parseTaskToml(text) {
  const out = {}
  let inTask = false
  let inMetadata = false
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim()
    if (/^\[task\]$/.test(line)) { inTask = true; inMetadata = false; continue }
    if (/^\[metadata\]$/.test(line)) { inTask = false; inMetadata = true; continue }
    if (/^\[/.test(line)) { inTask = false; inMetadata = false; continue }
    if (!inTask && !inMetadata) continue
    const match = /^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$/.exec(line)
    if (!match) continue
    const [, key, rawValue] = match
    if (inTask) {
      if (key === 'name' || key === 'version' || key === 'description') {
        const quoted = /^"((?:[^"\\]|\\.)*)"$/.exec(rawValue)
        if (quoted) out[key] = quoted[1].replaceAll('\\"', '"')
      } else if (key === 'keywords') {
        out.keywords = [...rawValue.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1].replaceAll('\\"', '"'))
      }
    } else if (key === 'upstream_repository' || key === 'source_tag' || key === 'target_tag') {
      const quoted = /^"((?:[^"\\]|\\.)*)"$/.exec(rawValue)
      if (quoted) out[key] = quoted[1].replaceAll('\\"', '"')
    }
  }
  return out
}

/** Sentence-level outcome/model scrubbing applied to README text: drops any
 *  sentence (or line) carrying reward paths, expected rewards, or model
 *  names, while preserving the judge behavioral contract (tier caps, gates).
 *  Package names like @deepseek-ai/dsh-session are NOT model names and are
 *  preserved. */
export const OUTCOME_LINE_PATTERN = /reward\.txt|0–1\s+reward|期望\s*reward|expected\s+reward|reward\s+[0-9]|reference\s+answer\s+must\s+score|with-skill|no-skill|no-injected-skill|\bcodex\b|\bterminus\b|\bclaude\b|gpt-5\.6|deepseek-v4|normalized\s+(?:0-100\s+)?(?:to|into)\s*$/i

export function stripOutcomeSentences(text) {
  return text
    .split('\n')
    .map((line) => {
      if (!OUTCOME_LINE_PATTERN.test(line)) return line
      const parts = line.split(/(?<=[.。])/).filter((part) => !OUTCOME_LINE_PATTERN.test(part))
      return parts.join(' ').replace(/\s{2,}/g, ' ').trim()
    })
    .filter((line) => line !== '')
    .join('\n')
}

/** Split a task README into summary + environment + verifier paragraphs,
 *  scrubbed of every outcome-adjacent artifact (oracle reward lines, reward
 *  normalization sentences, reward tables, reward fenced blocks). */
export function scrubTaskReadme(text) {
  // re-join verifier paths that the README wraps across lines so the
  // sentence-level scrub below can see them as one token
  text = text.replaceAll('\r\n', '\n').replace(/reward\.\n\s*txt/gi, 'reward.txt')
  const lines = text.split('\n')
  const kept = []
  let droppingFence = false
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const trimmed = line.trim()
    if (/^```/.test(trimmed)) {
      if (droppingFence) { droppingFence = false; continue }
      // look ahead: drop the fence block if it contains outcome material
      let j = i + 1
      let blockText = ''
      while (j < lines.length && !/^```/.test(lines[j].trim())) { blockText += lines[j] + '\n'; j += 1 }
      if (/expected\s+reward|reward\.txt|\breward\b|\bscore\b/i.test(blockText)) { i = j; continue }
      kept.push(line)
      continue
    }
    if (droppingFence) continue
    // drop Oracle bullets entirely (they state expected rewards)
    if (/^\s*-\s*\*\*Oracle\*\*:/i.test(line)) {
      // skip continuation lines (indented or fenced) that belong to the bullet
      let j = i + 1
      while (j < lines.length) {
        const next = lines[j]
        if (/^\s*-\s+\*\*/.test(next) || /^#{1,6}\s/.test(next)) break
        if (/^```/.test(next.trim())) { j += 1; while (j < lines.length && !/^```/.test(lines[j].trim())) j += 1; continue }
        if (/^\s{2,}\S/.test(next) || /^\s*\|/.test(next) || /^\s*$/.test(next)) { j += 1; continue }
        break
      }
      i = j - 1
      continue
    }
    // drop whole tables whose header advertises expected rewards
    if (/^\s*\|/.test(line)) {
      const table = [line]
      let j = i + 1
      while (j < lines.length && /^\s*\|/.test(lines[j])) { table.push(lines[j]); j += 1 }
      if (/expected\s+reward|\breward\b/i.test(table.slice(0, 3).join('\n'))) { i = j - 1; continue }
      for (const t of table) kept.push(t)
      i = j - 1
      continue
    }
    kept.push(line)
  }
  let scrubbed = kept.join('\n')
  // strip reward-normalization sentences inside verifier bullets
  scrubbed = scrubbed.replace(/(?:the\s+)?(?:reward|score)\s+is\s+normalized\s+into\s+[^.]*?reward\.txt/gi, '(normalized per the verifier contract)')
  scrubbed = scrubbed.replace(/expected\s+reward\s+`?[0-9][0-9.]*`?/gi, '')
  return scrubbed.trim().replaceAll('\n{3,}', '\n\n')
}

/** Extract summary / environment / verifier paragraphs from a scrubbed
 *  task README (deterministic line surgery, no markdown dependency). */
export function splitReadmeSections(text) {
  const lines = text.split('\n')
  const summary = []
  let environment = ''
  let verifier = ''
  let captureBullet = null
  let bulletLines = []
  const flush = () => {
    if (captureBullet === 'environment') environment = bulletLines.join('\n').trim()
    if (captureBullet === 'verifier') verifier = bulletLines.join('\n').trim()
    bulletLines = []
    captureBullet = null
  }
  for (const line of lines) {
    if (/^\s*-\s+\*\*Environment\*\*/.test(line)) { flush(); captureBullet = 'environment'; bulletLines = [line]; continue }
    if (/^\s*-\s+\*\*Verifier\*\*/.test(line)) { flush(); captureBullet = 'verifier'; bulletLines = [line]; continue }
    if (captureBullet) {
      // a new top-level bullet (not indented continuation) ends the capture
      if (/^\s*-\s+/.test(line) && !/^\s{2,}/.test(line) && !/^\s*-\s+\*\*(Environment|Verifier)\*\*/.test(line)) { flush(); continue }
      bulletLines.push(line)
      continue
    }
    // summary: everything before the first bullet
    if (/^\s*-\s+/.test(line)) { flush(); continue }
    summary.push(line)
  }
  flush()
  return {
    summary: summary.join('\n').trim().replace(/^#.*\n/, '').trim(),
    environment,
    verifier,
  }
}

/** Card references found in a task instruction (short and canonical ids). */
export function extractCardRefs(text) {
  const refs = new Set()
  for (const match of text.matchAll(/\b(?:DSH-[\d.]+-)?(?:A|R)\d+-\d{2}\b/g)) refs.add(match[0])
  return [...refs].sort()
}

/** Resolve a card reference against the pinned references corpus: return the
 *  matching bullet (plus its indented continuation) from every file that
 *  contains it. */
export function resolveCardRefs(refs, refFileContents) {
  const resolved = []
  const unresolved = []
  for (const ref of refs) {
    const short = ref.replace(/^DSH-[\d.]+-/, '')
    const needle = new RegExp(`(^|\\s)-?${ref.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`)
    let found = false
    for (const { file, text } of refFileContents) {
      const lines = text.split('\n')
      for (let i = 0; i < lines.length; i += 1) {
        const line = lines[i]
        const isBullet = /^\s*-\s+/.test(line)
        const isIndented = /^\s{2,}\S/.test(line)
        if (isBullet && (line.includes(ref) || line.includes(short))) {
          const capture = [line.replace(/^\s*-\s+/, '').trim()]
          let j = i + 1
          while (j < lines.length && /^\s{2,}\S/.test(lines[j])) { capture.push(lines[j].trim()); j += 1 }
          resolved.push({ cardId: ref, source: file, text: capture.join('\n') })
          found = true
        } else if (!isBullet && !isIndented && needle.test(line)) {
          // prose mention outside a bullet: record the line for completeness
          resolved.push({ cardId: ref, source: file, text: line.trim() })
          found = true
        }
      }
    }
    if (!found) unresolved.push(ref)
  }
  return { resolved, unresolved }
}

/** Build the full packet object from the inventory + git objects at
 *  inventoryCommit. Pure function of (inventory, repoRoot). */
export function buildPacket(inventory, repoRoot) {
  const commit = inventory.inventoryCommit
  const refFiles = git(repoRoot, ['ls-tree', '--name-only', `${commit}:skills/plugin-upgrade/references/`], { allowFailure: true })
    ?.split('\n').filter((name) => name.endsWith('.md')) ?? []
  const refFileContents = refFiles.map((file) => ({
    file: `skills/plugin-upgrade/references/${file}`,
    text: git(repoRoot, ['show', `${commit}:skills/plugin-upgrade/references/${file}`], { allowFailure: true }) ?? '',
  }))
  const tasks = inventory.tasks.map((entry) => {
    const id = entry.id
    const instruction = git(repoRoot, ['show', `${commit}:benchmark/tasks/${id}/instruction.md`]) ?? ''
    const readmeText = git(repoRoot, ['show', `${commit}:benchmark/tasks/${id}/README.md`], { allowFailure: true }) ?? ''
    const scrubbed = stripOutcomeSentences(scrubTaskReadme(readmeText))
    const sections = splitReadmeSections(scrubbed)
    const tomlText = git(repoRoot, ['show', `${commit}:benchmark/tasks/${id}/task.toml`], { allowFailure: true }) ?? ''
    const taskToml = parseTaskToml(tomlText)
    const fixtureFiles = (git(repoRoot, ['ls-tree', '-r', '--name-only', `${commit}:benchmark/tasks/${id}/environment/fixture`], { allowFailure: true }) ?? '')
      .split('\n').filter(Boolean).sort()
    const refs = extractCardRefs(instruction)
    const { resolved, unresolved } = resolveCardRefs(refs, refFileContents)
    return {
      taskId: id,
      interactionMode: entry.interactionMode,
      taskTreeSha: entry.treeSha,
      taskToml,
      instruction,
      readme: sections,
      fixtureFiles,
      referencedCards: resolved,
      unresolvedCardRefs: unresolved,
    }
  })
  return {
    schemaVersion: 1,
    packetId: 'task-annotation-v1-packet',
    inventoryCommit: commit,
    inventoryStatus: inventory.inventoryStatus,
    annotationStatus: inventory.annotationStatus,
    generatedBy: 'paper/scripts/generate-task-annotation-packet.mjs',
    taskCount: tasks.length,
    tasks,
  }
}

export function renderPacket(inventory, repoRoot) {
  return JSON.stringify(buildPacket(inventory, repoRoot), null, 2) + '\n'
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  const check = process.argv.includes('--check')
  const repoRoot = resolve(dirname(dirname(dirname(fileURLToPath(import.meta.url)))))
  const inventory = JSON.parse(readFileSync(join(repoRoot, REPO_FILES.inventory), 'utf8'))
  const rendered = renderPacket(inventory, repoRoot)
  if (check) {
    const packetPath = join(repoRoot, REPO_FILES.packet)
    if (!existsSync(packetPath) || readFileSync(packetPath, 'utf8') !== rendered) {
      console.error(`annotation packet out of date: ${REPO_FILES.packet}`)
      process.exit(1)
    }
    console.log(`task annotation packet up to date (${inventory.taskCount} tasks at ${inventory.inventoryCommit.slice(0, 12)})`)
    process.exit(0)
  }
  writeFileSync(join(repoRoot, REPO_FILES.packet), rendered)
  console.log(`wrote ${REPO_FILES.packet} (${inventory.taskCount} tasks at ${inventory.inventoryCommit.slice(0, 12)})`)
}
