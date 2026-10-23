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

Core, module and addon changes are ordered patches listed in
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

Compile each changed C++ file against `.module-cache/prepared-core`, then run
the fixtures and the other checks the change touches, as the
[build guide](docs/building.md#integration-checks) lists them:

```bash
python3 cmake/tests/run_fixtures.py check
python3 cmake/tests/run_fixtures.py gameplay
```

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
