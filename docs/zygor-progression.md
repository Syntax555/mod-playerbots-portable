# Zygor Individual Progression

Zygor Guides Viewer Remaster follows each character's own Individual
Progression tier with a pinned local patch. The server reports the tier, quest
availability and instance access through the MultiBot Bridge; the addon only
reads them. It cannot award, change or bypass progression, and an unknown
state never unlocks content.

## Installation

Use WoW **3.3.5a, build 12340** and the matching server and Zygor IP installer
from the [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
The prebuilt server includes the bridge support; no server setting is needed.

1. Download [Zygor-IP-latest.zip](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/Zygor-IP-latest.zip)
   and extract it to a folder outside your WoW installation.
2. Close WoW completely. Run `Install-Zygor.cmd` and enter your client's
   `Interface/AddOns/` folder when prompted. Internet access is required; the
   installer uses Windows PowerShell and does not require administrator rights.
3. Start WoW and enable Zygor Guides Viewer in the addon list. Disable a
   separate `ZygorGuidesViewer` or `ZygorTalentAdvisor` addon; the installer
   warns when it finds one.

The installer downloads the pinned addon directly from upstream. It accepts the
archive only when every file of its `ZygorGuidesViewerRM/` folder matches the
pinned Git tree, applies the integration locally and checks every patched file
and the TOC's interface and files. It backs up an existing `ZygorGuidesViewerRM/`
folder before replacement and records the installed revision in
`SOURCE_REVISION.txt` and `SOURCE_MANIFEST.json`. Account and character
SavedVariables, including Zygor's settings, are preserved. The release ZIP
contains only the installer, the file list and the patch data.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Zygor.ps1 -AddOnsPath 'C:\Games\WoW\Interface\AddOns'
```

## Guide behaviour

The **Progress** options panel (`/zgprogress`) and `/zygorip` show the mode,
the saved and usable tier, the realm ceiling, the experience cap and the next
milestone of the default chain. `/zygorip refresh` asks the server again.

| Mode | Behaviour |
| --- | --- |
| Automatic (default) | Follows the server when it reports Individual Progression. Without a bridge, or on a realm without the module, guides behave as on an ordinary realm. |
| On | As Automatic, but later content stays locked while no server answer is available. |
| Off | No Individual Progression limits. |

Until the server's first answer arrives, later content counts as unknown. A
client that gets no bridge answer after three probes, about a minute, uses the
mode's behaviour without a bridge.

Gates apply to normal accounts. Bot and excluded accounts and game master mode
are not limited, as on the server. Content is classified as available, locked
or unknown; locked and unknown content is never presented as available.

- **Quests.** A step is skipped and a goal hidden only when the server reports
  its quest unavailable for a lasting reason: a progression marker condition,
  a quest giver hidden at this tier, class, race, a disabled quest, an
  outleveled quest, a taken alternative or a breadcrumb whose follow-up is
  taken. A missing level, reputation, skill, previous quest or reset keeps the
  step. Quests in the quest log and completed quests are always kept. Goal
  tooltips name the reason and the tier a quest needs or retired at.
- **Guides.** A guide needs the tier of the zones it travels to: Outland 8,
  Isle of Quel'Danas 12 and Northrend 13, as Individual Progression's map gate
  decides. The TBC race starting zones need no tier for Draenei and Blood
  Elves; other races are treated as tier 8 because their account unlock is not
  visible to the client. A leveling guide that starts at the character's
  experience cap (60 before tier 8, 70 before tier 13) is locked, and so is a
  guide entering an instance that Individual Progression's map gate refuses.
- **Guide chains.** A finished guide does not switch to a next guide this
  character cannot follow; a final step names the guide and the reason.
  Loading such a guide manually prints the reason once. The guide browser's
  suggestions leave such guides out, and its details show the reason.
- **Milestones.** *Individual Progression\\Milestone Chain* lists the default
  chain; each step completes from the server's tier, and milestones above the
  realm ceiling are replaced by a note.
- **Gear Finder.** Dungeon and raid loot counts as current only when the earned
  tier opens the content's era and Wrath phase and the server reports the
  instance accessible in its difficulty. Content behind a later tier is a
  *next tier* or *later tier* source. Disabled, unmapped and unverified sources,
  such as outdoor world bosses, are neither current nor future. Currency
  vendors follow their era. Crafted gear needs an earned era and a recipe the
  character knows or a trainer recipe; other recipe sources are not verified.
  The stat weights follow the character's talents: for an EraTalents
  character, the most-spent tab of its Vanilla or TBC tree. Before Wrath,
  without EraTalents data, the class's leveling build applies and can be
  chosen in the gear options.
- **Best-in-slot lists.** The Wrath lists apply from tier 13; tier 13 opens T7
  and each later tier the next list. Earlier eras get no annotation.
- **Talent Advisor.** The bundled advisor knows only the native Wrath trees.
  It stays inactive, with the native `LearnTalent` function and learn button,
  for EraTalents characters, before the earned Wrath era and while the era is
  unknown. It makes no suggestions, popups or automatic learning then.
- **Quest automation.** *Bang a Gong!*, *Chaos and Destruction* and *Into the
  Breach* decide progression and are never accepted or turned in automatically.
- **Gold Guide.** Farming and gathering routes follow the same zone and
  instance checks.

Text is available in English and German.

### Feature review

| Feature | Upstream behaviour | Progression risk | Server source | Integration | Unknown state | Off or other realms | Verification | Limit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Leveling steps | Level and quest chain data | Quests of later tiers or hidden givers | `IP_QUESTS` | Skip steps, hide goals | Step kept | Unchanged | Fixture | Unspawned or differently scripted givers count as visible |
| Guide chains | `next` switches at the end | TBC at 60, Wrath at 70 | `IP_STATE`, `IP_ACCESS` | Hold with reason | Held | Unchanged | Fixture | Zones outside the table need no tier |
| Guide browser | Level, class and chain suggestions | Later-tier guides suggested | Same | Suggestions filtered, reason shown | Filtered | Unchanged | Fixture | Manual selection stays possible |
| Dungeons and raids | Level and attunement | Locked raids shown as current | `IP_ACCESS` | Future or unknown source | Not current | Unchanged | Fixture | Locks and group rules not reported |
| Gear Finder phases | All Wrath phases on 3.3.5a | Later raid tiers | `IP_STATE` | Phase per tier 13–17 | Inactive | Unchanged | Fixture | Wrath phases only |
| Gear Finder weights | Spec from native talent points, retried while empty | Endless rescans for historical trees | EraTalents, `IP_STATE` | Historical tab points | Native retry | Unchanged | Fixture | Feral tank check uses native talents |
| Vendors and crafting | Expansion filters | Later-era currency and recipes | `IP_STATE` | Era gate, known or trainer recipes | Not current | Unchanged | Fixture | Recipe drops not verified |
| Best-in-slot | Wrath phase lists | Later raid lists as current | `IP_STATE` | Rank from tier | No annotation | Unchanged | Fixture | Wrath lists only |
| Talent Advisor | Wraps `LearnTalent`, Wrath builds | Wrong trees, automatic spending | `IP_STATE`, EraTalents | Inactive outside Wrath | Inactive | Unchanged | Fixture | Wrath builds only |
| Quest automation | Auto accept and turn-in | Progression decisions | — | Transition quests manual | Manual | Unchanged | Fixture | — |
| Gold Guide routes | Skill and level | Routes in locked zones | Same as guides | Route validity | Invalid | Unchanged | Fixture | Auction data is the player's own scan |
| Questie and MultiBot | Separate addons | — | Bridge | Unchanged | — | — | Upstream suites | — |

Reputation, profession, mount, pet, achievement, daily and event guides use the
same quest, zone and instance checks. Their own requirements remain the
guides' steps. The module does not change navigation and adds no route,
teleport or purchase.

### Upstream revision

The patch is pinned to `ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK`; see
[dependencies](module-versions.md). The fell-lucas fork adds party goal sync
(`Sync.lua`, AceComm and LibDeflate) on an older base. It is not included: it
shares goal progress between party members and does not concern progression.

## Server progression interface

`IP_PROGRESS_V1` in the bridge's `HELLO` capabilities advertises three requests.
They concern the sending character only and carry no character name:

```text
GET~IP_STATE~token[~WATCH|~UNWATCH]
GET~IP_QUESTS~token~questId,questId,...
GET~IP_ACCESS~token
```

Replies are self-sender addon whispers on the `MBOT` prefix. Errors use the
bridge's `ERR~GET~<request>~token~reason` format.

### State

```text
IP_STATE~token~1~ip~strict~stored~effective~limit~era~next~nextMet~account~gm~maxLevel
```

| Field | Meaning |
| --- | --- |
| `ip` | `1` when Individual Progression is enabled; `0` on other realms, with the remaining progression fields at their defaults. |
| `strict` | `1` for the strict default milestone chain. |
| `stored` | Highest rewarded marker quest 66001–66018. |
| `effective` | `stored` clamped to the realm tier limit, as the module's own gates use it. |
| `limit` | `IndividualProgression.ProgressionLimit`; `0` means none. |
| `era` | `0` Vanilla, `1` TBC, `2` Wrath, `255` unavailable or custom chain. |
| `next` | The next strict milestone; tier 11 is skipped and `0` follows tier 18. |
| `nextMet` | `1` when the next milestone is a quest (tiers 4, 5 and 8) that is already rewarded. |
| `account` | `N` normal, `B` bot account, `X` excluded from Individual Progression. |
| `gm` | `1` while game master mode bypasses the module's gates. |
| `maxLevel` | The realm's `MaxPlayerLevel`. |

Boss credits saved for later milestones are not reported: their player setting
getter stores a missing entry, which a read-only request must not do.

`WATCH` subscribes the token for 180 seconds; the client renews it every 60
seconds. The server compares the watched state once per second and sends a new
`IP_STATE` with the watch token only when it changes. `UNWATCH` with the same
token ends the subscription; another token cannot.

### Quest availability

```text
IP_QUESTS_BEGIN~token~count
IP_QUESTS~token~entry,entry,...
IP_QUESTS_END~token~count
```

Each entry is `questId:status`. `R`, `I`, `C` and `F` are the character's
rewarded, incomplete, complete and failed quest status, `U` an unknown quest,
`A` an available quest, and `L<hex>` an unavailable quest with these reasons:

| Bit | Reason | Bit | Reason |
| --- | --- | --- | --- |
| `1` | Disabled quest | `800` | A previous chain quest is active |
| `2` | Class | `1000` | Breadcrumb whose target is taken |
| `4` | Race | `2000` | Active breadcrumb for this quest |
| `8` | Level too low | `4000` | Daily, weekly, monthly or seasonal reset |
| `10` | Level too high | `8000` | Quest conditions |
| `20` | Skill | `10000` | A progression marker condition |
| `40` | Reputation | `20000` | Every quest giver is hidden by progression |
| `80` | Previous quest | `40000` | Quest log full |
| `100` | Timed quest active | | |
| `200` | Exclusive alternative taken | | |
| `400` | A later chain quest is taken | | |

A marker condition adds `:+n` when the quest needs tier `n` or `:-n` when tier
`n` retired it. The checks are the core's `CanTakeQuest` checks and the
quest-available conditions, called without client messages, as
[quest diagnostics](quest-diagnostics.md) reads them. A giver counts as hidden
only when every spawn of every quest starter uses one of the module's tier
visibility scripts and that script hides it from this character. Unspawned,
area-phased and differently scripted givers count as visible. At most 32 quest
IDs fit one request.

### Instance access

`IP_ACCESS` uses the same framing. Each entry is `mapId:` followed by one code
per difficulty 0–3:

| Code | Meaning |
| --- | --- |
| `A` | The portal's checks accept the character. |
| `G` | Individual Progression's map gate refuses: a missing milestone or its key or attunement rule. |
| `R` | A native access requirement is missing: level, item, quest or achievement. |
| `D` | The map or difficulty is disabled. |
| `-` | The difficulty does not exist. |

Individual Progression's map gate runs without a session, so it sends no text
and moves no ship passenger. The native requirements run without reports. Raid
group membership, instance locks and the hourly instance limit are not part of
the answer. Native requirements marked for the group leader follow the current
leader, as the portal does.

### Limits

Each character may send 20 requests per two seconds; at most 512 characters are
tracked, and their state ends 180 seconds after the last request or when the
session closes. Packets stay within the 255-byte addon message budget; a reply
that cannot be framed is refused with `PACKET_TOO_LARGE` instead of truncated.
A realm without the module answers `ip=0`, every quest without progression
reasons and every map without the progression gate.

## Verification

`python3 cmake/tests/TestIpProgressBridge.py` compiles the actual endpoint, its
[progression unit](../patches/mod-multibot-bridge-progression-state.patch) and
Individual Progression's own progression functions against native-shaped
doubles. It compares every visibility rule with the module's scripts, checks
that the native checks it calls send no messages, and rejects 27 mutations of
its gates.

`python3 cmake/tests/TestZygorProgression.py` loads the
[patched addon files](../patches/zygor-individual-progression.patch) with Lua
5.1 and the bridge's wire format: discovery, state validation, quest batching,
step and goal gating, guide chains, the milestone guide, quest automation, the
Gear Finder, best-in-slot lists and the Talent Advisor. It ties the zone,
experience, instance, difficulty, milestone and reason tables to Individual
Progression's, the bridge's and the core's sources, rejects every mutation of
these gates and runs the upstream Zygor regression suite on the patched addon.

`TestZygorInstallerPackaging.py` and `TestZygorInstaller.py` check the release
ZIP and the PowerShell installer: file-by-file verification, rejected
archives, patch and TOC checks, backup, rollback and preserved SavedVariables.
The release build downloads the pinned upstream archive, installs it with the
packaged installer and compares the result with the tested prepared addon.
None of these tests starts a realm or a WoW client.
