// Opt-in transport for the same sealed report-judge protocol using Codex login.
import { spawn, execFileSync } from 'node:child_process'
import { cpSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { grade, isMain, judgeInput, JudgeError, scoreDecisions, sha256, SubmissionError, SYSTEM, writeResult } from './judge.mjs'

export const CODEX_SETTINGS = {
  approval_policy: 'never', sandbox_mode: 'read-only', web_search: 'disabled', suppress_unstable_features_warning: true,
  'skills.include_instructions': false, 'skills.bundled.enabled': false,
  'apps._default.enabled': false,
  ...Object.fromEntries(['shell_tool', 'unified_exec', 'shell_snapshot', 'multi_agent', 'multi_agent_v2',
    'memories', 'apps', 'plugins', 'remote_plugin', 'hooks', 'skill_search', 'skill_mcp_dependency_install',
    'browser_use', 'computer_use', 'image_generation', 'view_image', 'workspace_dependencies',
    'goals', 'sleep_tool', 'tool_suggest', 'code_mode', 'code_mode_only'].map(name => [`features.${name}`, false])),
  'features.skip_host_skill_discovery': true,
}

const object = properties => ({ type: 'object', properties, required: Object.keys(properties), additionalProperties: false })
const string = { type: 'string' }
const array = items => ({ type: 'array', items })
export function outputSchema(packet) {
  return object({
    decisions: array(object({ id: { type: 'string', enum: packet.rubric.criteria.map(c => c.id) },
      verdict: { type: 'string', enum: ['pass', 'partial', 'fail', 'missing'] }, reason: string })),
    caps: array(object({ id: string, triggered: { type: 'boolean' }, reason: string })),
  })
}

export function auditEvents(events) {
  const completed = events.filter(e => e.type === 'turn.completed')
  if (completed.length !== 1 || events.some(e => ['turn.failed', 'error'].includes(e.type))) {
    throw new JudgeError('Codex judge did not complete exactly one successful turn')
  }
  for (const event of events) {
    // Codex emits startup warnings as item.completed/error, separately from fatal
    // top-level error/turn.failed. Preserve these diagnostics without calling them tools.
    if (event.type?.startsWith('item.') && !['agent_message', 'reasoning', 'error'].includes(event.item?.type)) {
      throw new JudgeError('Codex judge attempted a tool or other non-text action; no score awarded')
    }
  }
  return { usage: completed[0].usage ?? null,
    request_id: events.find(e => e.type === 'thread.started')?.thread_id ?? null, tool_calls: 0,
    diagnostics: events.filter(e => e.item?.type === 'error').map(e => e.item.message) }
}

function runCodex(bin, args, { env, cwd, input, timeoutMs }) {
  return new Promise((accept, reject) => {
    const child = spawn(bin, args, { env, cwd, stdio: ['pipe', 'pipe', 'pipe'] })
    let stdout = '', stderr = '', failure = null, pending = ''
    const fail = reason => { failure ??= reason; child.kill('SIGTERM') }
    const timer = setTimeout(() => fail('Codex judge timed out; no score awarded'), timeoutMs)
    child.stdout.on('data', chunk => {
      stdout += chunk; pending += chunk
      if (Buffer.byteLength(stdout) > 8388608) fail('Codex judge output exceeded the limit')
      const lines = pending.split('\n'); pending = lines.pop()
      for (const line of lines) {
        try {
          const event = JSON.parse(line)
          if (event.type?.startsWith('item.') && !['agent_message', 'reasoning', 'error'].includes(event.item?.type)) {
            fail(`Codex judge attempted a non-text action (${event.item?.type}); no score awarded`)
          }
        } catch {}
      }
    })
    child.stderr.on('data', chunk => {
      stderr += chunk
      if (Buffer.byteLength(stderr) > 1048576) fail('Codex judge diagnostics exceeded the limit')
    })
    child.on('error', () => { clearTimeout(timer); reject(new JudgeError('Codex judge process could not start')) })
    child.on('close', code => {
      clearTimeout(timer)
      if (failure || code !== 0) reject(Object.assign(new JudgeError(failure ?? `Codex judge exited ${code}; no score awarded`), { diagnostic: { stdout, stderr } }))
      else accept({ stdout, stderr })
    })
    child.stdin.on('error', () => {})
    child.stdin.end(input)
  })
}

function rolloutFiles(root) {
  try { return readdirSync(root, { withFileTypes: true }).flatMap(e => e.isDirectory()
    ? rolloutFiles(join(root, e.name)) : e.name.endsWith('.jsonl') ? [join(root, e.name)] : []) }
  catch { return [] }
}

export async function codexJudge(packet, reports, { bin, model, authPath, logs,
  effort = 'high', timeoutMs = 240000, run = runCodex }) {
  if (!bin || !model || !authPath || !logs) throw new JudgeError('Codex judge requires bin, model, authPath and logs')
  const scratch = mkdtempSync(join(tmpdir(), 'report-codex-judge-'))
  const home = join(scratch, 'home'), cwd = join(scratch, 'empty-workspace')
  mkdirSync(home); mkdirSync(cwd); mkdirSync(logs, { recursive: true })
  const input = judgeInput(packet, reports)
  const schema = outputSchema(packet)
  const settings = { ...CODEX_SETTINGS, model_reasoning_effort: effort }
  const request = { transport: 'codex-exec-v1', model, settings, system: SYSTEM, input, schema }
  writeFileSync(join(logs, 'request.json'), JSON.stringify(request, null, 2) + '\n')
  try {
    // Copy only the explicitly selected credential, never user config/plugins/history.
    writeFileSync(join(home, 'auth.json'), readFileSync(authPath), { mode: 0o600 })
    writeFileSync(join(scratch, 'system.txt'), SYSTEM)
    writeFileSync(join(scratch, 'schema.json'), JSON.stringify(schema))
    const args = ['exec', '--ignore-user-config', '--ignore-rules', '--skip-git-repo-check',
      '--sandbox', 'read-only', '--model', model, '--json', '--color', 'never',
      '--output-schema', join(scratch, 'schema.json'), '--output-last-message', join(scratch, 'answer.json'),
      '-c', `model_instructions_file=${JSON.stringify(join(scratch, 'system.txt'))}`,
      ...Object.entries(settings).flatMap(([key, value]) => ['-c', `${key}=${JSON.stringify(value)}`]), '-']
    const env = { PATH: process.env.PATH, CODEX_HOME: home, LANG: 'en_US.UTF-8',
      ...(process.env.SYSTEMROOT ? { SYSTEMROOT: process.env.SYSTEMROOT } : {}) }
    const version = execFileSync(bin, ['--version'], { env, encoding: 'utf8', timeout: 10000 }).trim()
    writeFileSync(join(logs, 'invocation.json'), JSON.stringify({ version, args, cwd, settings }, null, 2) + '\n')
    const output = await run(bin, args, { env, cwd, input: JSON.stringify(input), timeoutMs })
    writeFileSync(join(logs, 'events.jsonl'), output.stdout)
    let events
    try { events = output.stdout.trim().split('\n').map(line => JSON.parse(line)) }
    catch { throw new JudgeError('Codex judge event stream is not valid JSONL') }
    const audit = auditEvents(events)
    const paths = rolloutFiles(join(home, 'sessions'))
    const contexts = []
    for (const path of paths) {
      const text = readFileSync(path, 'utf8')
      const entries = text.trim().split('\n').map(line => JSON.parse(line))
      if (entries.some(e => e.type === 'response_item' && ['function_call', 'custom_tool_call'].includes(e.payload?.type))) {
        throw new JudgeError('Codex judge native trace contains a tool call')
      }
      contexts.push(...entries.filter(e => e.type === 'turn_context').map(e => e.payload))
      // Native trace is retained for context/model auditing; the auth file is excluded.
      cpSync(path, join(logs, `native-${paths.indexOf(path)}.jsonl`))
    }
    if (contexts.some(c => c.model && c.model !== model)) throw new JudgeError('Codex judge used an unexpected model')
    const raw = readFileSync(join(scratch, 'answer.json'), 'utf8')
    writeFileSync(join(logs, 'response.json'), raw)
    let verdict
    try { verdict = JSON.parse(raw) } catch { throw new JudgeError('Codex judge answer is not JSON') }
    const result = scoreDecisions(packet, reports, verdict)
    return { ...result, model: { requested: model, returned: null, resolved: contexts[0]?.model ?? null,
      endpoint: 'codex://chatgpt-login', transport: 'codex-exec-v1', cli_version: version, reasoning_effort: effort,
      ...audit, request_sha256: sha256(JSON.stringify(request)), response_sha256: sha256(raw) } }
  } catch (error) {
    // Keep CLI diagnostics locally for evaluator failures; never echo them or copy auth.
    if (error.diagnostic) {
      writeFileSync(join(logs, 'failed-events.jsonl'), error.diagnostic.stdout)
      writeFileSync(join(logs, 'failed-cli.txt'), error.diagnostic.stderr)
    }
    throw error
  } finally { rmSync(scratch, { recursive: true, force: true }) }
}

export async function main(args = process.argv.slice(2)) {
  if (args.length % 2) throw new JudgeError('expected --name value arguments')
  const options = Object.fromEntries(args.reduce((all, key, index) => index % 2 ? all : [...all, [key, args[index + 1]]], []))
  if (!options['--packet'] || !options['--app'] || !options['--logs'] || !options['--model']) {
    throw new JudgeError('Usage: codex-judge.mjs --packet packet.json --app candidate-app --logs grade-dir --model model [--bin codex] [--auth auth.json] [--effort high]')
  }
  const logs = resolve(options['--logs'])
  writeResult(logs, { status: 'judge_error', reason: 'verification has not completed' })
  let packet, result
  try {
    packet = JSON.parse(readFileSync(options['--packet'], 'utf8'))
    result = await grade({ packet, appRoot: resolve(options['--app']), evaluate: (p, reports) => codexJudge(p, reports, {
      bin: options['--bin'] ?? 'codex', model: options['--model'], logs,
      authPath: options['--auth'] ?? join(homedir(), '.codex/auth.json'), effort: options['--effort'] ?? 'high' }) })
  } catch (error) {
    result = error instanceof SubmissionError ? { status: 'invalid_submission', score: 0, max: 100, reason: error.message }
      : { status: 'judge_error', reason: error instanceof JudgeError ? error.message : 'Codex verifier configuration or execution failed' }
  }
  result.protocol = packet?.protocol ?? 'report-judge-v2'
  result.packet_sha256 = packet ? sha256(JSON.stringify(packet)) : null
  result.judge_sha256 = sha256(readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'judge.mjs')))
  result.adapter_sha256 = sha256(readFileSync(fileURLToPath(import.meta.url)))
  writeResult(logs, result)
  console.log(JSON.stringify({ status: result.status, score: result.score, reason: result.reason }))
  if (result.status === 'judge_error') process.exitCode = 1
  return result
}

if (isMain(import.meta.url)) await main()
