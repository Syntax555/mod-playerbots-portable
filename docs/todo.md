# Roadmap and validation

Open integration work and gameplay validation. Planned work is not a claim of
release support; [bot dungeons and raids](bot-dungeons.md),
[class quests](class-quests.md) and [server adaptations](adaptations.md)
describe the current behavior. Prefer existing AzerothCore and module
functions, with small integration changes where required by earned progression
and ordinary player actions.

## Keeping this list current

Track open implementation and validation work here, with concrete steps and
the checks needed to finish each item. Update affected entries as work
progresses. Check an item only after its required verification passes, and
update the relevant guides in the same commit. Keep in-game and Windows
validation open when those checks have not been run, even if source fixtures
pass.

## Dungeon integration

- [ ] Earned replacements for the refused Dungeon Clear events so the remaining
  Vanilla dungeons can be enabled: Uldaman (earned acquisition of the Staff of
  Prehistoria for Ironaya's keystone), Zul'Farrak (audited acquisition and use of
  the Executioner's Key for the Troll Cage, and ordinary handling of the
  Gahz'rilla gong's special lock) and Blackrock Depths (earned access through
  the Shadowforge Lock with the group's own key).
- [ ] Expand the audited TBC and Wrath routes by providing ordinary player
  actions for currently refused event controllers, escorts, vehicle sequences
  and locked objectives. Verify complete runs before advertising completion.
- [ ] Evaluate heroic autonomous parties separately, including earned access,
  keys, gear suitability and heroic-only encounter mechanics.

## Raid integration

- [ ] Implement autonomous raid scheduling, roster formation and real entrance
  and return travel using native module roles, invitations, groups and raid
  strategies. Preserve every bot's personal access and lockouts, ordinary
  difficulty selection and the pinned Vanilla Naxxramas entrance interaction.
  Do not schedule unsupported routes or encounters.
- [ ] Bots earn raid attunements and keys through their own quest progress
  (Drakefire Amulet, Blackhand's Command, Naxxramas) and respect instance
  lockouts.
- [ ] Molten Core rune dousing with Aqual Quintessence earned by a bot.
- [ ] Raid Clear coverage for Naxxramas as upstream adds it; verify the raid
  before relying on it.
- [ ] Integrate native Sunwell Plateau (map 580) and Trial of the Crusader
  (map 649) strategies when available upstream, or implement their missing
  tactics with earned-progression checks. Neither has a dedicated strategy
  registration in the pinned Playerbots fork; verify complete runs separately.

## Gameplay validation

- [ ] Compare native Vanilla world-buff events with 1.12 behavior and validate
  real Rend, Onyxia/Nefarian and Heart of Hakkar turn-ins in game: both faction
  capitals, Crossroads/Yojamba/Booty Bay delivery, event cooldowns, recipient
  levels and aura scaling, durations, death and dispelling. The shipped profile
  disables simulated turn-ins; the WotLK core's native scripts are not yet a
  verified 1:1 Vanilla implementation.
- [ ] Verify the integrated Playerbots/Raid Clear build on Windows and a stopped
  copy of an existing realm: migrate customized `RaidClear.*` settings into
  `playerbots.conf`, preserve explicit destination values and the old active
  file, then confirm the server loads the migrated switches. Validate raid
  strategy registration, ordinary recovery and natural-progression refusals
  in game; source fixtures do not start a realm.
- [ ] Verify addon startup on a live 3.3.5a client with the forks' MultiBot
  package and Questie installer: the minimap button loads and all three Questie
  bindings remain available without library or duplicate-header errors. Keep
  existing account and character settings; fixtures cover the library load
  order and binding definitions, not the client's rendered UI.
- [ ] Validate the dependency refresh on a stopped test copy of an existing
  realm: numeric account locales migrate to language codes without changing
  login language or characters; `.lfgprogress` explains mixed human/bot earned
  eras; MultiBot role changes survive an AI reset. Verify revised TBC tactics,
  Twin Emperors target priority and dungeon navigation/loot/recovery in-game.
  Natural progression must still refuse floor-rescue teleports and unpaid
  Rocknot quest progress. Native fixtures do not start a realm or WoW client.
- [ ] Validate [combat profiles and equipment](combat-profiles.md) on a live
  client: automatic specialization changes, manual profiles for every class,
  relog/reset persistence, preserved travel and loot settings, and owned bag
  equipment changes, including protection weapon/shield and feral cat/bear.
  Check combat refusals, inventory-space failures, controlled altbots and
  SelfBots, including the compact SelfBot profile selector and returning to
  automatic selection. Verify random-bot builds while leveling across both
  historical eras.
- [ ] Verify loot rolls and automatic equipping with real random-property
  variants of the same item: a stronger variant, an identical or weaker copy,
  equipped unique items and bank-only copies. Check both ordinary group loot
  and native LFG Need restrictions with `Playerbots.LootNeedRollLevel = 2`;
  a refused Need must retain the ordinary Greed/Pass behavior.
- [ ] Verify startup data repairs on a fresh world database and an existing
  installation: historical priest rank chains, AQ event dragon menus, the
  retired Mirelow pool and the native Submerge Visual binding. Confirm the
  Mirelow patrol, AQ actors and submerge/stand transitions in-game; source
  fixtures do not start a realm.
- [ ] Start the worldserver on an empty world database and on a stopped copy of
  an existing realm: the updater must finish without errors, record the
  Individual Progression cleanup under its new name without reapplying it, and
  `.help lfgprogress` must show the help text. On the upgraded copy, complete
  Drijya's escort (quest 10310) and confirm Summoner Kanthin's patrol and no
  duplicate Sunfury Magisters. A MySQL replay of the updater and the fixtures
  cover the data, not a running realm.
- [ ] Verify MultiBot altbot vendor purchases on a live 3.3.5a client: Buy mode,
  left/right clicks, quantities, expensive and currency-item confirmations,
  bot switches and inventory closure. Confirm the bot's own gold and bag
  changes, native vendor refusals and no owner purchase on bridge failure.
- [ ] Verify MultiBot altbot talent learning on a live 3.3.5a client for Vanilla
  and TBC bots: the talent button opens the inspect talent tab, each click buys
  one rank with the bot's own points, refused prerequisites leave the ranks
  unchanged and repeated clicks spend one point at a time. Confirm that other
  characters, out-of-range bots and bots that leave your group or control stay
  read-only.
- [ ] Validate the [Questie Playerbots integration](questie-playerbots.md) on a
  live 3.3.5a client using the fork's installer and matching server ZIP.
  Creature, item and map tooltips for a shared item quest with an Individual
  Progression item mismatch, and party map icons for a bot-only kill quest,
  are confirmed with one altbot and the adapted addon. Still check
  simultaneous bot progress, kill-credit and event objectives,
  turn-in/abandonment, mixed human groups and logout/reconnect. Measure tick
  time and addon traffic with several watched groups; standalone C++/Lua
  fixtures do not exercise rendering or sustained realm load.
- [ ] Validate the [Zygor Individual Progression integration](zygor-progression.md)
  on a live 3.3.5a client using the fork's installer and matching server ZIP:
  status after login and
  reconnect, step skipping for a tier-gated quest and a hidden giver, the hold
  before Outland at level 60 and before Northrend at 70, the guide browser,
  Gear Finder sources at tiers 7, 8 and 13, the inactive Talent Advisor for an
  EraTalents character and addon traffic in a group. The Lua fixture does not
  render frames or exercise the live bridge.
- [ ] Verify the inspected-altbot Gear Finder on a live client with stock and
  DragonUI inspect windows: current and later-era dungeons, quest-giver access,
  faction-specific vendors, different owner/bot classes and profiles, cold
  inspect data, empty equipment, profile and equipment changes, rapid target
  switches and closing the view during replies. Measure frame time and addon
  traffic; source fixtures cover the scan slices and cancellation, not rendered
  graphics or a loaded realm.
- [ ] Validate the [DragonUI talent route](era-talents.md#dragonui) on a live
  client with DragonUI's talent module enabled: talent key, micro-button,
  `/talents`, spec tabs, glyph page, a hunter's pet tree, and inspecting an
  era altbot and a Wrath character. Check the historical talent nodes, seven-row
  Vanilla and nine-row TBC layout, connections, search and tooltips in the
  DragonUI window, plus manual learning through MultiBot and target switching.
  Check that the spellbook's unlearned spells
  match a class trainer for a Vanilla, TBC and Wrath character. The Lua
  fixtures run DragonUI's talent renderer and controls, entry points,
  spellbook catalogue and level-up builder but do not render game graphics.
  Confirm the selected bot's MultiBot talent button stays pressed only while
  its stock or DragonUI inspect view is visible, while the player's talent
  micro-button follows the player's own window. Check split background textures
  on D3D9 and D3D9Ex, including historical class trees and the hunter's pet tree.
- [ ] Check the MultiBot bot spellbook in DragonUI's book on a live client:
  art, tabs, tree sections, search, paging, single-page mode, cast, macro and
  shift-click skip for an era altbot, next to the player's own book. The Lua
  fixture runs DragonUI's layout and search code and MultiBot's spellbook
  collection but does not render frames. Check both halves of the book header
  in single- and two-page views on D3D9 and D3D9Ex.
- [ ] Decide whether characters that trained a TBC or Wrath class lesson
  before the trainer gate existed should unlearn it with a refund of the
  training cost. The gate only stops new training.
- [ ] DragonUI's level-up notice hard-codes its Dungeon Finder, glyph and dual
  specialization lines in local tables. Hiding them before a character can use
  them needs a data hook in upstream DragonUI.
- [ ] Verify complete runs in-game for each enabled Vanilla, TBC and Wrath
  dungeon: walking to the entrance, combat, loot rolls, quest objectives, wipes
  and normal recovery.
  Remove a failing dungeon from the default list until it is fixed. Confirm bot
  logout after the last real player session ends.
- [ ] Verify complete Wailing Caverns clears in-game: backtrack from Skum to
  Anacondra's platform, climb the native patrol ramp to Serpentis and return
  from Verdan over the ramp to the Disciple. Check every member's actual path,
  bends, correct floor and water movement; missing mesh or an unsafe follower
  route must stop the attempt. Cover all four Fanglord prerequisites, ordinary
  gossip, the native escort pace, ambushes, cleansing channel, ritual waves,
  Mutanus and Naralex's final dialogue. Check combat, loot, casting, food/drink
  and group spacing between waves, a dead or absent Disciple, native range reset,
  wipe and normal return travel, stop/pause/resume, the fifteen-minute budget,
  a fresh instance and a missed departure marker after the native despawn.
- [ ] Verify the Deadmines cannon in-game: the tank walks to and loots the
  gunpowder chest, handles its native ambushes, returns to the cannon and
  consumes the powder through ordinary item use. Cover full bags, missing or
  inaccessible powder, another character carrying it, interrupted casts,
  druid forms, an already open door and resuming the same instance. Confirm
  an autonomous party retains every member's personal entry and era checks.
- [ ] Verify both Uldaman altars in-game: physical approach and line of sight,
  the native five-second channel, interruptions and retries, an already active
  keeper chain or Archaedas fight, reset after a wipe and walking back from the
  entrance, resuming the same instance, a completed encounter, ritual-owner
  group changes or logout, and a fresh instance. Confirm normal combat and
  door opening, with no direct awakening casts or premature objective credit.
  Check Ironaya's seal with the group's own Staff of Prehistoria; autonomous
  recruitment must remain refused until its acquisition has an audited path.
- [ ] Verify complete player-led Zul'Farrak clears in-game: the tank walks into
  Zum'rah's native trigger volume, the core activates him and the party fights
  normally. Cover interrupted approaches, combat, casting and looting, missing
  mesh, an unavailable boss, a different phase or instance, a human starting
  first, an already hostile or dead boss, a native reset after a wipe, ordinary
  resurrection and return travel, stop/pause/resume and a fresh instance. A
  refused trigger must not produce artificial activation or kill credit.
  Confirm the Troll Cage still needs an earned Executioner's Key and the
  Gahz'rilla gong keeps its own normal opening requirements; autonomous
  recruitment must remain refused until those interactions are audited.
- [ ] Verify complete Ring of Law and Blackrock Depths clears in-game: every
  member physically enters the arena, the native trigger starts Grimstone,
  both waves and the random boss are fought normally, and the objective waits
  for Grimstone's final waypoint and native encounter credit. Cover interrupted
  approaches, combat and looting while gathering, missing mesh, a trailing or
  disconnected member, a human starting early, an already running event,
  a wipe with ordinary resurrection and return travel, the two-minute reset
  cooldown, stop/resume, a completed event and a fresh instance. Confirm the
  separate Shadowforge key requirement still refuses autonomous recruitment.
- [ ] Verify long entrance and return paths in-game, including bends,
  interrupted movement and changed obstacles. Measure server tick time while
  multiple groups are travelling.
- [ ] Verify player-led Molten Core, Blackwing Lair, Zul'Gurub and Ahn'Qiraj raids
  with Raid Clear, including the Suppression Room without the raid cheat.
- [ ] Verify a complete player-led Onyxia clear with Raid Clear and Playerbots:
  each member's personal progression, Drakefire Amulet and portal refusal;
  ground, air and landing phases; all Deep Breath directions, Fireball spacing,
  head/tail positioning, Fear and threat recovery; restored Vanilla whelp
  targeting, evading mobs, wipe and ordinary recovery. Check earned-era
  EraTalents spells with normal resources, cooldowns, range and line of sight,
  plus strategy recovery after an AI reset and the Onyxia enable switch.
- [ ] Audit historical class quests beyond the restored priest families across
  Vanilla, TBC and Wrath, including teacher availability, objectives, rewards
  and paid training. Apply targeted fixes for confirmed discrepancies.
- [ ] Record verified content and remaining limits in the public guides,
  including matching EraTalents and MultiBot inspection behavior.
- [ ] Verify in-game the behavior covered so far only by fixtures: discovered
  flight routes, Drain Soul shards for every warlock spec, SelfBot talent
  points, weighted bot specs, Spirit of Zandalar at the Zul'Gurub stage, Halion
  credit in the Twilight Realm, dungeon recruitment at refused portals,
  vendor bag purchases, pet-food reserves for summoned and stored hunter pets,
  and earned auction trading: market trips, listings, bids, refusals and receipt
  collection.
- [ ] Verify era experience in game: quest values per era, battleground
  objective XP, heirloom and holiday bonuses, and rest and quest money at the
  60/70 era caps. Check Thrallmar's and Honor Hold's Favor on kills, quests and
  exploration, including stacking with other XP bonuses and pet XP.

## Dependency updates

- [x] Use Zygor's existing Gear Finder for the visibly inspected controlled
  altbot, with its own profile, equipment, progression and verified source
  access. Fixtures cover owner isolation, bounded scanning, target changes and
  stale replies; live validation remains listed above.
- [ ] Expose reusable DragonUI spellbook card, section-header and window
  construction for EraTalents' bot book. Keep bot data and MultiBot actions in
  EraTalents, and reuse DragonUI's rendering helpers instead of mirroring
  `book_slots.lua`. Cover standalone MultiBot, disabled DragonUI modules,
  paging, search and bot switching before removing the duplicate UI code.
- [ ] Submit the prepared Individual Progression filter fix upstream when
  repository permissions allow; see the
  [upstream proposals](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/upstream/README.md).
- [ ] Track the generic core proposals and Individual Progression empty-filter
  guards; the [checked upstream sources](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/upstream/README.md#integration-status)
  still need all four local fixes. Pin compatible accepted fixes before removing
  only their corresponding local hunks.
- [ ] Follow the Questie Playerbots integration upstream in
  [Aldori15/Questie#172](https://github.com/Aldori15/Questie/pull/172), which
  carries the fork's change and its regression test. After it is accepted,
  merge upstream into the fork's `335` branch, pin the merge and point
  `forkChanges` at the accepted commit before rerunning the Questie fixtures.

## Core and module forks

- [ ] Share talent-tab totals between Playerbots' `AiFactory::GetPlayerSpecTabs`
  and the MultiBot bridge's `BuildTalentTabPoints`. First align removed-talent,
  active-spec mask and `TalentEntry::RankID` handling in the native helper;
  compare both callers for Wrath and historical trees in the combat-profile
  fixtures before removing the bridge calculation.
- [ ] Correct native bank quest accounting before replacing the bridge's
  `MoveNaturalBankItem`: deposits must check quest counts before removing the
  source item, and withdrawals must credit only the transferred count when
  merging stacks. Exercise completed objectives and existing destination
  stacks, then retain banker interaction, session ownership and transfer-result
  checks around the native handlers.
- [ ] Keep the rated-arena team-era filter while retained level-70 teams can
  enter the same native bracket with different earned eras after a TBC-to-Wrath
  realm transition. Remove it only if the native admission rules make this
  impossible without restricting existing characters or teams.
- [ ] Decide era experience rules with weak sources: Vanilla repeatable quests
  paying XP on every turn-in; the 1.12/2.4.3 hunter pet XP requirement; dungeon
  and raid elite multipliers (Outland ×4.5 versus TBC DB ×2.5/×2.0, Vanilla
  bosses ×4 versus ×5); gray level 47 at level 60 for group splits, which needs
  a core change.
- [ ] Heirloom item stats and Experience Eliminator availability before Wrath.
- [x] [Core experience rules](changing-expansions.md#experience-by-era) shared
  by every era: raid groups receive no party XP bonus outside raid maps, and
  online rest accrues at the ordinary inn rate.
- [x] Thrallmar's and Honor Hold's Favor grant their 5% XP bonus once per
  award: kills use the linked aura in `KillRewarder`, while quest and
  exploration rewards keep the zone bonus in `Player::GiveXP`. The TBC era
  policy retains the kill aura.
- [ ] Recruit-a-Friend started after the 2.4.3 release; decide whether TBC and
  Wrath characters should regain it.

## Auction economy

- [ ] Disenchanting in natural upkeep. Enchanting bots sell outgrown bound gear
  to vendors and keep gear without a sell price.
- [ ] `Playerbots.DeleteRandomBotAccounts` deletes the items of random bots'
  auctions with their characters; the core then drops those auctions without
  refunding their bidders.
- [ ] While a hunter's quiver or ammo pouch is its smallest bag, bots buy no
  larger general bag for the other slots, because `EquipAction` would replace
  the quiver. A type-aware bag slot there would also change players' equip
  commands.
- [ ] Unsold-stock records live in server memory; a restart forgets them.
- [x] Won items refused by the core's unique-item or ownership-category limits
  stay in mail without blocking other auction purchases. Native fixtures cover
  inventory and bank limits, preserved receipts and ordinary collection after
  the owned count drops.
- [ ] Upkeep can buy a vendor bag while a won auction bag still waits in the
  mail; the later bag may no longer be an upgrade.
- [x] Protect the last pet-food reserve for owned hunter pets, including
  dismissed and stabled pets and pets temporarily unsummoned by a mount,
  using their native food types and diets.

## Launcher and updates

- [ ] Sign `UPDATE_MANIFEST.json` so a token that can upload release assets
  cannot push code to installations.
- [ ] Evaluate starting `mysqld` with `--no-monitor` and tracking the server
  process directly, and applying updates in-process instead of through the
  detached helper.

## Release and tests

- [ ] Verify the pinned core and all nine native module forks with the full
  server checks and a complete Windows server and matching client-package
  build before publishing the resulting release.
- [ ] Measure a compiler cache for the Windows compile step.
