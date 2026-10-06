# AzerothCore Playerbots Portable

A prebuilt **Windows x64 ZIP** for AzerothCore 3.3.5a, Playerbots and seven additional modules. Extract the release archive and run `startup.exe`; no compiler or separate MySQL installation is needed. The default realm uses **earned individual progression through Vanilla, TBC and Wrath, level-1 random bots, and a target of 2,500 bots while a real player is connected**.

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

The [configuration audit](docs/vanilla-config-audit.md) describes the profiles released in v1.0.9: normal talent/skill rules, riding at 40/60, disabled shortcut bot mail and quiet event broadcasts. Its v1.0.10 addendum covers Quest Loot Party. Use the new version's launcher to apply them to an existing installation; v1.0.8 embeds the earlier profiles.

## MultiBot Chatless client addon

The original MultiBot distribution has been replaced with
[MultiBot Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) and its
matching server module, [mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge).

Players can download **`MultiBot-Chatless-<version>.zip`** independently from
[GitHub Releases](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
Extract its `MultiBot` folder into the WoW 3.3.5a client's `Interface/AddOns/`
folder. The server ZIP also provides the same copy under `addons/MultiBot/`.
When replacing an old installation, remove the old client `MultiBot` folder
before copying the replacement, so legacy Lua files cannot remain mixed in.
The final path must be `Interface/AddOns/MultiBot/MultiBot.toc`, even though the
download is named Chatless. Restart the client and enable MultiBot in the AddOns
menu; open the interface with `/multibot`, `/mbot` or `/mb`.

For a direct upstream download matching this server, use the
[pinned Chatless source ZIP](https://github.com/Wishmaster117/MultiBot-Chatless/archive/80148dff3f3a25a56d38dba0ecbd4f165b8c1d3f.zip)
and rename the extracted addon folder to `MultiBot`. Prefer the matching portable
release addon when upgrading; arbitrary newer addons may expect newer bridge
capabilities. Players install the addon themselves; the server cannot install
it into a separate client directory.

Chatless moves many reads and actions to structured addon messages; upstream
still describes it as mostly chatless because some legacy commands remain.
The server's level cap, earned progression and disabled shortcut commands also
apply to addon requests. The bridge's natural-progression patch blocks write
paths that bypass ordinary interaction rules; see the
[current integration audit](docs/vanilla-config-audit.md#chatless-and-token-turn-in-addendum).

## Included modules and defaults

Server module sources are pinned in [versions.lock.json](versions.lock.json), compiled into the server and shipped with their configuration templates, SQL where applicable and licenses. The client addon has its own pinned revision in the same manifest.

| Module | Default behavior |
| --- | --- |
| [Playerbots](https://github.com/mod-playerbots/mod-playerbots) | Enabled; 2,500 online target with real players connected, level 1 creation and the natural progression patch described below. |
| [AutoBalance](https://github.com/azerothcore/mod-autobalance) | Enabled; adjusts instance difficulty to the party size, keeps original creature levels and disables extra reward tokens. |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | Enabled; characters start at tier 0 and earn Vanilla, TBC and Wrath tiers. Random bots follow the same gates; expansion race creation also requires their own account's unlock. |
| [AH Bot Plus](https://github.com/NathanHandley/mod-ah-bot-plus) | Included; automatic seller and buyer disabled. The seller creates items rather than farming them. Humans can use the AH, but this Playerbots revision has no active autonomous auction trading. |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | Included; disabled in the strict profile because some scripted routes teleport bots across navigation gaps. Queue fillers and route/recovery shortcuts are also disabled. Its optional post-combat resurrection uses a surviving party member's normal spell. |
| [Quest Loot Party](https://github.com/pangolp/mod-quest-loot-party) | Enabled; eligible party members can each loot a copy of naturally dropped normal-quality quest items. Each member still opens the corpse; login announcements are disabled. |
| [MultiBot Bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | Included for the Chatless addon, with quiet logging and additional natural-progression restrictions on shortcut actions. |
| [Token Turn-in](https://github.com/Zerathane/mod-token-turnin) | Enabled for `.tokenturnin check` on grouped bots. Shortcut `.tokenturnin redeem` is blocked during natural progression because upstream skips normal NPC, reputation and material requirements. |

All locked sources were compared with their upstream branch heads on **5 October
2026**. Existing server pins were already current; the Chatless addon and both
new modules use the current upstream heads. [Module versions](docs/module-versions.md)
records the exact revisions, source choices and verification limits.

Token Turn-in's check only previews token-to-item mappings for the bot's class
and spec. It does not establish quest eligibility or grant equipment. Bots must
farm the tokens and all additional materials, earn the required reputation and
complete the original NPC exchange. Other real group members are excluded.

The pinned Playerbots version provides the native `ForceRebuffState` API used by Dungeon Clear's raid preparation. Its compatibility patch also supports older Playerbots versions: those use normal buffs for a bounded phase (25 seconds by default, within the 60-second overall muster budget). Module checkout and patch application happen during the build, never during server startup.

Quest Loot Party uses the original author's narrow quest-loot module. It keeps normal drop chances, quest eligibility and inventory checks, and leaves ordinary equipment loot rules unchanged. It does not auto-complete quests or send items directly to party members. Shared quest drops are an intentional convenience change from ordinary Vanilla party loot; forced drops and broad personal-loot features from other forks are not included.

## Vanilla and earned bot progression

The launcher merges the bundled [profiles](cmd/startup/profiles) into complete upstream templates **only when an active configuration file does not exist**. Your edits survive later launches. The ZIP includes readable profile copies in `defaults/`; the launcher uses its embedded profiles.

The fresh realm uses:

- A realm ceiling of 80, normal XP/drop/money rates, zero starting gold and no Dungeon Finder. Individual Progression holds each character at 60/70 until it earns TBC/Wrath access.
- Vanilla races/classes on fresh accounts. Blood elves and draenei require that account to earn tier 8; human-controlled death knights require tier 13. Death knight bots stay disabled because all new random bots must start at level 1.
- Individual Progression starts every ordinary character at tier 0, with no random-bot account exemption. The patched bot factory and login both enforce account unlocks. Core `Expansion = 2` supports later content and restored Vanilla Naxxramas.
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

Nearby greetings are enabled for real players only, with at most one automated greeting per real player per minute across the bot population. Global random emotes, bot-to-bot greetings, unsolicited channel announcements and toxic-link/Thunderfury meme replies stay disabled. Direct command replies remain available. This uses existing Playerbots behavior; no additional NPC, reward or random-battleground module is required.

Bot mail commands are disabled because the upstream implementation bypasses mailbox proximity and normal postage. Ordinary player mail and direct trading remain available. With AH Bot Plus disabled, a single-human realm has no verified autonomous auction supply or demand; earned bot auctions would require a separate AI implementation.

## AI limits and existing installations

**Limits:** This does not add a complete human-like farming, crafting or questing AI. Bots may get stuck, lack supplies or fail a quest/profession step; disabling teleport recovery increases that possibility. Some upstream encounter scripts, particularly in later expansions, still contain special movement or combat shortcuts and need further audits before a literal zero-shortcut guarantee. The online population is a target, not a performance guarantee. Upstream activity scaling reduces remote bot work when world ticks slow down; combat, instances and bots near or grouped with players remain active. CPU, RAM, storage and the first-run creation workload determine whether your machine can sustain 2,500 loaded characters.

Bot debug logging is disabled by default and log writes run asynchronously. Empty Individual Progression account filters skip repeated database queries and regex construction, while preserving the same progression gates for players and bots.

Progression begins with Vanilla content on the WotLK core, with its client/class mechanics and some later-added low-level quests and professions. **The talent trees remain Wrath trees.** Normal talent rates give 51 earned points at level 60; `LimitTalentsExpansion` approximates Vanilla/TBC depth for bot templates and fallback allocation, without replacing talent identities or restricting human trees. Human glyphs, pet talent trees and some later low-level class spells also remain. Natural bot talent allocation retains existing talents and spends earned points without free resets. Individual mode keeps new dual specialization purchases unavailable below level 80. True 1.12 talents require coordinated client, server and bot changes; the optional Individual Progression DBC files do not contain replacement talent tables.

AutoBalance counts the non-GM players actually present, including bots. A human plus four bots receives normal five-player dungeon stats; smaller parties use the upstream scaling curve and scaled XP/money, with original creature levels. Outdoor elites and world bosses retain their ordinary difficulty and need suitable companions. Instance scaling does not solve every encounter tactic; full AQ40/Naxx40 bot support is not established. A source/configuration audit cannot establish exact historical class balance or completion of every raid.

See [the configuration audit](docs/vanilla-config-audit.md), included in the ZIP, for the effective settings, module coverage, remaining Vanilla fidelity choices and migration from v1.0.8.

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
| `configs/modules/mod-quest-loot-party.conf` | Shared normal-quality quest loot and the module's login message. |
| `configs/modules/MultiBotBridge.conf` | Structured addon bridge logging; natural-progression restrictions follow the Playerbots setting. |
| `configs/modules/mod_token_turnin.conf` | Token inventory checks and which group members are included; natural progression blocks shortcut redemption. |
| `mysql/my.cnf` | MySQL/InnoDB tuning generated for the host's RAM. |

Fresh installations use individual progression automatically. To remove an
older realm's global Vanilla/TBC ceiling, install the complete v1.0.13 server
ZIP, stop the launcher and servers, then run:

```powershell
.\startup.exe --set-expansion individual
.\startup.exe --apply-profiles
```

Start `startup.exe` normally afterwards. Every character still earns its own
tiers: TBC at 8 and Wrath at 13. TBC race creation also requires tier 8 on that
same account. Changed configs are backed up; characters and databases are
preserved. The mode survives profile updates and missing-config creation.
`--show-expansion` displays it. Optional `vanilla`/`tbc` modes retain shared realm
ceilings. See [Changing expansions](docs/changing-expansions.md) for migration
and remaining gameplay limits. The bot safeguards require the updated server
binaries, not just a replacement launcher.

The Vanilla bot PvP restriction remains active and excludes bots above level 60. Later bot battlegrounds and arenas require a separate review of eligibility, team creation and upstream catch-up shortcuts before enabling them.

For commands and AI behavior, see the [Playerbot wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands). Enabling AH generation, Dungeon Clear or upstream cheat features changes the strict earned-play behavior above.

## Build and release

The [GitHub Actions workflow](.github/workflows/release.yml) tests the launcher,
prepares pinned modules, builds Release binaries and verifies both the portable
server ZIP and separate player addon ZIP before uploading them. A pushed `v*`
tag publishes both assets. Pull requests and pushes to `main` or `codex/**`
review branches create downloadable build artifacts with read-only repository
permissions. New pushes cancel an unfinished build on the same branch.
The workflow checks the portable launcher logic on Linux before starting the
Windows server build, then runs the launcher tests again on Windows.

For a fork, first enable workflows on the repository's [Actions page](https://github.com/Syntax555/mod-playerbots-portable/actions), if GitHub shows the **Enable workflows** button. Enabling them does not replay tags pushed while Actions was disabled. To publish an existing tag, open **Build portable ZIP**, choose **Run workflow** on `main`, enter the tag (for example `v1.0.10`) in **release_tag**, and start the run. It checks out that exact tag and publishes its compiled ZIP only after all build and verification steps succeed. Leave **release_tag** empty to create a downloadable build artifact without publishing a release.

For a local source build, use Windows 10/11 x64, Visual Studio 2022 with the C++ workload, CMake 3.21+, Go 1.26.6+, PowerShell 7+, Git, Boost 1.84+, MySQL Server 8.0 x64 and OpenSSL 3 x64:

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
cmake -DPACKAGE_VERSION="dev" -P cmake/PackageClientAddons.cmake
```

This generates `output/mod-playerbots-portable-dev.zip` and the separate
`output/MultiBot-Chatless-dev.zip`. Subsequent configuration reuses the pinned
module cache. Changing a revision or patch rebuilds the managed module copy;
unmarked module directories are never overwritten. `cmake -P cmake/PrepareModules.cmake`
can also prepare the modules independently.

## Licenses

The portable launcher and build tooling use the [MIT License](LICENSE).
AzerothCore and modules retain their upstream licenses or source notices under
`licenses/` in the ZIP. The bridge's upstream revision has no explicit license
declaration; its NOTICE records provenance without assigning one. The ZIP also
includes the source revision manifest and applied patches so its server sources
can be reproduced. Client data comes from the [wowgaming community](https://github.com/wowgaming/client-data).
