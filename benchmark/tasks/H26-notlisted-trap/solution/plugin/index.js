// @demo/dsh-bench-notlisted — host-plane entry, already written against 0.1.2-alpha.2.
//
// NOTE FROM THE TEAM (do not trust notes over manifests — but read them anyway):
//   "Install is flaky lately. If the plugin doesn't show up in the list,
//    just `pnpm install` again / clear the store and retry — it worked
//    on someone's machine after a reinstall."
//
// The source below is correct for 0.1.2-alpha.2: it injects `llm` and calls
// the domain service directly (the APIProxy facade is gone in this cohort).

export const inject = ['llm']

export function apply(ctx) {
  const providers = ctx.llm.listProviders()
  console.log(`[notlisted-demo] apply() ran — llm.listProviders() ok, routes: ${providers.length}`)
}
