# AzerothCore Playerbots Portable

A prebuilt **Windows x64 ZIP** for AzerothCore 3.3.5a, Playerbots and four additional modules. Extract the release archive and run `startup.exe`; no compiler or separate MySQL installation is needed. The default realm starts with **Vanilla progression, level 1 characters and a target of 2,500 bots while a real player is connected**.

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
| [Playerbots](https://github.com/mod-playerbots/mod-playerbots) | Enabled; 2,500 online target with real players connected, level 1 creation and the natural progression patch described below. |
| [AutoBalance](https://github.com/azerothcore/mod-autobalance) | Enabled; adjusts instance difficulty to the party size, keeps original creature levels and disables extra reward tokens. |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | Enabled; every character starts at tier 0 and earns Vanilla progression through tier 7 (Naxxramas). Random bot accounts follow the same gates. |
| [AH Bot Plus](https://github.com/NathanHandley/mod-ah-bot-plus) | Included; automatic seller and buyer disabled. The seller creates items rather than farming them. Players and ordinary bot activity can still use the auction house. |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | Included; disabled in the strict profile because some scripted routes teleport bots across navigation gaps. Queue fillers and route/recovery shortcuts are also disabled. Its optional post-combat resurrection uses a surviving party member's normal spell. |

The pinned Playerbots version provides the native `ForceRebuffState` API used by Dungeon Clear's raid preparation. Its compatibility patch also supports older Playerbots versions: those use normal buffs for a bounded phase (25 seconds by default, within the 60-second overall muster budget). Module checkout and patch application happen during the build, never during server startup.

## Vanilla and earned bot progression

The launcher merges the bundled [profiles](cmd/startup/profiles) into complete upstream templates **only when an active configuration file does not exist**. Your edits survive later launches. The ZIP includes readable profile copies in `defaults/`; the launcher uses its embedded profiles.

The fresh realm uses:

- A level cap of 60, normal XP/drop/money rates, zero starting gold and no Dungeon Finder.
- Vanilla races and classes. Blood elves, draenei and death knights are disabled using character creation masks.
- Individual Progression's Vanilla limit, with the usual random-bot account exemption removed. Core `Expansion = 2` is needed for the module's restored Naxxramas map; the module, level cap and creation masks enforce Vanilla access.
- 278 random-bot accounts with nine permitted classes: a pool of up to 2,502 characters, of which 2,500 are targeted online. They begin with the normal level 1 starter equipment and acquire XP, gold and equipment through gameplay.
- Gradual bot login begins after a real player session has been connected for 30 seconds. Bots save and log out about 60 seconds after the last real session disconnects. Character selection and queued sessions also count as a connection.
- Disabled random level jumps, equipment upgrades, character recycling and quest synchronization shortcuts.

The pinned upstream Playerbots code grants equipment, money, supplies and repairs even when several existing cheat settings are disabled. [The natural progression patch](patches/mod-playerbots-natural-progression.patch) adds `AiPlayerbot.NaturalProgression = 1` to disable these factory/refresh grants and additional free recovery, travel and resource shortcuts. Normal core XP, loot, quests, vendors, trainers and character creation remain available. The patch is applied to a generated module copy; both upstream submodules stay at their original revisions.

Autonomous bots also seek nearby trainers, vendors and repair NPCs for available spells, earned-loot sales and needed supplies. They walk to the NPC and use normal server interactions, prices, gold, level and learning prerequisites. Their maintenance target is cached for 30 seconds to limit repeated scans. Matching class quests are retained, and hunter pets can only be fed with owned suitable food through the learned Feed Pet spell.

## Vanilla battlegrounds and social behavior

Bots can fill a real player's named Vanilla battleground queue using their earned levels, equipment and faction. Autonomous all-bot match creation stays disabled. Fresh level 1 bots must level normally before they are eligible; an eligible population may take time to develop.

| Battleground | Eligible levels | Individual Progression brackets |
| --- | --- | --- |
| Warsong Gulch | 10–60 | 10–19, 20–29, 30–39, 40–49, 50–59, 60 only |
| Arathi Basin | 20–60 | 20–29, 30–39, 40–49, 50–59, 60 only |
| Alterac Valley | 51–60 | 51–60 |

`AiPlayerbot.VanillaBattlegroundsOnly = 1` restricts bot queue selection and execution to these three battlegrounds. Random battlegrounds, later-expansion battlegrounds and arenas are excluded during this phase. Ordinary team-size requirements still apply. Arathi Basin uses a 2,000-point victory limit; Alterac Valley has no reinforcement countdown. These settings restore those victory rules, rather than every historical version of Vanilla AV.

Battleground participation uses normal core queue invitations and transport. Dead bots release normally, walk to a friendly spirit guide when necessary and wait for the ordinary resurrection wave. The natural progression patch supplies no free equipment, levels or forced resurrection for PvP. Automatic instance strategies and AoE avoidance remain enabled.

Nearby greetings are enabled for real players only, with at most one automated greeting per real player per minute across the bot population. Global random emotes, bot-to-bot greetings and toxic-link/Thunderfury meme replies stay disabled, so the population does not turn routine encounters into ambient chat spam. This uses existing Playerbots behavior; no additional NPC, reward or random-battleground module is required.

## AI limits and existing installations

**Limits:** This does not add a complete human-like farming, crafting or questing AI. Bots may get stuck, lack supplies or fail a quest/profession step; disabling teleport recovery increases that possibility. Some upstream encounter scripts, particularly in later expansions, still contain special movement or combat shortcuts and need further audits before a literal zero-shortcut guarantee. The online population is a target, not a performance guarantee. Upstream activity scaling reduces remote bot work when world ticks slow down; combat, instances and bots near or grouped with players remain active. CPU, RAM, storage and the first-run creation workload determine whether your machine can sustain 2,500 loaded characters.

Bot debug logging is disabled by default and log writes run asynchronously. Empty Individual Progression account filters skip repeated database queries and regex construction, while preserving the same progression gates for players and bots.

This is Vanilla content progression on the WotLK core, with its client/class mechanics and some later-added low-level quests and professions. It does not reproduce the original 1.12 client rules exactly.

Existing characters keep their levels, inventory, money and progression. Existing active configs also keep their settings; the new defaults do not silently reset an established realm. Back up databases and configurations before migrating an existing realm.

To apply the recommended settings to an existing installation, stop the server, extract the new ZIP into its folder and run this once from PowerShell:

```powershell
.\startup.exe --apply-profiles
```

The command backs up every changed config, updates only the settings managed by the bundled profiles and exits without starting the servers. Database credentials, paths and unrelated custom settings are retained. Start `startup.exe` normally afterwards. This command does not reset characters or databases.

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

The Vanilla bot PvP restriction remains active until `AiPlayerbot.VanillaBattlegroundsOnly` is changed to 0. Keep it enabled for this level-60 realm. Arenas require a separate later review of eligibility, team creation and upstream catch-up shortcuts before enabling them.

For commands and AI behavior, see the [Playerbot wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands). Enabling AH generation, Dungeon Clear or upstream cheat features changes the strict earned-play behavior above.

## Build and release

The [GitHub Actions workflow](.github/workflows/release.yml) tests the launcher, prepares pinned modules, builds Release binaries and checks the portable distribution before uploading a ZIP. A pushed `v*` tag publishes that ZIP as the release asset. Pull requests validate the same build with read-only repository permissions.

For a fork, first enable workflows on the repository's [Actions page](https://github.com/Syntax555/mod-playerbots-portable/actions), if GitHub shows the **Enable workflows** button. Enabling them does not replay tags pushed while Actions was disabled. To publish an existing tag, open **Build portable ZIP**, choose **Run workflow** on `main`, enter the tag (for example `v1.0.8`) in **release_tag**, and start the run. It checks out that exact tag and publishes its compiled ZIP only after all build and verification steps succeed. Leave **release_tag** empty to create a downloadable build artifact without publishing a release.

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
