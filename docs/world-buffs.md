# World buffs

The default profile uses the core's quest-triggered world-buff events.
Automatic simulated turn-ins through
[World Buff Bots](https://github.com/Syntax555/mod-world-buff-bots) are
disabled. Playerbots' synthetic world-buff supplies are also disabled by
natural progression. No client addon is required.

## Vanilla events

Warchief's Blessing follows the Rend head quest, Rallying Cry of the
Dragonslayer follows the Onyxia/Nefarian head quests, and Spirit of Zandalar
follows the Heart of Hakkar quest. Their native scripts control delivery,
announcements and event state. Warchief lasts 60 minutes; Dragonslayer and
Zandalar last 120 minutes. The timer module does not change those durations
or the real quest events.

This distribution uses AzerothCore's WotLK implementation and Individual
Progression. Disabling simulated turn-ins does not establish complete Vanilla
1.12 parity; native event cooldowns, recipient rules and lower-level scaling
still require comparison and in-game validation.

## Optional simulator

Setting `WorldBuffBots.Enable = 1` opts into automatic events without a real
quest turn-in. These events are an alternative to the default quest-only
behavior. The simulator applies the following rules to humans, controlled
altbots, random bots and SelfBot characters alike.

| Buff | Timer location | Native duration | Recipient conditions |
| --- | --- | --- | --- |
| Warchief's Blessing, spell 16609 | Orgrimmar; the Crossroads 10 seconds later | 60 minutes | Horde, Friendly or higher with Orgrimmar |
| Rallying Cry of the Dragonslayer, spell 22888 | Stormwind | 120 minutes | Native aura conditions and lower-level stat scaling |
| Spirit of Zandalar, spell 24425 | Stranglethorn Vale | 120 minutes | Individual Progression's Zul'Gurub entry tier, 3 by default; native aura conditions |

All timer recipients must be alive, in the world, outside GM mode, at most
level 63 and in the Vanilla era after applying the realm's
`IndividualProgression.ProgressionLimit` ceiling (tiers 0–7 with the shipped
unlimited progression). Spirit of Zandalar also
requires the tier at which Zul'Gurub opens to the recipient
(`IndividualProgression.RequiredZulGurubProgression`). The recipient's own tier
is used even in a mixed-era party. On the shipped realm, TBC and Wrath characters
receive no aura from these simulated events. Native quest turn-ins retain their
core behavior.

Each buff has an independent timer: initially 30–150 minutes, then 90 minutes
plus or minus 60 minutes. Timers reset when worldserver starts or reloads its
configuration. Only characters present at the event's location receive its
aura; arriving later does not replay the event. The Crossroads delivery checks
eligibility again after its delay.

These events grant temporary auras. They do not complete quests, defeat bosses,
grant progression credit or create items, money or characters. Announcements
identify the available buff and location.

## TBC events

TBC buffs retain their regular quests, areas and world-state lifecycle:

- **A'dal's Song of Battle:** the Shattrath quest event, with native area handling
  for Shattrath and the Tempest Keep dungeons.
- **Magtheridon's head buffs:** the faction-specific Hellfire Peninsula events.
- **K'iru's Song of Victory:** Individual Progression's personal Isle of
  Quel'Danas requirements, including Shattered Sun Offensive reputation and
  rewarded daily quests.

The Vanilla timer module does not distribute TBC buffs. Playerbots' synthetic
world-buff supplies remain disabled by natural progression; flasks, food and
other consumables follow their ordinary acquisition rules.

## Configuration

Edit `configs/modules/mod_world_buff_bots.conf` with the servers stopped.

| Setting | Default | Purpose |
| --- | --- | --- |
| `WorldBuffBots.Enable` | `0` | Opt into simulated Vanilla events |
| `WorldBuffBots.BaseMinutes` / `VarianceMinutes` | `90` / `60` | Repeat interval and random variation |
| `WorldBuffBots.InitialMinMinutes` / `InitialMaxMinutes` | `30` / `150` | First event delay after startup or reload |
| `WorldBuffBots.Warchief.Enable` | `1` | Warchief event |
| `WorldBuffBots.Warchief.IncludeCrossroads` | `1` | Delayed Crossroads delivery |
| `WorldBuffBots.Dragonslayer.Enable` | `1` | Stormwind event |
| `WorldBuffBots.Zandalar.Enable` | `1` | Stranglethorn Vale event |
| `WorldBuffBots.Debug` | `0` | Additional event logs |

The three `*.Announcement` settings control broadcast text. Custom messages may
use `{player}` (or the legacy `%s`) for a random announcer name and `{buff}` for
the buff name. Warchief uses the Horde pool, Dragonslayer the Alliance pool and
Zandalar either pool. These are display names; no character is created or
credited with a quest turn-in. The default messages describe the buff and
location without an announcer name.

Each event also requires enabled Individual Progression, strict earned mode,
the default progression chain and an empty `CustomProgression`. With an inactive
or custom chain, the simulator supplies no Vanilla buffs because the tier numbers
no longer establish the required era.

The launcher adds missing module configuration. A saved, unchanged managed
`WorldBuffBots.Enable = 1` follows the new default of `0` on update; custom
values and existing values without a saved baseline are preserved. For a
quest-only existing realm, stop the servers and set `WorldBuffBots.Enable = 0`
in its active configuration. See [configuration updates](configuration.md) and
[server adaptations](adaptations.md) for the integration rules. Exact source
revisions and fork changes are recorded in [the manifest](../versions.lock.json).
