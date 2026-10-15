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
- Configurations and database tables of modules a release no longer bundles;
  the servers ignore them.

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
