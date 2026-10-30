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
  dragon menus, retired Mirelow pool, Submerge Visual, Drijya's escort (10310),
  Summoner Kanthin's patrol and duplicate Sunfury Magisters. MySQL replay and
  source fixtures do not establish running-realm behavior.

### Bots, talents and client interfaces

- [ ] Validate repeated deaths and long corpse runs outside and in dungeons,
  including reduced AI activity, controlled altbots and SelfBots. Check normal
  spirit release, group resurrection waits, reclaim limits and missing routes.
- [ ] Test [combat profiles](combat-profiles.md) for every class on random bots,
  controlled altbots and SelfBots: automatic/manual selection, relog/AI resets,
  combat refusal, retained travel/loot settings and owned-item upgrades.
  Include protection weapon/shield, feral cat/bear and historical-era builds;
  controlled characters' talent points must remain manual.
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
  restoration; no raid-cheat Suppression Room or floor-rescue bypass.
- [ ] Compare native Vanilla world-buff turn-ins with 1.12: faction delivery,
  cooldowns, recipient levels/scaling, duration, death and dispel. Simulated
  turn-ins remain disabled; native WotLK scripts are not a verified 1:1 model.
- [ ] Audit historical class quests beyond restored priest families and test
  teachers, requirements, rewards and paid training. Validate Halion's Twilight
  Realm credit and the Spirit of Zandalar earned tier.
- [ ] Verify era XP: quest values, battleground goals, rest/heirloom/holiday
  modifiers, era-cap money and Thrallmar/Honor Hold Favor without double bonuses.

## Dependency updates

- [ ] Submit the prepared Individual Progression empty-filter fix when upstream
  permissions permit. Track the generic core proposals and remove local hunks
  only after accepted compatible fixes are pinned and checked; see
  [upstream proposals](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/upstream/README.md).

## Core and module forks

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
- [ ] Protect bidders when `Playerbots.DeleteRandomBotAccounts` removes bot
  auction items; the core currently drops those auctions without refunds.
- [ ] Verify mixed bag upgrades in game: a smaller quiver, ammo pouch or
  profession bag must remain equipped while a normal bag upgrades. Cover all
  four slots, full bags, a new bag stored inside its intended replacement and
  no vendor bag purchase while a won or bid-on auction bag awaits collection.
- [ ] Decide whether unsold-stock memory should survive server restarts.

## Launcher and updates

- [ ] Evaluate direct MySQL process tracking with `--no-monitor` and in-process
  updates against the detached helper's Windows lock/recovery requirements.

## Release and tests

- [ ] Complete Windows server and matching client-package verification for
  runtime changes before publishing, alongside the full GitHub checks. Test
  existing-realm migrations on a stopped copy; source fixtures are insufficient.
- [ ] Measure a compiler cache for the Windows build.
