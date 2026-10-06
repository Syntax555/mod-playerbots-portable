# Vanilla configuration and module audit

Reviewed on 5 October 2026 against portable v1.0.8 (`2ef9230`), its exact locked sources and the generated patched modules. The follow-up changes described below affect configuration profiles and documentation. No CMake configuration, compilation, server start, SQL import, release tag or release was performed for this audit.

## Scope and effective configuration

The review combines the complete shipped templates with the launcher's managed profiles. Existing user installations retain custom values until deliberately changed; their active files and database were not available for this review.

| Configuration | Template settings | Managed settings after this audit |
| --- | ---: | ---: |
| `worldserver.conf` | 591 | 45 |
| `authserver.conf` | 36 | 0 |
| `dbimport.conf` | 25 | 0 |
| `playerbots.conf` | 894 | 125 |
| `individualProgression.conf` | 63 | 24 |
| `AutoBalance.conf` | 254 | 13 |
| `mod_ahbot.conf` | 448 | 3 |
| `mod_dungeon_clear.conf` | 117 | 8 |

All 2,428 template assignments were inventoried. All 218 managed assignments use known template keys, with no duplicate profile keys. This is a configuration validity check, with source review of relevant behavior; it does not mean every unused optional feature received a gameplay test. IP also applies runtime overrides: a 60-second breath timer, disabled low-level regeneration boost, enabled player settings, disabled item DBC attribute enforcement, monster sight 80, and hidden object quest markers/sparkles. These overrides were reviewed separately from the merged file assignments.

`authserver` and `dbimport` retain ordinary template defaults, with connection information, source/data paths and loopback bindings supplied by the launcher. The generated MySQL configuration binds to loopback, reserves roughly one quarter of detected RAM for its buffer pool (512 MiB to 8 GiB), and leaves memory for worldserver and bots. No database or credential migration is part of this audit.

## Confirmed configuration corrections

| Setting | Follow-up value | Reason |
| --- | --- | --- |
| `Rate.Talent`, `Rate.Talent.Pet` | `1` | Keep ordinary earned core talent points; this is not a replacement for historical talent data. |
| `MinDualSpecLevel` | `80` | Prevent new dual-specialization purchases during the level-60 phase. Existing specializations are retained. |
| `NoResetTalentsCost` | `0` | Normal paid trainer respecs; automatic bot template resets use a separate internal path. |
| `AlwaysMaxSkillForLevel`, `AlwaysMaxWeaponSkill` | `0` | Skills must improve through ordinary use. |
| `MaxPrimaryTradeSkill` | `2` | Ordinary profession limit. |
| Bot ground/fast-ground/flying mount minimum | `40 / 60 / 70` | Match IP's actual paid trainer/item requirements rather than inherited Wrath thresholds. |
| `AiPlayerbot.BotSendMailEnabled` | `0` | Upstream bot mail bypasses mailbox proximity and normal postage. Human mail and direct trading remain available. |
| All 34 `AiPlayerbot.BroadcastChance*` settings | `0` | Prevent unsolicited event, suggestion, guild-management and meme announcements across 2,500 bots. Scoped greetings and command replies use separate paths. |
| `AiPlayerbot.EnableBroadcasts` | `1` | Keep its random-range initialization valid; the unguarded upstream Thunderfury helper assumes a positive range. Zero event chances suppress output safely. |
| `IndividualProgression.DisableDefaultProgression`, `CustomProgression` | `0`, empty | Keep the normal earned progression chain. |
| IP Vanilla damage/healing, `BotOnlyAdjustments` | `1.0 / 1.0`, `0` | A shared output policy for humans and bots; no unmeasured extra global nerf stacked with party scaling. |
| `IndividualProgression.EnforceGroupRules` | `0` | Allow recruiting bots at different earned tiers; each character still meets their own content/quest/item gates. |
| `IndividualProgression.EnableAllSpellRanks` | `0` | Keep IP's default legacy-rank restriction for later Wrath progression; this flag is inactive during Vanilla and does not block later low-level spells. |
| AutoBalance normal/heroic dungeon and raid minima, difficulty offset | All minima `1`, offset `0` | Count the actual non-GM occupants, including playerbots, without an artificial count offset. Explicit heroic floors also cover restored Vanilla raids using an internal heroic difficulty. Existing per-instance overrides still take precedence. |

