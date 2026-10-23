# Questie Playerbots progress

Questie can display server-controlled group bots through its existing quest
communication, without a WoW client for each bot. The MultiBot Bridge supplies
the bots' real active quest logs. Questie uses `InsertQuestDataPacket`,
`remoteQuestLogs`, tooltip registration and `QuestiePartyObjectives` for both
bot and ordinary player data.

## Installation

Use WoW **3.3.5a, build 12340** and the matching server and Questie installer
from the [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
The prebuilt server includes the MultiBot Bridge integration. You need no
compiler, Git, Python, additional server module or new server setting.

1. Install or update the [server package](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/mod-playerbots-portable-latest.zip)
   using the normal [update guide](updating.md), then restart the server.
2. Download [Questie-335-latest.zip](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/Questie-335-latest.zip)
   from the same release and extract it to a folder outside your WoW installation.
3. Close WoW completely. Run `Install-Questie.cmd` and enter your client's
   `Interface/AddOns/` folder when prompted. Internet access is required; the
   installer uses Windows PowerShell and does not require administrator rights.
4. After installation succeeds, start WoW and enable Questie-335 in the addon list.

The installer downloads the pinned `335` addon directly from upstream, verifies
the archive and applies the matching integration locally. It backs up an existing
`Questie-335/` folder before replacement and preserves account and character
SavedVariables. The installed TOC must be
`Interface/AddOns/Questie-335/Questie-335.toc`; do not rename it or nest another
folder. The ordinary upstream download does not contain the complete adaptation.

To select the addon directory from a PowerShell prompt in the extracted folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Questie.ps1 -AddOnsPath 'C:\Games\WoW\Interface\AddOns'
```

The release ZIP contains the installer and integration metadata; upstream addon
files are downloaded separately and retain their existing terms and notices.

MultiBot Chatless may remain installed for bot controls. Its code and protocol
requests are unchanged. `mod-questie-bridge` provides separate optional server
information and is not required for bot quest progress.

Log in with Questie enabled and invite controlled altbots normally. Discovery,
initial snapshots and subscriptions happen automatically, including after
`/reload`. No chat command or quest-window interaction starts synchronization.

## Display and data flow

1. Questie probes `MBOT` with `HELLO~1` and reads the capability packets.
2. It requests every online group member by name. The bridge returns quest
   data only for visible, authorized, server-controlled bots in the same group.
   A real player remains on ordinary QuestieComms communication.
3. The bridge reads active quest slots, native `QuestStatusData` counters,
   template target IDs and required counts. Kill and spell-target credits use
   `CreatureOrGOCount`; delivery objectives use `ItemCount`. Exploration/event,
   player-kill, money and reputation objectives use their native state.
4. Questie maps IDs to its database objective indices, including kill-credit
   roots and alternative targets. Quest versions from Individual Progression
   can require other items or targets than Questie's database. When the
   database leaves as many objectives of a type as remain unmatched, they are
   paired in order and the bot reports Questie's objective, as a Questie
   client does, so its count appears on the same creatures as your own
   progress. When you have the same quest, group members' tooltip lines use
   your quest log's objective text, as map icon tooltips do; otherwise they
   use Questie's name. Complete snapshots replace only the bot's
   previously applied data; absent quests remove its old registrations.
5. The bridge checks watched bots once per second after the map-update barrier.
   It sends a new authoritative snapshot when state changes, including quest
   acceptance, progress, completion, failure, turn-in and abandonment.

NPC, item, gameobject and map-icon tooltips show group members' individual
counts. The native tracker remains the local player's tracker. Enable Questie's
**Show party quest objectives** option to draw objectives of other members'
quests that the local player does not have; the upstream feature is limited
to groups of at most five. Shared quests retain Questie's normal map icons and
group tooltip data. An open tooltip may need to be hovered again to redraw.

The server's objective order is not assumed to match Questie's corrected
database order. Unknown objectives retain their server counts safely, but
objectives missing from Questie's database cannot acquire invented map
locations. ID-less event, money and player-kill goals do not create entity
tooltip lookups. The server quest status remains authoritative.
Questie's native communication model attaches status to objectives; quests with
no objectives retain active-log membership but have no separate status display.

## MBOT protocol

Prefix: `MBOT`; separator: `~`; decimal integers; status: `I`, `C` or `F`.
The existing request uses a raw bot name and a validated request token:

```text
GET~QUEST_PROGRESS~Botname~token
GET~QUEST_PROGRESS~Botname~token~WATCH
GET~QUEST_PROGRESS~Botname~token~UNWATCH
```

`QUEST_PROGRESS_V1` advertises snapshots; `QUEST_PROGRESS_PUSH_V1` advertises
WATCH updates. Each complete response uses:

```text
QUEST_PROGRESS_BEGIN~encodedName~token~guid
QUEST_PROGRESS_QUEST~encodedName~token~questId~status
QUEST_PROGRESS_OBJECTIVE~encodedName~token~questId~type~index~id~current~required~finished
QUEST_PROGRESS_END~encodedName~token
```

Names in responses use the bridge's percent encoding. The GUID in BEGIN and
the explicit `finished` flag (`0` or `1`) are trailing extensions; the existing
Questie parser accepts the original fields. Types are `m` (creature or credit
target), `o` (gameobject), `i` (item), `e` (event), `p` (player kills), `g`
(money in copper) and `r` (reputation). Reputation values can be negative.
An unavailable target ID is `0`. Indices identify objectives inside a quest,
not Questie's database positions.

Responses go only to the requesting player's client as self-sender addon
whispers. Pushes reuse the WATCH token and the same complete-snapshot framing.
All packets are checked against the 255-byte wire budget, including `MBOT`
and its tab separator, before BEGIN is sent. An oversized snapshot is rejected
instead of being truncated. Errors use the existing
`ERR~GET~QUEST_PROGRESS~token~reason` format.

## Access, limits and lifecycle

The existing bridge visibility rules, same-group check and Playerbots security
check all apply. Real players and SelfBots are excluded from this endpoint.
The bridge reads state and executes no bot commands. Stored subscriptions use
GUIDs and retain no `Player*` pointers between updates.

Each requester can watch at most 40 bots; at most 512 requester states are
retained. Requests are limited to 80 per two seconds per requester and one
snapshot request per bot per second. WATCH leases last 180 seconds; the patched
addon renews them every 60 seconds. Unchanged polling sends no packets, and
multiple observers share the bot snapshot built during each poll.

Group departure, loss of bot access and logout invalidate subscriptions and
clear the bot's prior client data. The addon also rejects stale tokens,
non-group senders, malformed snapshots and incomplete frames. Partial replies
expire and requests retry. An unanswered bridge probe is retried three times
at 30-second intervals, and the addon probes again only when the group
changes; realms without the bridge therefore see no further addon traffic,
and Questie works as usual. Cleanup preserves tables subsequently
written by ordinary QuestieComms, including when a character gains a real
client. Older unpatched Questie can read ordinary snapshots, but needs the
supplied addon patch for lease renewal, robust cleanup and special objectives.

## Source builds

For development, [versions.lock.json](../versions.lock.json) pins the
AzerothCore/Playerbots and Questie sources. The integration patches are
[MultiBot Bridge](../patches/mod-multibot-bridge-quest-progress.patch) and
[Questie](../patches/questie-playerbots-progress.patch). From the source checkout:

```bash
cmake -P cmake/PrepareModules.cmake
```

The generated `.module-cache/prepared-core` contains the patched
`modules/mod-multibot-bridge`. Build and install the server using the normal
[build instructions](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md),
then restart it. Copying a C++ source file into an installed server does not
update its executable.

With WoW closed, back up the old addon folder outside `Interface/AddOns/` and
replace `Interface/AddOns/Questie-335/` with
`.module-cache/prepared-source-addons/Questie-335/`. Keep SavedVariables and the
`Questie-335.toc` filename. This prepared export is for local installation;
published installer ZIPs fetch their upstream files directly instead.

## Verification

The automated fixtures compile the actual bridge snapshot, serialization and
subscription code and exercise the actual Lua Questie integration. Their
mutation checks remove important gates to confirm the fixtures detect broken
behavior. Run after source preparation:

```bash
python3 cmake/tests/TestQuestProgressBridge.py
python3 cmake/tests/TestQuestiePlayerbots.py
python3 cmake/tests/TestClientAddonPatches.py
python3 cmake/tests/TestQuestieInstallerPackaging.py
python3 cmake/tests/TestQuestieInstaller.py
python3 cmake/tests/run_fixtures.py check
python3 cmake/tests/run_fixtures.py gameplay
```

The Lua fixture requires Lua 5.1, the C++ fixture requires a C++20 compiler,
and installation tests require PowerShell. CI also runs the installer with
Windows PowerShell 5.1.
Fixture coverage does not replace a live realm test. Check these cases with
the matching server and addon:

| Action | Expected result |
| --- | --- |
| Share a quest with a bot | Its own counts appear in group tooltips. |
| Kill a quest target with the bot | Counts update automatically, normally within about one second. |
| Use two bots with different counts | Both values remain assigned to their own names. |
| Complete or fail a quest | Updated status and objective counts reach Questie. |
| Turn in or abandon a quest | It disappears from that bot's active remote log. |
| Remove or log out a bot | Its registrations and WATCH are removed. |
| Add a real Questie player | Their normal QuestieComms data continues independently. |
| Use kill-credit, gameobject and ID-less event goals | Counts remain valid without Lua or server errors. |
| Reload, reconnect or log in again | Discovery and snapshots restart automatically. |
| Advance several bots simultaneously | All snapshots remain associated with the correct bot and token. |

Live UI behavior, Windows linking and sustained realm load require validation
on an installed server and client. No claim of a completed in-game run follows
from the standalone fixtures.

## Implementation files

| Files | Responsibility |
| --- | --- |
| `patches/mod-multibot-bridge-quest-progress.patch` | Updates upstream `src/MultiBotBridge.cpp`: native snapshots, MBOT capabilities, access checks and WATCH lifecycle. |
| `patches/questie-playerbots-progress.patch` | Updates `QuestiePlayerbots.lua`, `QuestieCommsData.lua` and `QuestiePartyObjectives.lua`: native comms ingestion, lifecycle, credit aliases and existing map rendering. |
| `versions.lock.json`, `scripts/patchwork.py`, `cmake/PrepareModules.cmake` | Pin Questie and reproducibly prepare the ordered server and source-only addon patches. |
| `cmake/PackageQuestieInstaller.py`, `client-addon/questie-installer/` | Package the installer and verified local changes; download the pinned upstream addon and install it with backup and rollback. |
| `cmake/tests/TestQuestieInstallerPackaging.py`, `cmake/tests/TestQuestieInstaller.py` | Verify package provenance, installation, integrity checks and preservation of existing client files. |
| `cmake/tests/TestQuestProgressBridge.py`, `cmake/tests/QuestProgressBridgeFixture.cpp` | Compile and exercise production server logic and mutation checks. |
| `cmake/tests/TestQuestiePlayerbots.py`, `cmake/tests/QuestiePlayerbotsFixture.lua` | Run production Questie comms and map logic under Lua 5.1 with client API doubles and mutation checks. |
| `cmake/tests/TestClientAddonPatches.py`, `cmake/tests/TestDocumentation.py` | Verify source-only preparation, package separation and pinned documentation. |
| `cmake/tests/run_fixtures.py`, `.github/workflows/checks.yml` | Run server and client regression fixtures in CI. |
| `README.md`, `docs/addons.md`, `docs/adaptations.md`, `docs/module-versions.md`, `docs/todo.md`, `docs/questie-playerbots.md` | Release installer, installation, behavior, protocol, source inventory and remaining live validation. |
