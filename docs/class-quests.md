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
Imp, Voidwalker, Succubus and Felhunter quest chains when the corresponding
summoning spell is missing. The action recognizes 43 chain quests and lets the
core decide race, level, prerequisites and quest availability. Characters under
player control retain their own quest decisions. Individual
Progression restores the original Imp questgiver relations; Summon Imp remains
a quest reward rather than trainer teaching.

Bots accept and turn in quests through ordinary NPC interactions, travel to
native objective spawns and use the existing combat and loot actions for kills
and quest chests. Binding quests use the bot's owned ritual item near its native
spell focus. Native scripts create the circle and demon, and ordinary combat
earns the objective credit. Quest rewards teach the summoning spell.

With [continent travel](configuration.md#continent-travel) enabled, bots select
quest destinations through their usable earned routes and continue journeys
aboard ships, zeppelins and other transports. This includes the continent
crossings in Alliance Heartswood and the Felhunter chains. With travel disabled
or its catalog unavailable, quest routing stays on the current map.

The blood elf Voidwalker quests The Stone (9529) and The Rune of Summoning
(9619) are outside this action's scope. Class mounts, Infernal, Doomguard and
historical demon grimoire purchases remain pending. End-to-end live verification
for all four Vanilla warlock races is still required; see the
[class audit](todo.md#dungeons-raids-and-outdoor-content).

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
and adds the scoped warlock, shaman and druid automation described above. Other class
quests retain the core and Individual Progression support. It does not provide three
complete historical quest databases or certify every class quest and scripted
objective.
