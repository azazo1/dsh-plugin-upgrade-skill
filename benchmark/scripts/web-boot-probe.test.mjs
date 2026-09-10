import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { bootWebAndFetchIndex as bootH8 } from '../tasks/H8-fire-drill/tests/judge-utils.mjs'
import { bootWebAndFetchIndex as bootM5 } from '../tasks/M5-token-auth-smoke/tests/judge-utils.mjs'

// Stop before the shell arguments following the embedded probe script.
const PROBE_RE = /node --input-type=module -e '([\s\S]+?)'\s+'/

async function captureProbeScript(boot) {
  const commands = []
  await boot('bench-test', '@demo/test', async (command) => {
    commands.push(command)
    return { stdout: commands.length === 1 ? 'started' : '', stderr: '' }
  })
  assert.equal(commands.length, 2, 'bootWebAndFetchIndex must launch once, then run the probe')
  const script = PROBE_RE.exec(commands[1])?.[1]
  assert(script, 'Expected an embedded Node probe in the generated command')
  return script
}

// Execute the generated script with a temporary boot log and mocked HTTP responses.
function executeProbe(script, logPath, bootUrl) {
  writeFileSync(logPath, `dsh web: ${bootUrl}\n`, 'utf8')
  const mockFetch = `
globalThis.__FETCH_CALLS__ = [];
globalThis.fetch = async (url, opts) => {
  const entry = { url, headers: opts ? opts.headers : undefined };
  globalThis.__FETCH_CALLS__.push(entry);
  if (url.includes('token=')) {
    return {
      headers: {
        getSetCookie: () => ['dsh_sid=test123; Path=/; HttpOnly'],
        get: (name) => (name === 'set-cookie' ? 'dsh_sid=test123; Path=/; HttpOnly' : null),
      },
    };
  }
  return { text: async () => '<html>mock-page</html>' };
};
`
  const wrapper = mockFetch + '\n' + script + '\nconsole.log("__FETCH_CALLS__" + JSON.stringify(globalThis.__FETCH_CALLS__));\n'
  const stdout = execFileSync(
    process.execPath,
    ['--input-type=module', '-e', wrapper, logPath, '@demo/test'],
    { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 15000 },
  )
  return {
    stdout,
    outcome: JSON.parse(/__RESULT__(\{.*\})/.exec(stdout)?.[1]),
    calls: JSON.parse(/__FETCH_CALLS__(\[.*\])/.exec(stdout)?.[1]),
  }
}

for (const [name, boot] of [['H8', bootH8], ['M5', bootM5]]) {
  test(`${name}: generated Web probe is valid JavaScript and returns observed host evidence`, async () => {
    const commands = []
    const evidence = { log: 'dsh web: http://127.0.0.1:3080/?token=fixture', html: '<html>fixture</html>' }
    const result = await boot('bench-test', '@demo/test', async (command) => {
      commands.push(command)
      return { stdout: commands.length === 1 ? 'started' : `__RESULT__${JSON.stringify(evidence)}`, stderr: '' }
    })
    assert.equal(commands.length, 2)
    const script = PROBE_RE.exec(commands[1])?.[1]
    assert(script, 'Expected an embedded Node probe')
    execFileSync(process.execPath, ['--input-type=module', '--check'], { input: script, stdio: ['pipe', 'pipe', 'pipe'] })
    assert.equal(result.output, evidence.log)
    assert.equal(result.html, evidence.html)
  })

  test(`${name}: probe fetches index at the discovered origin (non-default port) and forwards the auth cookie`, async () => {
    const script = await captureProbeScript(boot)

    const dir = mkdtempSync(join(tmpdir(), 'wbt-'))
    const bootUrl = 'http://127.0.0.1:9090/?token=abc123'
    let result
    try {
      result = executeProbe(script, join(dir, 'boot.log'), bootUrl)
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }

    assert.equal(result.outcome.html, '<html>mock-page</html>', 'probe must return the fetched index HTML')
    assert.equal(result.outcome.fetchError, undefined, 'probe must not hit a fetch error')
    assert.equal(result.calls.length, 2, 'probe must make exactly two fetch requests')
    assert.equal(result.calls[0].url, bootUrl, 'first fetch must use the discovered URL')
    assert.equal(result.calls[1].url, 'http://127.0.0.1:9090/', 'second fetch must use the discovered origin, not hardcoded :3080')
    assert.equal(result.calls[1].headers.cookie, 'dsh_sid=test123', 'cookie must propagate to the index fetch')
  })
}
