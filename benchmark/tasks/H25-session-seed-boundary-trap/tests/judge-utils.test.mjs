// Unit tests for the H25 judge helpers. Behavioral inputs and runtime facts
// are the values the real judge produced for each control in-container
// against the real alpha.4 runtime; the source-level trap detection and caps
// are exercised here.
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  assembleScore, capFor, extractNamedFunctions, scanPackageJson, scanSource, scoreHygiene, scoreMigration, stripComments,
} from './judge-utils.mjs'

const ORACLE_SOURCE = `
import { Session } from '@deepseek-ai/dsh-session'
import { SessionId, SessionLogOffset, SessionSeq, SESSION_FORMAT_VERSION } from '@deepseek-ai/dsh-session/types'
export function makeForkMeta(cut) { return { meta: { isSeeded: true }, inheritedEventCount: SessionLogOffset(cut) } }
export function buildForkSession(id, seedEvents, cut) {
  const meta = makeForkMeta(cut)
  return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1, ...meta.meta }, meta.inheritedEventCount)
}
export function resumeForkSession(id, seedEvents, cut) {
  const meta = makeForkMeta(cut)
  return Session.fromRestore(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1, ...meta.meta }, meta.inheritedEventCount)
}
export function buildSession(id, seedEvents) { return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1, isSeeded: false }) }
export function eventPosition(n) { return SessionSeq(n) }
export function logOffset(n) { return SessionLogOffset(n) }
export function makeProjection() { return { key: 'fork-state', stateSchema: undefined, init(header, inheritedEventCount) { return { inheritedCount: Number(inheritedEventCount), ownEvents: 0 } }, apply(state, event) { if (event.seq >= state.inheritedCount) return { ...state, ownEvents: state.ownEvents + 1 }; return state } } }
`

const ORACLE_RUNTIME = { metaShape: { isSeeded: true, hasSeedLengthKey: false, inheritedEventCount: 3 }, freshHeaderIsSeeded: true }
const ORACLE_OBS = { invalidRejected: true, resumedBoundaryPreserved: true }

const UNTOUCHED_SOURCE = `
export function makeForkMeta(cut) { return { seedLength: cut } }
export function buildForkSession(id, seedEvents, cut) { return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1, ...makeForkMeta(cut) }) }
export function resumeForkSession(id, seedEvents, cut) { return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1, seedLength: seedEvents.length }) }
export function buildSession(id, seedEvents) { return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1 }) }
export function eventPosition(n) { return n }
export function logOffset(n) { return n }
export function makeProjection() { return { key: 'fork-state', init(header, seedLength) { return { inheritedCount: header.seedLength ?? 0, ownEvents: 0 } }, apply(state, event) { if (event.seq >= state.inheritedCount) return { ...state, ownEvents: state.ownEvents + 1 }; return state } } }
`
const UNTOUCHED_RUNTIME = { metaShape: { isSeeded: undefined, hasSeedLengthKey: true, inheritedEventCount: undefined }, freshHeaderIsSeeded: false }
const UNTOUCHED_OBS = { invalidRejected: false }

const FRESH_ONLY_SOURCE = `
import { SessionLogOffset, SessionSeq } from '@deepseek-ai/dsh-session/types'
export function makeForkMeta(cut) { return { meta: { isSeeded: true }, inheritedEventCount: SessionLogOffset(cut) } }
export function resumeForkSession(id, seedEvents, cut) { return buildForkSession(id, seedEvents, seedEvents.length) }
export function eventPosition(n) { return SessionSeq(n) }
export function logOffset(n) { return SessionLogOffset(n) }
`
const FRESH_ONLY_RUNTIME = { metaShape: { isSeeded: true, hasSeedLengthKey: false, inheritedEventCount: 3 }, freshHeaderIsSeeded: true }
const FRESH_ONLY_OBS = { invalidRejected: true, resumedBoundaryPreserved: false }

