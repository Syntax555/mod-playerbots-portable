# Building from source

The
[Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
provides a ready-to-run Windows x64 server. A source build is useful for
development or custom configurations.

## Windows requirements

- Windows 10/11 x64.
- Visual Studio 2022 with the Desktop development with C++ workload.
- CMake 3.22 or newer, Go 1.27.3 or newer, Python 3.12 or newer, PowerShell 7 and Git.
- Boost 1.92, MySQL Server 8.0 x64 and OpenSSL 3 x64. Use the release workflow's
  [dependency versions](module-versions.md#bundled-runtime) for
  a build with the shipped runtime.

Use the Visual Studio generator and x64 dependencies throughout.

## Build the server bundle

Clone the repository, then configure with the paths to your
dependencies:

```powershell
git clone https://github.com/Syntax555/mod-playerbots-portable.git
cd mod-playerbots-portable
cmake -B build -S . `
  -G "Visual Studio 17 2022" -A x64 `
  -DPACKAGE_VERSION="dev" `
  -DMYSQL_ROOT_DIR="C:/tools/mysql/current" `
  -DOPENSSL_ROOT_DIR="C:/tools/openssl/current/x64" `
  -DBOOST_ROOT_DIR="C:/local/boost_1_92_0"
$env:CMAKE_BUILD_PARALLEL_LEVEL = '2'
$env:CL_MPCount = '2'
$env:UseStructuredOutput = 'false'
cmake --build build --config Release --parallel 2
pwsh -File scripts/CopyWindowsRuntime.ps1 -DistDir dist
pwsh -File scripts/CopyDependencyLicenses.ps1 -DistDir dist `
  -MySQLRootDir "C:/tools/mysql/current" `
  -OpenSSLRootDir "C:/tools/openssl/current/x64" `
  -BoostRootDir "C:/local/boost_1_92_0"
cmake --build build --config Release --target package_zip
cmake -DPACKAGE_VERSION="dev" -P cmake/PackageClientAddons.cmake
```

Run each command only after the previous command succeeds.
`CopyWindowsRuntime.ps1` bundles the Visual C++ runtime needed by the server and
portable MySQL. `CopyDependencyLicenses.ps1` preserves dependency notices; pass
the same dependency paths used to configure the build. If the OpenSSL package
lacks its license file, also pass `-OpenSSLVersion <version>` to add the
upstream license of that release.

Outputs:

- `output/mod-playerbots-portable-dev.zip`: portable server bundle.
- `output/MultiBot-Chatless-dev.zip`: the pinned MultiBot fork commit as an
  addon ZIP, for testing it with a local server build.

Published addon packages and the Questie and Zygor installers come from the
[addon forks](addons.md#addon-forks).

The complete `EraTalents-client-dev.zip` also requires the merged client MPQ. It
is built separately on Linux; see
[building the client package](era-talents.md#building-the-client-package). Use a
client package built from the same pinned sources as your server.

The server ZIP contains runtime files, configuration templates, required SQL,
user guides and license notices. Addons are separate downloads from their
[forks](addons.md#addon-forks); recommended configuration profiles are
embedded in the launcher. Client exports omit development files while
retaining their runtime resources.

`portable-release.json` records the source commit and package version. The
automatic updater applies only to `latest` packages; a `dev` build keeps its
custom binaries. See [updating](updating.md) for configuration merging and data
preservation.

## Build resources

The commands above and the release workflow set `CL_MPCount=2`, so MSBuild
limits each project's compiler workers to two. `CMAKE_BUILD_PARALLEL_LEVEL`
also limits the nested server build to two parallel projects, reducing peak
memory use.

On a machine with more memory, adjust `CL_MPCount` and
`CMAKE_BUILD_PARALLEL_LEVEL` before building. Increasing both limits can
multiply the number of active compiler processes.

Windows compiles only within RAM plus page files. If the build stops with
`fatal error C1060: compiler is out of heap space`, enlarge the page file or
lower `CL_MPCount` to `1`, then run the same build command again; compiled
objects are kept. Keep `UseStructuredOutput=false` to avoid MSBuild's background
structured-diagnostic reader exhausting memory. The release workflow prepares
extra page-file capacity and retries compiler memory failures with less
parallelism.

To generate the native server projects before starting the full C++ build:

```powershell
cmake --build build --target azerothcore-configure --config Release
```

The release workflow checks both servers' Windows resources before the C++
compile. Passing these checks does not establish that the full build passes.

## Reproducible dependencies

[versions.lock.json](../versions.lock.json) pins the core, modules, addons and
client-build dependencies. CMake fetches the locked core and module commits into
`.module-cache/`. The core and all native modules are exported from their
pinned fork commits. No submodule initialization is required.

Subsequent configurations reuse the prepared module cache. A changed revision
rebuilds its managed copy, while unmarked directories are not overwritten.
Prepare these copies independently with:

```powershell
cmake -P cmake/PrepareModules.cmake
```

Existing checkouts of `azerothcore-wotlk/` and `mod-playerbots/` from older
versions are ignored and left untouched, including local edits.

The server bundle includes the source manifest and applicable license
files or notices. Record the manifest when reporting a problem or sharing a
custom build; the rolling download name alone does not identify its sources.

## Integration checks

The checks run on Linux and require Go, Python with PyYAML 6.0.3, GCC with
AddressSanitizer and UndefinedBehaviorSanitizer support, PowerShell 7, Lua 5.1,
Ruff 0.17.1 and actionlint 1.7.11. The gameplay fixtures execute selected native
handlers with controlled adapters; a complete server build and live realm tests
remain necessary for platform and encounter validation.

Before committing, select local checks from the changed files and their affected
callers, configuration and integrations. Run the relevant fixtures directly,
rather than the complete suite or unrelated checks. For fork and dependency
updates, prepare the sources with `cmake -P cmake/PrepareModules.cmake` and compile
each changed C++ file against `.module-cache/prepared-core` before its fixtures.
For example, a combat-profile change uses
`python3 cmake/tests/TestCombatProfiles.py`; a documentation-only change uses
`python3 cmake/tests/TestDocumentation.py`.

| Changed area | Targeted local checks |
| --- | --- |
| Go launcher | Format changed files; run tests, vet and staticcheck for affected packages, including Windows checks where affected. |
| Core and module fork pins | Inspect the actual source diff; compile changed C++ files against the prepared sources and run the relevant native and integration fixtures. A documentation-only fork change needs documentation checks. |
| Addon forks | Check changed Lua files and affected addon behavior, then run the relevant server integration fixtures against the new pin. |
| Packaging and release | Run affected Python test modules and PowerShell fixtures, Ruff for changed Python files and actionlint for workflow changes. |
| Documentation | Run `python3 cmake/tests/TestDocumentation.py` for links, anchors and stated versions. |
| Fixture or CI wiring | Run `python3 cmake/tests/run_fixtures.py check`. |

GitHub Actions runs the complete checks separately on code pushes and before a
manual build. Use ordinary Python execution: fixtures refuse `python -O`, which
would skip their assertions. The checks include launcher behavior on Windows,
native gameplay fixtures, generated MPQ mechanics and locales, addon integration,
package inventories, dependency notices and update recovery.

## Client cache changes

When changing client-cached server query data, such as quest or item templates,
ship a new world SQL migration assigning a fresh, stable `version.cache_id`.
Keep previous migrations so established realms receive the new one; the SQL
updater's filename/hash tracking alone does not refresh client caches. Preserve
explicit `ClientCacheVersion` overrides and higher administrator-managed database
versions. See [runtime behavior](updating.md#server-data-and-the-client-cache).

Run the affected data fixtures and `python3 cmake/tests/TestClientCacheVersion.py`
against the prepared sources. On a backed-up test realm, compare the database's
`SELECT cache_id FROM version;` and the worldserver startup log before and after
the migration, then reconnect the client. An unchanged restart must retain the
same ID and skip the migration. Changes confined to AI, loot, spawns or rates do
not require a client cache bump. DBC/MPQ or addon changes need matching client
files installed separately.

## Automated builds

The [checks workflow](../.github/workflows/checks.yml) validates the launcher,
progression adaptations and packaging for pushes to `main` and pull requests;
feature branches are checked through their pull requests. Commits that change
only documentation or agent instructions skip the checks, and the documentation
check runs with the next checks or build.

The [release workflow](../.github/workflows/release.yml) builds the Windows
server and client packages only when started manually: open
[Build portable ZIP](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml),
choose **Run workflow** and select the branch. It runs the complete checks
first, compiles only after all of them pass and verifies the assembled archives.
Actions records the checks and source commit for each build. A manual build of
another branch produces build artifacts without publishing. Packaged guides
update with the next manual build of `main`.

The [publication workflow](../.github/workflows/publish-latest.yml) selects a
successful manual build of `main` only after all checks, builds and archive
verifications pass. A failing precheck stops the build before compilation. The
public [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
contains matching verified packages; successful runs also retain build artifacts.

Manual builds of a branch run one at a time: a running build always finishes,
and a newer request replaces any waiting build so the newest commit builds
next. Each publication selects the most recently created eligible successful
`main` build with matching workflow files and available server and client
artifacts, so re-running an older build cannot replace a newer build waiting
for publication.
The selected build is published when its commit is still part of `main` and is
not older than the current Latest.

Publication generates `UPDATE_MANIFEST.json` with each managed server file's
size and SHA-256 hash, plus `SHA256SUMS.txt` for the release payloads. It uploads
and verifies the replacement before moving the rolling `latest` tag and release;
previous downloads remain available until then. If publication stops during the
final tag/release handoff, rerun **Publish Latest** or publish the next verified
build. The launcher starts the installed release when the remote update is
temporarily unavailable. Publication selection and recovery are implemented in
[publish_latest.py](../scripts/publish_latest.py).

The executables are currently unsigned. Windows Smart App Control may block
them; package checksums and automated build checks do not replace a trusted
Windows code signature.
