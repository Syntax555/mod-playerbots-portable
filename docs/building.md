# Building from source

The
[Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
provides a ready-to-run Windows x64 server. A source build is useful for
development or custom configurations.

## Windows requirements

- Windows 10/11 x64.
- Visual Studio 2022 with the Desktop development with C++ workload.
- CMake 3.22 or newer, Go 1.26.6 or newer, Python 3.12 or newer, PowerShell 7 and Git.
- Boost 1.84 or newer, MySQL Server 8.0 x64 and OpenSSL 3 x64.

The Windows resource compiler requires CMake 3.22 or newer with the Visual
Studio generator. Use x64 dependencies throughout.

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
  -DBOOST_ROOT_DIR="C:/local/boost_1_84_0"
$env:CMAKE_BUILD_PARALLEL_LEVEL = '2'
$env:CL_MPCount = '2'
cmake --build build --config Release --parallel 2
pwsh -File scripts/CopyWindowsRuntime.ps1 -DistDir dist
pwsh -File scripts/CopyDependencyLicenses.ps1 -DistDir dist `
  -MySQLRootDir "C:/tools/mysql/current" `
  -OpenSSLRootDir "C:/tools/openssl/current/x64" `
  -BoostRootDir "C:/local/boost_1_84_0"
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
- `output/MultiBot-Chatless-dev.zip`: optional client interface.

The complete `EraTalents-client-dev.zip` also requires the merged client MPQ. It
is built separately on Linux; see
[building the client package](era-talents.md#building-the-client-package). Use a
client package built from the same pinned sources as your server.

The server ZIP contains runtime files, configuration templates, required SQL,
user guides and license notices. Addons are separate downloads; recommended
configuration profiles are embedded in the launcher. Client exports omit
development files while retaining their runtime resources.

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
objects are kept. The release workflow adds a 32 GB page file before compiling,
keeps compiler diagnostics as plain text (`UseStructuredOutput=false`) and
retries a memory failure with one parallel project, and with one compiler
worker when the modules project failed. A final step reports peak commit and
page-file use.

To generate the native server projects before starting the full C++ build:

```powershell
cmake --build build --target azerothcore-configure --config Release
```

The release workflow uses their `PrepareForBuild;ResourceCompile` targets to
check both `authserver` and `worldserver` resource commands before compiling
C++.

## Reproducible dependencies

[versions.lock.json](../versions.lock.json) pins the core, modules, addons and
client-build dependencies. CMake fetches the locked core and module commits into
`.module-cache/` and applies the ordered [patches](../patches) to managed source
copies. No submodule initialization is required.

Subsequent configurations reuse the prepared module cache. A changed revision or
patch rebuilds its managed copy, while unmarked directories are not overwritten.
Prepare these copies independently with:

```powershell
cmake -P cmake/PrepareModules.cmake
```

Existing checkouts of `azerothcore-wotlk/` and `mod-playerbots/` from older
versions are ignored and left untouched, including local edits. Patch work trees
use the locked commits in `.module-cache/`.

The server bundle includes the source manifest, patches and applicable license
files or notices. Record the manifest when reporting a problem or sharing a
custom build; the rolling download name alone does not identify its sources.

## Integration checks

The checks run on Linux and require Go, Python with PyYAML 6.0.3, GCC with
AddressSanitizer and UndefinedBehaviorSanitizer support, PowerShell 7, Lua 5.1
and Ruff 0.16.8. The gameplay fixtures execute selected native handlers with
controlled adapters; a complete server build and live realm tests remain
necessary for platform and encounter validation. These commands repeat the
release workflow's launcher job:

```bash
go test ./...
go vet ./...
GOOS=windows GOARCH=amd64 go test -c -o /dev/null ./cmd/startup
GOOS=windows GOARCH=amd64 go vet ./...
go install honnef.co/go/tools/cmd/staticcheck@v0.8.1
staticcheck ./...
GOOS=windows GOARCH=amd64 staticcheck ./...
python3 cmake/tests/run_fixtures.py check
ruff check cmake scripts
pwsh cmake/tests/TestPortableZip.ps1
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
pwsh cmake/tests/TestDependencyLicenses.ps1
python3 cmake/tests/TestEraClientPackaging.py
python3 cmake/tests/TestClientAddonPatches.py
python3 cmake/tests/TestClientLocales.py
cmake -P cmake/PrepareModules.cmake
python3 cmake/tests/run_fixtures.py gameplay
```

`python3 cmake/tests/run_fixtures.py check` fails when a fixture in
`cmake/tests` does not run in CI. The gameplay run also checks the
documentation's links, anchors and stated versions. The MultiBot Lua and
packaged-client fixtures run in the client job, as the release workflow names
them. Fixtures refuse to run under `python -O`, which would skip their assert
checks.

The release workflow also verifies historical spell mechanics in the generated
MPQ, client locales, dependency notices, package inventories and update
recovery. Historical class source revisions are recorded separately from the
module pins in `versions.lock.json`.

## Automated builds

The [release workflow](../.github/workflows/release.yml) validates the launcher
and progression adaptations, builds the Windows server and client packages, and
verifies the assembled archives.
[Actions](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml)
records the checks and source commit for each build. It runs for pushes to
`main` and `codex/**` branches, pull requests and manual runs; commits that
change only documentation do not start it, so packaged guides and release-note
links follow with the next build of `main` or a manual run.

The [publication workflow](../.github/workflows/publish-latest.yml) runs
[publish_latest.py](../scripts/publish_latest.py) after a successful push or
manual build of `main`.

The public
[Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
contains the matching verified packages. Build artifacts are also available from
eligible successful Actions runs.

Builds of `main` run one at a time: a running build always finishes, and a newer
push replaces any waiting build so the newest commit builds next. Each
publication selects the most recently created eligible successful `main` build
with available server and client artifacts, so re-running an older build cannot
replace a newer build waiting for publication. The selected build is published
when its commit is still part of `main` and is not older than the current Latest.

Publication generates `UPDATE_MANIFEST.json` from the verified final server ZIP,
recording each file's size and SHA-256 hash. Latest contains three ZIPs, this
update manifest and `SHA256SUMS.txt`, which covers all four payloads. GitHub
refuses the Actions token tag and release changes at commits whose workflow
files differ from `main`, so a build whose workflow files no longer match `main`
is skipped and the newer build publishes. Publication publishes and verifies the
replacement under its staging tag while the previous release still serves tag
`latest`, then moves `latest` to the build commit, deletes the previous release
and moves the replacement to `latest`; it creates no additional version tags. If
a run stops between the last two steps, `releases/latest/download` serves the
replacement, but the launcher's update check fails until the job is re-run or
the next build publishes. Drafts and unused temporary tags of failed runs are
removed when the next publication starts, and a release left under a temporary
tag is removed by the next successful publication.

The executables are currently unsigned. Windows Smart App Control may block
them; package checksums and automated build checks do not replace a trusted
Windows code signature.
