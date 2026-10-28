# Zygor Individual Progression

The [Zygor fork](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK)
adapts guides, Gear Finder and Talent Advisor to each character's own earned
Individual Progression tier. It reads progression, quest availability and
instance access through the server's MultiBot Bridge. It grants no gear or
progression and changes no server access rules.

## Installation

Use **WoW 3.3.5a, build 12340** and the matching
[server Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
The prebuilt server includes bridge support; no new server setting is needed.

1. Download [Zygor-IP-latest.zip](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest/download/Zygor-IP-latest.zip)
   and extract it to a writable folder outside WoW.
2. Close WoW completely. Run `Install-Zygor.cmd` and select the client's
   `Interface/AddOns/` folder. Internet access and Windows PowerShell 5.1 or
   later are required; no administrator rights are needed.
3. Start WoW and enable Zygor Guides Viewer. Disable separate
   `ZygorGuidesViewer` or `ZygorTalentAdvisor` addons; `ZygorGuidesViewerRM`
   includes the advisor, and the installer warns about duplicates.

The ZIP contains an **installer, not the addon**. It downloads the exact fork
commit it was built from, verifies every addon file against SHA-256 hashes and
checks the TOC. The installed path is
`Interface/AddOns/ZygorGuidesViewerRM/ZygorGuidesViewerRM.toc`. Existing addon
files are backed up, and account and character SavedVariables in `WTF/` are
preserved. Use the same steps for updates. `SOURCE_REVISION.txt` and
`SOURCE_MANIFEST.json` identify the installed source.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Zygor.ps1 -AddOnsPath 'C:\Games\WoW\Interface\AddOns'
```

The installer retains the addon's notices. Its MIT license covers tooling only;
the viewer's unspecified-version `GPL` metadata does not license every guide,
image or library. See [third-party notices](../THIRD_PARTY_NOTICES.md).

## Guide behavior

Open **Progress** with `/zgprogress` or inspect state with `/zygorip`.
`/zygorip refresh` requests new server data. The panel shows the saved and
usable tiers, realm ceiling, experience cap and next default-chain milestone.
Integration text is available in English and German.

| Mode | Behavior |
| --- | --- |
| Automatic (default) | Follow server progression; without bridge support or Individual Progression, use ordinary realm behavior. |
| On | Keep later content locked while no server answer is available. |
| Off | Disable the addon's progression filters; server rules still apply. |

Before the first answer, later content is unknown. Three unanswered probes,
about a minute, select the mode's behavior without bridge support. Normal
player views follow the server's account exclusions and GM bypass; the
inspected-bot view always follows that bot's personal progression.

- **Quest steps and goals:** hide only for lasting server refusals, such as a
  progression marker, hidden giver, class/race, disabled or outleveled quest,
  or an already taken alternative. Missing level, reputation, skill,
  prerequisites or reset keeps the step. Active and completed quests stay.
- **Guides and chains:** zone, experience-cap and instance checks filter
  suggestions and hold the next guide with a reason. Outland needs tier 8,
  Quel'Danas 12 and Northrend 13. TBC race starting zones open earlier for
  Draenei and Blood Elves; other races' account unlock is not visible to the
  addon, so it uses tier 8. Manual loading can still show a locked guide with
  its warning.
- **Milestones:** *Individual Progression\Milestone Chain* follows the default
  chain and the realm ceiling. While progression filters apply, decisions
  including *Bang a Gong!*,
  *Chaos and Destruction* and *Into the Breach* are never accepted or turned in
  automatically.
- **Other guides:** reputation, profession, mount, pet, achievement, daily,
  event and Gold Guide routes use the same quest, zone and instance checks.
  Their own requirements remain guide steps; navigation is unchanged.
- **Talent Advisor:** its builds cover native Wrath trees only. It stays
  inactive for EraTalents characters and, while progression filters apply,
  before Wrath or while the era is unknown. It leaves the native `LearnTalent`
  function and learn button
  in place in those cases.

## Gear Finder

Dungeon and raid sources count as current only when the earned era and Wrath
phase allow them and the server reports the instance difficulty accessible.
Later tiers are labeled *next tier* or *later tier*. Disabled, unmapped or
unverified sources, including outdoor world bosses, are unavailable.
Currency vendors follow their era. Crafted sources require the earned era and
a known or trainer recipe; other recipe sources are unverified. Wrath
best-in-slot annotations start at tier 13 and advance with tiers 14–17.

For players with EraTalents, weights use the most-spent historical talent tab.
Before Wrath without historical data, the class's leveling profile applies.
Druid Restoration uses healing weights; Feral uses Thick Hide ranks as a
bear/cat heuristic. `/zygortank`, `/zygordps` and `/zygorheal` select a role;
`/zygorrole auto` restores automatic selection. These remain the viewer's Wrath
stat priorities, with no claim of optimized Vanilla/TBC simulation. Scans run
in short slices while the window is open; progression changes invalidate
stale results.

### Inspected altbots

Open a controlled altbot's Blizzard or DragonUI inspect window. On the
**equipment tab**, click its Zygor button to open that bot's Gear Finder. The
bot must be online, in your group and within normal inspect range. Matching
server support is required; otherwise the button reports it unavailable.
Changing inspect tabs, closing the window or selecting another character
closes the view and cancels pending results.

Recommendations use that bot's class, level, equipment, effective combat
profile and personal progression, with server checks for its quests and
instances. Quest sources require a known giver spawn whose map and progression
visibility permit the bot's stage. Unknown, differently phased or unverified
sources stay unavailable; other scripted NPC visibility is not evaluated.
Crafting and profession-dependent recommendations are excluded because the
bot's learned recipes are not reported.

This view leaves the player's profile, talent advice and settings personal.
It recommends sources without granting items or buying them. Actual bot loot
rolls and equipping use Playerbots' native evaluation, which can differ from
Zygor's displayed scores.

## Server interface and limits

The bridge's `IP_PROGRESS_V1` capability provides `IP_STATE`, `IP_QUESTS` and
`IP_ACCESS` on `MBOT`. They read the sending character's state; WATCH renews
state subscriptions every 60 seconds for a 180-second lease. Quest requests
are batched to at most 32 IDs. Messages fit the 255-byte addon budget, and
oversized replies are refused as a whole.

`IP_TARGET_V1` accepts the same read-only requests for a controlled altbot.
The requester must be its current master, share its group and be within native
inspect distance. Random bots, SelfBots and other players are not valid
targets. Target requests do not support WATCH and share the requester's budget
of 20 requests per two seconds. At most 512 requester states are retained;
idle state expires after 180 seconds or logout.

Instance answers include progression gates and native level, key, quest and
achievement requirements. They omit raid-group membership, instance locks and
the hourly instance limit. Native group-leader requirements follow the current
leader. Player quest-source checks cannot fully evaluate unspawned, area-phased
or differently scripted givers. Unknown state does not prove availability, and
imported guides can still differ from server data. A custom progression chain
does not acquire an invented default milestone or era mapping.

## Source and verification

The [manifest](../versions.lock.json) records the fork and imported upstream
revisions and retained adaptations. The [fork README](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK)
links viewer documentation, licensing, installer tooling and contribution
instructions. See the [contributing guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md)
for source updates. After preparing pinned sources, the affected checks are:

```bash
python3 cmake/tests/TestIpProgressBridge.py
python3 cmake/tests/TestZygorProgression.py
```

These exercise production bridge and addon logic with doubles, compare gates
to the pinned server sources and reject mutations of the checks. The fork's
Latest workflow checks Lua and the installer, including file verification,
backup, rollback and preserved SavedVariables. These checks do not start a
realm or client. Guide routes, inspect interaction, UI responsiveness and
other addon combinations still need live validation; see
[open validation](todo.md#gameplay-validation).
