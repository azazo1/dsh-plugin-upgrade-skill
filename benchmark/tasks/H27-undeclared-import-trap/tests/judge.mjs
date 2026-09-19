// H27 judge: declares nothing, crashes on load.
// An import whose dependency was never declared — install and listing pass,
// the loader dies. Diagnosis must pin the missing declaration (not the host,
// not the code); the only accepted fix declares the dependency. Swallowing
// the import (try/catch-and-degrade) is the trap and is capped.
import {
  emit,
  readAgentText,
  fixtureChanges,
  localExec,
  dshAvailable,
  createProfile,
  addPlugin,
  cleanupProfile,
  bootHeadless,
  HEADLESS_ACTIVATED_SIGNAL,
} from './judge-utils.mjs'

const TASK = 'H27-undeclared-import-trap'
const PKG = '@demo/dsh-bench-undeclared'

async function main() {
  const reasons = []
  let score = 0
  const changed = (await fixtureChanges()).changed
  const text = readAgentText(undefined, TASK).text

  // ── Act 1: diagnosis ──────────────────────────────────────────
  if (text) score += 5, reasons.push('diagnosis report exists (+5)')
  else reasons.push('no diagnosis report found; graded as 0 for Act 1')

  const lower = text.toLowerCase()
  const namesImport = /@deepseek-ai\/dsh-llm|contentblock|module_not_found|cannot find (module|package)/.test(lower)
  if (namesImport) score += 15, reasons.push('names the failing import / resolution error (+15)')
  else reasons.push('does not name the failing import')

  const declCause = /(dependenc|package\.json).{0,120}(missing|not declared|undeclared|absent)|(missing|undeclared|absent).{0,80}(dependency|declaration)|(not|isn'?t) (in|declared in) (the )?dependencies/.test(lower)
  if (declCause) score += 20, reasons.push('attributes the crash to the undeclared dependency (+20)')
  else reasons.push('does not attribute the crash to a missing dependency declaration')

  const layerTalk = /implicit|host (used to|no longer)|provided by the host|runtime import/.test(lower)
  if (layerTalk) score += 10, reasons.push('explains why install never fetched it (implicit host provision is gone) (+10)')
  else reasons.push('does not explain why the install never fetched the package')

  // ── Act 2: the fix on disk ────────────────────────────────────
  let pkg = {}
  try { pkg = JSON.parse((await localExec(`cat /app/fixture/package.json`)).stdout) } catch {}
  const declared =
    (pkg.dependencies && Object.keys(pkg.dependencies).some((k) => k === '@deepseek-ai/dsh-llm')) ||
    (pkg.peerDependencies && pkg.peerDependencies['@deepseek-ai/dsh-llm'])
  if (declared) score += 15, reasons.push('package.json declares @deepseek-ai/dsh-llm (+15)')
  else reasons.push('package.json still does not declare @deepseek-ai/dsh-llm')

  const src = (await localExec(`cat /app/fixture/index.js`)).stdout || ''
  const stillImports = /from '@deepseek-ai\/dsh-llm'/.test(src)
  const swallowTrap = !stillImports || /try\s*{[\s\S]{0,200}from '@deepseek-ai\/dsh-llm'[\s\S]{0,400}}\s*catch/.test(src)
  if (swallowTrap) reasons.push('the import was swallowed (try/catch or dropped) — the trap is taken')

  // ── Act 3: live re-verification in a clean profile ────────────
  if (changed && (await dshAvailable())) {
    const profile = `bench-${TASK.toLowerCase()}`
    const tmpDir = `/tmp/${profile}`
    try {
      await createProfile(profile, ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'])
      const added = await addPlugin(profile, '/app/fixture')
      if (added.ok) score += 10, reasons.push('dsh plugin add succeeded (+10)')
      else reasons.push(`dsh plugin add failed: ${added.detail}`)

      const ls = await localExec(`dsh plugin --profile '${profile}' list 2>&1`)
      if (ls.code === 0 && ls.stdout.includes(PKG)) score += 5, reasons.push('the entry appears in dsh plugin list (+5)')
      else reasons.push('the entry does not appear in the list')

      const boot = await bootHeadless(profile)
      if (HEADLESS_ACTIVATED_SIGNAL.test(boot.output || '')) {
        score += 20, reasons.push('cold boot reached the application layer (MISSING_CREDENTIAL, no key) (+20)')
      } else {
        reasons.push('cold boot still fails (module resolution or otherwise)')
      }
    } finally {
      await cleanupProfile(profile, tmpDir)
    }
  } else {
    reasons.push('fixture untouched or dsh unavailable — live verification skipped')
  }

  if (swallowTrap) {
    score = Math.min(score, 40)
    reasons.push('swallow-the-import "fix" — capped at 40')
  }
  emit(score, reasons)
}

main().catch((error) => emit(0, [`judge error: ${error.message}`]))
