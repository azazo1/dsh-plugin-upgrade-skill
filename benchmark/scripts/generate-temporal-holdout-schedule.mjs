// benchmark/scripts/generate-temporal-holdout-schedule.mjs
//
// Deterministic schedule generator for temporal-holdout-execution-v1.
// Reads the preregistered protocol JSON and materializes the 120 logical
// slots (10 tasks × 2 models × 2 conditions × 3 attempts) into a fixed
// interleaved order:
//
//   for each model × task group:
//     digest = sha256(scheduleSeed + "|" + model + "|" + task)
//     first digest byte even → ABBAAB, odd → BAABBA
//     A = frozen-skill, B = no-injected-skill
//     each condition contributes 3 slots with attempts 1..3 in sequence order
//
// The same protocol + seed always produces byte-identical output: no clocks,
// no randomness, no filesystem order dependence.
//
// Usage:
//   node benchmark/scripts/generate-temporal-holdout-schedule.mjs [--check]
// Writes benchmark/holdouts/temporal-holdout-execution-v1.schedule.json;
// --check regenerates in memory and exits 1 when the committed file drifts.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export function sequenceFor(seed, model, task) {
  const digest = createHash('sha256').update(`${seed}|${model}|${task}`).digest('hex')
  const even = parseInt(digest.slice(0, 2), 16) % 2 === 0
  return { sequence: even ? 'ABBAAB' : 'BAABBA', digest }
}

/** Generate the 120 logical slots from the protocol definition. */
export function generateSlots(protocol) {
  const seed = protocol.scheduleSeed
  const models = protocol.models
  const tasks = protocol.tasks.map((task) => task.id)
  const slots = []
  let number = 1
  const groups = []
  for (const model of models) {
    for (const task of tasks) {
      const { sequence, digest } = sequenceFor(seed, model, task)
      const conditionOf = (letter) => (letter === 'A' ? 'frozen-skill' : 'no-injected-skill')
      const groupSlots = []
      const attempts = { 'frozen-skill': 0, 'no-injected-skill': 0 }
      for (let position = 0; position < sequence.length; position += 1) {
        const letter = sequence[position]
        const condition = conditionOf(letter)
        attempts[condition] += 1
        groupSlots.push({
          slot: number,
          model,
          task,
          condition,
          attempt: attempts[condition],
          groupSeq: position + 1,
          sequence,
          sequencePosition: position,
          sequenceDigest: digest,
        })
        number += 1
      }
      slots.push(...groupSlots)
      groups.push({ model, task, sequence, digest, slots: groupSlots.map((slot) => slot.slot) })
    }
  }
  return { slots, groups, generation: { seed, slotCount: slots.length } }
}

/** Render the committed schedule document. */
export function renderSchedule(protocol) {
  const { slots, groups, generation } = generateSlots(protocol)
  return JSON.stringify({
    schemaVersion: 1,
    executionId: protocol.id,
    selectionDefinitionCommit: protocol.selectionDefinitionCommit,
    scheduleSeed: protocol.scheduleSeed,
    logicalSlots: protocol.logicalSlots,
    conditions: protocol.conditions,
    models: protocol.models,
    generatedBy: 'benchmark/scripts/generate-temporal-holdout-schedule.mjs',
    generation,
    groups,
    slots,
  }, null, 2) + '\n'
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  const check = process.argv.includes('--check')
  const repoRoot = resolve(dirname(dirname(dirname(fileURLToPath(import.meta.url)))))
  const protocolPath = join(repoRoot, 'benchmark', 'holdouts', 'temporal-holdout-execution-v1.json')
  const schedulePath = join(repoRoot, 'benchmark', 'holdouts', 'temporal-holdout-execution-v1.schedule.json')
  const protocol = JSON.parse(readFileSync(protocolPath, 'utf8'))
  const rendered = renderSchedule(protocol)
  if (check) {
    if (!existsSync(schedulePath) || readFileSync(schedulePath, 'utf8') !== rendered) {
      console.error(`schedule out of date: ${schedulePath}`)
      process.exit(1)
    }
    console.log(`temporal-holdout schedule up to date (${protocol.logicalSlots} slots)`)
    process.exit(0)
  }
  writeFileSync(schedulePath, rendered)
  console.log(`wrote temporal-holdout-execution-v1.schedule.json (${protocol.logicalSlots} slots)`)
}
