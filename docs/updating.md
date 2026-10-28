# Running and updating the server

On normal startup, `startup.exe` checks the rolling
[Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
before starting the database and servers. It reads a small update manifest over
HTTPS, compares managed files and downloads only changed files from the server
ZIP. Each downloaded file must match its SHA-256 hash before installation.

The launcher stages the update, replaces managed server files and restarts itself.
SQL migrations run during normal database/server startup, and managed
configuration defaults merge where the previous default is still in use.
Keep a stopped-realm backup before updating an established realm: file rollback
does not undo SQL migrations applied after startup.

## Progress, restarts and shutdown

The console reports file checks, download, verification and installation, with
progress counters or activity messages while work continues.

While the realm runs, the launcher restarts MySQL, authserver or worldserver two
seconds after it exits or crashes. This includes the worldserver console's
`server shutdown` command, so that command restarts the worldserver.

Press **Ctrl+C** in the launcher console to stop the realm. The launcher asks its
authserver and worldserver to stop, waits for them to finish and then shuts down
its database. Processes that exceed the shutdown timeout are terminated; allow
the ordinary shutdown to finish so character saves can complete. During the
short update replacement step, let the helper finish or recover the transaction
before moving or changing files.

## Where your data lives

The launcher keeps active configurations in `configs/`, databases in
`mysql/data/`, logs in `logs/` and the downloaded server data in `data/`. These
folders are normally inside the server folder. MySQL settings normally live in
`mysql/my.cnf`; an existing `my.cnf` or `my.ini` is reused. Custom paths and
launcher options can put files elsewhere.

If the server folder is not writable, for example under `C:\Program Files`, the
launcher prints `Running in packaged mode. Working directory: ...` and keeps
these folders in `%LOCALAPPDATA%\Playerbots` instead. The `PLAYERBOTS_WORKDIR`
environment variable selects another data folder in the same way. While the data
folder is outside the server folder, the launcher neither checks for nor
installs or recovers server updates; use a writable server folder such as
`C:\Games\Playerbots`, or update manually.

## What is preserved

- Accounts, characters, inventories, money and existing databases.
- Active configurations, database credentials, configured paths and realm phase.
- Downloaded DBC/maps/vmaps/mmaps, logs and additional user files.
- Settings and database tables of modules a release no longer bundles. Retired
  configurations may be archived as `.backup.*` files instead of remaining active.

Bundled server binaries, libraries, templates, SQL and release notices follow
the release. Keep regular database and configuration backups, including before
an established realm receives new SQL migrations. Managed configuration defaults
change only where the active value still matches the previous default, with a
`.backup.*` copy of each changed file; see
[configuration updates](configuration.md).

## Backups and recovery

Press Ctrl+C and wait for the launcher, authserver, worldserver and MySQL to
exit before copying database files. Copying a running `mysql/data/` directory
does not produce a reliable backup. The simplest complete backup is a copy of
the stopped server folder, plus any data or configuration kept at custom paths.
Include `configs/` with its `.portable-profiles.json` and `realm-phase.txt`, the
MySQL configuration and data, and the matching server release. Keep a backup
outside the folder being updated.

Configuration `.backup.*` files protect settings; they are not database backups.
To revert after SQL migrations, restore the matching database, configuration and
server backup together. Replacing only older executables does not reverse a
database update. Existing levels, tiers, items and gold are preserved without
verifying how they were obtained; see
[realm updates](changing-expansions.md#updating-an-existing-realm).

## Moving the server folder

Stop the realm completely, then move the entire server folder to a writable
location. Include `configs/` and its `.portable-profiles.json` baseline, the
database data directories, downloaded server data and bundled `src/` SQL tree.
Start `startup.exe` from the new location. Data kept in
`%LOCALAPPDATA%\Playerbots` or `PLAYERBOTS_WORKDIR` stays where it is.

Generated SQL source paths are relative to the server's working directory. If
`SourceDirectory` in the active authserver or worldserver config is an absolute
`.../src` path that no longer exists, the launcher points it at the complete
bundled SQL tree and saves an adjacent configuration backup first. Valid custom
source directories are preserved. For a custom directory that has also moved,
adjust `SourceDirectory` in the active authserver/worldserver configs yourself.

## Manual installation

To install or replace the server files manually:

1. Choose a writable server folder. For an existing realm, stop the launcher,
   database and servers completely, then make a [backup](#backups-and-recovery).
2. Download the latest
   [server ZIP](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/mod-playerbots-portable-latest.zip)
   and verify it against
   [SHA256SUMS.txt](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/SHA256SUMS.txt).
3. Extract the ZIP into the server folder, replacing bundled files. Preserve an
   existing realm's configurations, database data directories and downloaded
   server data.
4. Run `startup.exe` normally and allow database updates to finish. The launcher
   manages setup and future server updates.

The selected realm mode is preserved; see
[realm updates](changing-expansions.md#updating-an-existing-realm).

## Client packages

The server updater does not install client addons or modify a WoW client. Each
player installs the EraTalents client pack of the same release as the server
manually; see [client installation](era-talents.md#install-the-matching-client-files).
The optional MultiBot, DragonUI, Questie and Zygor addons are updated from
their [forks' Latest releases](addons.md#addon-forks). Close WoW before replacing
client files; the EraTalents addon and `Data/patch-V.mpq` must belong to the same
generation as the server.

## Server data and the client cache

With the core default `ClientCacheVersion = 0`, worldserver reads
`acore_world.version.cache_id` after applying SQL migrations and sends that
version when a client session connects. A changed version refreshes the client's
cache of server query responses, such as quest, item, creature and gameobject
templates. Sending the same version again does not request another refresh.

The bundled migration sets a stable cache version for the distribution's quest
and item data. The native SQL updater records applied migrations and skips
unchanged files on subsequent starts. A higher administrator-managed database
version is preserved. Login, ordinary restart and configuration reload do not
increment the version.

World SQL updates require the world bit (`4`) in `Updates.EnableDatabases`;
the core default is `7`. Keep `SourceDirectory` pointing at the bundled `src/`
tree unless you maintain your own SQL tree. The launcher's `--skip-sql` skips
only database/user creation, not the core's migrations.

An explicit nonzero `ClientCacheVersion` in your active `worldserver.conf`
overrides the database value and is preserved. Administrators maintaining this
override or a higher database cache version must choose a fresh version when
their cached data changes. After changing `version.cache_id` manually, restart
worldserver: `.reload config` reuses the database value read at startup.

This mechanism does not install client DBC/MPQ data, spell descriptions, talent
trees, models or addon code. Changes to those assets require the matching client
packages, installed separately with WoW closed. A change confined to cached server
query responses needs only the cache version. Keep `WTF/`, addon SavedVariables,
active server configurations and databases; deleting them is not part of a cache
update.

To inspect the installed cache version, query the world database:

```sql
SELECT cache_id FROM version;
```

Compare it with `Client cache version set to:` in the worldserver startup log.
For source changes to cached server data, see the
[build guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md#client-cache-changes).

## Offline startup and failed updates

To skip the remote server-update check for one launch, run from the server folder:

```powershell
.\startup.exe --no-update
```

Normal configuration handling and database migrations still run. Offline checks,
unsupported downloads and failed hash verification report
`Update check unavailable; starting installed release` and leave the current
version intact. Automatic updates apply to packages from the Latest release; a
custom `dev` build keeps its own files.

Each launch spends at most 15 minutes downloading an update. Verified files of
an interrupted or slow download stay in `.portable-update/`, the installed
release starts, and the next launch continues with the remaining files.
Incomplete file installation is rolled back before starting services; if
rollback fails, startup stops to avoid running mixed files. Keep
`.portable-update/` intact while an interrupted update is being recovered.
The updater keeps `startup.exe` in place while preparing its verified backup,
then replaces it directly with the staged launcher.
After a completed update or successful rollback, a failure to remove temporary
update files reports a warning and retries on the next start without blocking
the realm.

If an update reports a running process or a locked file, stop the other launcher
and the realm's authserver, worldserver and MySQL, then retry. Windows may keep
an executable locked while its process exits. The updater refuses replacement
when it cannot establish that the relevant processes have stopped; keep its
recovery files intact.

## Launcher options

Run `startup.exe --help` for the same list.

| Option | Effect |
| --- | --- |
| `--no-update` | Start without checking Latest for a server update. |
| `--show-expansion` | Show the realm mode and level cap, then exit. |
| `--set-expansion <mode>` | Select `individual`, `vanilla`, `tbc` or `wotlk` with configuration backups, then exit; stop the realm first. See [realm ceilings](changing-expansions.md#optional-realm-ceilings). |
| `--port <port>` | MySQL process port and the port written to missing configurations (default 3306). Without this flag, follows the first local `LoginDatabaseInfo` in authserver/worldserver configs. Existing config files are not rewritten. |
| `--auth-port <port>` | Authserver port written to a newly created `authserver.conf` (default 3724). |
| `--timeout <seconds>` | Time to wait for MySQL to become ready (default 30). |
| `--download-data-only` | Download and extract the server data, then exit. |
| `--data-url <url>` | Download the server data archive from another URL. |
| `--skip-data-check` | Do not check for or download the server data. |
| `--init-only` | Create missing configurations, initialize MySQL and run the database/user creation script, then exit. Core/module SQL imports and migrations require a normal server start. |
| `--skip-sql` | Skip the bundled script that creates the AzerothCore databases and database user. |
| `--mysql-dir <path>` | MySQL installation to use; normally the bundled `mysql/`, with `MYSQL_ROOT` and executable search as fallbacks. |
| `--data-dir <path>` | MySQL data directory (default: `mysql/data/` in the data folder). |
| `--mysql-cnf <path>` | Existing MySQL option file to use. Otherwise an existing `my.cnf`/`my.ini` is detected, or `mysql/my.cnf` is created in the data folder. |

For example, `.\startup.exe --timeout 120` waits longer on a slow disk.
To move an existing realm to another MySQL port, stop it and change the port in
every `*DatabaseInfo` setting under `configs/`; the launcher follows that
setting on the next start. `--port` alone does not change an existing realm's
server connections. Authserver uses `RealmServerPort` in `authserver.conf`;
worldserver uses `WorldServerPort` in `worldserver.conf` (default 8085). The
shipped servers bind to `127.0.0.1` for local play.
