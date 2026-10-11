# World buffs

The default profile enables timed Vanilla events through
[World Buff Bots](https://github.com/Rockhopper1776/mod-world-buff-bots). Each
event checks the recipient's own rewarded Individual Progression milestones.
Humans, controlled altbots, random bots and SelfBot characters share these rules.
No client addon is required.

## Vanilla events

| Buff | Timer location | Native duration | Recipient conditions |
| --- | --- | --- | --- |
| Warchief's Blessing, spell 16609 | Orgrimmar; the Crossroads 10 seconds later | 60 minutes | Horde, Friendly or higher with Orgrimmar |
| Rallying Cry of the Dragonslayer, spell 22888 | Stormwind | 120 minutes | Native aura conditions and lower-level stat scaling |
| Spirit of Zandalar, spell 24425 | Stranglethorn Vale | 120 minutes | Native aura conditions |

All timer recipients must be alive, in the world, outside GM mode, at most
level 63 and in Vanilla progression (tiers 0–7). The recipient's own tier is
used even in a mixed-era party. TBC and Wrath characters receive no aura from
these simulated events. Native quest turn-ins retain their core behavior.

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
| `WorldBuffBots.Enable` | `1` | Enable simulated Vanilla events |
| `WorldBuffBots.BaseMinutes` / `VarianceMinutes` | `90` / `60` | Repeat interval and random variation |
| `WorldBuffBots.InitialMinMinutes` / `InitialMaxMinutes` | `30` / `150` | First event delay after startup or reload |
| `WorldBuffBots.Warchief.Enable` | `1` | Warchief event |
| `WorldBuffBots.Warchief.IncludeCrossroads` | `1` | Delayed Crossroads delivery |
| `WorldBuffBots.Dragonslayer.Enable` | `1` | Stormwind event |
| `WorldBuffBots.Zandalar.Enable` | `1` | Stranglethorn Vale event |
| `WorldBuffBots.Debug` | `0` | Additional event logs |

The three `*.Announcement` settings control broadcast text. Each event also
requires enabled Individual Progression, strict earned mode, the default
progression chain and an empty `CustomProgression`. With an inactive or custom
chain, the simulator supplies no Vanilla buffs because the tier numbers no
longer establish the required era.

The launcher adds missing module configuration and preserves existing custom
values. See [configuration updates](vanilla-config-audit.md) and
[server adaptations](adaptations.md) for the integration rules. Exact source
revisions and patches are recorded in [the manifest](../versions.lock.json).
