# AzerothCore Playerbots Portable

A prebuilt **Windows x64 ZIP** for AzerothCore 3.3.5a, Playerbots and four additional modules. Extract the release archive and run `startup.exe`; no compiler or separate MySQL installation is needed. The default realm starts with **Vanilla progression, level 1 characters and a target of 2,500 online bots**.

## Download and play

1. Download `mod-playerbots-portable-<version>.zip` from [GitHub Releases](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
2. Extract it into a writable folder and run `startup.exe`.
3. On first launch, the launcher downloads missing client data (DBC, maps, vmaps and mmaps), initializes portable MySQL and lets the server apply the bundled core and module SQL. This requires Internet access and can take considerable time, particularly when creating the bot population.
4. In the worldserver console, create a normal player account:
   ```text
   account create <username> <password>
   ```
5. Set your **WoW 3.3.5a** client's realmlist to `set realmlist 127.0.0.1` and log in.

The world/auth/database services bind locally by default. A Vanilla content progression server still requires the 3.3.5a client. Do not grant your playing account GM privileges if you want ordinary gameplay.

## MultiBot client addon

The release ZIP includes the pinned **MultiBot** addon under `addons/MultiBot/`.
Copy that entire folder into your WoW 3.3.5a client's `Interface/AddOns/` folder,
so the final path is `Interface/AddOns/MultiBot/MultiBot.toc`. Restart the client
and enable MultiBot in the character selection screen's AddOns menu.

Open its interface in-game with `/multibot`, `/mbot` or `/mb`.

MultiBot provides an in-game interface for controlling your bots. It does not
change the server's level cap, progression gates or natural progression rules;
server-disabled boost and shortcut commands stay disabled. The server cannot
install the addon into a separate client directory automatically.

The strict profile disables the class-based bot creator, free summoning and
quest synchronization; those addon shortcuts remain unavailable. Its optional
manual quest reward panel for your account's alternate characters requires
`AiPlayerbot.AutoPickReward = no`; autonomous random bots can still select their
own rewards. Keep quest synchronization disabled to preserve earned completion.

## Included modules and defaults

Server module sources are pinned in [versions.lock.json](versions.lock.json), compiled into the server and shipped with their configuration templates, SQL where applicable and licenses. The client addon has its own pinned revision in the same manifest.

| Module | Default behavior |
| --- | --- |
| [Playerbots](https://github.com/mod-playerbots/mod-playerbots) | Enabled; 2,500 online target, level 1 creation and the natural progression patch described below. |
| [AutoBalance](https://github.com/azerothcore/mod-autobalance) | Enabled; adjusts instance difficulty to the party size, keeps original creature levels and disables extra reward tokens. |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | Enabled; every character starts at tier 0 and earns Vanilla progression through tier 7 (Naxxramas). Random bot accounts follow the same gates. |
| [AH Bot Plus](https://github.com/NathanHandley/mod-ah-bot-plus) | Included; automatic seller and buyer disabled. The seller creates items rather than farming them. Players and ordinary bot activity can still use the auction house. |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | Included; disabled in the strict profile because some scripted routes teleport bots across navigation gaps. Queue fillers, free wipe recovery and other shortcuts are also disabled. |

The pinned Playerbots version provides the native `ForceRebuffState` API used by Dungeon Clear's raid preparation. Its compatibility patch also supports older Playerbots versions: those use normal buffs for a bounded phase (25 seconds by default, within the 60-second overall muster budget). Module checkout and patch application happen during the build, never during server startup.

## Vanilla and earned bot progression

The launcher merges the bundled [profiles](cmd/startup/profiles) into complete upstream templates **only when an active configuration file does not exist**. Your edits survive later launches. The ZIP includes readable profile copies in `defaults/`; the launcher uses its embedded profiles.

The fresh realm uses:

- A level cap of 60, normal XP/drop/money rates, zero starting gold and no Dungeon Finder.
- Vanilla races and classes. Blood elves, draenei and death knights are disabled using character creation masks.
- Individual Progression's Vanilla limit, with the usual random-bot account exemption removed. Core `Expansion = 2` is needed for the module's restored Naxxramas map; the module, level cap and creation masks enforce Vanilla access.
- 278 random-bot accounts with nine permitted classes: a pool of up to 2,502 characters, of which 2,500 are targeted online. They begin with the normal level 1 starter equipment and acquire XP, gold and equipment through gameplay.
- Disabled random level jumps, equipment upgrades, character recycling and quest synchronization shortcuts.

The pinned upstream Playerbots code grants equipment, money, supplies and repairs even when several existing cheat settings are disabled. [The natural progression patch](patches/mod-playerbots-natural-progression.patch) adds `AiPlayerbot.NaturalProgression = 1` to disable these factory/refresh grants and additional free recovery, travel and resource shortcuts. Normal core XP, loot, quests, vendors, trainers and character creation remain available. The patch is applied to a generated module copy; both upstream submodules stay at their original revisions.

**Limits:** This does not add a complete human-like farming, crafting or questing AI. Bots may get stuck, lack supplies or fail a quest/profession step; disabling teleport recovery increases that possibility. Some upstream encounter scripts, particularly in later expansions, still contain special movement or combat shortcuts and need further audits before a literal zero-shortcut guarantee. The online population is a target, not a performance guarantee. Keeping 2,500 bots active without nearby players is demanding; CPU, RAM, storage and the first-run creation workload determine whether your machine can sustain it.

This is Vanilla content progression on the WotLK core, with its client/class mechanics and some later-added low-level quests and professions. It does not reproduce the original 1.12 client rules exactly.

Existing characters keep their levels, inventory, money and progression. Existing active configs also keep their settings; the new defaults do not silently reset an established realm. Back up databases and configurations before migrating an existing realm.

## Configuration

After first launch:

| File | Settings |
| --- | --- |
| `configs/worldserver.conf` | Level cap, creation masks, normal rates, data/database paths. |
| `configs/authserver.conf` | Authentication and database connection. |
| `configs/modules/playerbots.conf` | Population, activity, natural progression and bot AI. |
| `configs/modules/individualProgression.conf` | Starting tier, content limit and account exemptions. |
| `configs/modules/AutoBalance.conf` | Instance difficulty and reward scaling. |
| `configs/modules/mod_ahbot.conf` | Optional generated auction-house supply and automated buying. |
| `configs/modules/mod_dungeon_clear.conf` | Optional dungeon navigation and queue filling. |
| `mysql/my.cnf` | MySQL/InnoDB tuning generated for the host's RAM. |

To open later expansions, raise `MaxPlayerLevel` and `AiPlayerbot.RandomBotMaxLevel` to 80, clear both `CharacterCreating.Disabled` race/class masks and set `IndividualProgression.ProgressionLimit = 0` (unlimited) and `IndividualProgression.BotAccountsMaxLevel = 80`. `Expansion` stays 2. Characters must still earn their progression tiers: 8 starts TBC, 13 starts Wrath, and 18 completes Wrath. Natural progression keeps random death knights excluded to preserve level 1 creation; player death knights ordinarily start at 55.

For commands and AI behavior, see the [Playerbot wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands). Enabling AH generation, Dungeon Clear or upstream cheat features changes the strict earned-play behavior above.

## Build and release

The [GitHub Actions workflow](.github/workflows/release.yml) tests the launcher, prepares pinned modules, builds Release binaries and checks the portable distribution before uploading a ZIP. A pushed `v*` tag publishes that ZIP as the release asset. Pull requests validate the same build with read-only repository permissions.

For a fork, first enable workflows on the repository's [Actions page](https://github.com/Syntax555/mod-playerbots-portable/actions), if GitHub shows the **Enable workflows** button. Enabling them does not replay tags pushed while Actions was disabled. To publish an existing tag, open **Build portable ZIP**, choose **Run workflow** on `main`, enter the tag (for example `v1.0.5`) in **release_tag**, and start the run. It checks out that exact tag and publishes its compiled ZIP only after all build and verification steps succeed. Leave **release_tag** empty to create a downloadable build artifact without publishing a release.

For a local source build, use Windows 10/11 x64, Visual Studio 2022 with the C++ workload, CMake 3.19+, Go 1.26.6+, PowerShell 7+, Git, Boost 1.84+, MySQL Server 8.0 x64 and OpenSSL 3 x64:

```powershell
git clone --recurse-submodules https://github.com/Syntax555/mod-playerbots-portable.git
cd mod-playerbots-portable
cmake -B build -S . `
  -G "Visual Studio 17 2022" -A x64 `
  -DPACKAGE_VERSION="dev" `
  -DMYSQL_ROOT_DIR="C:/tools/mysql/current" `
  -DOPENSSL_ROOT_DIR="C:/tools/openssl/current/x64" `
  -DBOOST_ROOT_DIR="C:/local/boost_1_84_0"
cmake --build build --config Release --parallel
# Bundle the Visual C++ runtime required by the core and portable MySQL.
pwsh -File scripts/CopyWindowsRuntime.ps1 -DistDir dist
cmake --build build --config Release --target package_zip
```

This generates `output/mod-playerbots-portable-dev.zip`. Subsequent configuration reuses the pinned module cache. Changing a revision or patch rebuilds the managed module copy; unmarked module directories are never overwritten. `cmake -P cmake/PrepareModules.cmake` can also prepare the modules independently.

## Licenses

The portable launcher and build tooling use the [MIT License](LICENSE). AzerothCore and the modules retain their upstream licenses, included under `licenses/` in the ZIP. The ZIP also includes the source revision manifest and applied patches so its server sources can be reproduced. Client data comes from the [wowgaming community](https://github.com/wowgaming/client-data).