const AS_CAST_SOURCE = `
export function makeForkMeta(cut) { return { meta: { isSeeded: true }, inheritedEventCount: cut as unknown as SessionLogOffset } }
export function eventPosition(n) { return n as unknown as SessionSeq }
export function logOffset(n) { return n as unknown as SessionLogOffset }
`
const AS_CAST_RUNTIME = { metaShape: { isSeeded: true, hasSeedLengthKey: false, inheritedEventCount: 3 }, freshHeaderIsSeeded: true }
const AS_CAST_OBS = { invalidRejected: false }

const SWAPPED_SOURCE = `
import { SessionLogOffset, SessionSeq } from '@deepseek-ai/dsh-session/types'
export function eventPosition(n) { return SessionLogOffset(n) }
export function logOffset(n) { return SessionSeq(n) }
`
const SWAPPED_RUNTIME = { metaShape: { isSeeded: true, hasSeedLengthKey: false, inheritedEventCount: 3 }, freshHeaderIsSeeded: true }
const SWAPPED_OBS = { invalidRejected: true }

const PINNED_PACKAGE = JSON.stringify({ dependencies: { '@deepseek-ai/dsh-session': '0.1.2-alpha.3' } })
const CLEAN_PACKAGE = JSON.stringify({ dependencies: { '@deepseek-ai/dsh-session': '0.1.2-alpha.4' } })

function run(runtime, source, { packageJson = CLEAN_PACKAGE, observations, behavioral = 0, loadFailed = false }) {
  return assembleScore({ behavioral, runtime, source, packageJson, observations, loadFailed }).score
}

test('stripComments removes line and block comments but keeps strings', () => {
  const out = stripComments('const a = "http://x" // line\n/* block */ const b = 1')
  assert.ok(!out.includes('line'))
  assert.ok(!out.includes('block'))
  assert.ok(out.includes('"http://x"'))
})

test('extractNamedFunctions handles function declarations and arrow consts', () => {
  const bodies = extractNamedFunctions(stripComments(ORACLE_SOURCE))
  for (const name of ['makeForkMeta', 'buildForkSession', 'resumeForkSession', 'buildSession', 'eventPosition', 'logOffset', 'makeProjection']) {
    assert.ok(bodies.has(name), `${name} missing`)
  }
})

test('scanSource detects stale seedLength, casts and brand placement', () => {
  const oracle = scanSource(ORACLE_SOURCE)
  assert.equal(oracle.staleSeedLength, false)
  assert.equal(oracle.asCasts, false)
  assert.equal(oracle.eventPositionHasSessionSeq, true)
  assert.equal(oracle.logOffsetHasSessionLogOffset, true)
  assert.equal(oracle.seqUsedForOffsets, false)
  assert.equal(oracle.offsetUsedForPositions, false)
  const untouched = scanSource(UNTOUCHED_SOURCE)
  assert.equal(untouched.staleSeedLength, true)
  assert.equal(untouched.eventPositionHasSessionSeq, false)
  assert.equal(scanSource(AS_CAST_SOURCE).asCasts, true)
  const swapped = scanSource(SWAPPED_SOURCE)
  assert.equal(swapped.seqUsedForOffsets, true)
  assert.equal(swapped.offsetUsedForPositions, true)
})

test('scanPackageJson detects the alpha.3 pin in dependency values only', () => {
  assert.equal(scanPackageJson(PINNED_PACKAGE).pinsAlpha3, true)
  assert.equal(scanPackageJson(CLEAN_PACKAGE).pinsAlpha3, false)
  const prose = JSON.stringify({ description: 'from 0.1.2-alpha.3 to 0.1.2-alpha.4', dependencies: { x: '0.1.2-alpha.4' } })
  assert.equal(scanPackageJson(prose).pinsAlpha3, false)
})

