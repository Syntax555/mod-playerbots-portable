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

The core and all nine native server modules are built from maintained forks.
Work on each fork's configured default branch, listed below. Read its
`AGENTS.md` and README before editing; its guidance links back to the server's
product rules and relevant integration guides.
The central product rules take precedence over instructions inherited from the
original upstream projects.

| Native component | Fork | Default branch |
| --- | --- | --- |
| AzerothCore Playerbots core | [Syntax555/azerothcore-wotlk](https://github.com/Syntax555/azerothcore-wotlk) | `Playerbot` |
| Playerbots with Raid Clear | [Syntax555/wow-mod-playerbots](https://github.com/Syntax555/wow-mod-playerbots) | `evermore` |
| Individual Progression | [Syntax555/mod-individual-progression](https://github.com/Syntax555/mod-individual-progression) | `master` |
| Dungeon Clear | [Syntax555/mod-dungeon-clear](https://github.com/Syntax555/mod-dungeon-clear) | `master` |
| Quest Loot Party | [Syntax555/mod-quest-loot-party](https://github.com/Syntax555/mod-quest-loot-party) | `master` |
| World Buff Bots | [Syntax555/mod-world-buff-bots](https://github.com/Syntax555/mod-world-buff-bots) | `main` |
| LFG Progression | [Syntax555/wow-mod-lfg-progression](https://github.com/Syntax555/wow-mod-lfg-progression) | `main` |
| Era Events | [Syntax555/wow-mod-era-events](https://github.com/Syntax555/wow-mod-era-events) | `main` |
| MultiBot Bridge | [Syntax555/mod-multibot-bridge](https://github.com/Syntax555/mod-multibot-bridge) | `main` |
| Era Talents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents) | `main` |

Make core and module changes as commits in their forks, then pin the tested
commit in `versions.lock.json`; do not add source patches to this repository.
Keep changes focused and preserve upstream authorship and source licenses.
Native fork CI runs selected server fixtures against the proposed fork commit.
The complete native build and integration run here with the pinned core and all
modules. Install the resulting server build to try a native change.

The client addons also use forks, so an addon can be tried without a server
build:

| Client addon | Fork and default branch | Latest asset |
| --- | --- | --- |
| Era Talents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents), `main` | `EraTalents-addon-latest.zip` (addon only) |
| MultiBot Chatless | [Syntax555/MultiBot-Chatless](https://github.com/Syntax555/MultiBot-Chatless), `main` | `MultiBot-Chatless-latest.zip` |
| DragonUI | [Syntax555/DragonUI](https://github.com/Syntax555/DragonUI), `main` | `DragonUI-latest.zip` |
| Questie-335 | [Syntax555/Questie](https://github.com/Syntax555/Questie), `335` | `Questie-335-latest.zip` (installer) |
| Zygor Guides Viewer Remaster | [Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK), `main` | `Zygor-IP-latest.zip` (installer) |

Commit to the fork's configured default branch. Addon pushes check the addon
and replace its asset in the fork's Latest release. For the core, modules and
addons, the server manifest's `revision` is the exact fork commit to build.
`upstream` records the original project and the original revision imported
last; retain that provenance when pinning a local change. `forkChanges` names
the commit of each fixture-covered change. The fixtures revert and reapply
that commit's diff, so add each new
covered change there together with its fixture and keep the recorded commits
reachable. Never rewrite a commit the server pins.

For a source update, compare the original project's history with the recorded
`upstream.revision`, merge the chosen upstream commit into the fork's branch
and resolve conflicts there. Preserve earned-play guards, manual talent choices,
configuration, characters and databases. Remove local code only after its native
replacement passes the relevant fixtures. Update `upstream.revision` to the
imported original commit and `revision` to the tested fork commit, then prepare
the sources and run the affected integration checks. Keep MultiBot and MultiBot
Bridge compatible and install matching EraTalents client files when generated
data changes. See [dependency updates](docs/module-versions.md#updating-dependencies).

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
