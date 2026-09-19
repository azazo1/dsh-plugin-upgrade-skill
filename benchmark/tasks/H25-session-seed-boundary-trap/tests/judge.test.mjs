// Real-runtime regressions: isolated git baseline and a separate verifier anchor.
import { after, before, beforeEach, test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { cpSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const task = fileURLToPath(new URL('../', import.meta.url))
const judgeUrl = new URL('./judge.mjs', import.meta.url).href
const oracle = readFileSync(join(task, 'solution/src/fork-state.mjs'), 'utf8')
let root, app, baseline, baselineFile
const git = (...args) => execFileSync('git', ['-C', app, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
const commit = () => git('-c', 'user.name=benchmark', '-c', 'user.email=benchmark@local', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'baseline')

before(() => {
  root = mkdtempSync(join(tmpdir(), 'h25-judge-'))
  app = join(root, 'app')
  baselineFile = join(root, 'verifier-baseline.sha')
  cpSync(join(task, 'environment/fixture'), join(app, 'fixture'), { recursive: true })
  git('init', '-q')
  git('add', '-f', 'fixture')
  commit()
  baseline = git('rev-parse', 'HEAD').trim()
})
beforeEach(() => {
  git('reset', '--hard', '-q', baseline)
  git('clean', '-fdq')
  writeFileSync(baselineFile, baseline)
})
after(() => { if (root) rmSync(root, { recursive: true, force: true }) })

function grade(source = oracle, prepare = () => {}) {
  if (source !== null) writeFileSync(join(app, 'fixture/src/fork-state.mjs'), typeof source === 'function' ? source() : source)
  prepare()
  const script = 'import { grade } from ' + JSON.stringify(judgeUrl) + '; await grade(' + JSON.stringify(app) + ', ' + JSON.stringify(baselineFile) + ');'
  const output = execFileSync(process.execPath, ['--input-type=module', '-e', script], { encoding: 'utf8', timeout: 30000 })
  return JSON.parse(output.trim().split('\n').at(-1))
}
function assertZero(result, reason = /sealed files modified|changed during verification/) {
  assert.equal(result.score, 0, JSON.stringify(result))
  assert.ok(result.reasons.some((text) => reason.test(text)), JSON.stringify(result))
}
const fsImport = "import { rmSync, readFileSync, writeFileSync, appendFileSync, readdirSync } from 'node:fs';\n"
const runtimeFile = 'fixture/node_modules/@deepseek-ai/dsh-session/lib/index.js'
function mutatePackage(mutate) {
  const path = join(app, 'fixture/package.json')
  const pkg = JSON.parse(readFileSync(path, 'utf8'))
  mutate(pkg)
  writeFileSync(path, JSON.stringify(pkg))
}

test('oracle earns 100 against the real runtime', () => assert.equal(grade().score, 100))
test('untouched fixture remains zero', () => assert.equal(grade(null).score, 0))
test('syntax error cannot pass', () => assert.ok(grade('export const broken = (').score <= 30))

for (const value of [null, '', 'invalid', '0'.repeat(40)]) {
  test('missing/invalid trusted anchor fails closed: ' + value, () => {
    assertZero(grade(oracle, () => {
      if (value === null) rmSync(baselineFile)
      else writeFileSync(baselineFile, value)
      writeFileSync(join(app, 'baseline.sha'), baseline)
    }), /trusted baseline unavailable/)
  })
}

for (const forge of [false, true]) {
  test('committing protected changes cannot replace the trusted baseline: ' + forge, () => {
    assertZero(grade(oracle, () => {
      writeFileSync(join(app, runtimeFile), readFileSync(join(app, runtimeFile), 'utf8') + '\n// altered\n')
      git('add', '-f', 'fixture')
      commit()
      if (forge) writeFileSync(join(app, 'baseline.sha'), git('rev-parse', 'HEAD'))
      writeFileSync(join(app, 'fixture/src/fork-state.mjs'), oracle + '\n// source still dirty\n')
    }), /git history rewritten/)
  })
}
test('import-time anchor rewrite fails closed', () => {
  assertZero(grade(() => fsImport + oracle + '\nwriteFileSync(' + JSON.stringify(baselineFile) + ', "0".repeat(40));'), /trusted baseline changed/)
})
test('runtime file edit before import is rejected', () => {
  assertZero(grade(oracle, () => writeFileSync(join(app, runtimeFile), '{}\n')))
})
test('git assume-unchanged cannot conceal a protected-file edit', () => {
  try {
    assertZero(grade(oracle, () => {
      git('update-index', '--assume-unchanged', runtimeFile)
      writeFileSync(join(app, runtimeFile), '{}\n')
    }))
  } finally { git('update-index', '--no-assume-unchanged', runtimeFile) }
})

for (const [label, mutate] of [
  ['all dependencies deleted', (pkg) => { delete pkg.dependencies }],
  ['wrong dependency version', (pkg) => { pkg.dependencies[Object.keys(pkg.dependencies)[0]] = '0.0.1' }],
  ['loose dependency range', (pkg) => { const key = Object.keys(pkg.dependencies)[0]; pkg.dependencies[key] = '^' + pkg.dependencies[key] }],
  ['runtime dependencies moved to devDependencies', (pkg) => { pkg.devDependencies = pkg.dependencies; delete pkg.dependencies }],
]) {
  test(label + ' cannot hide behind preinstalled packages', () => {
    const result = grade(oracle, () => mutatePackage(mutate))
    assert.equal(result.score, 20, JSON.stringify(result))
    assert.ok(result.reasons.some((text) => /required runtime dependencies missing or changed/.test(text)))
  })
}
test('manifest prose is not a dependency pin', () => {
  assert.equal(grade(oracle, () => mutatePackage((pkg) => { pkg.description = '0.1.2-alpha.3 migration' })).score, 100)
})
test('candidate cannot alter its manifest after inspection', () => {
  assertZero(grade(fsImport + oracle + '\nconst file = new URL("../package.json", import.meta.url); const pkg = JSON.parse(readFileSync(file)); delete pkg.dependencies; writeFileSync(file, JSON.stringify(pkg));'), /package.json changed during verification/)
})
test('candidate cannot hide a source scan by rewriting its own file', () => {
  assertZero(grade(fsImport + oracle + '\nappendFileSync(new URL("./fork-state.mjs", import.meta.url), "\\n// changed");'))
})
test('task-local integrity helpers stay identical', () => {
  assert.equal(readFileSync(new URL('./fixture-integrity.mjs', import.meta.url), 'utf8'),
    readFileSync(new URL('../../H24-invalid-record-salvage-trap/tests/fixture-integrity.mjs', import.meta.url), 'utf8'))
})

test('valid length guard keeps 100 with the real session runtime', () => {
  const source = oracle.replace('export function resumeForkSession(id, seedEvents, cut) {',
    'export function resumeForkSession(id, seedEvents, cut) {\n  if (cut > seedEvents.length) throw new RangeError("cut exceeds event count")')
  assert.equal(grade(source).score, 100)
})
for (const cut of ['seedEvents.length', '3']) {
  test('incorrect resumed boundary ' + cut + ' remains capped', () => {
    const source = oracle.replace('const meta = makeForkMeta(cut)\n  return Session.fromRestore(',
      'const meta = makeForkMeta(' + cut + ')\n  return Session.fromRestore(')
    const result = grade(source)
    assert.ok(result.score <= 65, JSON.stringify(result))
    assert.ok(result.reasons.some((reason) => /does not preserve the original inherited boundary/.test(reason)))
  })
}
const patchRuntime = 'appendFileSync(new URL("../node_modules/@deepseek-ai/dsh-session/lib/index.js", import.meta.url), "\\n// changed");'
for (const [name, source] of [
  ['patch runtime at import', fsImport + oracle + patchRuntime],
  ['patch then throw during import', fsImport + oracle + patchRuntime + 'throw new Error("failed");'],
  ['patch runtime inside a session helper', fsImport + oracle.replace('export function resumeForkSession(id, seedEvents, cut) {', 'export function resumeForkSession(id, seedEvents, cut) {\n' + patchRuntime)],
  ['add an untracked installed module', fsImport + oracle + 'writeFileSync(new URL("../node_modules/new-module.mjs", import.meta.url), "export default 1");'],
  ['patch runtime from projection callback', fsImport + oracle.replace('apply(state, event) {', 'apply(state, event) {\n' + patchRuntime)],
  ['patch runtime from constructor helper', fsImport + oracle.replace('export function eventPosition(n) {', 'export function eventPosition(n) {\n' + patchRuntime)],
]) {
  test(name + ' is a flat zero', () => assertZero(grade(source)))
}
test('in-memory session prototype changes are rejected', () => {
  assertZero(grade(oracle + '\nSession.prototype.auditAdded = () => 1;'), /Session prototype changed/)
})
