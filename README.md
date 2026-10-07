# AzerothCore Playerbots Portable

A prebuilt **Windows x64 ZIP** for AzerothCore 3.3.5a, Playerbots and eight additional modules. Extract the release archive and run `startup.exe`; no compiler or separate MySQL installation is needed. The default realm uses **earned individual progression through Vanilla, TBC and Wrath, historical Vanilla/TBC talent trees, level-1 random bots, and a target of 2,500 bots while a real player is connected**.

## Download and play

1. Download `mod-playerbots-portable-<version>.zip` from [GitHub Releases](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
2. Extract it into a writable folder and run `startup.exe`.
3. On first launch, the launcher downloads missing client data (DBC, maps, vmaps and mmaps), initializes portable MySQL and lets the server apply the bundled core and module SQL. This requires Internet access and can take considerable time, particularly when creating the bot population.
4. In the worldserver console, create a normal player account:
   ```text
   account create <username> <password>
   ```
5. Download **`EraTalents-client-<version>.zip`** from the same server release or Actions build. Close WoW completely, copy `Interface/AddOns/EraTalents/` into the matching client folder, and copy `Data/patch-V.mpq` into its `Data/` folder. Replace an older IP `patch-V.mpq` with this merged version. Both pieces are required for the default historical-talent profile; `/reload` cannot load an MPQ.
6. Set your **WoW 3.3.5a** client's realmlist to `set realmlist 127.0.0.1`, restart the client and log in.

The world/auth/database services bind locally by default. A Vanilla content progression server still requires the 3.3.5a client (build 12340). Bots need the server files only. Do not grant your playing account GM privileges if you want ordinary gameplay. See [historical talents and client installation](docs/era-talents.md) for generation checks and migration limits.

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
| [Playerbots](https://github.com/mod-playerbots/mod-playerbots) | Enabled; 2,500 online target with real players connected, level 1 creation, natural progression and earned-inventory auction trading described below. |
| [AutoBalance](https://github.com/azerothcore/mod-autobalance) | Enabled; adjusts instance difficulty to the party size, keeps original creature levels and disables extra reward tokens. |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | Enabled with strict earned milestones; characters start at tier 0 and complete their own boss/quest prerequisites. Random bots follow the same gates; expansion race creation also requires their own account's unlock. |
| [Era Talents](https://github.com/lathcf/azerothcore-mod-era-talents) | Enabled; human and bot Vanilla/TBC talent trees and class spell variants follow earned character progression. Requires the matching EraTalents addon and merged client MPQ. |
| [AH Bot Plus](https://github.com/NathanHandley/mod-ah-bot-plus) | Included; automatic seller and buyer disabled. Earned auctions use Playerbots' own inventory and gold instead of this module's generated supply and artificial demand. |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | Included; disabled in the strict profile because some scripted routes teleport bots across navigation gaps. Queue fillers and route/recovery shortcuts are also disabled. Its optional post-combat resurrection uses a surviving party member's normal spell. |
| [Quest Loot Party](https://github.com/pangolp/mod-quest-loot-party) | Enabled; eligible party members can each loot a copy of naturally dropped normal-quality quest items. Each member still opens the corpse; login announcements are disabled. |
| [MultiBot Bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | Included for the Chatless addon, with quiet logging and additional natural-progression restrictions on shortcut actions. |
| [Token Turn-in](https://github.com/Zerathane/mod-token-turnin) | Enabled for `.tokenturnin check` on grouped bots. Shortcut `.tokenturnin redeem` is blocked during natural progression because upstream skips normal NPC, reputation and material requirements. |

The existing core, module and Chatless source pins were compared with upstream
branch heads on **5 October 2026**. Era Talents and its client build dependency
have separately pinned immutable revisions. [Module versions](docs/module-versions.md)
records the exact revisions, local adaptations and verification limits.

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
- Vanilla races/classes on fresh accounts. Blood elves and draenei require that account to earn tier 8, then start at level 1/tier 0 themselves. Strict earned progression blocks new death knights because their level-55 class start cannot meet the level-1 policy; existing characters are preserved.
- Individual Progression starts every ordinary character at tier 0, with no random-bot account exemption. The patched bot factory and login both enforce account unlocks. Core `Expansion = 2` supports later content and restored Vanilla Naxxramas.
- 278 random-bot accounts with nine permitted classes: a pool of up to 2,502 characters, of which 2,500 are targeted online. They begin with the normal level 1 starter equipment and acquire XP, gold and equipment through gameplay.
- Gradual bot login begins after a real player session has been connected for 30 seconds. Bots save and log out about 60 seconds after the last real session disconnects. Character selection and queued sessions also count as a connection.
- Disabled random level jumps, equipment upgrades, character recycling and quest synchronization shortcuts.

The pinned upstream Playerbots code grants equipment, money, supplies and repairs even when several existing cheat settings are disabled. [The natural progression patch](patches/mod-playerbots-natural-progression.patch) adds `AiPlayerbot.NaturalProgression = 1` to disable these factory/refresh grants and additional free recovery, travel and resource shortcuts. Normal core XP, loot, quests, vendors, trainers and character creation remain available. Local patches are applied to generated core/module copies; both upstream submodules stay at their original revisions.

Autonomous bots also seek nearby trainers, vendors and repair NPCs for available spells, earned-loot sales and needed supplies. They walk to the NPC and use normal server interactions, prices, gold, level and learning prerequisites. Their maintenance target is cached for 30 seconds to limit repeated scans. Matching class quests are retained, and hunter pets can only be fed with owned suitable food through the learned Feed Pet spell.

Strict earned progression also protects the module's default milestone chain.
Each character records eligible boss credit and rewarded transition quests, then
advances only through completed prerequisites. Group-leader copying, account
exemptions and ordinary group-attunement item grants cannot replace that work.
The default Era Talents profile gives humans and bots historical trees based on
Vanilla 1.12.1 and TBC Classic 2.5.4 data; earned tier 13 returns to native Wrath
trees. Level or account progress alone cannot change a character's era. Bots
spend newly earned talent points without routine free resets, and class spell
variants require paid training or their earned talent/quest source. An actual
expansion crossing refunds the old tree's earned points once. Existing glyphs
are retained but inactive before earned Wrath. This improves historical class
behavior, but TBC Classic data is not an exact original 2.4.3 simulation and broad
item/vendor prices remain shared. Riding lessons use the purchasing character's
earned-era price with normal reputation discounts and retained IP level
prerequisites. See [expansion progression](docs/changing-expansions.md)
for the milestone chain and [Era Talents](docs/era-talents.md) for client setup,
training, respecs and compatibility limits.

## Earned auction-house economy

Autonomous random bots can now visit auctioneers to list surplus items from their
own bags and buy useful equipment or supplies with their own gold. They retain
quest items and needed equipment, profession materials and supplies. Listings use
normal auction deposits and sale cuts; purchases use the core's ordinary
buyout handling. Auction items and proceeds arrive through normal mail, which
bots collect at a mailbox when delivery and bag space permit. No items or gold
are generated to seed the market.

The default enables `AiPlayerbot.EarnedAuctions = 1` with a five-minute base visit
interval and a per-bot scheduling stagger. Trading requires natural progression
and an autonomous random bot without a player master. Busy bots and bots unable
to reach the NPC must wait.
AH Bot Plus and outgoing shortcut bot mail remain disabled. See
[earned auctions](docs/earned-auctions.md) for settings, migration and limits.

A fresh realm's market takes time to develop: bots need to earn tradable loot,
afford deposits or purchases and reach trading towns. The loop looks for nearby
auctioneers and mailboxes; eligible solo bots from level 10 can also walk to a
compatible auctioneer on the same map within 5,000 yards. Trips have a ten-minute
budget and a fifteen-minute cooldown, and ordinary pathfinding can still fail.
Existing items and gold
are preserved, so updating an older realm cannot prove that every existing
possession was earned. This adds a bounded trading loop; complete farming,
crafting, questing and live-market reliability still require in-game checks.

## Earned-era battlegrounds and social behavior

Bots fill real players' named battleground queues using their own earned levels, equipment, faction and expansion progression. Vanilla characters can queue Warsong Gulch, Arathi Basin and Alterac Valley; earning TBC adds Eye of the Storm, and earning Wrath adds Isle of Conquest. Autonomous all-bot match creation remains disabled. Fresh level-1 bots must level and earn expansion access before they qualify.

About 35% of random bots are assigned earned caps at 19, 29, 39, 49, 59, 69 or 79 (5% each); the rest continue individual progression. They earn every level and retain their own equipment. Capped bots can still farm and participate in eligible activities. Joining a party or activity supplies no catch-up levels, equipment or gold. Level-69 and level-79 residents first earn TBC and Wrath access respectively. See [earned bot brackets](docs/earned-bot-brackets.md) to customize or release caps.

| Battleground | Native level requirement | Earned era required for bot filling |
| --- | --- | --- |
| Warsong Gulch | 10+ | Vanilla or later |
| Arathi Basin | 20+ | Vanilla or later |
| Alterac Valley | 51+ | Vanilla or later |
| Eye of the Storm | 61+ | TBC, tier 8+ |
| Isle of Conquest | 71+ | Wrath, tier 13+ |

`AiPlayerbot.EarnedEraBattlegrounds = 1` enables this policy, with the older `VanillaBattlegroundsOnly` restriction disabled. Matchmaking separates earned eras within each native level bracket, including Vanilla/TBC characters at level 60 and TBC/Wrath characters at level 70. Group queues require every member to qualify and share the same earned era. Normal faction, invitation and team-size requirements still apply; a 2,500-bot population cannot guarantee a match in every bracket.

Selected match rules follow the earned era and remain fixed after players enter:

| Rule | Vanilla | TBC | Wrath |
| --- | --- | --- | --- |
| Arathi Basin victory points | 2,000 | 2,000 | 1,600 |
| Eye of the Storm victory points | Unavailable | 2,000 | 1,600 |
| Alterac Valley starting reinforcements | No countdown | 600 | 600 |
| Warsong Gulch time limit | None | None | Native 25 minutes |
| Warsong Focused/Brutal Assault penalties | Disabled | Native penalties | Native penalties |

The TBC/Wrath flag-carry penalties retain the pinned core's values. These changes
restore selected era rules, without recreating every historical patch version.

Humans unlock Strand of the Ancients and random battleground queues at tier 13,
and arena skirmishes at tier 8, subject to ordinary level/team requirements.
Native rated arenas require level 80, so rated participation needs earned Wrath;
TBC characters capped at 70 can use skirmishes only. TBC matches use Nagrand,
Blade's Edge and Ruins of Lordaeron; Wrath also adds Dalaran Sewers and Ring of
Valor. Bots do not fill Strand, random battlegrounds or arenas: the pinned AI
lacks Strand tactics, and its arena team gathering uses teleport shortcuts.
These human activities need enough ordinary participants.

Battleground participation uses normal core queue invitations and transport. Dead bots release normally, walk to a friendly spirit guide when necessary and wait for the ordinary resurrection wave. The natural progression patch supplies no free equipment, levels or forced resurrection for PvP. Automatic instance strategies and AoE avoidance remain enabled.

Nearby greetings are enabled for real players only, with at most one automated greeting per real player per minute across the bot population. Global random emotes, bot-to-bot greetings, unsolicited channel announcements and toxic-link/Thunderfury meme replies stay disabled. Direct command replies remain available. This uses existing Playerbots behavior; no additional NPC, reward or random-battleground module is required.

Outgoing bot mail commands are disabled because the upstream implementation
bypasses mailbox proximity and normal postage. The earned-auction loop collects
delivered auction mail at a mailbox through normal core handlers. Ordinary
player mail and direct trading remain available. Natural mode also blocks legacy
bot mail-management shortcuts in source, including when old settings are re-enabled.

## AI limits and existing installations

**Limits:** This does not add a complete human-like farming, crafting or questing AI. Bots may get stuck, lack supplies or fail a quest/profession step; disabling teleport recovery increases that possibility. Some upstream encounter scripts, particularly in later expansions, still contain special movement or combat shortcuts and need further audits before a literal zero-shortcut guarantee. The online population is a target, not a performance guarantee. Upstream activity scaling reduces remote bot work when world ticks slow down; combat, instances and bots near or grouped with players remain active. CPU, RAM, storage and the first-run creation workload determine whether your machine can sustain 2,500 loaded characters.

Bot debug logging is disabled by default and log writes run asynchronously. Empty Individual Progression account filters skip repeated database queries and regex construction, while preserving the same progression gates for players and bots.

Progression still runs on the WotLK core and 3.3.5a client. The default historical
module replaces human and bot Vanilla/TBC talent allocation and selected class
spell behavior, with 51/61 earned points at levels 60/70. It does not replace
every combat formula, pet system, low-level quest, profession or world price
with historical data. Individual mode keeps new dual specialization purchases
unavailable below level 80. The native Wrath-tree depth approximation remains a
fallback for a fresh realm deliberately configured without Era Talents; disabling
the module after characters have custom talents needs a separate migration.

AutoBalance counts the non-GM players actually present, including bots. A human plus four bots receives normal five-player dungeon stats; smaller parties use the upstream scaling curve and scaled XP/money, with original creature levels. Outdoor elites and world bosses retain their ordinary difficulty and need suitable companions. Instance scaling does not solve every encounter tactic; full AQ40/Naxx40 bot support is not established. A source/configuration audit cannot establish exact historical class balance or completion of every raid.

See [the configuration audit](docs/vanilla-config-audit.md), included in the ZIP, for the effective settings, module coverage, remaining Vanilla fidelity choices and migration from v1.0.8.

Existing characters keep their levels, inventory, money and progression. Existing active configs also keep their settings; the new defaults do not silently reset an established realm. Back up databases and configurations before migrating an existing realm.

To apply the recommended settings to an existing installation, back up its
databases and configurations, stop the launcher and servers, install the complete
updated server ZIP, update each player's matching EraTalents client files, and run
this once from PowerShell:

```powershell
.\startup.exe --apply-profiles
```

The command backs up every changed config, updates only the settings managed by
the bundled profiles and exits without starting the servers. Database credentials,
paths and unrelated custom settings are retained. Start `startup.exe` normally
afterwards; the normal server updater imports bundled SQL. This command does not
reset characters or databases. Activating historical trees converts talent/spell
state for the character's earned era; see [the migration notes](docs/era-talents.md#updating-an-existing-realm).

## Configuration

After first launch:

| File | Settings |
| --- | --- |
| `configs/worldserver.conf` | Level cap, creation masks, normal rates, data/database paths. |
| `configs/authserver.conf` | Authentication and database connection. |
| `configs/modules/playerbots.conf` | Population, activity, natural progression, earned auctions and bot AI. |
| `configs/modules/individualProgression.conf` | Starting tier, content limit and account exemptions. |
| `configs/modules/mod_era_talents.conf` | Historical human/bot talent trees, earned-era class spell variants and glyph gate. |
| `configs/modules/AutoBalance.conf` | Instance difficulty and reward scaling. |
| `configs/modules/mod_ahbot.conf` | Generated auction-house supply and automated buying; both disabled for earned auctions. |
| `configs/modules/mod_dungeon_clear.conf` | Optional dungeon navigation and queue filling. |
| `configs/modules/mod-quest-loot-party.conf` | Shared normal-quality quest loot and the module's login message. |
| `configs/modules/MultiBotBridge.conf` | Structured addon bridge logging; natural-progression restrictions follow the Playerbots setting. |
| `configs/modules/mod_token_turnin.conf` | Token inventory checks and which group members are included; natural progression blocks shortcut redemption. |
| `mysql/my.cnf` | MySQL/InnoDB tuning generated for the host's RAM. |

Fresh installations use individual progression automatically. To remove an
older realm's global Vanilla/TBC ceiling, install the complete updated server
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

The updated server and `--apply-profiles` replace the older Vanilla-only bot queue restriction with earned-era filling. Existing custom configs otherwise remain unchanged; copying only the launcher cannot add the server queue and match-rule hooks.

For commands and AI behavior, see the [Playerbot wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands). Enabling AH generation, Dungeon Clear or upstream cheat features changes the strict earned-play behavior above.

## Build and release

The [GitHub Actions workflow](.github/workflows/release.yml) tests the launcher,
prepares pinned modules, builds Release binaries and verifies the portable
server ZIP and separate player addon ZIPs. A Linux job builds and verifies the
merged historical client package from pinned sources. A pushed `v*` tag publishes
these assets. Pull requests and pushes to `main` or `codex/**`
review branches create downloadable build artifacts with read-only repository
permissions. New pushes cancel an unfinished build on the same branch.
The workflow checks the portable launcher logic on Linux before starting the
Windows server build, then runs the launcher tests again on Windows.

For a fork, first enable workflows on the repository's [Actions page](https://github.com/Syntax555/mod-playerbots-portable/actions), if GitHub shows the **Enable workflows** button. Enabling them does not replay tags pushed while Actions was disabled. To publish an existing tag, open **Build portable ZIP**, choose **Run workflow** on `main`, enter the tag (for example `v1.0.10`) in **release_tag**, and start the run. It checks out that exact tag and publishes its compiled ZIP only after all build and verification steps succeed. Leave **release_tag** empty to create a downloadable build artifact without publishing a release.

For a local source build, use Windows 10/11 x64, Visual Studio 2022 with the C++ workload, CMake 3.22+, Go 1.26.6+, PowerShell 7+, Git, Boost 1.84+, MySQL Server 8.0 x64 and OpenSSL 3 x64:

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
# Bundle the Visual C++ runtime required by the core and portable MySQL.
pwsh -File scripts/CopyWindowsRuntime.ps1 -DistDir dist
cmake --build build --config Release --target package_zip
cmake -DPACKAGE_VERSION="dev" -P cmake/PackageClientAddons.cmake
```

The native MSVC build defaults to two compiler processes per project. The
environment variable also limits the nested server build to two parallel
projects to reduce peak compiler memory use on the Windows release runner.
For a machine with more memory, change the environment variable and configure
`-DPORTABLE_MSVC_COMPILE_JOBS=<count>` together.

This generates `output/mod-playerbots-portable-dev.zip` and the separate
`output/MultiBot-Chatless-dev.zip` and `output/EraTalents-dev.zip` addon archives.
The required combined `EraTalents-client-dev.zip` is built separately on Linux;
see [the client build instructions](docs/era-talents.md#building-the-client-package).
Subsequent configuration reuses the pinned module cache. Changing a revision or
patch rebuilds the managed module copy;
unmarked module directories are never overwritten. `cmake -P cmake/PrepareModules.cmake`
can also prepare the modules independently.

## Licenses

The portable launcher and build tooling use the [MIT License](LICENSE).
AzerothCore and modules retain their upstream licenses or source notices under
`licenses/` in the ZIP. The bridge's upstream revision has no explicit license
declaration; its NOTICE records provenance without assigning one. The ZIP also
includes the source revision manifest and applied patches so its server sources
can be reproduced. Client data comes from the [wowgaming community](https://github.com/wowgaming/client-data).