test('scoreMigration: oracle 25, untouched 0, swapped 15', () => {
  assert.equal(scoreMigration(ORACLE_RUNTIME, scanSource(ORACLE_SOURCE)).score, 25)
  assert.equal(scoreMigration(UNTOUCHED_RUNTIME, scanSource(UNTOUCHED_SOURCE)).score, 0)
  assert.equal(scoreMigration(SWAPPED_RUNTIME, scanSource(SWAPPED_SOURCE)).score, 15)
})

test('control 15: oracle scores 100', () => {
  assert.equal(run(ORACLE_RUNTIME, ORACLE_SOURCE, { observations: ORACLE_OBS, behavioral: 65 }), 100)
})

test('control 1: untouched scores 0 (judge gates flat 0; assembler alone stays low)', () => {
  const score = run(UNTOUCHED_RUNTIME, UNTOUCHED_SOURCE, { observations: UNTOUCHED_OBS, behavioral: 0 })
  assert.ok(score <= 20, `got ${score}`)
})

test('control 14 (fresh-only): resume using the current log length caps at 65', () => {
  const score = run(FRESH_ONLY_RUNTIME, FRESH_ONLY_SOURCE, { observations: FRESH_ONLY_OBS, behavioral: 45 })
  assert.equal(score, 65)
})

test('control 3/4: unsafe as-cast bypass caps at 30 (casts) / 40 (constructors bypassed)', () => {
  const score = run(AS_CAST_RUNTIME, AS_CAST_SOURCE, { observations: AS_CAST_OBS, behavioral: 40 })
  assert.ok(score <= 40, `got ${score}`)
  assert.equal(score, 30, 'as-cast cap 30 beats the constructor-bypass cap 40')
})

test('control 5/6: swapped brand usage caps at 60', () => {
  assert.equal(run(SWAPPED_RUNTIME, SWAPPED_SOURCE, { observations: SWAPPED_OBS, behavioral: 60 }), 60)
})

test('control 13: alpha.3 dependency pin caps at 20', () => {
  assert.equal(run(ORACLE_RUNTIME, ORACLE_SOURCE, { packageJson: PINNED_PACKAGE, observations: ORACLE_OBS, behavioral: 65 }), 20)
})

test('control 11: stale seedLength kept caps at 70', () => {
  const compatSource = `
import { SessionLogOffset, SessionSeq } from '@deepseek-ai/dsh-session/types'
export function makeForkMeta(cut) { return { meta: { isSeeded: true }, inheritedEventCount: SessionLogOffset(cut), seedLength: cut } }
export function eventPosition(n) { return SessionSeq(n) }
export function logOffset(n) { return SessionLogOffset(n) }
`
  const runtime = { metaShape: { isSeeded: true, hasSeedLengthKey: true, inheritedEventCount: 3 }, freshHeaderIsSeeded: true }
  assert.equal(run(runtime, compatSource, { observations: ORACLE_OBS, behavioral: 65 }), 70)
})

test('control 9: isSeeded true without the inherited count caps at 40', () => {
  const source = `
export function makeForkMeta(cut) { return { meta: { isSeeded: true } } }
export function eventPosition(n) { return SessionSeq(n) }
export function logOffset(n) { return SessionLogOffset(n) }
`
  const runtime = { metaShape: { isSeeded: true, hasSeedLengthKey: false, inheritedEventCount: undefined }, freshHeaderIsSeeded: true }
  assert.equal(run(runtime, source, { observations: ORACLE_OBS, behavioral: 20 }), 40)
})

test('control 10: inherited count without isSeeded caps at 40', () => {
  const source = `
import { SessionLogOffset } from '@deepseek-ai/dsh-session/types'
export function makeForkMeta(cut) { return { inheritedEventCount: SessionLogOffset(cut) } }
export function eventPosition(n) { return n }
export function logOffset(n) { return n }
`
  const runtime = { metaShape: { isSeeded: undefined, hasSeedLengthKey: false, inheritedEventCount: 3 }, freshHeaderIsSeeded: false }
  assert.equal(run(runtime, source, { observations: { invalidRejected: false }, behavioral: 10 }), 30, 'below the 40 cap naturally')
})

