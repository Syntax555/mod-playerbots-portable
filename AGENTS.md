# Repository guidance

These rules apply to every change, by people and by coding agents. Read the
files you change and the code that calls them before editing.

## Agent skills

The shared skills in `.agents/skills/` apply to every repo chat and delegated
agent. For coding tasks, read `.agents/skills/ponytail/SKILL.md` and use its
`full` mode unless the user chooses another mode.

Select relevant Matt Pocock skills from the same directory autonomously and
read their `SKILL.md` before applying them. Preserve their invocation policy:
skills marked `disable-model-invocation: true` require the user to name them.
User instructions and the repository rules take precedence over skill advice.
Sources, licenses and update instructions are in
[the shared skill guide](.agents/skills/README.md).

## Product rules

- The server is an earned-progression realm. Under natural progression a bot
  may only do what an ordinary player can: walk real navigation-mesh routes,
  use flight paths and portals it discovered, open objects without a lock or
  with its own key, pay with its own gold and earn its own items, quests,
  attunements and era. Never add teleports, item or money grants, free
  resurrections, speed or position shortcuts, or hidden bypasses, and keep the
  existing refusals in place when refactoring.
- Real players, SelfBot characters and controlled altbots keep human rights:
  never treat them as random bots, recruit them automatically or spend their
  talent points.
- Content follows each character's own earned era (Individual Progression).
  An account, a party leader or a higher level never unlocks it for someone else.
- Preserve user configuration, characters and databases when changing
  installation, packaging, migration or updates. Managed defaults may change
  only where the user kept the previous managed value.

## Changing code

- Prefer existing AzerothCore, Playerbots and module functions, data and
  configuration over new logic. Check the pinned sources before writing a
  replacement. Do not call hooks with side effects to probe a decision.
- Core and module changes are ordered patches listed in `versions.lock.json`.
  Never edit a `.patch` file by hand. Use `python3 scripts/patchwork.py open
  patches/<name>.patch`, edit the printed work tree, then run
  `python3 scripts/patchwork.py save <work tree>`; it checks the whole chain.
  Keep patches functional: no reformatting, include reordering or unrelated
  hunks.
- Do not bump a pinned revision blindly. Compare the upstream history, check
  config key renames and removed APIs, refresh every affected patch and keep
  the shipped profile keys effective.
- Match the surrounding style, naming and comment density. Comments explain
  why, not what changed.
- The launcher must read configuration exactly as the servers do, and write
  files atomically. Windows behaviour (file locks, running executables,
  process identity) needs explicit handling and tests.

## Verifying a change

Run what applies before every commit; all of it must pass:

- Go launcher: `gofmt -l cmd`, `go vet ./...`, `GOOS=windows go vet ./...`,
  `go test ./...`, `GOOS=windows go test -c -o /dev/null ./cmd/startup` and
  staticcheck for both systems, as in `.github/workflows/checks.yml`.
- Patches: `cmake -P cmake/PrepareModules.cmake`, then compile every changed
  C++ file against the prepared sources, then
  `python3 cmake/tests/run_fixtures.py check` and
  `python3 cmake/tests/run_fixtures.py gameplay`.
- Packaging and release: `python3 -m unittest discover -s scripts/tests -p 'test_*.py'`,
  the PowerShell checks in `cmake/tests`, `ruff check cmake scripts` and
  actionlint for workflow edits.

State honestly what could not be run (for example the Windows build) and
leave it to CI rather than claiming it works.

## Tests

- Every behaviour fix and every earned-play gate gets a fixture case and a
  mutation check that fails when the gate is removed.
- Fixtures compile the real production sources. Test doubles must return what
  the real producer returns; assert the native contract a double relies on, so
  a test cannot pass against data production never provides.
- New fixtures must be wired into `cmake/tests/run_fixtures.py`.

## Documentation

- Keep README and release notes concise, professional and focused on the
  current product: installation, supported behaviour and relevant limits.
- Describe what users can do. Avoid conversation history, "we replaced",
  "now fixed", dated audit addenda and prior release narratives.
- Derive tables and claims from the code and data, and update every
  statement a change makes inaccurate in the same commit. Do not advertise
  behaviour that has not been verified.
- Put detailed settings, source revisions and adaptations in the linked
  guides and dependency manifest. Preserve accurate upgrade steps and material
  gameplay limitations. Track open work and outstanding validation in
  `docs/todo.md`; update affected entries as tasks are completed.

## Releases and licensing

- Use one rolling `latest` tag and **Latest** release with stable asset names.
  Publish only verified server and matching client packages; keep the current
  downloads until the replacement assets are verified.
- The launcher and build tools are MIT-licensed. Upstream files retain their
  own terms; do not apply MIT to the complete distribution or invent a license
  for a dependency.

## Commits

- One logical change per commit with an imperative summary under about 72
  characters and a short body explaining why.
- Commit and push only validated work, directly to `main` unless asked
  otherwise. Never leave a half-regenerated patch chain or failing fixtures.
