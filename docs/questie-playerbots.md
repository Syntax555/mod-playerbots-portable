# Questie Playerbots progress

Questie-335 displays authorized group bots' own quest counters without a WoW
client for each bot. The server's MultiBot Bridge reads their active quest logs;
Questie renders the results through its normal communication, tooltips and
party objectives. The tracker remains the local player's tracker. The server's
Questie Bridge also shows each character only the quests of its own
[era](#quests-of-the-characters-era).

## Installation

Use **WoW 3.3.5a, build 12340** and the matching
[server Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
The prebuilt server includes both bridges; no additional module, compiler or new
server setting is required.

1. Update and restart the server using the [update guide](updating.md).
2. Download [Questie-335-latest.zip](https://github.com/Syntax555/Questie/releases/latest/download/Questie-335-latest.zip)
   and extract it to a writable folder outside WoW.
3. Close WoW completely. Run `Install-Questie.cmd` and select the client's
   `Interface/AddOns/` folder. Internet access and Windows PowerShell 5.1 or
   later are required; no administrator rights are needed.
4. Start WoW, enable Questie-335, and invite bots normally. In `/questie`, enable
   **Show party quest objectives** for markers from quests you do not share.

The ZIP contains an **installer, not the addon**. It downloads the exact fork
commit it was built from, verifies every file against SHA-256 hashes and
installs `Interface/AddOns/Questie-335/Questie-335.toc`. Existing addon files are
backed up; account and character SavedVariables in `WTF/` are preserved. Use
the same steps for updates. The installed `SOURCE_REVISION.txt` and
`SOURCE_MANIFEST.json` identify the source.

For a noninteractive installation from the extracted folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Questie.ps1 -AddOnsPath 'C:\Games\WoW\Interface\AddOns'
```

MultiBot is optional for controls. The installer retains the addon's existing notices; its MIT license applies
only to the installation tooling. See [third-party notices](../THIRD_PARTY_NOTICES.md).

## Supported behavior

Discovery, complete quest snapshots and WATCH subscriptions start
automatically after login, `/reload` and group changes. The server checks
watched bots once per second and sends a new snapshot only when state changes.
Quest acceptance, objective progress, completion, failure, turn-in and
abandonment update the bot's remote active log. Ordinary player clients keep
their independent QuestieComms data.

NPC, item, gameobject and map-icon tooltips show individual group counts.
Party-only objective markers support groups of at most five; shared quests use
Questie's normal map icons and group tooltips. Rehover an open tooltip if its
contents have not redrawn.

Questie maps server target IDs, credit aliases and counters to its database
objectives. Where custom quest versions leave an equal number of unmatched
objectives of one type, they are paired in order. Shared quests can use the
local quest log's objective text. Questie's database can still differ from
Individual Progression: missing locations cannot be invented, and ID-less
money, event and player-kill goals do not create entity tooltip lookups. Quests
without objectives retain active-log membership but have no separate status
display. The server's quest status remains authoritative.

## Quests of the character's era

Questie's database lists the quests of every patch up to 3.3.5. The server
[gates later content](changing-expansions.md#world-content-by-era-and-patch)
per character, and the included Questie Bridge reports that state to Questie:

- Quests whose availability conditions the character fails, such as a later
  era's or patch's quests, or Vanilla versions that Individual Progression
  retires at a later tier, are hidden from the map and quest lists like quests
  the server disables. Quest
  details label them *Disabled by server*. A quest already in the quest log
  stays tracked.
- Questgivers that are hidden from the character, by the era's visibility
  conditions or by Individual Progression's scripts, no longer show quest
  markers in its current zone once they are within viewing distance. Restrictions from the server's questgiver
  templates also apply on continent and world maps.
- Both follow a new tier within a few seconds; no `/reload` is needed.

Each character gets its own snapshot, so characters of different tiers on one
account or realm see different quests. The bridge reads the server's live
checks, so Questie matches what the character can accept.

`/qserver quest <quest ID>` shows whether the server reports a quest as
disabled for the character, and `/qserver giver <NPC ID>` shows template
restrictions and observed spawns that offer it nothing. In
`configs/modules/QuestieBridge.conf`,
`QuestieBridge.QuestConditions = 0` turns the quest reports off and
`QuestieBridge.Questgivers = 0` the negative questgiver observations.
`QuestieBridge.QuestgiverTemplates = 0` disables global template restrictions.

Questie's database still supplies locations, prerequisites and rewards: quest
XP follows its normal rate reports, not era XP changes, and quests it does not
know cannot appear. Quests Individual Progression restores, such as Vanilla's
battleground turn-ins, keep only the game's own quest markers. Server template
restrictions apply on zone, continent and world maps. Loaded questgivers in the
current zone can override those restrictions only while present at the client's
viewing distance and passing its visibility checks. Hidden era questgivers within
that distance remain negative observations. At most 64 observations fit in one snapshot; incomplete
observations or template catalogs are withheld. Trainer and vendor markers are
unaffected. If the closed quests would not fit into one snapshot, none are sent
and Questie shows its usual quests.
An unavailable giver does not hide a daily or weekly quest offered by another
valid starter.

Questie Bridge and Questie use matching protocol 21 builds. A version mismatch
restores Questie's static behavior; `/qserver` reports the expected version.

## Access and compatibility

The bridge accepts only visible, authorized, server-controlled bots in the
requester's group. Real players and SelfBots are excluded. This interface reads
quest state and runs no bot commands.

The native upstream integration includes snapshots, lease renewal, special
objectives, connected-roster discovery, cleanup and Questie's binding header.
It excludes the local player from requests. The matching MultiBot Bridge's
BEGIN message carries the core's `ObjectGuid::ToString()` form
(`GUID Full: 0x… Type: Player Low: …`), which the client normalizes and compares
with `UnitGUID`. Malformed or mismatched supplied identities are rejected.
Legacy bridges may omit the optional GUID; current-roster, sender and token
checks still apply.

The client also rejects stale tokens, malformed or incomplete snapshots and
unexpected senders. Group departure, logout or lost access clears prior bot
data while preserving data later supplied by an ordinary Questie client.
Partial replies expire and retry. An unanswered bridge probe has three retries
30 seconds apart; after those fail, another group change is needed to probe
again. Normal Questie features remain usable without bridge support.

WATCH leases last 180 seconds and renew every 60 seconds. The server permits
40 watched bots per requester and 512 requester states, with 80 requests per
two seconds and one snapshot request per bot per second. Messages respect the
255-byte addon wire budget; an oversized snapshot is refused as a whole.

## Source and verification

The [manifest](../versions.lock.json) pins the Questie, MultiBot Bridge and
Questie Bridge forks. The [upstream integration](https://github.com/Aldori15/Questie/commit/f1b5c606f582c7e588646fde8894919c68eedac5)
provides progress, roster refresh, identity checks and bindings without a
separate client implementation. Fork source, installation tooling and update
instructions are linked in the [Questie README](https://github.com/Syntax555/Questie/tree/335).
Follow the [contributing guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md)
for fork changes. To prepare the pinned sources, run
`cmake -P cmake/PrepareModules.cmake`; a local addon export is available in
`.module-cache/prepared-source-addons/Questie-335/`.

For a behavior change, run the affected checks after source preparation:

```bash
python3 cmake/tests/TestQuestProgressBridge.py
python3 cmake/tests/TestQuestiePlayerbots.py
python3 cmake/tests/TestQuestieEraQuests.py
```

These exercise production C++ and Lua logic with native-shaped doubles and
mutation checks. The shared installer tests check backup, rollback and
preserved client files, and the fork's Latest workflow installs and verifies
each packaged commit before publishing. They do not start a realm or client.
Live objective pins and tooltips, turn-in and abandonment, reconnects,
disconnect/group-departure cleanup and sustained load still need validation
with the matching server and addon; see [open validation](todo.md#gameplay-validation).