test('control 12: module load failure caps at 30', () => {
  assert.equal(run({ metaShape: {}, freshHeaderIsSeeded: false }, 'export const broken = (', { observations: { invalidRejected: false }, behavioral: 0, loadFailed: true }), 10)
})

test('capFor picks the smallest triggered cap and null when clean', () => {
  const clean = { scan: scanSource(ORACLE_SOURCE), packageScan: scanPackageJson(CLEAN_PACKAGE), observations: ORACLE_OBS, runtime: ORACLE_RUNTIME, loadFailed: false }
  assert.equal(capFor(clean), null)
  const swapped = { scan: scanSource(SWAPPED_SOURCE), packageScan: scanPackageJson(CLEAN_PACKAGE), observations: SWAPPED_OBS, runtime: SWAPPED_RUNTIME, loadFailed: false }
  assert.equal(capFor(swapped), 60)
  const pinned = { scan: scanSource(ORACLE_SOURCE), packageScan: scanPackageJson(PINNED_PACKAGE), observations: ORACLE_OBS, runtime: ORACLE_RUNTIME, loadFailed: false }
  assert.equal(capFor(pinned), 20)
})

test('scoreHygiene subtracts for the alpha.3 pin only', () => {
  assert.equal(scoreHygiene(scanPackageJson(CLEAN_PACKAGE)), 10)
  assert.equal(scoreHygiene(scanPackageJson(PINNED_PACKAGE)), 7)
})

test('assembleScore is byte-deterministic and reports reasons', () => {
  const args = { behavioral: 65, runtime: ORACLE_RUNTIME, source: ORACLE_SOURCE, packageJson: CLEAN_PACKAGE, observations: ORACLE_OBS, loadFailed: false }
  assert.deepEqual(assembleScore(args), assembleScore(args))
  const out = assembleScore(args)
  assert.equal(out.score, 100)
  assert.ok(out.reasons.length >= 1)
})

test('keyword/comment mention without real migration keeps the failure', () => {
  const mention = `
// SessionSeq / SessionLogOffset / isSeeded / inheritedEventCount are the alpha.4 contract.
export function makeForkMeta(cut) { return { seedLength: cut } }
export function buildForkSession(id, seedEvents, cut) { return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1, ...makeForkMeta(cut) }) }
export function resumeForkSession(id, seedEvents, cut) { return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1, seedLength: seedEvents.length }) }
export function buildSession(id, seedEvents) { return Session.create(SessionId(id), seedEvents, { version: SESSION_FORMAT_VERSION, id: SessionId(id), createdAt: 1 }) }
export function eventPosition(n) { return n }
export function logOffset(n) { return n }
export function makeProjection() { return { key: 'fork-state', init(header, seedLength) { return { inheritedCount: header.seedLength ?? 0, ownEvents: 0 } }, apply(state, event) { if (event.seq >= state.inheritedCount) return { ...state, ownEvents: state.ownEvents + 1 }; return state } } }
`
  const score = run(UNTOUCHED_RUNTIME, mention, { observations: UNTOUCHED_OBS, behavioral: 0 })
  assert.ok(score <= 20, `got ${score}`)
})

test('a valid length check is not evidence of a lost inherited boundary', () => {
  const source = ORACLE_SOURCE.replace('export function resumeForkSession(id, seedEvents, cut) {',
    'export function resumeForkSession(id, seedEvents, cut) { if (cut > seedEvents.length) throw new RangeError("cut");')
  assert.equal(run(ORACLE_RUNTIME, source, { observations: ORACLE_OBS, behavioral: 65 }), 100)
  assert.equal(run(ORACLE_RUNTIME, source, { observations: FRESH_ONLY_OBS, behavioral: 65 }), 65)
})
