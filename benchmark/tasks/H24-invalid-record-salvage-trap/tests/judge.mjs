// H24-invalid-record-salvage-trap grading.
//
// One current-version schema-invalid record in a disposable derived-data
// domain rejects the entire domain open. The judge verifies the salvage
// against the REAL published alpha.5 storage packages and the preloaded
// persisted records.
//
//   70 — behavioral, against the real runtime:
//        domain open resolves (20); healthy A+B intact with correct values
//        (15); the corrupt document was moved to a .bak (15); backup bytes
//        equal the sealed baseline bytes (10); damaged key absent before
//        rebuild (5); rebuilt key persists across close+reopen (5);
//   20 — migration correctness from the IMPORTED spec + schema probes:
//        scoped invalidRecords 'backup-and-skip' (10), schema preserving
//        records and rejecting invalid fields (5), domain name/version/layout
//        contract preserved (5);
//   10 — hygiene: required runtime dependencies retain their exact pins;
//   caps — spec fails to load → 30; version downgrade → 20; alpha.4 pin
//        → 20; catch-and-empty → 30; schema loosened → 40 (z.any) / 60
//        (field-level); manual backup → 50; policy
//        globalized → 70;
//    0 — fixture untouched, sealed files modified (the runtime's authorized
//        rename of the one corrupt document excepted), or the baseline
//        rewritten; checks run before and after candidate execution.
// The judge always exits 0; the last stdout line is the {score, max, reasons} JSON.
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { isDeepStrictEqual } from 'node:util'
import { assembleScore, schemaContractHolds, stripComments } from './judge-utils.mjs'
import { createIntegrityGuard } from './fixture-integrity.mjs'

function emit(score, reasons) {
  console.log(JSON.stringify({ score, max: 100, reasons }))
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  grade().catch((error) => emit(0, [`judge error: ${error.message}`]))
}

