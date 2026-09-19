// Shipped in each task's /tests directory: Harbor copies task tests separately.
// Compare actual file bytes with the trusted commit, not the candidate's index
// flags (assume-unchanged/skip-worktree can hide edits from git status).
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { lstatSync, readFileSync, readlinkSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const editable = (path) => path.startsWith('fixture/src/') || path === 'fixture/package.json'
const sealed = (path) => ['fixture/data/', 'fixture/source/', 'fixture/tests/', 'fixture/node_modules/'].some((prefix) => path.startsWith(prefix))
const blob = (bytes) => createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex')

function fingerprint(path) {
  try {
    const stat = lstatSync(path)
    if (stat.isSymbolicLink()) return `120000 ${blob(Buffer.from(readlinkSync(path)))}`
    if (stat.isFile()) return `${stat.mode & 0o111 ? '100755' : '100644'} ${blob(readFileSync(path))}`
    return 'directory'
  } catch (error) {
    if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return null
    throw error
  }
}

function files(root, dir = 'fixture') {
  const result = []
  for (const name of readdirSync(join(root, dir))) {
    const path = `${dir}/${name}`
    const stat = lstatSync(join(root, path))
    if (stat.isDirectory()) result.push(...files(root, path))
    else result.push(path)
  }
  return result
}

export function createIntegrityGuard(app, baselineFile) {
  const git = (...args) => execFileSync('git', ['--no-replace-objects', '-C', app, ...args], { stdio: ['ignore', 'pipe', 'pipe'] })
  let baseline
  let tree
  try {
    baseline = readFileSync(baselineFile, 'utf8').trim()
    if (!/^[a-f0-9]{40}$/.test(baseline)) throw new Error('invalid baseline SHA')
    git('cat-file', '-e', `${baseline}^{commit}`)
    tree = git('ls-tree', '-rz', baseline).toString('utf8')
  } catch (error) {
    throw new Error(`trusted baseline unavailable: ${error.message}`)
  }
  const tracked = new Map(tree.split('\0').filter(Boolean).map((entry) => {
    const [metadata, path] = entry.split('\t')
    const [mode, type, hash] = metadata.split(' ')
    if (type !== 'blob') throw new Error(`unsupported baseline entry: ${path}`)
    return [path, `${mode} ${hash}`]
  }))
  if (!tracked.has('fixture/package.json')) throw new Error('trusted baseline has no fixture manifest')
  const candidate = new Map(files(app).filter(editable).map((path) => [path, fingerprint(join(app, path))]))
  const packageJson = readFileSync(join(app, 'fixture/package.json'), 'utf8')
  const changed = [...tracked].some(([path, expected]) => editable(path) && candidate.get(path) !== expected)
    || [...candidate.keys()].some((path) => !tracked.has(path))
  const authorized = new Map()

  return {
    changed,
    packageJson,
    readBaseline: (path) => git('show', `${baseline}:${path}`),
    // Only verifier code may authorize a specific runtime write or rename.
    allowFile(path, bytes) {
      if (!sealed(path)) throw new Error(`write allowance outside sealed data: ${path}`)
      authorized.set(path, bytes === null ? null : `100644 ${blob(bytes)}`)
    },
    check() {
      if (readFileSync(baselineFile, 'utf8').trim() !== baseline) throw new Error('trusted baseline changed')
      if (git('rev-parse', 'HEAD').toString('utf8').trim() !== baseline) throw new Error('git history rewritten (baseline commit moved)')
      if (readFileSync(join(app, 'fixture/package.json'), 'utf8') !== packageJson) throw new Error('candidate package.json changed during verification')
      const currentFiles = files(app)
      for (const path of new Set([...candidate.keys(), ...currentFiles.filter(editable)])) {
        if (candidate.get(path) !== fingerprint(join(app, path))) throw new Error(`candidate source changed during verification: ${path}`)
      }
      for (const [path, expected] of new Map([...tracked, ...authorized])) {
        if (editable(path)) continue
        if (fingerprint(join(app, path)) !== expected) throw new Error(`sealed files modified: ${path}`)
      }
      for (const path of currentFiles) {
        if (sealed(path) && !tracked.has(path) && !authorized.has(path)) throw new Error(`sealed files modified: untracked ${path}`)
      }
    },
  }
}
