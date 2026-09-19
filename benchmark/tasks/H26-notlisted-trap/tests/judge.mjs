// H26 judge: the package that installs but never registers.
// Layered: diagnosis (two-layer attribution, anti-reinstall) + manifest fix +
// live re-verification (add → listed → cold boot reaches the app layer).
// Coarse keyword sieve for the report; container-verified signals for the fix.
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

const TASK = 'H26-notlisted-trap'
const PKG = '@demo/dsh-bench-notlisted'

async function main() {
  const reasons = []
  let score = 0
  const gate = await fixtureChanges()
  const text = readAgentText(undefined, TASK).text

  // ── Act 1: diagnosis ──────────────────────────────────────────
  if (text) score += 5, reasons.push('diagnosis report exists (+5)')
  else reasons.push('no diagnosis report found; graded as 0 for Act 1')

  const lower = text.toLowerCase()
  const twoLayers = /install|dependenc/.test(lower) && /regist|list|enab/.test(lower)
  if (twoLayers) score += 20, reasons.push('distinguishes dependency installation from plugin registration (+20)')
  else reasons.push('does not separate the install layer from the registration layer')

  const manifestCause = /manifest|package\.json|\bmain\b|exports|declaration|self-descri|dsh (field|block|entry)/.test(lower)
  if (manifestCause) score += 20, reasons.push('attributes the gap to the missing plugin self-description in package.json (+20)')
  else reasons.push('does not name the missing manifest fields (main/exports/dsh)')

  const antiReinstall = /(reinstall|re-install|reinstall|cache|store clean).{0,120}(won'?t|will not|does not|doesn'?t|cannot|can'?t|not fix|useless|no effect)|(not|isn'?t).{0,40}(a )?(reinstall|install) (problem|issue|fix)/.test(lower)
  if (antiReinstall) score += 10, reasons.push('explicitly rules out reinstalling as the fix (+10)')
  else reasons.push('does not explicitly rule out the reinstall path')

  const reinstallAsFix = /^(?:#[^\n]*\n)*[\s\S]*?(reinstall|re-install|clear (the )?(npm|pnpm) (store|cache)).{0,80}(fix|resolve|should work|and retry)/im.test(lower) && !antiReinstall
  if (reinstallAsFix) reasons.push('diagnosis leads with a reinstall/cache fix — the trap is taken')

  // ── Act 2: the manifest fix on disk ───────────────────────────
  let pkg = {}
  try { pkg = JSON.parse((await localExec(`cat /app/fixture/package.json`)).stdout) } catch {}
  const hasMain = typeof pkg.main === 'string' && pkg.main.length > 0
  const hasExports = pkg.exports && Object.keys(pkg.exports).length > 0
  const hasDsh = pkg.dsh && typeof pkg.dsh === 'object'
  const fixPieces = [hasMain, hasExports, hasDsh].filter(Boolean).length
  if (fixPieces === 3) score += 15, reasons.push('package.json carries main + exports + dsh (+15)')
  else if (fixPieces > 0) score += 5, reasons.push(`partial manifest fix (${fixPieces}/3 fields) (+5)`)
  else reasons.push('package.json still has no plugin self-description')

  // ── Act 3: live re-verification in a clean profile ────────────
  if (gate.changed === true && (await dshAvailable())) {
    const profile = `bench-${TASK.toLowerCase()}`
    const tmpDir = `/tmp/${profile}`
    let listedOk = false, bootOk = false, addOk = false
    try {
      await createProfile(profile, ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'])
      const added = await addPlugin(profile, '/app/fixture')
      addOk = added.ok
      if (addOk) score += 10, reasons.push('dsh plugin add succeeded (+10)')
      else reasons.push(`dsh plugin add failed: ${added.detail}`)

      const ls = await localExec(`dsh plugin --profile '${profile}' list 2>&1`)
      listedOk = ls.code === 0 && ls.stdout.includes(PKG)
      if (listedOk) score += 10, reasons.push('the entry appears in dsh plugin list (+10)')
      else reasons.push('the entry still does not appear in the list')

      const boot = await bootHeadless(profile)
      bootOk = HEADLESS_ACTIVATED_SIGNAL.test(boot.output || '')
      if (bootOk) score += 10, reasons.push('headless cold boot reached the application layer (MISSING_CREDENTIAL, no key) (+10)')
      else reasons.push('cold boot did not produce the alive signal')
    } finally {
      await cleanupProfile(profile, tmpDir)
    }
  } else {
    reasons.push('fixture untouched or dsh unavailable — live verification skipped')
  }

  if (reinstallAsFix) {
    score = Math.min(score, 40)
    reasons.push('reinstall-led diagnosis — capped at 40')
  }
  emit(score, reasons)
}

main().catch((error) => emit(0, [`judge error: ${error.message}`]))