export async function grade(APP = '/app', baselineFile = '/opt/h24-verifier/baseline.sha') {
  const SPEC_FILE = join(APP, 'fixture', 'src', 'domain-spec.mjs')
  const DATA_ROOT = join(APP, 'fixture', 'data')
  const ENTRIES_DIR = join(DATA_ROOT, 'artifact_index', 'entries')
  const BROKEN_FILE = join(ENTRIES_DIR, 'broken.json')
  const CORDIS = join(APP, 'fixture', 'node_modules', '@deepseek-ai', 'cordis', 'lib', 'index.js')
  const STORAGE = join(APP, 'fixture', 'node_modules', '@deepseek-ai', 'dsh-storage', 'lib', 'index.js')
  const STORAGE_JSON = join(APP, 'fixture', 'node_modules', '@deepseek-ai', 'dsh-storage-json', 'lib', 'index.js')
  const STORAGE_DOMAIN = join(APP, 'fixture', 'node_modules', '@deepseek-ai', 'dsh-storage-domain', 'lib', 'index.js')
  const BAK_RE = /^broken\.json\.bak\.\d{12}$/
  const reasons = []
  if (!existsSync(SPEC_FILE)) { emit(0, ['fixture domain spec missing']); return }

  let integrity
  let initialBytes
  let expected
  try {
    integrity = createIntegrityGuard(APP, baselineFile)
    initialBytes = integrity.readBaseline('fixture/data/artifact_index/entries/broken.json')
    expected = Object.fromEntries(['A', 'B'].map((key) => [key,
      JSON.parse(integrity.readBaseline(`fixture/data/artifact_index/entries/${key}.json`)).record,
    ]))
  } catch (error) { emit(0, [error.message]); return }

  // The agent may already have run the prescribed reader app. Accept only a
  // byte-identical backup of the original corrupt record, not arbitrary data
  // changes. Freeze this allowance before executing candidate code; refresh it
  // only immediately after the real runtime's first open.
  function authorizeSalvage() {
    const baks = readdirSync(ENTRIES_DIR).filter((name) => BAK_RE.test(name))
    for (const name of baks) {
      if (!readFileSync(join(ENTRIES_DIR, name)).equals(initialBytes)) throw new Error(`sealed files modified: backup bytes differ (${name})`)
      integrity.allowFile(`fixture/data/artifact_index/entries/${name}`, initialBytes)
    }
    if (!existsSync(BROKEN_FILE)) {
      if (!baks.length) throw new Error('sealed files modified: corrupt record deleted without its backup')
      integrity.allowFile('fixture/data/artifact_index/entries/broken.json', null)
    }
  }
  function integrityHolds() {
    try { integrity.check(); return true }
    catch (error) { emit(0, [`integrity check failed: ${error.message}`]); return false }
  }
  try { authorizeSalvage() } catch (error) { emit(0, [error.message]); return }
  if (!integrityHolds()) return
  if (!integrity.changed) { emit(0, ['fixture untouched — no migration performed']); return }

  // Import the agent's spec module.
  let spec = null
  let specSource = ''
  let packageJson = ''
  const srcTexts = []
  try {
    specSource = readFileSync(SPEC_FILE, 'utf8')
    packageJson = integrity.packageJson
    for (const name of readdirSync(join(APP, 'fixture', 'src')).sort()) {
      if (/\.(mjs|js|cjs)$/.test(name)) srcTexts.push(readFileSync(join(APP, 'fixture', 'src', name), 'utf8'))
    }
  } catch (error) { emit(0, [`fixture files unreadable: ${error.message}`]); return }
  let policyOutsideSpec = false
  for (const text of srcTexts) {
    if (text !== specSource && /invalidRecords\s*:\s*['"]backup-and-skip['"]/.test(stripComments(text))) policyOutsideSpec = true
  }
  try {
    const mod = await import(pathToFileURL(SPEC_FILE).href)
    spec = mod.spec ?? null
  } catch (error) {
    reasons.push(`domain spec fails to load: ${String(error.message).slice(0, 160)}`)
  }
  if (!integrityHolds()) return
  const schemaHonest = schemaContractHolds(spec)
  if (!integrityHolds()) return

  // Behavioral checks against the real alpha.5 runtime.
  let behavioral = 0
  const observations = {
    openRejected: spec === null,
    brokenVisible: false,
    brokenFileAbsent: !existsSync(BROKEN_FILE),
    backupExists: false,
    catchPresent: false,
  }
  if (spec !== null) {
    try {
      const { Context } = await import(pathToFileURL(CORDIS).href)
      const { default: Storage } = await import(pathToFileURL(STORAGE).href)
      const { JsonStorageBackend } = await import(pathToFileURL(STORAGE_JSON).href)
      const { DomainFacility } = await import(pathToFileURL(STORAGE_DOMAIN).href)

      async function openDomain() {
        const ctx = new Context()
        await ctx.plugin(Storage)
        ctx.storage.backend.register('json', new JsonStorageBackend(DATA_ROOT))
        const facility = new DomainFacility(ctx, { backend: 'json' })
        const domain = await facility.open(spec)
        return { domain, table: domain.table('entries') }
      }

      const first = await openDomain()
      authorizeSalvage()
      if (!integrityHolds()) return
      observations.openRejected = false
      behavioral += 20
      reasons.push('+20 domain open resolves')
      const keys1 = [...first.table.keys()].sort()
      const a = first.table.get('A')
      const b = first.table.get('B')
      if (keys1.includes('A') && keys1.includes('B') && isDeepStrictEqual(a, expected.A) && isDeepStrictEqual(b, expected.B)) {
        behavioral += 15
        reasons.push('+15 healthy A+B intact with correct values')
      } else {
        reasons.push(`+0 healthy records not intact (got ${keys1.join(',') || 'none'})`)
      }
      // backup evidence (filesystem, before any rebuild write)
      const entries = readdirSync(ENTRIES_DIR)
      const baks = entries.filter((name) => BAK_RE.test(name))
      observations.brokenFileAbsent = !existsSync(BROKEN_FILE)
      observations.backupExists = baks.length > 0
      if (observations.brokenFileAbsent && observations.backupExists) {
        behavioral += 15
        reasons.push('+15 corrupt document moved to a backup file')
      } else {
        reasons.push(`+0 corrupt document not moved to a backup (broken absent=${observations.brokenFileAbsent}, backups=${baks.length})`)
      }
      const backupMatches = baks.some((name) => readFileSync(join(ENTRIES_DIR, name)).equals(initialBytes))
      if (backupMatches) {
        behavioral += 10
        reasons.push('+10 backup bytes equal the sealed baseline bytes')
      } else {
        reasons.push('+0 backup bytes do not match the sealed baseline')
      }
      if (first.table.get('broken') === undefined) {
        behavioral += 5
        reasons.push('+5 damaged key absent before rebuild')
      } else {
        observations.brokenVisible = true
        reasons.push('+0 damaged key still visible (schema loosened?)')
      }
      // rebuild + reopen
      if (!integrityHolds()) return
      const rebuiltRecord = { id: 'broken', sourceHash: 'abc', tokens: 3 }
      await first.table.put('broken', rebuiltRecord)
      const writtenBytes = readFileSync(BROKEN_FILE)
      const written = JSON.parse(writtenBytes)
      if (written.version === 5 && isDeepStrictEqual(written.record, rebuiltRecord)) {
        integrity.allowFile('fixture/data/artifact_index/entries/broken.json', writtenBytes)
      }
      if (!integrityHolds()) return
      await first.domain.close()
      if (!integrityHolds()) return
      const second = await openDomain()
      if (!integrityHolds()) return
      const rebuilt = second.table.get('broken')
      if (isDeepStrictEqual(rebuilt, rebuiltRecord) && isDeepStrictEqual(second.table.get('A'), expected.A) && isDeepStrictEqual(second.table.get('B'), expected.B)) {
        behavioral += 5
        reasons.push('+5 rebuilt key persists across reopen')
      } else {
        reasons.push('+0 rebuilt key does not persist across reopen')
      }
      await second.domain.close()
    } catch (error) {
      observations.openRejected = true
      reasons.push(`behavioral: domain open rejected — ${String(error.message).slice(0, 160)}`)
    }
  }
  if (!integrityHolds()) return

  const { score, reasons: sourceReasons } = assembleScore({
    behavioral,
    spec,
    specSource,
    packageJson,
    srcTexts,
    observations,
    policyOutsideSpec,
    schemaHonest,
  })
  if (!integrityHolds()) return
  reasons.push(...sourceReasons)
  emit(score, reasons)
}
