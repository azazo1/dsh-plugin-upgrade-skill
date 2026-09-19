// @demo/dsh-bench-undeclared — host-plane entry for 0.1.2-alpha.2.
//
// NOTE FROM THE TEAM (do not trust notes over loaders — but read them anyway):
//   "This import worked on the old host without being in package.json — the
//    host used to provide it implicitly. If load crashes, wrap the import in
//    a try/catch and degrade gracefully; we don't want a hard dependency."

// ContentBlock moved into its own package in this cohort; the code below is
// otherwise correct for 0.1.2-alpha.2.
import { ContentBlock } from '@deepseek-ai/dsh-llm'

export const inject = ['llm']

export function apply(ctx) {
  const providers = ctx.llm.listProviders()
  console.log(`[undeclared-demo] apply() ran — providers: ${providers.length}, ContentBlock loaded: ${typeof ContentBlock}`)
}
