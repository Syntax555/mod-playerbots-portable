# Individual progression through expansions

The default `individual` mode supports Vanilla, TBC and Wrath on the WoW 3.3.5a
client. Each new character starts at level 1, tier 0 and earns its own access.
Players and bots use the same milestone chain. Account race unlocks permit
character creation; they do not advance an alt.

| Earned progression | Content and level ceiling | Account creation unlock |
| --- | --- | --- |
| Tiers 0–7 | Vanilla; level 60 | Vanilla races and classes |
| Tier 8 | TBC; level 70 | Blood elves and draenei |
| Tier 13 | Wrath; level 80 | No additional level-1 class |
| Tier 18 | Completed default Wrath chain | No levels, equipment or gold granted |

Strict earned progression requires each preceding milestone. Eligible boss
credit is saved even when earned out of order, but cannot fill missing earlier
tiers. Transition quests must be rewarded as well as have their prerequisites
met. Ordinary quest, item, map and attunement requirements remain in force.

## Required milestone chain

These are the completion markers for each tier, rather than every encounter
available in that tier. Optional quests and raids are not additional requirements.

| Tier earned | Required completion | Progression opened |
| --- | --- | --- |
| 1 | Ragnaros | Blackwing Lair progression |
| 2 | Restored Vanilla Onyxia | Next Vanilla milestone |
| 3 | Nefarian | Zul'Gurub and AQ preparation |
| 4 | Rewarded Bang a Gong! or IP's Simply Bang a Gong | AQ gates and outdoor war |
| 5 | Rewarded Chaos and Destruction | Remaining AQ war progression |
| 6 | C'Thun | Restored Naxxramas 40 and Scourge progression |
| 7 | Kel'Thuzad in restored Naxxramas 40 | Into the Breach transition |
| 8 | Rewarded Into the Breach, after the Vanilla chain | TBC and level 61–70 XP |
| 9 | Prince Malchezaar | Serpentshrine Cavern / Tempest Keep progression |
| 10 | Kael'thas | Hyjal / Black Temple progression |
| 12 | Illidan | Sunwell progression |
| 13 | Kil'jaeden | Wrath and level 71–80 XP |
| 14 | Wrath Kel'Thuzad | Ulduar progression |
| 15 | Yogg-Saron | Trial of the Crusader progression |
| 16 | Anub'arak in Trial of the Crusader | Icecrown Citadel progression |
| 17 | The Lich King | Ruby Sanctum progression |
| 18 | Halion | Completed default chain |

Tier 11 is reserved; the default chain moves from 10 to 12.

Boss credit requires eligible participation in the tapped encounter. Nearby
eligible party members can receive their own credit. Group membership alone,
a leader's tier or a broad raid achievement does not award it. Progress-copy
and group-attunement shortcuts are disabled in strict mode. GM administration
remains available; playing accounts should use ordinary player privileges.

An already-rewarded transition quest becomes usable once the preceding chain is
complete and the realm ceiling permits advancement. It is not rewarded twice.

## Accounts and the bot population

Blood elf and draenei creation uses earned markers on the same account. An
unlocked character still starts at level 1, tier 0 with normal starter items and
zero gold. A player's account unlock does not apply to random-bot accounts.
Existing expansion-race bots without their account unlock remain offline.

Strict mode blocks new death knight creation because their native level-55 start
conflicts with the level-1 policy. Existing death knights retain native class
talents. Bot death knight login is disabled in the default profile.

About 5% of random bots are assigned each earned cap at 19, 29, 39, 49, 59, 69
and 79; the remaining 65% continue progression. Every bot levels from 1, and
level-69/79 residents must first earn TBC/Wrath. See
[earned bot brackets](earned-bot-brackets.md) to adjust or release these caps.

## Battleground access and rules

Classic battlegrounds use ordinary level requirements. Tier 8 opens Eye of the
Storm and human TBC arena skirmishes; tier 13 opens Isle of Conquest, Strand of
the Ancients, random battlegrounds and Wrath arenas. Rated arenas require the
native level 80, so TBC characters can use skirmishes only.

