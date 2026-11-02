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
  duplicate Sunfury Magisters. MySQL replay and source fixtures do not
  establish running-realm behavior.

### Bots, talents and client interfaces

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
- [ ] Test Zygor's inspected-altbot Gear Finder with stock and DragonUI views:
  bot/owner class differences, empty/cold data, profile/equipment changes,
  faction/era/quest/vendor access, rapid target switches and closing during
  replies. Measure frame time and traffic; fixtures do not render the UI.
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
  The Affray 1719; and paladin The Tome of Valor 1652 / Return to Silvermoon
  9691. Verify the correct owned items, targets, ordinary interactions, rewards
  and each character's own era. Native quest availability alone does not prove
  autonomous completion. Retain player-controlled character ownership.
- [ ] **Warrior:** Verify the racial defensive-stance quest routes, including
  Path of Defense (1498), and The Islander / The Affray (1719) for Berserker
  Stance and Intercept. Check ordinary quest-giver access, the arena event,
  survival, quest credit, turn-in and later paid ranks in each earned era.
- [ ] **Paladin:** Verify racial resurrection quest chains, including The Tome
  of Divinity (1785/1788), Redemption (9600) and Redeeming the Dead (9685),
  plus The Tome of Valor (1652) / Return to Silvermoon (9691) and their
  prerequisites. Check the event, earned spell and later trainer availability;
  audit class-mount quest chains separately.
- [ ] **Hunter:** Validate all six first-pet lesson chains and Training the
  Beast using the existing native-quest bot actions, including interrupted
  casts, owned rods, travel, pet preservation and subsequent feeding/revival.
  Historical ability acquisition by taming additional beasts is not implemented;
  keep `VanillaHunterPets` disabled until that and existing-pet migration have
  been evaluated.
- [ ] **Rogue:** Audit the racial lockpicking and poison quest chains, including
  Klaven's Tower (2359), for the required keys, chests, skills, quest items and
  native credit. Verify that learned poison abilities and owned consumables are
  available to the existing combat actions in the character's earned era.
- [ ] **Priest:** Verify each restored racial quest family end to end, including
  Desperate Prayer, Fear Ward and the race-specific rewards listed in the
  [class quest guide](class-quests.md#priest-training). Check teacher access,
  prerequisites, ordinary turn-in, earned rank 1 and paid later ranks; do not
  infer autonomous completion from the restored quest data.
- [ ] **Shaman:** Audit racial Call of Earth, Fire, Water and Air chains,
  including 1518/1521/9451, 1527/9555, 96/9509 and 1531/1532/9554. Check
  source items, elemental encounters, native quest credit, totem rewards and
  subsequent paid spells; scripted objectives need explicit handling if the
  ordinary quest actions cannot perform them.
- [ ] **Mage:** Audit class quest chains and their era-specific prerequisites,
  including Magecraft (8250), Fragmented Magic (9364) and Attunement to Dalaran
  (12172/12173). Verify actual rewards and trainer requirements before treating
  a quest as necessary for a spell; check ordinary travel and item use.
- [ ] **Warlock:** Live-verify the 43-quest Imp, Voidwalker, Succubus and
  Felhunter action for all four Vanilla warlock races. It accepts and rewards
  native quests, uses ordinary kills/chest loot and owned ritual items, and
  leaves demon combat and credit to native scripts. Imp questgiver relations
  are restored by Individual Progression. Verify the earned continent routes
  for Alliance Heartswood and the Felhunter chains, including map transfers
  while aboard and disembarking. Check recovery after relogs, missing ritual
  items and native event resets before claiming autonomous end-to-end completion.
  Add the blood elf Voidwalker quests 9529/9619, class mounts, Infernal and
  Doomguard quests. Historical demon grimoire purchases remain unimplemented;
  keep `WarlockDemonTrainers` disabled until evaluated. See the
  [implemented scope](class-quests.md#autonomous-warlock-demon-quests).
- [ ] **Druid:** Audit racial form and class-spell quests, including Aquatic
  Form (31/5061), Body and Heart (6001/6002) and Power over Poison (6125/6130).
  Verify ordinary underwater travel, quest items, native rewards and trainer
  requirements for each earned era; existing form combat actions alone do not
  establish that the prerequisite quests can be completed.
- [ ] **Death knight:** Audit the Acherus starting chain, including The
  Emblazoned Runeblade (12619), Into the Realm of Shadows (12687) and The Light
  of Dawn (12801), before claiming autonomous completion. Random death-knight
  login is disabled in the portable profile; controlled characters keep their
  owner's choices and must meet ordinary starting-chain and era requirements.
- [ ] Verify era XP: quest values, battleground goals, rest/heirloom/holiday
  modifiers, era-cap money and Thrallmar/Honor Hold Favor without double bonuses.
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
  the reference core pins aligned with the verified source data.
- [ ] Submit the prepared Individual Progression empty-filter fix when upstream
  permissions permit. Track the generic core proposals and remove local hunks
  only after accepted compatible fixes are pinned and checked; see
  [upstream proposals](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/upstream/README.md).

## Core and module forks

- [ ] Validate Grimfeather's Individual Progression and core changes in game:
  the original Alterac Valley layout, mines, quests and Playerbots tactics;
  restored quest, escort and dungeon scripts; and the matching client pack.
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

- [ ] Disenchanting in natural upkeep; bound outgrown equipment currently goes
  to vendors when it has a sell price.
- [ ] Verify mixed bag upgrades in game: a smaller quiver, ammo pouch or
  profession bag must remain equipped while a normal bag upgrades. Cover all
  four slots, full bags, a new bag stored inside its intended replacement and
  no vendor bag purchase while a won or bid-on auction bag awaits collection.

## Release and tests

- [ ] Complete Windows server and matching client-package verification for
  runtime changes before publishing, alongside the full GitHub checks. Test
  existing-realm migrations on a stopped copy; source fixtures are insufficient.
- [ ] Measure a compiler cache for the Windows build.
