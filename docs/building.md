# Building from source

The [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest) provides a ready-to-run Windows x64 server. A source build is useful for development or custom configurations.

## Windows requirements

- Windows 10/11 x64.
- Visual Studio 2022 with the Desktop development with C++ workload.
- CMake 3.22 or newer, Go 1.26.6 or newer, PowerShell 7 and Git.
- Boost 1.84 or newer, MySQL Server 8.0 x64 and OpenSSL 3 x64.

The Windows resource compiler requires CMake 3.22 or newer with the Visual Studio generator. Use x64 dependencies throughout.

## Build the server bundle

Clone the repository with its submodules, then configure with the paths to your dependencies:

```powershell
git clone --recurse-submodules https://github.com/Syntax555/mod-playerbots-portable.git
cd mod-playerbots-portable
cmake -B build -S . `
  -G "Visual Studio 17 2022" -A x64 `
  -DPACKAGE_VERSION="dev" `
  -DMYSQL_ROOT_DIR="C:/tools/mysql/current" `
  -DOPENSSL_ROOT_DIR="C:/tools/openssl/current/x64" `
  -DBOOST_ROOT_DIR="C:/local/boost_1_84_0"
$env:CMAKE_BUILD_PARALLEL_LEVEL = '2'
cmake --build build --config Release --parallel 2
pwsh -File scripts/CopyWindowsRuntime.ps1 -DistDir dist
cmake --build build --config Release --target package_zip
cmake -DPACKAGE_VERSION="dev" -P cmake/PackageClientAddons.cmake
```

Run each command only after the previous command succeeds. `CopyWindowsRuntime.ps1` bundles the Visual C++ runtime needed by the server and portable MySQL.

Outputs:

- `output/mod-playerbots-portable-dev.zip`: portable server bundle.
- `output/MultiBot-Chatless-dev.zip`: optional client interface.
- `output/EraTalents-dev.zip`: historical-talents addon only.

The complete `EraTalents-client-dev.zip` also requires the merged client MPQ. It is built separately on Linux; see [building the client package](era-talents.md#building-the-client-package). Use a client package built from the same pinned sources as your server.

## Build resources

The default MSVC configuration uses two compiler processes per project. `CMAKE_BUILD_PARALLEL_LEVEL` also limits the nested server build to two parallel projects, reducing peak memory use.

On a machine with more memory, adjust that environment variable and set `-DPORTABLE_MSVC_COMPILE_JOBS=<count>` when configuring. Increasing both limits can multiply the number of active compiler processes.

To generate the native server projects before starting the full C++ build:

```powershell
cmake --build build --target azerothcore-configure --config Release
```

This generates the native server projects. The release workflow uses their `PrepareForBuild;ResourceCompile` targets to check both `authserver` and `worldserver` resource commands before compiling C++.

## Reproducible dependencies

[versions.lock.json](../versions.lock.json) pins the core, modules, addons and client-build dependencies. CMake applies the ordered [patches](../patches) to managed source copies; the upstream submodules remain at their pinned revisions.

Subsequent configurations reuse the prepared module cache. A changed revision or patch rebuilds its managed copy, while unmarked directories are not overwritten. Prepare these copies independently with:

```powershell
cmake -P cmake/PrepareModules.cmake
```

The server bundle includes the source manifest, patches and applicable license files or notices. Record the manifest when reporting a problem or sharing a custom build; the rolling download name alone does not identify its sources.

## Automated builds

The [release workflow](../.github/workflows/release.yml) validates the launcher and progression adaptations, builds the Windows server and client packages, and verifies the assembled archives. [Actions](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml) records the checks and source commit for each build.

The public [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest) contains the matching verified packages. Build artifacts are also available from eligible successful Actions runs.
