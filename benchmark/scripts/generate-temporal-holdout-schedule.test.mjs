// benchmark/scripts/generate-temporal-holdout-schedule.test.mjs
//
// Determinism and structure tests for the preregistered schedule generator.
// Pure arithmetic over pinned constants: zero model calls, zero network.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { sequenceFor, generateSlots, renderSchedule } from './generate-temporal-holdout-schedule.mjs'
import { validateExecutionProtocol } from './validate-temporal-holdout-execution.mjs'

const protocol = JSON.parse(readFileSync(join(import.meta.dirname, '..', 'holdouts', 'temporal-holdout-execution-v1.json'), 'utf8'))
const schedule = JSON.parse(readFileSync(join(import.meta.dirname, '..', 'holdouts', 'temporal-holdout-execution-v1.schedule.json'), 'utf8'))

test('sequenceFor uses the exact seed format', () => {
  const seq = sequenceFor('temporal-holdout-v1-t2-2026-09', 'deepseek/deepseek-v4-flash', 'H4-tsbuildinfo-trap')
  assert.ok(['ABBAAB', 'BAABBA'].includes(seq.sequence))
  assert.match(seq.digest, /^[0-9a-f]{64}$/)
})

test('schedule has exactly 120 logical slots', () => {
  assert.equal(schedule.slots.length, 120)
  assert.equal(protocol.logicalSlots, 120)
})

test('slot count = tasks × models × conditions × attempts', () => {
  const expected = protocol.tasks.length * protocol.models.length * protocol.conditions.length * protocol.attemptsPerCell
  assert.equal(schedule.slots.length, expected)
  assert.equal(expected, 120)
})

test('every task appears 12 times (2 models × 2 conditions × 3 attempts)', () => {
  for (const task of protocol.tasks) {
    const count = schedule.slots.filter((s) => s.task === task.id).length
    assert.equal(count, 12, `${task.id} appears ${count} times`)
  }
})

test('every model appears 60 times', () => {
  for (const model of protocol.models) {
    assert.equal(schedule.slots.filter((s) => s.model === model).length, 60)
  }
})

test('every condition appears 60 times', () => {
  for (const condition of protocol.conditions) {
    assert.equal(schedule.slots.filter((s) => s.condition === condition).length, 60)
  }
})

test('every cell has exactly attempts 1, 2, 3 in order', () => {
  const groups = new Map()
  for (const slot of schedule.slots) {
    const key = `${slot.model}|${slot.task}|${slot.condition}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(slot.attempt)
  }
  assert.equal(groups.size, 40)
  for (const [key, attempts] of groups) {
    assert.deepEqual(attempts, [1, 2, 3], `${key} attempts ${attempts}`)
  }
})

test('no duplicate logical slots', () => {
  const keys = schedule.slots.map((s) => `${s.model}|${s.task}|${s.condition}|${s.attempt}`)
  assert.equal(new Set(keys).size, 120)
})

test('each model/task group occupies a contiguous run of 6 slots', () => {
  const positions = new Map()
  schedule.slots.forEach((slot, index) => {
    const key = `${slot.model}|${slot.task}`
    if (!positions.has(key)) positions.set(key, [])
    positions.get(key).push(index)
  })
  assert.equal(positions.size, 20)
  for (const [key, indices] of positions) {
    assert.equal(indices.length, 6, `${key} has ${indices.length} slots`)
    for (let i = 1; i < indices.length; i += 1) {
      assert.equal(indices[i], indices[i - 1] + 1, `${key} is not contiguous at ${indices}`)
    }
  }
})

test('first group opens with the pinned ABBAAB/BAABBA sequence shape', () => {
  const firstModel = schedule.slots[0].model
  const firstTask = schedule.slots[0].task
  const seq = sequenceFor(protocol.scheduleSeed, firstModel, firstTask).sequence
  const observed = schedule.slots.slice(0, 6).map((s) => (s.condition === 'frozen-skill' ? 'A' : 'B')).join('')
  assert.equal(observed, seq)
})

test('renderSchedule is byte-stable across calls', () => {
  assert.equal(renderSchedule(protocol), renderSchedule(protocol))
  assert.equal(renderSchedule(protocol), readFileSync(join(import.meta.dirname, '..', 'holdouts', 'temporal-holdout-execution-v1.schedule.json'), 'utf8'))
})

test('generateSlots matches the committed schedule', () => {
  assert.deepEqual(generateSlots(protocol).slots, schedule.slots)
})

test('committed schedule validates against the protocol (self-consistency)', () => {
  const failures = validateExecutionProtocol(protocol, join(import.meta.dirname, '..', '..'))
  assert.deepEqual(failures, [])
})
