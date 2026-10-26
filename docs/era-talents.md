# Historical talents with earned progression

[Era Talents](https://github.com/lathcf/azerothcore-mod-era-talents), built from
[its fork](https://github.com/Syntax555/azerothcore-mod-era-talents), provides
historical trees for players and bots according to their own earned progression.
Level, group leadership and another character's account progress cannot select
a later era.

| Earned progression | Talent system | Earned point budget |
| --- | --- | --- |
| Tiers 0–7 | Vanilla 1.12.1, nine original classes | One per level from 10; up to 51 at 60 |
| Tiers 8–12 | TBC Classic 2.5.4, nine original classes | One per level from 10; up to 61 at 70 |
| Tier 13+ | Native Wrath | Normal core rules |

The talent window and server effects change together. Historical passives,
abilities and selected class spell variants are supported. Other combat formulas
and class subsystems still use the Wrath core. TBC Classic 2.5.4 includes later
balance changes, including paladin seals, and is not exact original 2.4.3 balance.
Existing death knights retain native trees; strict mode blocks new hero characters.

## Install the matching client files

Every player needs the addon and merged MPQ from `EraTalents-client-latest.zip`
in the same [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
as the server. Install the matching pair whenever updating client files. Client
packages are separate downloads; the server updater does not install them or
modify WoW client folders.

1. Close WoW completely. Use client 3.3.5a, build 12340.
2. Replace `Interface/AddOns/EraTalents/` with the combined package's folder.
   The final path must be `Interface/AddOns/EraTalents/EraTalents.toc`.
3. Copy `Data/patch-V.mpq` into the client's `Data/` folder, replacing that file
   if present. The package's `README.txt`, `SOURCE_MANIFEST.json` and `licenses/`
   describe the package and are not needed in the client.
4. Restart WoW, enable EraTalents in the AddOns menu and open the normal talent
   window. Native Wrath talents return when that character earns tier 13.

`/reload` cannot replace an MPQ. Other later-loading DBC patches can override
these rows, so keep a consistent client patch set. Bots need only the server
binaries and SQL.

The package merges historical spell and skill rows into IP's pinned client
archive and preserves its other entries byte for byte, including restored
world/DBC support. Client and server share a generation marker recorded in
`README.txt` and `SOURCE_MANIFEST.json`. To inspect the client's marker in game:

```lua
/run print(GetSpellInfo(932999))
```

The result should contain `EraTalents Gen` and the package generation in every
client locale. If the addon reports a stale generation, install the matching
addon/MPQ pair and fully restart the client.

To try an addon change without a server build, the fork's
[Latest release](https://github.com/Syntax555/azerothcore-mod-era-talents/releases/latest)
offers `EraTalents-addon-latest.zip` with the `EraTalents/` folder of its
`main` branch. It contains no MPQ; keep the MPQ of the client pack that matches
the server.

### Client language

German (`deDE`) clients automatically use German talent names, rank descriptions,
tree labels and addon messages. The matching MPQ also includes German names,
spellbook descriptions and aura text for the custom historical spells. Keep
your German client; no language setting or additional translation pack is needed.

English clients retain English text. Other client locales use the authored
English fallback. Translation follows the historical effects and rank values;
it does not substitute descriptions from a different expansion. Other game
and module text follows the translations available in those components.

### DragonUI

[DragonUI](https://github.com/NeticSoul/DragonUI)'s talent module replaces the
talent window; install it from its
[fork's Latest release](https://github.com/Syntax555/DragonUI/releases/latest). EraTalents works with it automatically; the module can stay
enabled:

- For a Vanilla or TBC character, the talent key, the micro-button and
  `/talents` open the historical trees inside DragonUI's talent window, with
  its talent nodes, prerequisite connections and search. Vanilla uses seven
  rows and TBC nine; ranks, remaining points and learning use EraTalents data.
  Learned partial ranks are gold when no point can be spent; reachable talents
  remain green while the owner can buy another rank.
- DragonUI keeps the pet tree (`/pettalents` opens it) and characters on
  native Wrath trees. Its glyph page opens once the character has earned
  Wrath; before that the glyph key, the glyph tab and using a glyph show a
  notice instead.
- Inspecting a character with a historical tree shows it read-only in the
  same DragonUI talent window. MultiBot's talent button opens that window for
  the selected bot; controlled group altbots can spend their earned points
  there. Other targets keep DragonUI's native inspect view. Without DragonUI,
  historical trees use EraTalents' own window and the standard inspect tab.
- DragonUI's spellbook shows the spells still to learn, and its level-up
  notice the new class spells, from the character's own class trainer list on
  this server. The list follows the earned era, talents and class quests and
  shows level, base cost and any required talent or spell.
- The level-up notice lists riding at this realm's trainer levels and leaves
  out dungeons, raids and heroic modes of a later expansion than the
  character's earned era. Raid progression and attunements still apply on
  entry. DragonUI's own fixed lines remain: Dungeon Finder and glyphs at 15,
  dual specialization at 40 and glyph slots at 30, 50, 70 and 80.
- With MultiBot, a bot's spellbook opens in DragonUI's book while DragonUI's
  spellbook module is enabled: the same window, General and class tabs,
  two-page spreads, talent-tree sections, search and paging, filled with the
  bot's spells and the trainer spells it can still learn on this server, with
  their level and cost. Left-click casts, right-click creates a macro and
  shift-click adds the spell to MultiBot's skip list or removes it.

Update DragonUI and the EraTalents addon together from their forks' Latest
releases. Keep the MPQ from the client package matching your server's data
generation. Disabling DragonUI's talent module also restores the standard route.

## Points, training, respecs and glyphs

The server validates talent purchases against earned era, level-earned budget,
row depth, rank and prerequisites. Native Wrath purchases are blocked while a
historical tree is active. Random bots add points to their existing build and use
the full native tree after earning Wrath. A new historical build follows the PvE
spec weights in `Playerbots.RandomClassSpecProb`, including feral cat druids.
`Playerbots.LimitTalentsExpansion = 0` disables the level-based factory limit
for that allocation. Altbots and SelfBot characters keep unspent points for their
owner to spend.

With the matching MultiBot and EraTalents addons, use the grouped altbot's talent
button to open its Vanilla or TBC tree. Click a talent to buy one rank with that
bot's unspent points; the displayed ranks and remaining points update from the
server's reply. The bot must be under your control, in your group and within
normal inspect range. Other characters' trees remain read-only.
With automatic [combat profiles](combat-profiles.md), a different specialization
refreshes the bot's class strategies and equipment preferences outside combat.
MultiBot also allows an explicit profile without spending the bot's talent points.

Historical trainer spells require ordinary paid purchases with gold, level and
prerequisite checks. Talent and class-quest spells require their earned sources.
Class lessons that TBC or Wrath introduced, such as Victory Rush, Shiv or Wind
Shear, stay unavailable until the character has earned that expansion; the
trainer window, bot training and the spellbook's trainer list follow the same
rule. Lessons a character already knows stay known.
Known spell variants transfer on an era conversion; ambiguous collapsed ranks
are mapped conservatively without awarding every rank allowed at that level.

Ordinary respecs use the class trainer: 1g, 5g, 10g, then 5g steps to 50g, with
the core's monthly cost decay. A successful reset charges once and records
normal cost history. Bots do not receive routine free resets on login, leveling
or maintenance. Administrative no-cost resets remain GM operations.

A genuine Vanilla→TBC or TBC→Wrath crossing refunds the departing tree's earned
points once. In combat it waits until combat ends and rechecks the earned era.
Relogs and repeated era checks preserve the allocation. The transition grants
no levels, trained ranks, equipment or gold.

Glyph effects and new glyph use are blocked before earned Wrath. Owned glyph
IDs remain stored in both specializations and become usable in Wrath. Riding
lesson prices also follow earned era; general prices and the auction market
remain shared. See [training and prices](changing-expansions.md#era-talents-training-and-prices).

## Configuration

The active file is `configs/modules/mod_era_talents.conf`:

```ini
EraTalents.Enable = 1
EraTalents.Debug = 0
EraTalents.BotTalents = 1
EraTalents.GlyphGate = 1
EraTalents.AdvanceGossip = 0
```

`AdvanceGossip` is a compatibility key; force-advance gossip is inactive. Earned
IP boss/quest paths remain authoritative. Strict milestones require the default
IP chain, with `CustomProgression` empty and `DisableDefaultProgression = 0`.

A fresh realm can explicitly choose native Wrath trees before characters
accumulate historical allocations. Disabling historical mode on an established
realm requires a separate talent/spell migration; an in-place toggle is not a
supported conversion.

## Updating an existing realm

See [realm updates](changing-expansions.md#updating-an-existing-realm) for
server updates, realm ceilings and preserved progress, and install the matching
client package for each player.

Historical activation converts incompatible native talent/spell state for the
character's earned era and makes its earned points available in that tree.
Valid custom allocations persist on relog. Owned glyphs remain stored. Broad
upstream spellbook cleanup SQL is not applied.

GM/console diagnostics `.eratalents status` and `.eratalents doctor` inspect an
online character. Administrative learn/reset commands require GM privileges.

## Building the client package

Sources, the IP base client archive and StormLib are pinned in
[the dependency manifest](../versions.lock.json). Era Talents is pinned as a
commit of [its fork](https://github.com/Syntax555/azerothcore-mod-era-talents);
preparation and packaging include the hashes of the remaining ordered local
patches as part of build identity.

From a source checkout on Linux with Git, CMake 3.25 or newer, a C/C++ toolchain,
Python 3/PyYAML, 7z, zlib and bzip2 development libraries:

```bash
cmake -P cmake/PrepareModules.cmake
cmake -DPACKAGE_VERSION=dev -P cmake/PackageEraClient.cmake
```

The result is `output/EraTalents-client-dev.zip`, including the addon, merged
MPQ, dependency licenses and source/hash manifest. Packaging checks generated
rows, generation agreement, preserved base entries and final bytes. See
[building](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md)
for the complete source-build workflow and the
[configuration reference](configuration.md#supported-scope) for gameplay limits.
