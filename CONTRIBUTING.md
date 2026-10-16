# Contributing

## Reporting problems

Report problems through
[GitHub Issues](https://github.com/Syntax555/mod-playerbots-portable/issues).
Include the `revision` from the server's `portable-release.json`, the client
build, the affected activity, relevant configuration and a short reproduction.
Attach relevant excerpts from `logs/` with account passwords removed; copy the
folder before restarting the realm, because every server start overwrites its
logs.

## Changing the server

[AGENTS.md](AGENTS.md) sets the product rules and the checks every change must
pass, for people and coding agents alike. Progression changes keep normal XP,
inventory, gold and per-character eligibility. The [build guide](docs/building.md)
covers the Windows build and the local checks.

Core, module and addon changes are ordered patches listed in
[versions.lock.json](versions.lock.json). Change a patch through its work tree:

```bash
git submodule update --init --depth=1 azerothcore-wotlk mod-playerbots
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

Compile each changed C++ file against `.module-cache/prepared-core`, then run
the fixtures and the other checks the change touches, as the
[build guide](docs/building.md#integration-checks) lists them:

```bash
python3 cmake/tests/run_fixtures.py check
python3 cmake/tests/run_fixtures.py gameplay
```

New fixtures go into `GAMEPLAY` in `cmake/tests/run_fixtures.py`, or into the
release workflow when they need its build outputs.

## Documentation and releases

Documentation describes the current product. Keep the README focused on
downloads, setup, features and useful limits, and put configuration and
technical details in the linked guides. The server ZIP contains `README.md`,
`THIRD_PARTY_NOTICES.md` and `docs/` without `building.md`, so those files link
to `docs/building.md` and this guide by their GitHub URLs; the documentation
check in the gameplay fixtures enforces this.

Release notes use [.github/RELEASE_TEMPLATE.md](.github/RELEASE_TEMPLATE.md),
which accepts the fields `{repository_url}`, `{source_url}`, `{commit_url}` and
`{revision}`. Avoid conversational updates, implementation history and lists of
past versions.

Verified builds from `main` update the single **Latest** release. Pull requests
and pushes to `codex/**` branches produce build artifacts without publishing.
Keep stable asset names and retain the previous download until the replacement
packages have passed verification.
