# Updating the portable server

On normal startup, `startup.exe` checks the rolling
[Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
before starting the database and servers. It reads a small update manifest over
HTTPS, compares managed files and downloads only changed files from the server
ZIP. Each downloaded file must match its SHA-256 hash before installation.

The launcher stages the update, replaces managed server files and restarts itself.
SQL migrations run during normal database/server startup, without resetting the
existing databases. New configuration defaults are merged automatically.

## What is preserved

- Accounts, characters, inventories, money and existing databases.
- Active configurations, database credentials, configured paths and realm phase.
- Downloaded DBC/maps/vmaps/mmaps, logs and additional user files.

Bundled server binaries, libraries, templates, SQL and release notices follow
the release. Keep regular database and configuration backups, including before
an established realm receives new SQL migrations.

Configuration updates compare the active value with the previous managed
default. A new default replaces it only if it still matches that previous value;
custom values remain intact. Missing managed settings are added, and changed
files receive adjacent `.backup.*` copies. Without a saved baseline, the first
startup preserves all existing values, adds only missing managed settings and
records the bundled defaults for future comparisons. See the
[configuration reference](vanilla-config-audit.md).

## Manual installation

To install or replace the server files manually:

1. Choose a writable server folder. For an existing realm, back up the databases
   and `configs/`, then stop the launcher, database and servers completely.
2. Download the latest
   [server ZIP](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/mod-playerbots-portable-latest.zip)
   and verify it against
   [SHA256SUMS.txt](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/SHA256SUMS.txt).
3. Extract the ZIP into the server folder, replacing bundled files. Preserve an
   existing realm's configurations, database data directories and downloaded
   server data.
4. Run `startup.exe` normally. The launcher manages setup and automatic server updates.

The selected expansion ceiling is preserved. To deliberately remove a shared
Vanilla/TBC ceiling, use `startup.exe --set-expansion individual` with initialized
configs and stopped servers. See [realm updates](changing-expansions.md#updating-an-existing-realm).

## Client packages

The server updater does not install client addons or modify a WoW client. Each
player must install the matching
[EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip),
including both the addon and `Data/patch-V.mpq`, with WoW fully closed. The
optional [MultiBot addon](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/MultiBot-Chatless-latest.zip)
is also a separate manual installation. See [client installation](era-talents.md#install-the-matching-client-files).

## Offline startup and failed updates

To skip the remote server-update check for one launch, run from the server folder:

```powershell
.\startup.exe --no-update
```

Normal configuration handling and database migrations still run. Offline checks,
unsupported downloads and failed hash verification report a warning and leave
the current version intact. Incomplete file installation is rolled back before
starting services; if rollback fails, startup stops to avoid running mixed files.
Keep `.portable-update/` intact while an interrupted update is being recovered.
