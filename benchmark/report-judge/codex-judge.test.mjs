import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { auditEvents, CODEX_SETTINGS, codexJudge, outputSchema } from './codex-judge.mjs'
import { makePacket } from './prepare.mjs'

test('Codex judge rejects failed, repeated and tool-using turns', () => {
  const complete = { type: 'turn.completed', usage: { input_tokens: 42, output_tokens: 3 } }
  assert.equal(auditEvents([complete]).tool_calls, 0)
  assert.deepEqual(auditEvents([{ type: 'item.completed', item: { type: 'error', message: 'Startup warning' } }, complete]).diagnostics, ['Startup warning'])
  for (const events of [[], [complete, complete], [complete, { type: 'error' }],
    [complete, { type: 'item.started', item: { type: 'command_execution' } }]]) {
    assert.throws(() => auditEvents(events), /Codex judge/)
  }
  for (const key of ['features.shell_tool', 'features.unified_exec', 'features.multi_agent',
    'features.apps', 'features.plugins', 'features.memories', 'skills.include_instructions', 'skills.bundled.enabled']) {
    assert.equal(CODEX_SETTINGS[key], false)
  }
})

test('Codex transport preserves decision scoring, records usage, isolates and removes copied auth', async () => {
  const root = mkdtempSync(join(tmpdir(), 'codex-judge-test-'))
  try {
    const packet = makePacket('S2-negative-scan')
    const reports = { 'report.md': 'A located and explained observation.' }
    const answer = { decisions: packet.rubric.criteria.map(c => ({ id: c.id, verdict: 'pass', reason: 'Protocol test.' })), caps: [] }
    const authPath = join(root, 'auth.json'); writeFileSync(authPath, '{}')
    let temporaryHome
    const result = await codexJudge(packet, reports, { bin: process.execPath, model: 'test-model', authPath, logs: join(root, 'logs'),
      run: async (_bin, args, { env, input }) => {
        temporaryHome = env.CODEX_HOME
        assert.equal(env.OPENAI_API_KEY, undefined)
        assert.equal(readFileSync(join(temporaryHome, 'auth.json'), 'utf8'), '{}')
        assert.deepEqual(JSON.parse(input).candidate_reports, reports)
        assert.ok(args.includes('--ignore-user-config'))
        assert.deepEqual(outputSchema(packet).properties.decisions.items.properties.id.enum, packet.rubric.criteria.map(c => c.id))
        assert.deepEqual(outputSchema(packet).properties.decisions.items.required, ['id', 'verdict', 'reason'])
        assert.deepEqual(outputSchema(packet).properties.caps.items.required, ['id', 'triggered', 'reason'])
        writeFileSync(args[args.indexOf('--output-last-message') + 1], JSON.stringify(answer))
        mkdirSync(join(temporaryHome, 'sessions'))
        writeFileSync(join(temporaryHome, 'sessions/test.jsonl'), JSON.stringify({ type: 'turn_context', payload: { model: 'test-model' } }) + '\n')
        return { stdout: JSON.stringify({ type: 'turn.completed', usage: { input_tokens: 42 } }) + '\n', stderr: '' }
      } })
    assert.equal(result.score, 100)
    assert.equal(result.model.usage.input_tokens, 42)
    assert.equal(result.model.resolved, 'test-model')
    assert.equal(existsSync(temporaryHome), false)
    assert.equal(existsSync(join(root, 'logs/auth.json')), false)
    assert.equal(JSON.parse(readFileSync(join(root, 'logs/request.json'), 'utf8')).transport, 'codex-exec-v1')
  } finally { rmSync(root, { recursive: true, force: true }) }
})
