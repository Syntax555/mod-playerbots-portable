# Historical class quests

Class quests use each character's own earned progression. Selected historical
priest quests retain their original teacher relations, race and level conditions
and reward a matching historical spell. Players and bots follow the same access
rules.

## Priest training

| Family | Historical race |
| --- | --- |
| Desperate Prayer | Human and dwarf |
| Fear Ward | Dwarf in Vanilla; ordinary all-race training in TBC |
| Starshards | Night elf |
| Elune's Grace | Night elf |
| Touch of Weakness | Undead; also blood elf in TBC |
| Hex of Weakness | Troll |
| Shadowguard | Troll |
| Feedback | Human |
| Devouring Plague | Undead |

Desperate Prayer begins at level 10 for human and dwarf priests. Eligible
teachers offer the original quest variants, and the final teacher grants rank
1. Later ranks require ordinary paid training. The Vanilla spell uses its
historical rank levels and cooldown rather than the Wrath talent's values.

Historical quest rewards and removed spell ranks use separate spell records.
Vanilla and TBC mechanics follow the corresponding source data; native Wrath
records remain in place for Wrath progression. Native quest conditions check
personal progression markers when offering or accepting the quests. Reward
spells, learning and casting also require the character's eligible earned era,
clamped to the realm ceiling. Another party member's progression does not unlock
these spells.

Quest availability follows saved personal markers, including markers above the
realm ceiling. Quests retired by those markers stay unavailable. A quest already
in the log can still be turned in through native quest rules; its historical
spell reward remains subject to the character's race, class, level and era.

The client patch preserves native Wrath mana costs for Desperate Prayer and
Devouring Plague; historical versions use separate spell records. Package
provenance records the source data and adjusted client fields.

TBC also includes historical racial spells learned directly through paid
training, without a quest prerequisite:

| Family | Race | First level |
| --- | --- | --- |
| Chastise | Dwarf and draenei | 20 |
| Symbol of Hope | Draenei | 10 |
| Consume Magic | Blood elf | 20 |
| Touch of Weakness | Blood elf | 10 |

Consume Magic requires consuming an eligible priest aura. TBC blood elf training
does not require completing an undead quest. These trainer purchases retain
ordinary range, race, progression, level and money requirements.

Logging in can restore a missing rank-1 root when the character has already
earned the matching quest reward. It does not complete missing quests, grant
higher ranks or bypass trainer costs.

## Quest-taught lessons

Before Wrath, two lessons come only from the class quests that taught them in
Vanilla and TBC; trainers sell them from Wrath on.

| Lesson | Class | Quest |
| --- | --- | --- |
| Intercept, with Berserker Stance | Warrior, level 30 | The Affray, after The Islander from a warrior trainer |
| Sense Undead | Paladin, level 20 | The Tome of Valor; blood elves: Return to Silvermoon after The Second Trial |

