# Roadmap and validation

Open implementation and verification work. Current behavior belongs in the
[player guides](../README.md#documentation), not in a list of completed changes.
A passing source fixture is not a completed in-game run.

## Keeping this list current

Keep concrete acceptance criteria and links to the relevant guide. Close a task
only after its required verification passes, then update that guide. Preserve
unresolved gameplay, Windows and sustained-load checks even when local source
fixtures pass. Use native core/module functions before adding replacements.

## Dungeon integration

- [ ] Add earned ordinary handling for refused routes: Uldaman's Staff of
  Prehistoria, Zul'Farrak's Executioner's Key and Gahz'rilla gong, and BRD's
  Shadowforge Lock. Keep each character's own items and native eligibility.
- [ ] Audit Blackfathom Deeps' disconnected entrance, swimming sections and pool
  exit using complete checked routes without relocation or authored shortcuts.
  Audit Stratholme's required ziggurat and trap-alley controllers before
  autonomous recruitment. Both remain accessible to player-led groups.
- [ ] Expand TBC/Wrath coverage only with ordinary event, escort, vehicle and
  locked-object handling; verify complete runs before advertising completion.
- [ ] Evaluate heroic parties separately for earned entry, keys, equipment and
  heroic mechanics. See [dungeon scope](bot-dungeons.md).

## Raid integration

- [ ] Provide native raid scheduling, roster formation and real entrance/return
  travel before enabling autonomous raids. Retain personal access, keys,
  attunements, difficulty and lockouts, including the Vanilla Naxxramas entrance.
- [ ] Let bots earn Drakefire Amulet, Blackhand's Command, Naxxramas access and
  Aqual Quintessence through ordinary quests and interactions.
- [ ] Review native Raid Clear/Naxxramas coverage as upstream develops it.
  Sunwell Plateau (580) and Trial of the Crusader (649) have no dedicated
  strategy registration in the pinned Playerbots source; verify tactics and
  earned-play guards before treating either as supported.

## Gameplay validation

### Server updates and data

- [ ] Test a fresh realm and a fully stopped copy of an existing realm. Verify
  SQL updater completion/order, numeric-to-language account locale migration,
  preserved custom configuration/characters, and `RaidClear.*` migration into
  `playerbots.conf` without overwriting explicit destination values.
- [ ] Validate guarded world-data repairs in game: priest rank chains, AQ event
  dragon menus, Drijya's escort (10310), Summoner Kanthin's patrol and
  duplicate Sunfury Magisters; Howling Fjord's Dead Man's Debt, Stairway to
  Mercy and Mimicking Nature's Call. MySQL replay and source fixtures do not
  establish running-realm behavior.

### Bots, talents and client interfaces

- [ ] Validate profession-rank caps with trainers, rank books and spell learning
  at tiers 0, 8 and 13, including bots, GM/excluded accounts and config reloads.
  Verify that login preserves existing skills, achievements, titles and gear.
- [ ] Validate [hunter companion acquisition](combat-profiles.md#hunter-companions)
  in game for all six racial taming-lesson chains, including ordinary quest
  acceptance, owned rods, interrupted channels, native completion and turn-in.
  Check first-pet taming, missing paths, other characters' targets, death,
  feeding and relogs; preserve current, dismissed and stabled pets.
- [ ] Validate repeated deaths and long corpse runs outside and in dungeons,
  including reduced AI activity, controlled altbots and SelfBots. Check normal
  spirit release, group resurrection waits, reclaim limits, missing routes,
  ghost legs on long runs and bodies off the navigation mesh, such as in cities.
- [ ] Validate [continent travel](configuration.md#continent-travel) in game: waiting,
  boarding and leaving at every ship, zeppelin and turtle stop, missed departures
  and full docks; the Thunder Bluff, Undercity and Freewind elevators and the
  Deeprun Tram, including neighbouring doors and lifts; portals in Shattrath,
  Dalaran and the capitals, Darnassus to Rut'theran, the Dark Portal and
  Thalassian Pass; mage teleports with and without runes, hearthstones and
  discovered flights to a dock; faction and earned-era refusals; companions left
  on another continent or island; travel-data islands that split walkable areas;
  route times. Measure planning cost with the 2,500-bot target.
- [ ] Validate companions riding with their player in game: Deeprun Tram cars,
  Thunder Bluff and Undercity elevators beside their doors, ships and zeppelins,
  several companions on one car, missed departures and the next ride after the
  player arrives.
- [ ] Validate home binding with the master in game: companions in and out of
  innkeeper range, several companions at once, and following the master's
  hearthstone to the shared inn and from another continent.
- [ ] Validate flight master discovery in game: zones with several flight
  masters, unreachable or hostile ones, Rut'theran from Teldrassil's canopy and
  detours during a route.
- [ ] Test [combat profiles](combat-profiles.md) for every class on random bots,
  controlled altbots and SelfBots: automatic/manual selection, relog/AI resets,
  combat refusal, retained travel/loot settings and owned-item upgrades.
  Include protection weapon/shield, feral cat/bear and historical-era builds;
  controlled characters' talent points must remain manual.
- [ ] Check equipment upgrades in game across Vanilla, TBC and Wrath eras:
  set pieces kept against stronger single items, hit-capped casters and melee,
  Shadow Focus/Arcane Focus/Suppression ranks, two-hander versus one-hander and
  shield or off-hand, dual wield and Titan's Grip, rings/trinkets and no repeated
  swaps. Measure the equip and loot evaluation cost with the 2,500-bot target.
- [ ] Verify native loot eligibility and actual rolls with Need level 2:
  stronger/identical/weaker random-property variants, unique equipped items,
  bank-only copies and LFG Need restrictions. Refused Need retains Greed/Pass.
- [ ] Validate personal-bank transfers in game with incomplete and completed
  delivery quests, merged stacks, full bags/bank, stale source items and lost
  banker access. Include MultiBot bulk and exact-stack commands and their
  reported quantities.
- [ ] Validate MultiBot startup, vendor purchases and talent learning: preserved
  settings, correct bot gold/items, quantities and confirmations, no owner
  purchase on bridge failure, one earned talent rank per click and read-only
  behavior after losing group/control/range. Include SelfBot state confirmations,
  group orders and event-driven inventory refresh across map changes.
- [ ] Check [DragonUI/EraTalents](era-talents.md#dragonui) on the live client:
  talent key, buttons and `/talents`; seven-row Vanilla/nine-row TBC trees,
  ranks/connections/tooltips, spec and glyph tabs, hunter pet trees and target
  switching. Bot and player button state must follow their own visible window.
  Check the dressing-room skin with the stock frame and addons that replace or
  resize it, including login and live module toggles.
- [ ] Test the native trainer catalogue and bot spellbook across all eras:
  learned/unlearned entries, cost/level, class/talent sections, cast/macro/skip,
  search, paging and single/two-page layouts. Toggle DragonUI's spellbook live
  from both login states, then change UI scale with the bot book open.
  Check Clique parent restoration and D3D9/D3D9Ex art.
- [ ] Verify [Questie](questie-playerbots.md) with the native roster integration: simultaneous
  bots, kill-credit/event goals, turn-in/abandonment, WATCH renewal, token/GUID
  isolation, mixed real clients and disconnect/rejoin cleanup. Shared item
  tooltip counts and a bot-only quest's party marker were observed with one
  altbot; full rendering, traffic and sustained realm load remain unverified.
- [ ] Validate [Zygor](zygor-progression.md) login/reconnect, locked quests and
  givers, level-60/70 holds, guide browsing, tier-7/8/13 sources and suppressed
  native Talent Advisor while EraTalents owns the tree.
- [ ] Check the Zygor era tabs and the corrected Brewfest, holiday, fishing
  and exploration routes in game for each era and faction. Vanilla routes lack
  the experience the 1.12 curve needs where TBC-era quests are refused,
  notably Alliance Dustwallow Marsh (41-45). Includes that no guide loads
  still hold Cataclysm and Pandaria steps; the fork's parse test keeps them
  out of loaded guides.
- [ ] Test Zygor's inspected-altbot Gear Finder with stock and DragonUI views:
  bot/owner class differences, empty/cold data, profile/equipment changes,
  faction/era/quest/vendor access, rapid target switches and closing during
  replies. Measure frame time and traffic; fixtures do not render the UI.
- [ ] Validate the [Journal](addons.md#journal) and its Progression tab in game
  for each era and faction: stage locks on instances, quest headings, directory,
  lore and collections; every tier's steps, map flags and milestone after a
  stage change; reference-loot counts under MySQL 8; humanoid boss models; the
  gear check with and without DragonUI; and the first start's zone calculation
  time and memory with the full world database.
- [ ] Measure sustained world/map tick time, memory and addon traffic with the
  2,500-bot target and several active groups. Verify delayed login and logout
  after the last real session, ordinary vendor/auction trips, paid training,
  discovered flights, hunter food reserves and all-warlock Drain Soul shards.

### Dungeons, raids and outdoor content

- [ ] Complete runs of each admitted dungeon: entrance/return travel, combat,
  loot/quests, missing mesh, late or disconnected members, death, native
  resurrection, wipe, stop/pause/resume and a fresh instance. Remove a failing
  route from autonomous eligibility until resolved.
- [ ] Check player-led clear deaths with a SelfBot tank: party resurrection by
  a living healer, a real player's own accept, release and corpse run when no
  resurrecter is left with the tank waiting until they return, a wipe and the
  tank's own death.
- [ ] Wailing Caverns: checked ramp joins and floors, safe group spacing,
  four Fanglords, ordinary Disciple gossip/escort, combat/food interruptions,
  ritual waves, Mutanus and the final departure marker. Cover reset/death,
  missed marker, fresh instance and the fifteen-minute attempt budget.
- [ ] Deadmines: detour to the native gunpowder chest, ambushes, owned powder,
  full bags, cast/form interruptions and cannon/door completion. Uldaman:
  both altars' native five-second rituals, owner/group/range/reset handling;
  autonomous recruitment must still refuse the unaudited staff acquisition.
- [ ] Zul'Farrak: physical Zum'rah wake-up, native reset and interruption guards;
  no artificial activation/credit, and ordinary cage/gong requirements remain.
  BRD: every member inside Ring of Law, native waves/final waypoint credit,
  cooldown and ordinary recovery; Shadowforge access remains separately gated.
- [ ] Player-led Onyxia, MC, BWL, ZG and AQ: personal entry/attunement, native
  tactics and earned-play refusals. Cover Onyxia's ground/air/landing phases,
  all Deep Breaths, whelps, threat/fear, ordinary recovery and AI-reset strategy
  restoration; no raid-cheat Suppression Room or floor-rescue bypass. Verify
  Arlokk's ordinary gong interaction and Ouro's approach/summon, submerged
  phase, wipe/reset and native completion. Check ordinary Jeklik and Plugger
  pulls with forced aggro refused, including an unreachable boss that stalls.
- [ ] Compare native Vanilla world-buff turn-ins with 1.12: faction delivery,
  cooldowns, recipient levels/scaling, duration, death and dispel. Simulated
  turn-ins remain disabled; native WotLK scripts are not a verified 1:1 model.
- [ ] Audit historical class quests beyond restored priest families and test
  teachers, requirements, rewards and paid training. Validate Halion's Twilight
  Realm credit and the Spirit of Zandalar earned tier.
- [ ] Audit autonomous class-quest item and event handling against the native
  quest scripts before enabling additional routes. Live-test the warlock
  Binding handling for 1471, 1474, 1504, 1513, 1689, 1739 and 1795; audit shaman
  Call of Earth 1518/1521/9451, Call of Fire 1527/9555 and Call of Water 96/9509; warrior
  The Affray 1719, Ulag 1819, Bartleby 1640 and Strength of One 9582; paladin
  Tome of Divinity 1786/1783, Redemption 9600, First Trial 9678, Claiming the
  Light 9684, Redeeming the Dead 9685, Tome of Valor 1651 and The Second Trial
  9686. Verify the correct owned items, targets, ordinary interactions, rewards
  and each character's own era. Native quest availability alone does not prove
  autonomous completion. Retain player-controlled character ownership.
- [ ] Live-verify the shared action's other class quests for all nine classes:
  class letters, equipment and robe chains, the quest level rules for new
  steps, ordinary loot from containers and keys, and the Rethban Gauntlet's
  area trigger and timer. Keep group, dungeon, raid, crafting and pickpocket
  class quests listed as player content in the
  [class quest guide](class-quests.md#autonomous-class-quests-for-every-class).
- [ ] **Warrior:** Live-verify the shared class quest action on all six
  Defensive Stance chains, including Path of Defense (1498), the Mausoleum
  Trigger and Ulag (1819), Bartleby's fight (1640) and the draenei ravager cage
  (9582), and on The Islander / The Affray (1719) for Berserker Stance and
  Intercept. Check the grate start beside Twiggy Flathead, all challenger waves,
  survival, failure on death with abandon/reaccept, the timer, turn-in and later
  paid ranks in each earned era. See
  [class quest coverage](class-quests.md#autonomous-class-quests-for-every-class).
- [ ] **Paladin:** Live-verify the four Redemption chains: Linen Cloth from
  ordinary loot, the Symbol of Life on Henze and Narm Faulk before turn-in
  (1786/1783), the Young Furbolg Shaman (9600), the Gilded Brazier and Sangrias
  Stillblade (9678), both Shimmering Vessels (9684/9685) and recovery when an
  item is consumed without credit. Check the item-started Tome of Valor (1649),
  Daphne Stilwell's escort with attacks on her raiders (1651), the Second Trial's
  harbinger and champions (9686), both warhorses (1661/9712) and later trainer
  availability. Audit the level-60 Charger chains separately.
- [ ] **Hunter:** Validate all six first-pet lesson chains and Training the
  Beast using the existing native-quest bot actions, including interrupted
  casts, owned rods, travel, pet preservation and subsequent feeding/revival.
  Historical ability acquisition by taming additional beasts is not implemented;
  keep `VanillaHunterPets` disabled until that and existing-pet migration have
  been evaluated.
- [ ] **Rogue:** Live-verify the 30 solo class quests of the shared action,
  including Klaven's Tower (2359) with the looted Defias Tower Key and its
  chest. The Horde poison chain (2460/2458/2478), pickpocketed quest items and
  Ravenholdt (6681) remain player content; check them with players.
- [ ] **Priest:** Verify each restored racial quest family end to end, including
  Desperate Prayer, Fear Ward and the race-specific rewards listed in the
  [class quest guide](class-quests.md#priest-training), for players and random
  bots. Live-test the robe quests' Lesser Heal rank 2 and Fortitude sequence,
  Help Tavara and Cleansing the Scar. Check teacher access, prerequisites, travel to the capital takers,
  ordinary turn-in, earned rank 1, paid later ranks and the TBC-era variants.
- [ ] **Shaman:** Live-verify the 33-step Vanilla Horde totem and recovery
  action for Orc, Troll and Tauren: owned Sapta, invisible spirits, all three
  waterskin focuses, normal brazier acceptance/turn-in and earned continent
  routes. Test the native quest-100 start event, duplicate-spirit refusal,
  death/relog/despawn recovery, normal abandon/reaccept and full bags.
  Live-verify the 24 Draenei steps through 9451/9555/9509/9554: ordinary satchel
  opening and loot, both ritual objects, native delayed summons, owned Water
  Breathing potions, underwater paths to Aqueous and the Stardust Ruins crossing.
  Check full bags, evade/despawn retry and missing quest items after relog.
  Optional return orbs and Susurrus's flight remain unaudited; use ordinary
  travel. Audit the cosmetic Temper/Hauteur Reborn reward scene after 9467
  separately; it grants no required quest credit. Audit optional equipment,
  dungeon and raid quests before claiming all Shaman class quests complete.
  See [totem coverage](class-quests.md#autonomous-shaman-totem-quests) and the
  [nine-class source comparison](class-quest-comparison.md).
- [ ] **Mage:** Live-verify the 29 solo class quests of the shared action,
  including the Mirror Lake, Waters of Xavian and Purest Water flask fills at
  their spell focus, the Ju-Ju Heaps and Magecraft (8250). The containment
  coffers (1920/1960), Uldaman, Fragmented Magic (9364) and Attunement to
  Dalaran (12172/12173) remain player content.
- [ ] **Warlock:** Live-verify the 53 Imp, Voidwalker, Succubus, Felhunter,
  Felsteed and Inferno lessons of the shared action for all five warlock races. It accepts
  and rewards native quests, uses ordinary kills/chest loot and owned ritual items,
  and leaves demon combat and credit to native scripts. Imp questgiver relations
  are restored by Individual Progression. Verify the earned continent routes
  for Alliance Heartswood and the Felhunter chains, including map transfers
  while aboard and disembarking. Check recovery after relogs, Strahad Farsan's
  escort, abandoning for a missing ritual item and native event resets before
  claiming autonomous end-to-end completion.
  Check the blood elf Voidstone questgiver objects (9529/9619) and the Rune of
  Summoning event. Check the Infernal chain (7601–7603): Impsy, the three
  Flawless Fel Essences from Azshara, Jaedenar and the Blasted Lands, the owned
  Fel Fire at Kroshius' Remains, the waking event, Kroshius' core looted before
  the used-up Fel Fire is replaced, full bags and the Inferno reward. Kroshius'
  native waking script despawns every other creature within 10 yards; check the
  bot's own demon and simultaneous rituals. The Dreadsteed and Doomguard chains need
  Scholomance, Dire Maul or a group and stay player content. Historical
  demon grimoire purchases remain unimplemented;
  keep `WarlockDemonTrainers` disabled until evaluated. See the
  [implemented scope](class-quests.md#autonomous-warlock-demon-quests).
- [ ] **Druid:** Live-verify the 32 basic Bear, Aquatic and Cure Poison variants
  for Night Elf and Tauren. Check full spirit dialogues, the faction's native
  Moonkin Stone, Lunaclaw combat/spirit and missing-dust recovery after relog.
  Check the timed Bauble, both owned pendant halves, underwater navigation and
  earned continent routes through Aquatic Form (31/5061). Verify sample ambushes,
  ten-charge salve targeting, creature entry changes and empty-spawn retries.
  Check Earthroot vendor stock, prices, own gold, full bags and other reagent
  collection through Power over Poison (6125/6130). See
  [implemented scope](class-quests.md#autonomous-druid-class-quests).
  Audit the optional level-50 equipment chain 9063/9052/9051/9053 and TBC Swift
  Flight separately, including the earned heroic Sethekk/Anzu requirement.
- [ ] **Death knight:** Audit the Acherus starting chain, including The
  Emblazoned Runeblade (12619), Into the Realm of Shadows (12687) and The Light
  of Dawn (12801), before claiming autonomous completion. Random death-knight
  login is disabled in the portable profile; controlled characters keep their
  owner's choices and must meet ordinary starting-chain and era requirements.
- [ ] Verify era XP: quest values, battleground goals, rest/heirloom/holiday
  modifiers, era-cap money and Thrallmar/Honor Hold Favor without double bonuses.
- [ ] Check historical creature levels and HP in game: Mekkatorque and the other
  city leaders, Lor'themar, Velen and city guards. Confirm city training dummies
  stay hidden before tier 13 and appear for Wrath characters in mixed-era groups.
  Shared outdoor creature statistics retain their historical template era.
- [ ] Check the [restored quests](changing-expansions.md#world-content-by-era-and-patch)
  in game: each bracket's Warsong Gulch and Arathi Basin turn-in with earned marks,
  gone at tier 8; Guard Didier and his writ from tier 6; Seer Nakha's A Strange Vision.
- [ ] Check the [quest-taught lessons](class-quests.md#quest-taught-lessons) in game for
  players and bots: Intercept and Sense Undead missing from Vanilla and TBC trainers until
  The Affray, The Tome of Valor or Return to Silvermoon, then trainable in later ranks;
  The Affray's and The Second Trial's events; the matching Zygor steps.
- [ ] In-game checks of the era gates at tiers 0, 3, 4, 6, 8, 10 and 13: Cenarion Hold,
  Silithus, Yojamba Isle, Shadowmoon's Netherwing, Shattrath and Dalaran; phased
  Undercity and Silithus givers; renumbered quests left visible. Hidden hostile
  creatures (2.3 Dustwallow) must not aggro, cast at or block lower-tier players,
  their pets or mixed-tier groups. See
  [world content by era and patch](changing-expansions.md#world-content-by-era-and-patch).
- [ ] Check [Questie's era display](questie-playerbots.md#quests-of-the-characters-era)
  in game with characters at tiers 0, 3, 4, 8 and 13: later quests and hidden givers
  absent from map and quest lists, `/qserver quest` and `/qserver giver` results,
  updates within seconds of a new tier, kept log quests, party sharing of quests
  Individual Progression retires, and snapshot size and frame time in Shattrath
  and Dalaran.

## Dependency updates

- [ ] Evaluate newer CMaNGOS Classic/TBC database snapshots before importing
  them: replay their migrations, regenerate historical quest and era-world
  data, and verify the TBC `QuestLevel=-1` changes against era XP rules. Keep
  the CMaNGOS Classic/TBC and VMaNGOS reference core pins aligned with the
  verified source data.
- [ ] Submit the prepared Individual Progression empty-filter fix when upstream
  permissions permit. Track the generic core proposals and remove local hunks
  only after accepted compatible fixes are pinned and checked; see
  [upstream proposals](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/upstream/README.md).

## Core and module forks

- [ ] Validate Grimfeather's Individual Progression and core changes in game:
  the original Alterac Valley layout, mines, quests and Playerbots tactics;
  mining its ore with ordinary skill requirements; Windsor's Great Masquerade
  phase, restored quest, escort and dungeon scripts; and the matching client pack.
- [ ] Validate the current upstream imports in game: the Playerbots blessing
  planner with historical Blessing of Sanctuary and Improved Might/Wisdom, its
  count-based login rotation with `DisabledWithoutRealPlayer`, Individual
  Progression's Onyxia and Naxxramas 40 entrances for levels 60, 70 and 80,
  DragonUI's inspect window under the EraTalents inspect view, and Questie
  protocol 21 pacing with hidden era questgivers.
- [ ] Validate Dungeon Clear's final-loot wait with open rolls, nearby boss
  corpses and unlootable drops, including the 60-second timeout and ordinary
  party loot rights.
- [ ] Evaluate `IndividualProgression.VanillaHunterPets` and
  `IndividualProgression.WarlockDemonTrainers` before enabling them: existing
  pets lose untaught abilities, and bots still need historical pet-ability
  acquisition from additional beasts and ordinary grimoire purchases.
- [ ] Retain the rated-arena team-era filter while level-70 teams of different
  earned eras can share a native bracket after a TBC-to-Wrath transition.
- [ ] Resolve historically uncertain XP rules before implementation: Vanilla
  repeatable XP, 1.12/2.4.3 hunter-pet XP, elite/raid multipliers and level-60
  gray-level/group split behavior. Review pre-Wrath heirlooms, Experience
  Eliminator and post-2.4.3 Recruit-a-Friend availability separately.
- [ ] Decide a paid-training refund/unlearn policy for later-era class lessons
  learned before the trainer gate. The current gate blocks only new training.

## Auction economy

- [ ] Verify natural disenchanting in game with random enchanters: bound gear
  rated for disenchanting is cast on after vendor, repair and training visits,
  the materials are looted and later listed, Enchanting skill rises, and quest
  items, armor of another type, gear above the bot's level and a real guild's
  rare items are never disenchanted. Cover full bags, mounted or moving bots and
  failed casts.
- [ ] Verify mixed bag upgrades in game: a smaller quiver, ammo pouch or
  profession bag must remain equipped while a normal bag upgrades. Cover all
  four slots, full bags, a new bag stored inside its intended replacement and
  no vendor bag purchase while a won or bid-on auction bag awaits collection.

## Release and tests

- [ ] Complete Windows server and matching client-package verification for
  runtime changes before publishing, alongside the full GitHub checks. Test
  existing-realm migrations on a stopped copy; source fixtures are insufficient.
- [ ] Measure a compiler cache for the Windows build.