Matchmaking separates earned eras within each level bracket. Every member of a
queued group must qualify and share one era. Match rules remain fixed for that
instance, including refills. Invitation acceptance checks the selected map and
match era again. Preserved characters above their earned level ceiling must earn
the required expansion before queueing; their levels are retained.

Bots fill real players' named Warsong, Arathi, Alterac, Eye and Isle queues.
Bot Strand, random battlegrounds, arena teams and autonomous all-bot matches are
disabled. See the [PvP guide](earned-bot-brackets.md#waiting-for-battlegrounds)
for brackets, minimum participants, historical scores and timers, and AI limits.

## Era talents, training and prices

[Era Talents](era-talents.md) selects each character's tree from earned
progression: Vanilla 1.12.1 below tier 8, TBC Classic 2.5.4 at tiers 8–12 and
native Wrath at tier 13+. The TBC dataset includes changes from original 2.4.3.
Players need the matching EraTalents addon and `Data/patch-V.mpq`; bots use
server data only.

Bots add earned points to their existing build. Ordinary respecs use a paid
trainer. A genuine era crossing refunds the departing tree's points once,
out of combat. Training requires the paid lesson or earned talent/quest source.
Glyph ownership is retained, with effects and new use blocked before Wrath.

Riding lesson prices follow the purchasing character's earned era. Normal
reputation discounts apply to these base prices.

| Riding skill | Vanilla | TBC | Wrath |
| --- | ---: | ---: | ---: |
| Apprentice | 90g | 35g | 4g |
| Journeyman | 900g | 600g | 50g |
| Expert | Configured cost and ordinary prerequisites | 800g | 250g |
| Artisan | Configured cost and ordinary prerequisites | 5,000g | 5,000g |

Riding acquisition levels remain 40/60 for ground mounts and 70 for flying.
Owned skills, earlier purchases and mount-item prices are unchanged. General
vendor and trainer prices use shared world data. The auction house is one market
with owned items, earned gold and ordinary fees.

## Updating an existing realm

Download the complete server and matching client packages from
[Latest](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).

1. Back up databases and configurations, then stop the launcher and servers.
2. Install the complete server package using the installation's upgrade procedure.
3. Install `EraTalents-client-latest.zip` in each player's client and fully restart WoW.
4. If removing a shared Vanilla/TBC ceiling, run `startup.exe --set-expansion individual`.
5. Run `startup.exe --apply-profiles`, then restart the launcher normally. The
   server updater imports the bundled SQL migrations.

The launcher backs up changed configs and preserves unrelated settings,
characters and databases. Applying profiles restores managed defaults; make
custom profile edits afterward. Replacing the launcher alone cannot update
server behavior. See [talent migration](era-talents.md#updating-an-existing-realm).

Existing levels, stored tiers, inventory and gold are retained. An update cannot
certify that earlier grants were earned, and missing durable milestone credit
may require another eligible kill. A fresh database establishes the level-1,
tier-0 policy from character creation.

## Optional realm ceilings

`startup.exe --show-expansion` displays the selected mode. The alternatives add
shared ceilings while retaining each character's earned requirements:

| Mode | Realm level ceiling | Progression ceiling |
| --- | ---: | --- |
| `individual` | 80 | None |
| `vanilla` | 60 | Tier 7 |
| `tbc` | 70 | Tier 12 |
| `wotlk` | 80 | None |

`individual` requires level 80 for new dual-spec purchases. The `wotlk` option
permits dual spec from 40. Existing choices survive profile updates; an upgrade
does not automatically open an established realm.

Phase changes require initialized configs and stopped servers. The launcher
validates linked changes, creates `.backup.*` copies and rolls back failed
writes. It refuses a lower level ceiling after an expansion has opened; reverting
requires matching database/config backups. Do not edit `configs/realm-phase.txt`
alone. Core `Expansion = 2` is needed for restored Vanilla Naxxramas.

Historical progression remains on a Wrath core and client. AutoBalance scales
smaller instance parties; it does not add encounter tactics. General prices,
world data, professions, pets and every combat formula are not independently
historical for each character. See the [configuration reference](vanilla-config-audit.md).