The quests teach the spells directly. A character that already knows Intercept
can train its later ranks as usual. Players and bots follow the same rule, and
[Zygor](zygor-progression.md#guide-behavior) leads each class through its chain.

## Autonomous warlock demon quests

Solo, headless random warlocks using natural progression can pursue the native
Imp, Voidwalker, Succubus, Felhunter and Felsteed quest chains when the
corresponding summoning spell is missing. The shared
[class quest table](#autonomous-class-quests-for-every-class) holds these 50
chain quests as warlock lessons and lets the core decide race, level,
prerequisites and quest availability.
Characters under player control retain their own quest decisions. Individual
Progression restores the original Imp questgiver relations and the level-40
Felsteed quests; Summon Imp and Summon Felsteed remain quest rewards rather than
trainer teaching.

Bots accept and turn in quests through ordinary NPC interactions, travel to
native objective spawns and use the existing combat and loot actions for kills
and quest chests. Binding quests use the bot's owned ritual item near its native
spell focus. Native scripts create the circle and demon, and ordinary combat
earns the objective credit. For The Summoning, the bot stays with Strahad Farsan
while his escort creates the focus. A lost ritual item or a failed quest is
recovered by abandoning the quest and accepting it again. Quest rewards teach
the summoning spell.

With [continent travel](configuration.md#continent-travel) enabled, bots select
quest destinations through their usable earned routes and continue journeys
aboard ships, zeppelins and other transports. This includes the continent
crossings in Alliance Heartswood and the Felhunter and Felsteed chains. With
travel disabled or its catalog unavailable, quest routing stays on the current map.

Blood elf warlocks turn in The Stone (9529) at the Voidstone in the Dead Scar,
accept The Rune of Summoning (9619) from it and use their own Voidstone at the
Rune of Summoning in Goldenmist Village. The native event summons the Voidwalker.
The Infernal chain (7601–7603) and historical demon grimoire purchases remain
pending. The Dreadsteed and Doomguard chains need Scholomance, Dire Maul or a
group and remain player content. End-to-end live verification for all five warlock races is still
required; see the [class audit](todo.md#dungeons-raids-and-outdoor-content).

## Autonomous shaman totem quests

Solo, headless random shamans using natural progression can pursue the Vanilla
Horde and Draenei Earth, Fire, Water and Air chains. The action recognizes 52 main
quests and five native Horde recovery quests. Draenei content follows the
character's own TBC eligibility. It stops a totem family when the character
owns its totem or has already earned its final reward. Ordinary trainers still
control paid spell training; the Air reward's Swift Wind buff is not a learned
spell.

Bots use their own Sapta at the matching native shrine before approaching
invisible spirits. This includes Earth delivery quests that the core already
marks complete before the spirit can be seen. Empty waterskins are filled at
their spell's native focus, including destinations on another continent.
Kills, loot, brazier acceptance and turn-in use the ordinary core handlers.

Call of Water (100) starts the native purified-spirit event when accepted at
its brazier or Tiev Mordune. This start behavior follows the pinned Classic and
TBC quest scripts. Nearby living spirits prevent duplicate summons. When an
unrewarded quest 100 has waited without its spirit, a bot can abandon that empty
quest and accept it again normally. It retains the rewards of earlier steps.
Other Sapta and spirit recovery still follows the native quest requirements.

Draenei bots open their owned Fireproof Satchel and use its Ritual Torch at
the Wickerman Effigy. They fill the Empty Bota Bag at Stardust Ruins and use
their Skin of Purest Water at the Barrel of Filth. Native events create Hauteur
and Tel'athion; ordinary combat and loot earn the required quest items. A living
opponent or a corpse the bot can loot prevents another ritual. Water quests can
use the character's own Water Breathing potion while underwater without an
existing breathing aura. Optional return orbs and Susurrus's flight are not
automated; bots use ordinary travel back to their questgivers.

Optional class equipment quests and complete live runs remain
on the [class audit](todo.md#dungeons-raids-and-outdoor-content). The
[source comparison](class-quest-comparison.md) distinguishes existing quest
restoration from class-specific bot actions.

## Autonomous druid class quests

Solo, headless random druids using natural progression can pursue 32 native
quest variants: 14 for Bear Form, eight for Aquatic Form and ten for Cure Poison.
These include alternative introductions; one character follows its eligible
racial chain. The core retains race, level, prerequisite and personal-era
checks. A learned ability or an earned final reward ends that family.

Bots follow the Great Bear Spirit's full dialogue and use their owned dust at
the Moonkin Stone matching its native summon event. Ordinary combat creates
Lunaclaw's spirit, and its dialogue supplies quest credit. Moonglade teaching
comes from the native introductory quest; existing travel can use the bot's
own learned teleport normally. No ability or quest credit is granted by the
bot action.

If an incomplete Body and Heart quest has lost its dust, the bot waits at the
native ritual site for Lunaclaw or its spirit. It can abandon and accept that
empty event quest again normally when neither appears and no dust is owned,
including in the bank. This recovery is restricted to quests 6001/6002 and
refuses required items, source-drop items or explicit creature objectives.
Aquatic quests retain their earned components.

The lake trial uses ordinary Bauble Container loot and the native Shrine
Bauble spell. Bots collect both pendant halves, travel to Remulos's shrine
and use their owned Agility half with its Endurance reagent. Native casting
consumes the components and creates the pendant. Source-drop items use the
core's quest-loot eligibility; existing opening and loot actions retain their
ordinary access and inventory checks.
Cross-continent steps require enabled
[continent travel](configuration.md#continent-travel) and the character's own
usable routes.

Cure quests fill owned samplers at their spell's native focus and use the
owned ten-charge salve on the matching sick animal species. Native scripts
transform the animals and award cure credit. Reached empty or recently cured
spawns are temporarily skipped. The required Earthroot can be bought from
eligible native vendors with the character's own gold; limited stock, prices,
visibility, range and bag space remain in force. Other ingredients use normal
fungus loot or kodo combat. Unavailable stock or funds can delay completion;
the action does not grant herbs or gathering skills.

Complete live runs, underwater navigation, the optional level-50 equipment
chain and TBC Swift Flight remain on the
[class audit](todo.md#dungeons-raids-and-outdoor-content).

## Autonomous class quests for every class

Solo, headless random bots of every class using natural progression pursue
their native class quests. One shared table of 300 quest steps holds the
warrior, paladin, priest and warlock lessons and, for all nine classes, the other
class quests an ordinary solo character can finish on the open continents. The
shaman, druid and hunter lesson actions above keep their own quests and run
first. A bot finishes one lesson at a time, starting at the nearest native
giver it can use; a learned lesson or its rewarded final quest ends that chain.

| Lesson | Class | Chains |
| --- | --- | --- |
| Defensive Stance, Sunder Armor and Taunt | Warrior, level 10 | Uzzek (Barrens), Ulag the Cleaver (Tirisfal), Bartleby (Stormwind), Vejrek (Dun Morogh), Vorlus Vilehoof (Teldrassil), Strength of One (Azuremyst) |
| Berserker Stance and Intercept | Warrior, level 30 | The Islander and The Affray |
| Redemption | Paladin, level 12 | Human and dwarf Tome of Divinity, draenei Redemption, blood elf First Trial to Redeeming the Dead |
| Sense Undead | Paladin, level 20 | The Tome of Valor with Daphne Stilwell; blood elf The Second Trial |
| Summon Warhorse with Apprentice Riding | Paladin, level 40 | The Tome of Nobility; The Thalassian Warhorse |
| Racial priest spells | Priest, level 10 and 20 | The nine restored families listed under [priest training](#priest-training) |
| Imp, Voidwalker, Succubus, Felhunter and Felsteed | Warlock | The chains listed under [warlock demon quests](#autonomous-warlock-demon-quests) |

The other 157 class quests are the class letters and training breadcrumbs, the
race-specific weapon, armor, robe and wand chains, and their follow-ups:

| Class | Quests | Class | Quests | Class | Quests |
| --- | --- | --- | --- | --- | --- |
| Warrior | 29 | Rogue | 30 | Mage | 29 |
| Paladin | 5 | Priest | 21 | Warlock | 9 |
| Hunter | 25 | Shaman | 5 | Druid | 4 |

Each has a native giver, needs only ordinary continent creatures, containers,
quest objects or its own start item, and follows a reachable predecessor. A bot
starts one only while it passes the ordinary quest level rules used by the RPG
quest picker: no grey, repeatable, elite, group or dungeon quests and no quests
more than three levels above the bot. Lessons are pursued regardless of level.

The core still checks race, class, level, prerequisites, exclusive groups and
personal era conditions, and grants every reward. Players see and complete the
same quests. Individual Progression supplies the Tome of Nobility, Thalassian
Warhorse and priest quest givers.

Bots accept item-started quests from their own items and use their own Symbol
of Life, Shimmering Vessels and Ravager Cage Key on the native targets. Henze and
Narm Faulk accept the turn-in once the bot has revived them with its Symbol.
Bots use the Mausoleum Trigger, Gilded Brazier, Harbinger of the Second Trial and
Ju-Ju Heaps, and fight Ulag, the Death Ravager, Sangrias Stillblade and the
champions through ordinary combat. Mages fill their own flasks at the native
spell focus. Priests cast their own Lesser Heal and Power Word: Fortitude on the
wounded creatures of the robe quests, in the order the native script requires.
For The Rethban Gauntlet, a bot reports the area trigger it has entered; for The
Affray, it waits on the grate beside Twiggy Flathead until the challengers
attack. It stays beside Bartleby for his fight and beside Daphne Stilwell during
her escort, attacking the raiders who strike her.

A failed quest, such as a lost Affray, trial, escort or timed quest, is
abandoned through the quest log and accepted again. The same applies to an
event quest whose bot has waited at its site for five minutes without combat,
and to a step whose own source item is gone from bags and bank. Other quest
items, such as Linen Cloth and the Defias and Dark Iron scripts, come from
ordinary kills and loot. Cross-continent steps, such as The Islander for
Alliance warriors, need enabled
[continent travel](configuration.md#continent-travel) and the bot's own usable
routes.

Class quests that need a group, dungeon, raid, profession, pickpocketing or
raid tokens remain player content. These include the Charger, Dreadsteed,
Doomguard, Rhok'delar and Swift Flight Form chains, the Zul'Gurub, Ahn'Qiraj and Naxxramas
class rewards, the elite Fire Hardened Mail, Test of Righteousness and Cyclonian
quests, the crafted Brutal Armor and enchanted robes, the Horde rogue poison
chain and the mage containment coffers. Complete live runs remain on the
[class audit](todo.md#dungeons-raids-and-outdoor-content).

## Client installation

Install the release's matching EraTalents addon and `Data/patch-V.mpq` with WoW
fully closed. The MPQ contains the restored spell records and German and English
text, and must match the server's generation. See [EraTalents](era-talents.md)
for installation and generation checks.

Questie and guide addons maintain their own quest databases. Their markers can
omit restored quests even when the server offers them. The NPC quest list and
server-side eligibility determine availability; see [client addons](addons.md).

For a missing quest, inspect the affected character with `.quest status` before
reporting it. The [quest diagnosis guide](quest-diagnostics.md) covers class/race
gates, alternative quests, personal progression conditions and spell-reward limits.

## Source and scope

Quest relations, ranks and mechanics use pinned CMaNGOS Classic and TBC sources.
[Build provenance](module-versions.md), [versions.lock.json](../versions.lock.json)
and packaged license notices identify the exact source revisions and adaptations.
SQL updates run through the ordinary database updater.

This integration restores the listed priest families and quest-taught lessons,
and adds the class quest automation described above. Player-only class quests retain the
core and Individual Progression support. It does not provide three
complete historical quest databases or certify every class quest and scripted
objective.