Mail behavior is established in [SendMailAction.cpp](https://github.com/mod-playerbots/mod-playerbots/blob/037c01418b5d01506917a3db9b44fd56ac5f965c/src/Ai/Base/Actions/SendMailAction.cpp), including the enable check before item/money handling. Broadcast probabilities and the separate Thunderfury path are in [BroadcastHelper.cpp](https://github.com/mod-playerbots/mod-playerbots/blob/037c01418b5d01506917a3db9b44fd56ac5f965c/src/Util/BroadcastHelper.cpp). IP restores the riding trainer levels and costs in [mounts_and_riding.sql](https://github.com/ZhengPeiRu21/mod-individual-progression/blob/60336b349cce2bc209d154bb840f2370f1cc16f2/data/sql/world/base/mounts_and_riding.sql). Actual group/guild invitation messages can still appear through a separate path; the profile does not mute ordinary command responses or every social interaction.

## Individual Progression is correctly limited to Vanilla

The required policy remains:

- Enabled; starting tier `0`, progression limit `7` (completed Vanilla Naxxramas). Tier `8` starts TBC; a limit of `0` means unlimited.
- Core and random-bot maximum level `60`; fresh humans and bots start at level `1` with ordinary earned resources.
- Empty bot/excluded account regexes. Random bots receive normal attunement and boss progression instead of class-spell grants, account exemptions or leader-tier copying.
- Blood elves, draenei and death knights blocked by core creation masks, with IP expansion unlock tiers `8` and `13`.
- Core `Expansion = 2` retained for restored map 533. Changing it to `0` is not the correct way to enforce this IP setup.
- Core Dungeon Finder mask `0`, IP `DisableRDF = 0`. Setting IP's flag to `1` would overwrite the fully disabled core mask with `4`.
- Early Dungeon Set 2/Scourge bosses and reputation administration commands disabled. The module's default Molten Core rune/quest requirements and Naxx mechanics retained.

Every IP template key has a corresponding source configuration consumer. Its base SQL is already included in the distribution; no additional progression or AQ war-effort module is required. IP supplies a personal war-effort completion route after the faction's collection quests.

Naxx40's SQL-backed map difficulty has `MaxPlayers = 40` on difficulty 2; the custom entrance selects that mode. Core loads the SQL DBC override, so AutoBalance uses the 40-player capacity rather than incorrectly treating the restored raid as a ten-player instance. This is source/data-input verification, not an inspection of the user's running database.

## Talents and class balance are not original 1.12 rules

**51 earned talent points at level 60 are correct. The talent identities, trees and effects remain Wrath.** Vanilla's end-of-tree talent required 31 points in that tree; a 51-point total was distributed across trees. The current core instead lets a human invest those 51 points into a Wrath tree and obtain a Wrath capstone.

`AiPlayerbot.LimitTalentsExpansion = 1` only restricts the depth of bot talent templates approximately to the seven-row/31-point tier. It does not recreate old talent identities, provide a global human talent gate, or fully constrain fallback allocation. Humans also retain Wrath glyphs and pet talent trees; natural bots receive no generated glyphs and limit pet talent auto-allocation. Consequently, the current setup must not be advertised as equal original-1.12 talent rules for humans and bots.

Automatic bot talent allocation also calls the factory with `reset = true`, which internally performs a free talent reset. `NoResetTalentsCost = 0` controls normal trainer respecs, not that AI path. Simply disabling `AutoPickTalents` would leave naturally levelling bots without their automatic talent allocation. A future code correction should spend new earned points incrementally without resetting previously chosen talents; this audit does not change that source behavior or claim a complete zero-shortcut talent implementation.

IP restores many class quest/book acquisitions, professions, mounts, items and dungeon rules. Some later low-level skills and professions remain, including Wrath class abilities and Inscription/Jewelcrafting. Its optional archives contain profession/reagent or Spell DBC overrides plus paired client patches; none contains `Talent.dbc` or `TalentTab.dbc`.

Original Vanilla talent trees need a coordinated client/server data, spell and bot-template/rotation implementation. There is no verified drop-in maintained module for that with this exact core/module pair. A server configuration toggle cannot perform the conversion.

Do not import IP's optional expansion-spell SQL unchanged: it ends with a fixed `USE acore_characters` and deletes existing learned spells. Selected trainer restrictions would need a separate world-only policy and AI review. Likewise, optional DBC/MPQ pairs require matching client and server changes; they are not silently applied by this portable launcher.

IP documents approximate damage `0.5–0.6` and healing `0.5` adjustments as tuning options. They do not establish per-class historical balance. The reviewed profile keeps both at `1.0`, applied equally to humans/bots, rather than claiming an arbitrary global nerf has recreated Vanilla. Actual class/encounter tuning remains a separate gameplay decision.

## Solo play and module coverage

At the original audit, the existing core/module/addon pins matched their stable/default upstream heads in fresh checks on 5 October 2026. The later Chatless replacement and added modules are recorded in the addendum below and in [module-versions.md](module-versions.md). They cover the necessary systems for one human with companions:

| Component | Policy |
| --- | --- |
| Playerbots | Enabled, natural earned progression, local companions and ordinary groups, human-triggered Vanilla BGs. |
| Individual Progression | Enabled, earned Vanilla tier gates and restored content. |
| AutoBalance | Enabled for instances, original creature levels, normal full-party stats, smaller-party scaling with matching XP/money scaling. |
| AH Bot Plus | Included but seller/buyer off: they generate supply and synthetic demand. |
| Dungeon Clear | Included but off: scripted navigation teleports and filler/recovery shortcuts conflict with the current policy. |
| MultiBot (original audit) | Client control UI, subsequently replaced by MultiBot Chatless and its server bridge. |

Do not add SoloCraft alongside AutoBalance: it buffs player stats/spellpower, restores health/mana and modifies XP while AutoBalance already reduces instance enemies. Solo Dungeon Finder adds no value when RDF is disabled. NPC buffers and generated bot/gear services conflict with earned play; extra AQ/PvP reward modules duplicate IP systems.

AutoBalance counts the actual non-GM players in an instance, including bots. One human plus four bots therefore receives ordinary five-player creature stats. Its default curve gives approximately `12.4%` of the ordinary creature health/damage multiplier with one occupant in a five-player dungeon, before any creature-specific overrides. This is a curve calculation, not proof every class can solo every mechanic. Scaling is locked against reducing party count mid-combat and reduces XP/money for scaled-down encounters.

Outdoor elites and world bosses remain at ordinary world difficulty. Suitable earned companions are the intended solution; a second outdoor/solo scaler would change that policy.

**No autonomous earned-item auction economy is implemented in this Playerbots revision.** Its auction-listing function is commented out; `ITEM_USAGE_AH` is an inventory valuation category that vendor selling also consumes. Humans can use the ordinary AH, but with one human and synthetic AH operations off there is no verified bot supply/demand. A real earned auction AI would require separate source work using existing inventory, normal deposits/cuts and available gold. Earlier wording that ordinary bot activity supplies the AH has been corrected.

Raid AI has concrete compatibility boundaries. For example, the specialized Onyxia whelp action recognizes entry `11262`, whereas IP's restored whelps use `301001`. Generic combat may still attack them, but that is not complete encounter support. AQ40 and restored Naxx40 coverage is also incomplete/unverified. AutoBalance cannot supply missing positioning or mechanic tactics. Optional Naxx mechanic simplifications, early no-cooldown Quintessence, removed Garr adds and fortyfold AQ reputation/drop boosts remain unapplied.

## Applying the audited profiles

The published **v1.0.8 ZIP remains unchanged**. `startup.exe` embeds its profiles at compile time; the v1.0.8 `--apply-profiles` command still applies its earlier defaults and does not read replacement source profiles from `defaults/`.

The reviewed profiles are in the v1.0.9 sources. After downloading that version's compiled ZIP, stop the servers, extract it into the existing installation and run `startup.exe --apply-profiles` once. The new launcher applies its embedded profiles, creates config backups and exits without starting the services. No existing character, inventory, spellbook or progression state is reset.

Alternatively, individual values can be applied manually to the corresponding active configuration files after stopping the servers and backing up those files. These short profiles are overlays, not complete replacement configurations. Preserve database connection strings, ports, paths and unrelated custom values. Exact 1.12 talents, broader class restoration, an earned auction AI and targeted raid compatibility fixes remain separate implementation choices.

## v1.0.10 addendum: Quest Loot Party

Added at the user's request after the v1.0.9 configuration audit. The original author's [mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party/tree/6f073c1bef1bba1aa73787d1e30db7429f2b1c7b) is pinned to `6f073c1bef1bba1aa73787d1e30db7429f2b1c7b`, the upstream default branch head checked for this integration. All previous core, module and addon pins remain unchanged.

Its shipped template is `configs/modules/mod-quest-loot-party.conf.dist`; the launcher creates `mod-quest-loot-party.conf` with `QuestParty.Enable = true` and `QuestParty.Message = false`. These two known template settings bring the managed total to 220 assignments across seven profiles and the complete template inventory to 2,430 assignments across nine templates.

The source marks only normal-quality entries passing through the core's quest-loot list as free-for-all. The pinned core already provides `OnPlayerBeforeFillQuestLootItem`; its existing loot code determines eligibility, creates per-player loot slots and checks inventory when an item is taken. A qualifying party member must still loot the corpse. This preserves drop rolls, ordinary equipment loot, quest prerequisites and earned progression. It intentionally changes party quest-item distribution; it does not recreate original Vanilla loot rules or guarantee every quest item's sharing, since higher-quality quest items are unchanged.

Playerbots use the ordinary player/corpse loot path, so the feature applies to eligible bots as well as humans. Quest synchronization remains disabled. No automatic bag delivery, forced drop chance or general personal equipment loot from broader forks is included. The module's SQL only installs its scoped login-message translations; it does not alter character state or loot tables. Its SQL and upstream AGPL license are included in the ZIP and handled by the existing packaging/database updater.

For an existing installation, stop the servers, extract the v1.0.10 ZIP into the installation and run its new `startup.exe --apply-profiles` once. Missing module configurations are created from the new template; an existing configuration is updated with a backup. Characters, inventory and progression are preserved.

## Chatless and token turn-in addendum

The current sources replace `Macx-Lio/MultiBot` with the matching
`Wishmaster117/MultiBot-Chatless` addon and `Wishmaster117/mod-multibot-bridge`
server module, and add `Zerathane/mod-token-turnin`. Their exact upstream heads,
checked on 5 October 2026, are pinned in `versions.lock.json` and summarized in
[module-versions.md](module-versions.md). Existing server module revisions were
already current and remain unchanged.

Players can download `MultiBot-Chatless-<version>.zip` separately from the server
ZIP. Both contain the same pinned addon, installed as `Interface/AddOns/MultiBot/`.
Replace the old client folder completely. This project remains mostly chatless:
some upstream UI controls still use scoped legacy Playerbots commands.

The bridge's new `mod-multibot-bridge-natural-progression.patch` follows
`AiPlayerbot.NaturalProgression` on the server. It applies these restrictions:

- Custom talent application and preset specialization writes are rejected,
  because upstream rebuilds talent templates without an ordinary paid trainer
  reset. Existing earned talents and automatic talent selection are retained.
- Bridge trainer purchases require authorization and the bot's normal NPC
  interaction range. Purchases run through the core trainer handler, including
  costs, prerequisites and progression hooks. Remote manual spell grants are
  unavailable in strict mode.
- Personal bank transfers, including exact deposits, require the bot to be
  within ordinary banker interaction range and use the core's validated item
  storage APIs. The bridge corrects quest-item accounting when depositing items
  and withdrawing into an existing stack; capacity failures retain their reason
  and partial transfers report the amount actually moved. Guild-bank actions retain their
  existing core interaction and membership/withdrawal checks.
- SelfBot autogear and maintenance shortcuts are rejected even if their
  individual command settings are later enabled.

Rejected shortcuts return `NATURAL_PROGRESSION` to the addon. Roster/inventory
inspection and normal resource-consuming actions remain available. Existing
Playerbots restrictions still block free summoning, quest synchronization,
generated gear/gold and cheat masks. This is a targeted integration audit, not
a guarantee that every upstream action or encounter is free of shortcuts; the
earlier AI and Vanilla class-system limitations still apply.

`MultiBotBridge.conf` disables console logs. `mod_token_turnin.conf` enables the
module with `IncludeSelf = 0` and `IncludeRealPlayers = 0`, so token checks target
grouped bots rather than altering a human teammate's possessions.

Upstream Token Turn-in directly awards gear and destroys tokens, intentionally
waiving normal AQ/Naxx reputation and extra materials. Its
`mod-token-turnin-natural-progression.patch` therefore blocks `.tokenturnin redeem`
before any character is processed while natural progression is enabled, with a
second guard in the conversion function. `.tokenturnin check` remains a read-only
inventory/spec mapping preview and explicitly states that it does not verify
normal exchange eligibility. Bots still have to farm every required item, earn
reputation and complete the original quest/NPC exchange.

The release build prepares both modules with the other pinned sources, includes
their configuration templates, token SQL, provenance/licenses and local patches,
and embeds the two new profiles into the launcher. Its separate addon asset is
verified against every prepared file, including textures, the 3.3.5a TOC, license
and source revision. Preparation re-exports the addon from its immutable cached
Git revision, and packaging independently compares every asset against that
revision before creating the player ZIP. The server ZIP verifier also checks
every addon byte and rejects obsolete SQL migrations. Assembly replaces only
generated SQL exports, preserving live databases and active configs.
Existing configurations require the new launcher's
`--apply-profiles` command to apply the recommended settings with backups;
characters and databases are preserved.

Local verification includes forward/reverse patch checks, C++20 syntax compilation
of all four new module source files against the pinned core and patched Playerbots
headers, Windows launcher/test cross-compilation and vet, native launcher tests
with race detection, standalone addon verification and 45 positive/negative
assembly/ZIP regression checks. The workflow runs the launcher and packaging
checks before compiling, smoke-testing and packaging the Windows server.
Live in-game verification remains unperformed in this Linux workspace.

## Expansion phase switch addendum

The launcher now supports `--set-expansion vanilla|tbc|wotlk` and
`--show-expansion`; see [changing-expansions.md](changing-expansions.md).
Selecting a later phase changes the linked caps, map lists and creation masks
with config backups. The selected phase survives `--apply-profiles` and
missing-config creation. No characters or databases are reset; earned tier
requirements remain active for bots and humans.

The Individual Progression patch also restores an already-rewarded **Into the
Breach** transition when the character has earned tier 7 and the realm's limit
allows tier 8. This resolves a quest completed while TBC was still locked.
The existing raid-achievement recovery remains, and no unearned levels, loot,
quest completions or reputation are granted. The original v1.0.11 server does
not include this added recovery path; use updated server binaries for it.
