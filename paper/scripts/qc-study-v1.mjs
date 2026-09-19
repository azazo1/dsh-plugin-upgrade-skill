// Offline evidence replay and synthetic runtime controls. No model/API calls.
import { readFileSync, writeFileSync, mkdirSync, cpSync, mkdtempSync, readdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { resolve, join } from 'node:path'
import { tmpdir } from 'node:os'
import { pathToFileURL, fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import { scoreDecisions, sha256 } from '../../benchmark/report-judge/judge.mjs'
const ROOT = resolve(fileURLToPath(new URL('../../', import.meta.url)))
const out = resolve(process.argv[2] ?? 'paper/study-v1/qc/results.json')
const installed = process.argv[3]
if (!installed) throw Error('Usage: node paper/scripts/qc-study-v1.mjs <output.json> <isolated-H25-fixture-with-installed-dependencies>')
const load = p => JSON.parse(readFileSync(p, 'utf8'))
const artifacts = join(ROOT, 'benchmark/results/artifacts')
const old = join(artifacts, '2026-09-12-luna-h4-h6-h12-semantic-no-skill')
const newer = join(artifacts, '2026-09-12-luna-h4-h6-h12-decision-judge')
const replay = []
for (const id of ['H4', 'H6', 'H12']) {
  const before = load(join(old, id, 'packet.json')), after = load(join(newer, id, 'packet.json'))
  const identity = Object.fromEntries(['instruction', 'fixture', 'references', 'rubric'].map(k => [k, JSON.stringify(before[k]) === JSON.stringify(after[k])]))
  assert.ok(Object.values(identity).every(Boolean), 'Historical input drift: ' + id)
  const response = load(join(newer, id, 'judge.response.json'))
  const reports = Object.fromEntries(readdirSync(join(old, id, 'reports')).map(p => [p, readFileSync(join(old, id, 'reports', p), 'utf8')]))
  const score = scoreDecisions(after, reports, response)
  assert.equal(score.score, {H4:85, H6:75, H12:82.5}[id])
  replay.push({task:id, identity, priorStatus:load(join(old,id,'judge.details.json')).status,
    currentScore:score.score, interpretation:'reassembly of archived decisions; not a new semantic judgment',
    answerHashes:Object.fromEntries(Object.entries(reports).map(([p,b])=>[p,sha256(b)])),
    beforePacketSha256:sha256(readFileSync(join(old,id,'packet.json'))), afterPacketSha256:sha256(readFileSync(join(newer,id,'packet.json')))})
}
const task = join(ROOT, 'benchmark/tasks/H25-session-seed-boundary-trap')
assert.equal(sha256(readFileSync(join(installed,'package-lock.json'))),sha256(readFileSync(join(task,'environment/fixture/package-lock.json'))))
const scratch = mkdtempSync(join(tmpdir(), 'study-qc-h25-'))
const verifier = join(scratch, 'verifier'); cpSync(join(task,'tests'),verifier,{recursive:true})
// Add diagnostic fields to the copy only. Original judge and historical scores unchanged.
const judgeFile = join(verifier,'judge.mjs')
let judge = readFileSync(judgeFile,'utf8')
assert.equal(judge.split('emit(score, reasons)\n}').length, 2)
judge=judge.replace('function emit(score, reasons) {','function emit(score, reasons, metrics = null) {')
 .replace('JSON.stringify({ score, max: 100, reasons })','JSON.stringify({ score, max: 100, reasons, metrics })')
 .replace('emit(score, reasons)\n}', 'emit(score, reasons, { behavioral, observations, runtime, loadFailed })\n}')
writeFileSync(judgeFile,judge)
const oracle=readFileSync(join(task,'solution/src/fork-state.mjs'),'utf8')
const variants = {
 oracle,
 'equivalent-direct-cut':oracle.replace('return { meta: { isSeeded: true }, inheritedEventCount: SessionLogOffset(cut) }','return { meta: { isSeeded: true } }').replaceAll('meta.inheritedEventCount,','logOffset(cut),'),
 'wrong-restored-cut':oracle.replace('const meta = makeForkMeta(cut)\n  return Session.fromRestore(', 'const meta = makeForkMeta(seedEvents.length)\n  return Session.fromRestore('),
 'invalid-constructor-bypass':oracle.replace('return SessionSeq(n)','return n').replace('return SessionLogOffset(n)','return n'),
 untouched:null,
 'syntax-error':'export const broken = (',
}
const controls=[]
for (const [id,source] of Object.entries(variants)) {
  const app=join(scratch,id); mkdirSync(app)
  cpSync(installed,join(app,'fixture'),{recursive:true})
  const git=(...args)=>execFileSync('git',['-C',app,...args],{stdio:['ignore','pipe','pipe']}).toString().trim()
  git('init','-q'); git('add','-f','fixture')
  git('-c','user.name=study-qc','-c','user.email=study-qc@local','-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false','commit','-qm','baseline')
  const anchor=join(scratch,id+'.baseline.sha');writeFileSync(anchor,git('rev-parse','HEAD'))
  if(source!==null)writeFileSync(join(app,'fixture/src/fork-state.mjs'),source)
  const program=`import {grade} from ${JSON.stringify(pathToFileURL(judgeFile).href)}; await grade(${JSON.stringify(app)},${JSON.stringify(anchor)});`
  const output=execFileSync(process.execPath,['--input-type=module','-e',program],{encoding:'utf8',timeout:30000})
  const result=JSON.parse(output.trim().split('\n').at(-1))
  if(id==='oracle')assert.equal(result.score,100)
  if(id==='equivalent-direct-cut'){assert.equal(result.score,40);assert.equal(result.metrics.behavioral,65)}
  if(id==='wrong-restored-cut'){assert.ok(result.metrics.behavioral<65);assert.equal(result.metrics.observations.resumedBoundaryPreserved,false)}
  if(id==='invalid-constructor-bypass')assert.equal(result.metrics.observations.invalidRejected,false)
  if(id==='untouched')assert.equal(result.score,0)
  if(id==='syntax-error')assert.ok(result.score<=30)
  controls.push({id,synthetic:true,sourceSha256:source===null?null:sha256(source),result})
}
const result={mode:'offline-QC; synthetic runtime controls, not a historical H25 regrade',
  nodeVersion:process.version, fixtureLockSha256:sha256(readFileSync(join(installed,'package-lock.json'))),
  originalJudgeSha256:sha256(readFileSync(join(task,'tests/judge.mjs'))), instrumentedJudgeSha256:sha256(judge),
  historicalDecisionReplay:replay,h25Controls:controls,
  solverCalls:0,judgeModelCalls:0,actualModelCost:0,
  decision:'Retain historical capped score. For new study report functional boundary checks separately from helper-shape diagnostics; do not infer functional failure from the 40 cap.',scratch}
mkdirSync(resolve(out,'..'),{recursive:true});writeFileSync(out,JSON.stringify(result,null,2)+'\n')
console.log('QC passed: 3 historical decision replays; 6 synthetic H25 controls on real pinned runtime. Output:',out)
