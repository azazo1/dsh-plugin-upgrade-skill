# Source-derived factual supplement

This supplement restates facts in the same pinned entry document. It adds no task
answers or task-specific instructions. It is supplied identically to C and D.

- Source repository identity (owner/repository or URL) and registry package identity
  (scope/package) are separate coordinates; one does not determine the other.
- Package manifests and lockfiles describe packages and dependencies.
  `dsh-plugin.json`, when adopted, is the community-standard manifest.
  `cordis.patch.yml`, `agent.cordis.yml`, and historical `cordis.yml` describe
  profile composition. Resolved configuration is the runtime composition result.
- Successful dependency installation alone does not establish plugin enablement:
  profile composition resolution and runtime entry activation are distinct states.
- A plugin's release version and the DSH host dependency corridor are distinct
  version coordinates. The packed artifact has its own plugin version in its
  filename and manifest; that version is not automatically the host version.

The pinned entry additionally describes the following global-install failure
scenario. These are source claims about that scenario, not independently verified
universal behavior of every operating system or package manager:

- A DSH session executes in its host process. Replacing that host's global package
  tree during the session can interrupt the executing host and leave package
  content without regenerated command shims.
- A running host can hold native-module file locks, associated with EBUSY in the
  described install failure. Refreshing a browser does not stop the host process.
- A bare npm package install resolves the `latest` dist-tag; it does not necessarily
  select the newer release line intended by the user. A version-pinned install
  identifies the intended release explicitly.
- In the described interrupted-install case, recovery is a version-pinned formal
  installation from an external shell. Manually copying package directories or
  writing command shims is not the recovery method specified by the source.
