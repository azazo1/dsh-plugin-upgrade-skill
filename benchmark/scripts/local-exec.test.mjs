import test from 'node:test'
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

const tasksRoot = new URL('../tasks/', import.meta.url)
const localExecTasks = readdirSync(tasksRoot).sort().filter((task) => {
  const file = new URL(`${task}/tests/judge-utils.mjs`, tasksRoot)
  return existsSync(file) && /export\s+(?:async\s+)?function\s+localExec\(/.test(readFileSync(file, 'utf8'))
})
assert(localExecTasks.length > 0, 'Expected command helpers in the task inventory')

for (const task of localExecTasks) {
  test(`localExec rejects timeout and signal termination (${task})`, async () => {
    const { localExec } = await import(new URL(`${task}/tests/judge-utils.mjs`, tasksRoot))
    // exec replaces the shell so timeout cleanup cannot leave a grandchild.
    const timedOut = await localExec('exec sleep 1', { timeout: 50 })
    assert.equal(timedOut.code, 1)
    assert.equal(timedOut.killed, true)
    const signaled = await localExec('kill -TERM $$', { timeout: 5000 })
    assert.equal(signaled.code, 1)
  })

  test(`localExec preserves ordinary exit status and output (${task})`, async () => {
    const { localExec } = await import(new URL(`${task}/tests/judge-utils.mjs`, tasksRoot))
    const success = await localExec('printf ok', { timeout: 5000 })
    assert.equal(success.code, 0)
    assert.equal(success.stdout, 'ok')
    assert.equal(success.killed, false)
    const failure = await localExec('printf err >&2; exit 3', { timeout: 5000 })
    assert.equal(failure.code, 3)
    assert.equal(failure.stderr, 'err')
    assert.equal(failure.killed, false)
  })
}

const { run: runH10 } = await import(new URL('H10-browser-activation-trap/tests/judge-utils.mjs', tasksRoot))
// H9 starts its verifier on import. Evaluate its actual helper body without
// invoking the entrypoint or copying the exit-status logic into this test.
const h9Source = readFileSync(new URL('H9-dsh-web-alpha2/tests/judge.mjs', tasksRoot), 'utf8')
const h9RunSource = h9Source.match(/^function run\([\s\S]*?^\}/m)?.[0]
assert(h9RunSource, 'Expected H9 command helper')
const runH9 = runInNewContext(`(${h9RunSource})`, { execFile })
const runners = [
  ['H10', (file, args, timeout) => runH10(file, args, { timeout })],
  ['H9', (file, args, timeout) => runH9(file, args, undefined, timeout)],
]
for (const [name, run] of runners) {
  test(`${name} rejects timeout, signal termination, and spawn failure`, async () => {
    assert.equal((await run('sleep', ['1'], 50)).code, 1)
    assert.equal((await run('sh', ['-c', 'kill -TERM $$'], 5000)).code, 1)
    assert.equal((await run('/nonexistent-dsh-benchmark-test-command', [], 5000)).code, 1)
  })
  test(`${name} preserves ordinary exit status and output`, async () => {
    const success = await run('printf', ['ok'], 5000)
    assert.equal(success.code, 0)
    assert.equal(success.stdout, 'ok')
    const failure = await run('sh', ['-c', 'printf err >&2; exit 3'], 5000)
    assert.equal(failure.code, 3)
    assert.equal(failure.stderr, 'err')
  })
}
