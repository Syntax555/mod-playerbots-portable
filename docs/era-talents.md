# Historical talents with earned progression

The portable default enables [mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents)
with local earned-progression adaptations. Humans and bots use historical
Vanilla/TBC trees according to **their own earned Individual Progression tier**.
Their level, group leader and account's best character cannot choose a later era.

| Character progression | Talent system | Earned point budget |
| --- | --- | --- |
| Tiers 0–7 | Vanilla 1.12.1 trees for the nine original classes | One per level from 10; up to 51 at 60 |
| Tiers 8–12 | TBC Classic 2.5.4 trees for the nine original classes | One per level from 10; up to 61 at 70 |
| Tier 13+ | Native Wrath trees | Normal core talent rules |

The talent window and server effects change together. The module implements
historical passives, abilities and selected class spell variants, with small core
compatibility patches for effects handled in core code. It does not recreate
every original combat formula or class subsystem. In particular, TBC Classic
2.5.4 includes later balance changes, including paladin seal changes, so this is
not an exact original 2.4.3 class-balance simulation. Existing death knights keep
native trees; strict progression blocks creation of new level-55 hero characters.

## Install the matching client files

Every human player needs **both** the EraTalents addon and merged MPQ for the
default historical profile. Use `EraTalents-client-<version>.zip` from the same
release or Actions build as the server. The server ZIP's `addons/EraTalents/` and
standalone `EraTalents-<version>.zip` contain the addon alone; they do not replace
the combined client package.

1. Close WoW completely.
2. Remove an old `Interface/AddOns/EraTalents/` folder, then copy the combined
   package's `Interface/AddOns/EraTalents/` into the corresponding client folder.
   The final path must be `Interface/AddOns/EraTalents/EraTalents.toc`.
3. Copy the package's `Data/patch-V.mpq` into the client's `Data/` folder, replacing
   a previous IP `patch-V.mpq`. Use WoW 3.3.5a, build 12340.
4. Restart WoW and enable EraTalents in the AddOns menu. Open the normal talent
   window/key; the addon provides the Vanilla/TBC trees and native Wrath returns
   when that character earns tier 13.

`/reload` cannot load or replace an MPQ. Another later-loading client DBC patch
can override these rows, so use a consistent client patch set. Bots have no WoW
client and need only the matching server binaries and SQL.

The package is built by merging the historical module's generated
`Spell.dbc` and `SkillLineAbility.dbc` rows into the pinned IP client archive. Other
IP client patch entries are retained and verified byte for byte. This includes
the base patch's restored world/DBC support; replacing it with an unrelated
talent-only archive can lose that support.

The client and server use the same generation marker. The combined ZIP's
`README.txt` and `SOURCE_MANIFEST.json` record it. In game:

```lua
/run print(GetSpellInfo(932999))
```

The result should contain `EraTalents Gen` and the package generation. The addon
also reports a stale generation. Fix the addon/MPQ pair and fully restart the
client rather than trying to change server progression to clear the warning.

## Points, training, respecs and glyphs

Bot allocation adds newly earned points to the existing tree. Login, level
changes, factory maintenance and ordinary refresh do not give bots a free respec.
Bots' specialization and spell-resolution bridges recognize historical talents
and their known class spell variants. At earned Wrath, bot allocation uses the
full native tree even if the character is still level 70. The portable profile
sets `AiPlayerbot.LimitTalentsExpansion = 0`: earned progression, rather than
the older level-based factory limit, selects and validates the tree.

The server validates each talent purchase against its era, level-earned budget,
row depth, rank and prerequisites. It blocks native Wrath talent purchases while
a historical tree is active. Neither the addon nor a crafted talent packet can
supply extra points or bypass the authoritative checks.

Historical trained spells are available through normal trainer purchases, with
their gold, level and prerequisite checks. Talent spells require the appropriate
earned talent; class-quest spells require their actual earned source. Level alone
does not award trainer ranks. Legitimately known variants can transfer on an era
conversion, with ambiguous later collapsed ranks mapped conservatively rather
than granting every older rank allowed at the character's level.

Ordinary historical respecs use the class trainer's normal reset path. The native
cost history is retained: 1g, 5g, 10g, then 5g steps to 50g, with the core's monthly
decay. A successful paid reset charges once and records the ordinary reset
history. Administrative no-cost resets remain GM operations.

An actual earned Vanilla→TBC or TBC→Wrath crossing refunds the departing tree's
earned points once so they can be spent in the new tree. It grants no levels,
equipment or gold. A crossing detected during combat waits until the character
leaves combat, then rechecks its actual earned era. Ordinary relogs and repeated
era checks do not reset an existing allocation. There is no faction-leader
advance gossip or manual progress-copy shortcut.

