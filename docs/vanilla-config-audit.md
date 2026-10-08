# Configuration reference

The launcher creates missing active configurations from full templates and its
embedded profiles. Active server files live in `configs/`; module files live in
`configs/modules/`. Edit these active files with the servers stopped.

Normal startup merges profile updates automatically. A setting follows a new
default only while its active value still matches the previous managed default.
Custom values, database credentials, paths and the selected realm phase are
preserved; missing managed settings are added. Changed files receive `.backup.*`
copies before replacement. Without a saved baseline, the first startup preserves
all existing values, adds only missing managed settings and records the bundled
defaults for future comparisons.

`configs/.portable-profiles.json` records the managed baseline for future
updates; keep it with the active configs when backing up or moving a realm.
Server binaries and SQL update through the launcher's normal startup check.
See the [update guide](updating.md) for older installations and offline startup.

## Progression and character creation

| Setting or system | Default behavior |
| --- | --- |
| Realm mode | `individual`: per-character Vanilla→TBC→Wrath progression |
| Core expansion / maximum level | `Expansion = 2`, `MaxPlayerLevel = 80` |
| Fresh characters | Level 1, tier 0, normal starter items, zero gold |
| Strict earned milestones | Enabled; preceding boss and rewarded-quest markers required |
| TBC / Wrath access | Earned tiers 8 / 13; XP stops at 60 / 70 until unlocked |
| Expansion races | Same-account earned TBC unlock; alts start at tier 0 |
| New death knights | Blocked by strict mode; existing characters retained |
| XP, drops, reputation and honor | Normal 1.0 rates |
| Skills and professions | Trained and improved normally; two primary professions |
| Talent points | Normal 1.0 rate; historical trees selected by earned era |
| New dual-spec purchases | Level 80 in individual mode |
| Ordinary respecs | Paid trainer path and normal cost history |
| Dungeon Finder | Disabled |

`IndividualProgression.StrictEarnedProgression = 1` depends on the module's
default chain: enabled IP, an empty `CustomProgression` and
`DisableDefaultProgression = 0`. Random-bot and human accounts share the gates;
the account exclusion expressions are empty. GM login starts in ordinary visible
player mode, but explicit GM administration remains possible.

Core expansion access is required for restored Vanilla Naxxramas. Optional realm
ceilings must be changed through the launcher's linked settings, rather than a
single core expansion toggle. See [progression and ceilings](changing-expansions.md).

## Bots and population

| Setting | Default |
| --- | --- |
| Natural progression | Enabled |
| Fresh bot level / XP rate | 1 / 1.0 |
| Online population target | 2,500 while a real player session is connected |
| Login / logout delays | 30 / 60 seconds after real-player presence changes |
| Resident earned caps | About 5% each at 19, 29, 39, 49, 59, 69 and 79 |
| Free factory equipment, money and supplies | Disabled |
| Level, quest and leader-progress synchronization | Disabled |
| Routine free talent resets / spell grants | Disabled |
| Ordinary paid training and earned talent allocation | Enabled |
| Automatic use of earned loot upgrades | Enabled |
| Teleport recovery and free summon support | Disabled |
| Earned auction trading | Enabled; ordinary auctioneer/mailbox access |
| Unsolicited broadcasts and random emotes | Disabled |
| Nearby greetings | Real players only |

The population logs in gradually. Smart activity scaling reduces distant solo
activity as tick time rises, while nearby/grouped bots and combat stay active.
A target of 2,500 requires substantial server resources and does not imply every
bot is available in every level, faction or era. Lower
`AiPlayerbot.MinRandomBots` and `AiPlayerbot.MaxRandomBots` to fit the host.

See [earned bot brackets and PvP](earned-bot-brackets.md) and
[earned auction trading](earned-auctions.md) for their settings and limits.

## Modules and group play

| Component | Default policy |
| --- | --- |
| AutoBalance | Scale smaller instance parties; count actual non-GM occupants, including bots |
| Individual Progression | Earned maps, items, quests, attunements and era access |
| Era Talents | Historical Vanilla/TBC trees; native Wrath after earned access |
| MultiBot Chatless and Bridge | Bot-control UI with natural-progression restrictions |
| Quest Loot Party | Share naturally rolled normal-quality quest loot with eligible corpse looters |
| AH Bot Plus | Seller, buyer and generated stock disabled |
| Dungeon Clear | Scripted runs, filler creation, recovery and spectate shortcuts disabled |
| Token Turn-in | Read-only checks available; shortcut redemption blocked in natural mode |

AutoBalance keeps creature levels unchanged. Full parties retain normal stats;
smaller parties receive the upstream scaling curve with reduced XP and money.
Bonus tokens and party-count difficulty offsets are disabled. Outdoor elites
and world bosses retain ordinary world difficulty. Scaling cannot supply missing
mechanic tactics or guarantee that every class can solo an encounter.

Quest Loot Party changes only eligible normal-quality quest-item distribution.
Players and bots must still loot the corpse; drop rolls, ordinary equipment loot,
quest prerequisites and earned progression remain in place.

MultiBot trainer actions require ordinary NPC range and paid core transactions.
Personal bank actions require banker range and validated storage operations.
Free preset talent writes, SelfBot autogear and maintenance grants are blocked
in natural mode. Token checks do not waive NPC exchange reputation, materials or
quest requirements.

## Historical rules and shared settings

Talent data uses Vanilla 1.12.1, TBC Classic 2.5.4 and native Wrath. Every human
client needs the matching [EraTalents addon and MPQ](era-talents.md).
Riding prices follow earned era, while acquisition levels remain 40/60/70.
General vendor/trainer prices and the auction market use shared data.

Battleground matching separates earned eras, with fixed per-instance scores,
reinforcements and Warsong timers. Ordinary minimum team sizes apply.
Bot Strand, random battleground and arena participation is disabled. See the
[queue and rules reference](earned-bot-brackets.md#waiting-for-battlegrounds).

IP also applies realm-wide settings: a 60-second breath timer, no low-level
regeneration boost, enabled player settings, disabled item DBC attribute
enforcement, monster sight range 80 and hidden object quest markers/sparkles.
Vanilla/TBC damage and healing modifiers remain 1.0 for both humans and bots.
These are shared settings rather than complete per-character historical rules.

## Supported scope

The project uses a Wrath core and client. Historical trees and selected spell,
price and battleground rules do not replace every combat formula, profession,
pet system, world-data rule or original patch balance value. TBC talents use
Classic 2.5.4 rather than exact original 2.4.3 data.

Bot pathfinding and encounter tactics depend on upstream AI. Disabling teleport
recovery can leave bots stuck. Autonomous completion of every class quest,
profession and raid is not guaranteed. Some upstream encounter actions retain
special movement or combat shortcuts; the earned-play guards do not cover every
AI action. For example, the specialized Onyxia
whelp action recognizes entry `11262`, while restored Vanilla whelps use
`301001`; generic combat does not establish full encounter support.

Source fixtures, launcher checks and package verification cover the implemented
policies and release tooling. Full compilation verifies integration. These
checks do not establish perfect live tactics, market activity, historical class
balance or a fixed 2,500-bot performance target.

Existing-realm upgrades preserve prior levels, tiers, items and gold. They cannot
retroactively prove those possessions were earned. Use a fresh database when
a level-1 earned history for every character is required. See
[upgrade behavior](changing-expansions.md#updating-an-existing-realm),
[dependencies](module-versions.md) and
[building](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md).
