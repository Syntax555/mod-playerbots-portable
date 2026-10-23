# Running and updating the server

On normal startup, `startup.exe` checks the rolling
[Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
before starting the database and servers. It reads a small update manifest over
HTTPS, compares managed files and downloads only changed files from the server
ZIP. Each downloaded file must match its SHA-256 hash before installation.

The launcher stages the update, replaces managed server files and restarts itself.
SQL migrations run during normal database/server startup, without resetting the
existing databases. New configuration defaults are merged automatically.

## Progress, restarts and shutdown

The console reports file checks, download, verification and installation as
separate stages. Counters and progress bars use checked files, unpacked download
bytes or installed files, depending on the stage. Metadata requests and other
operations without a known total show activity and elapsed time. Redirected
output uses readable status lines and periodic activity messages.

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
folders are normally inside the server folder. Back up `configs/` and
`mysql/data/` together with the realm stopped.

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

The selected realm mode is preserved; see
[realm updates](changing-expansions.md#updating-an-existing-realm).

## Client packages

The server updater does not install client addons or modify a WoW client. Each
player installs the matching client packages manually; see
[client installation](era-talents.md#install-the-matching-client-files).

## Server data and the client cache

With the core default `ClientCacheVersion = 0`, worldserver reads
`acore_world.version.cache_id` after applying SQL migrations and sends that
version when a client session connects. A changed version refreshes the client's
cache of server query responses, such as quest, item, creature and gameobject
templates. Sending the same version again does not request another refresh.

The bundled migration `2026_10_21_00_portable_client_cache.sql` sets the database
cache version to `20261021` for the distribution's quest and item data. The native
SQL updater records its filename and hash in `acore_world.updates`; unchanged
files are skipped on subsequent starts. A higher administrator-managed database
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

### Reproduce a data update and an unchanged restart

Use a stopped test copy of an existing realm, with its configurations and
databases backed up. Keep `ClientCacheVersion = 0` for the database-driven check.

1. Start the old copy with `startup.exe --no-update` and record these world
   database queries, then stop the realm with Ctrl+C:

   ```sql
   SELECT cache_id FROM version;
   SELECT ID, RewardDisplaySpell, RewardSpell FROM quest_template WHERE ID = 5634;
   SELECT name, hash, state FROM updates
     WHERE name = '2026_10_21_00_portable_client_cache.sql';
   ```

   For the unmodified pinned world database, the cache ID is `17`. The cache
   migration is absent before installation. Quest 5634's stock reward pair is
   `13908, 19338`; an already migrated realm can have `948081, 948090` already.
2. Install the matching server release in the test copy using the normal
   [update steps](#manual-installation), preserving its data and configuration.
   Start normally. The SQL log applies the cache migration once, the queries
   show cache ID `20261021` and one migration row with a nonempty hash, and the
   startup log reports `Client cache version set to: 20261021`. The historical
   quest migration changes the stock reward pair to `948081, 948090`; its guards
   preserve custom reward values. Reconnect WoW to receive the version.
3. Run `.reload config` as a GM (or `reload config` in the server console),
   then stop and start the same installed release with `--no-update`. Repeat
   the queries. The ID, migration hash and reward values stay the same; the
   cache migration is not applied again. Reconnecting receives the same ID.

The source fixture reproduces the migration and unchanged restart with the real
core SQL updater and cache functions, using isolated data:

```bash
cmake -P cmake/PrepareModules.cmake
python3 cmake/tests/TestClientCacheVersion.py
```

For future changes to client-cached server data, ship a new world SQL migration
with a fresh, stable `version.cache_id` alongside the data change. Retain previous
migrations so established realms receive the new one. The SQL updater's hash
tracking alone does not update the cache version. Changes confined to AI,
loot, spawns or rates do not require a client cache bump; changes to client files
still require their corresponding client package.

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

## Launcher options

Run `startup.exe --help` for the same list.

| Option | Effect |
| --- | --- |
| `--no-update` | Start without checking Latest for a server update. |
| `--show-expansion` | Show the realm mode and level cap, then exit. |
| `--set-expansion <mode>` | Select `individual`, `vanilla`, `tbc` or `wotlk` with configuration backups, then exit; stop the realm first. See [realm ceilings](changing-expansions.md#optional-realm-ceilings). |
| `--port <port>` | MySQL port for new configurations (default 3306). An existing realm uses the port of its `LoginDatabaseInfo` setting. |
| `--auth-port <port>` | Authserver port written to a newly created `authserver.conf` (default 3724). |
| `--timeout <seconds>` | Time to wait for MySQL to become ready (default 30). |
| `--download-data-only` | Download and extract the server data, then exit. |
| `--data-url <url>` | Download the server data archive from another URL. |
| `--skip-data-check` | Do not check for or download the server data. |
| `--init-only` | Create missing configurations, initialize and set up the database, then exit without starting the game servers. |
| `--skip-sql` | Skip the bundled script that creates the AzerothCore databases and database user. |
| `--mysql-dir <path>` | MySQL installation to use (default: the bundled `mysql/`). |
| `--data-dir <path>` | MySQL data directory (default: `mysql/data/` in the data folder). |
| `--mysql-cnf <path>` | MySQL configuration file (default: the generated `mysql/my.cnf` in the data folder). |

For example, `.\startup.exe --timeout 120` waits longer on a slow disk.
To move an existing realm to another MySQL port, stop it and change the port in
every `*DatabaseInfo` setting under `configs/`; the launcher follows that
setting on the next start.