Glyph effects and new glyph use are blocked until earned Wrath. Existing glyph
IDs remain stored in both specializations; their client slots/effects are
suppressed in earlier eras and the owned active-spec glyphs become usable again
in Wrath. The gate does not destroy a paid glyph or generate a replacement.

Riding lesson prices also follow the purchasing character's earned era, with
normal reputation discounts and unchanged trainer level prerequisites. Other
item/vendor and trainer prices remain shared; the
[expansion guide](changing-expansions.md#era-talents-training-and-prices) lists the
riding prices and their limits. The auction house stays one market using owned
items, earned gold and ordinary fees rather than separate generated era stock.
Battleground queue access and match rules also follow earned progression; see
[earned bot levels and PvP brackets](earned-bot-brackets.md#waiting-for-battlegrounds).

## Configuration

The launcher applies these defaults to a missing configuration, or when the
updated launcher's `--apply-profiles` command is requested:

```ini
EraTalents.Enable = 1
EraTalents.Debug = 0
EraTalents.BotTalents = 1
EraTalents.GlyphGate = 1
EraTalents.AdvanceGossip = 0
```

The active file is `configs/modules/mod_era_talents.conf`.
`AdvanceGossip` is retained as a compatibility key; force-advance gossip is
inactive. The normal IP boss/quest paths remain authoritative. Strict milestones
also require the normal default chain: the portable profile enables IP, leaves
`CustomProgression` empty and disables `DisableDefaultProgression`.

A deliberately configured fresh realm can omit historical mode and use the
native Wrath-tree depth approximation. This requires an explicit choice before
characters accumulate custom trees. Disabling the module on an established
historical realm needs a separate talent/spell migration; an in-place toggle is
not a supported conversion back to native trees.

## Updating an existing realm

Back up the databases and configurations, stop the launcher and servers, install
the complete updated server ZIP, install the same build's client package, then
run:

```powershell
.\startup.exe --apply-profiles
```

If an older shared Vanilla/TBC ceiling should be removed, run
`startup.exe --set-expansion individual` before applying profiles. Restart the
launcher normally and let the server's ordinary updater import the bundled
world/character SQL. The profile command backs up changed settings and does not
reset databases or characters. Existing custom configuration otherwise survives
an upgrade, so copying binaries alone does not activate every new default.

Existing levels, highest stored progression tiers, money and inventory are
retained. Activating historical mode replaces incompatible native talent/spell
state for the character's earned era and makes the level-earned points available
in the historical tree. Existing valid custom allocations are preserved on relog.
Owned glyphs remain stored. Broad upstream character-spell cleanup SQL has been
neutralized; conversion is handled for the character's actual era instead.

The update cannot prove that old equipment, gold, tiers or trained spells were
originally earned. It does not erase those characters to manufacture that claim.
New strict boss credit records future eligible encounters, and missing future
milestones may need another kill. A fresh realm establishes the new level-1,
tier-0 policy from creation.

For diagnostics, a GM or the worldserver console can use `.eratalents status`
and `.eratalents doctor` on an online character. Administrative learn/reset
commands are deliberately privileged and should not be used as normal gameplay.

## Building the client package

The portable workflow uses pinned sources and local patches rather than the
upstream bootstrap script or mutable branch heads. `versions.lock.json` records
the era module, IP base client archive and StormLib revisions. Module/addon
preparation and independent packaging checks also include the ordered local
patch hashes, so the upstream revision alone is not the complete build identity.

On Linux, provide Git, CMake, a C/C++ toolchain, Python 3 with PyYAML, 7z, zlib and
bzip2 development libraries, then run from the repository:

```bash
cmake -P cmake/PrepareModules.cmake
cmake -DPACKAGE_VERSION=dev -P cmake/PackageEraClient.cmake
```

This writes `output/EraTalents-client-dev.zip`. It includes the addon, merged MPQ,
dependency licenses and source/hash manifest. The packager verifies generated
spell/skill rows, preserves the IP base entries and checks every packaged byte.
The Linux Actions job builds the same client asset; the Windows job builds the
portable server and standalone addon assets. Old release tags without the client
packager remain supported by capability checks.

Source fixtures and actual-core compilation check integration, persistence,
earned transitions, bot allocation, paid training and glyph handling. Native
client packaging is independently verified and repeatable. These checks do not
establish exact historical class balance, every raid's bot tactics or live realm
performance; see [the audit](vanilla-config-audit.md#strict-milestones-and-historical-talents-addendum).
