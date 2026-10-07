# Historical talents with earned progression

[Era Talents](https://github.com/lathcf/azerothcore-mod-era-talents) provides
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
as the server. Install them together when updating. The server's
`addons/EraTalents/` folder contains only the addon; use the complete client
package for the required MPQ.

1. Close WoW completely. Use client 3.3.5a, build 12340.
2. Replace `Interface/AddOns/EraTalents/` with the combined package's folder.
   The final path must be `Interface/AddOns/EraTalents/EraTalents.toc`.
3. Copy `Data/patch-V.mpq` into the client's `Data/` folder, replacing a previous
   IP `patch-V.mpq`.
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

The result should contain `EraTalents Gen` and the package generation. If the
addon reports a stale generation, install the matching addon/MPQ pair and fully
restart the client.

## Points, training, respecs and glyphs

The server validates talent purchases against earned era, level-earned budget,
row depth, rank and prerequisites. Native Wrath purchases are blocked while a
historical tree is active. Bots add points to their existing build and use the
full native tree after earning Wrath. `AiPlayerbot.LimitTalentsExpansion = 0`
keeps an older level-based factory limit from restricting that allocation.

Historical trainer spells require ordinary paid purchases with gold, level and
prerequisite checks. Talent and class-quest spells require their earned sources.
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

Back up databases and configs, stop the launcher and servers, then install the
complete server package and matching client package. Run:

```powershell
.\startup.exe --apply-profiles
```

To remove an existing shared Vanilla/TBC ceiling, run
`startup.exe --set-expansion individual` first. Restart normally and allow the
server updater to import bundled SQL. Managed config changes receive backups;
databases, characters and unrelated custom settings are preserved. Applying
profiles restores managed defaults, so make custom edits afterward.

Historical activation converts incompatible native talent/spell state for the
character's earned era and makes its earned points available in that tree.
Valid custom allocations persist on relog. Owned glyphs remain stored. Broad
upstream spellbook cleanup SQL is not applied.

Levels, highest stored tiers, inventory and gold are retained. An update cannot
prove old grants were earned; missing durable boss credit may require another
eligible kill. A fresh realm establishes the creation policy from the start.

GM/console diagnostics `.eratalents status` and `.eratalents doctor` inspect an
online character. Administrative learn/reset commands require GM privileges.

## Building the client package

Sources, the IP base client archive and StormLib are pinned in
[the dependency manifest](../versions.lock.json). Preparation and packaging
include ordered local patch hashes as part of build identity.

On Linux with Git, CMake, a C/C++ toolchain, Python 3/PyYAML, 7z, zlib and bzip2
development libraries:

```bash
cmake -P cmake/PrepareModules.cmake
cmake -DPACKAGE_VERSION=dev -P cmake/PackageEraClient.cmake
```

The result is `output/EraTalents-client-dev.zip`, including the addon, merged
MPQ, dependency licenses and source/hash manifest. Packaging checks generated
rows, generation agreement, preserved base entries and final bytes. See
[building](building.md) for the complete source-build workflow and the
[configuration reference](vanilla-config-audit.md#supported-scope) for gameplay limits.
