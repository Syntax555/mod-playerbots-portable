# Zygor Individual Progression

The server reports each character's own Individual Progression state to its
client through the MultiBot Bridge. Client addons read it to follow the
character's earned tier instead of its level. The interface only reads state;
it cannot award, change or bypass progression.

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
its gates. It does not start a realm or a WoW client.
