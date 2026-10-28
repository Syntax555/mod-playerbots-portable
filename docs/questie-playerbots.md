# Questie Playerbots progress

Questie-335 displays authorized group bots' own quest counters without a WoW
client for each bot. The server's MultiBot Bridge reads their active quest logs;
Questie renders the results through its normal communication, tooltips and
party objectives. The tracker remains the local player's tracker.

## Installation

Use **WoW 3.3.5a, build 12340** and the matching
[server Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
The prebuilt server includes the bridge; no additional module, compiler or new
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

MultiBot is optional for controls. The separate upstream `mod-questie-bridge`
provides other server information and is not required for bot quest progress.
The installer retains the addon's existing notices; its MIT license applies
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

## Access and compatibility

The bridge accepts only visible, authorized, server-controlled bots in the
requester's group. Real players and SelfBots are excluded. This interface reads
quest state and runs no bot commands.

The native upstream integration includes snapshots, lease renewal, special
objectives, cleanup and Questie's binding header. This fork additionally reuses
the connected roster for discovery and cleanup, excludes the local player from
requests, and **requires each snapshot's GUID to match the watched group
member**. Use the matching MultiBot Bridge: its BEGIN message carries the
core's `ObjectGuid::ToString()` form (`GUID Full: 0x… Type: Player Low: …`),
which the client normalizes and compares with `UnitGUID`. Missing, malformed or
mismatched identity is rejected; compatibility with bridges that omit GUIDs is
not provided by this fork.

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

The [manifest](../versions.lock.json) pins the Questie and MultiBot Bridge
forks. The [merged upstream integration](https://github.com/Aldori15/Questie/commit/30222ccb0821e6d8cdd8fe8d24334b5f9846bca7)
provides the native progress and binding behavior; `forkChanges` identifies the
retained roster and GUID checks. Fork source, installation tooling and update
instructions are linked in the [Questie README](https://github.com/Syntax555/Questie/tree/335).
Follow the [contributing guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md)
for fork changes. To prepare the pinned sources, run
`cmake -P cmake/PrepareModules.cmake`; a local addon export is available in
`.module-cache/prepared-source-addons/Questie-335/`.

For a behavior change, run the affected checks after source preparation:

```bash
python3 cmake/tests/TestQuestProgressBridge.py
python3 cmake/tests/TestQuestiePlayerbots.py
```

These exercise production C++ and Lua logic with native-shaped doubles and
mutation checks. The fork also checks the installer, backup, rollback and
preserved client files before publishing. They do not start a realm or client.
Live objective pins and tooltips, turn-in and abandonment, reconnects,
disconnect/group-departure cleanup and sustained load still need validation
with the matching server and addon; see [open validation](todo.md#gameplay-validation).
