# Contributing

## Reporting problems

Report problems through
[GitHub Issues](https://github.com/Syntax555/mod-playerbots-portable/issues).
Include the `revision` from the server's `portable-release.json`, the client
build, the affected activity, relevant configuration and a short reproduction.
Attach relevant excerpts from `logs/` with account passwords removed; copy the
folder before restarting the realm, because every server start overwrites its
logs.

For quest availability or historical class-quest reports, follow the
[quest diagnostics](docs/quest-diagnostics.md) and include the affected character's
complete status and condition output.

## Changing the server

[AGENTS.md](AGENTS.md) sets the product rules and the checks every change must
pass, for people and coding agents alike. Progression changes keep normal XP,
inventory, gold and per-character eligibility. The [build guide](docs/building.md)
covers the Windows build and the local checks.

Core and module changes are ordered patches listed in
[versions.lock.json](versions.lock.json). Change a patch through its work tree:

```bash
cmake -P cmake/PrepareModules.cmake
python3 scripts/patchwork.py open patches/<name>.patch
# edit the sources in the printed work tree, then:
python3 scripts/patchwork.py save <work tree>
cmake -P cmake/PrepareModules.cmake
```

`open` extracts the pinned upstream revision, commits the preceding patches of
the chain as tag `base` and applies the target patch. A new patch is listed at
its position in `versions.lock.json` first; `open` then starts it empty. `save`
regenerates the patch from the work tree and checks that the whole chain still
applies to the pinned revision; if a later patch of the chain stops applying,
open and save that one too. Delete the work trees under
`.module-cache/patchwork/` afterwards.

Era Talents and the MultiBot, DragonUI, Questie and Zygor addons are built from
forks instead of patches, so an addon can be changed and tried without a server
build:

| Component | Fork and branch | Latest asset |
| --- | --- | --- |
| Era Talents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents), `main` | `EraTalents-addon-latest.zip` (addon only) |
| MultiBot Chatless | [Syntax555/MultiBot-Chatless](https://github.com/Syntax555/MultiBot-Chatless), `main` | `MultiBot-Chatless-latest.zip` |
| DragonUI | [Syntax555/DragonUI](https://github.com/Syntax555/DragonUI), `main` | `DragonUI-latest.zip` |
| Questie-335 | [Syntax555/Questie](https://github.com/Syntax555/Questie), `335` | `Questie-335-latest.zip` (installer) |
| Zygor Guides Viewer Remaster | [Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK), `main` | `Zygor-IP-latest.zip` (installer) |

Commit to the fork's branch; each push checks the addon and replaces the asset
in the fork's Latest release. To take a fork commit into the server, set the
component's `revision` in `versions.lock.json` to it. `upstream` records the
original project and the revision merged last. `forkChanges` names the commit
of each fixture-covered change; the fixtures revert and reapply that commit's
diff, so add a new change there together with its fixture, and update a commit
that is amended or replaced. Then prepare the sources and run the fixtures as
below.

Before committing, run targeted local checks for the changed files and their
affected callers, configuration and integrations, as the
[build guide](docs/building.md#integration-checks) describes. Compile each changed
C++ file against `.module-cache/prepared-core` and run only the relevant
`cmake/tests/Test*.py` fixtures directly. Run
`python3 cmake/tests/run_fixtures.py check` when fixture or CI wiring changes.
The complete suite runs separately in GitHub Actions on code pushes and before
manual builds; do not repeat the full suite or unrelated checks locally.

New fixtures go into `GAMEPLAY` in `cmake/tests/run_fixtures.py`, or into the
checks workflow when they need its build outputs.

## Documentation and releases

Documentation describes the current product. Keep the README focused on
downloads, setup, features and useful limits, and put configuration and
technical details in the linked guides. The server ZIP contains `README.md`,
`THIRD_PARTY_NOTICES.md` and `docs/` without `building.md` and the upstream
proposals in `docs/upstream/`, so those files link to them and this guide by
their GitHub URLs; the documentation check in the gameplay fixtures enforces
this.

Release notes use [.github/RELEASE_TEMPLATE.md](.github/RELEASE_TEMPLATE.md),
which accepts the fields `{repository_url}`, `{source_url}`, `{commit_url}` and
`{revision}`. Avoid conversational updates, implementation history and lists of
past versions.

Pushes to `main` and pull requests run the checks without building packages.
Packages are built on request with **Build portable ZIP > Run workflow** in
Actions. A verified manual build of `main` updates the single **Latest**
release; a manual build of another branch produces build artifacts without
publishing.
Keep stable asset names and retain the previous download until the replacement
packages have passed verification.
