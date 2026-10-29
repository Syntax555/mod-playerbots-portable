# Client addons

Use **WoW 3.3.5a, build 12340** (Interface `30300`). Retail and current Classic
addons target different APIs, even for the same content era. Close WoW
completely before replacing files: `/reload` does not discover new addon
folders or refresh TOC metadata.

## Matching client packages

The server's [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
provides the required EraTalents client pack. Optional addons come from their
own [forks](#addon-forks).

| Package | Installation and controls |
| --- | --- |
| [EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip) | Required: copy both `Interface/AddOns/EraTalents/` and `Data/patch-V.mpq`; see [matching client files](era-talents.md#install-the-matching-client-files). |
| [MultiBot Chatless](https://github.com/Syntax555/MultiBot-Chatless/releases/latest/download/MultiBot-Chatless-latest.zip) | Install its `MultiBot/` folder in `Interface/AddOns/`. Open controls with `/mb`, settings with `/mbopt`. |
| [DragonUI](https://github.com/Syntax555/DragonUI/releases/latest/download/DragonUI-latest.zip) | Install both `DragonUI/` and `DragonUI_Options/` in `Interface/AddOns/`. Open settings with `/dui`. |
| [Questie-335 installer](https://github.com/Syntax555/Questie/releases/latest/download/Questie-335-latest.zip) | Extract outside WoW, close WoW, run `Install-Questie.cmd`; see [installation](questie-playerbots.md#installation). |
| [Zygor IP installer](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest/download/Zygor-IP-latest.zip) | Extract outside WoW, close WoW, run `Install-Zygor.cmd`; see [installation](zygor-progression.md#installation). |

Each addon folder must directly contain its matching `.toc` file. Back up
existing folders outside `Interface/AddOns/` before replacement; preserve
account and character SavedVariables in `WTF/`. Avoid nested archive folders
and mixed versions. The Questie and Zygor ZIPs contain installers, not addon
files: they need Internet access and Windows PowerShell 5.1 or later, verify
their exact source commit, and back up existing addon folders automatically.

## Bot controls and historical UI

With matching EraTalents and MultiBot versions, a selected bot's talent button
opens its historical Vanilla/TBC tree in DragonUI's talent window, or the
Blizzard inspect window with EraTalents otherwise. Wrath uses native inspect.
For a controlled altbot in your group, clicks spend that bot's earned points;
other characters remain read-only. Server prerequisites, ordinary inspect
access and range apply. This route does not open MultiBot's separate
Custom/Glyph tabs. With `EraTalents.Enable = 0`, the server sends no historical
data and MultiBot keeps its own talent window. See
[historical talents](era-talents.md#dragonui).

The **Select combat profile** button offers automatic talent detection and
manual class profiles. Carried equipment is checked against the selected
profile; see [combat profiles and equipment](combat-profiles.md). No profile
creates gear. In an altbot's MultiBot inventory, **Buy** routes merchant clicks
to that bot while the inventory remains in Buy mode. The bot needs vendor
access, its own gold and space. Leaving Buy mode, switching bots or closing
the inventory cancels pending purchases. Inventory, outfit and trainer requests
require the bot and player to be in the same map instance.

Under natural progression, personal-bank commands require a banker within the
bot's interaction range. Native bank handling checks space and item eligibility;
the reply reports the quantity actually moved. Quest-item counters follow the
transferred quantity, including when stacks merge.

DragonUI's talent controls, spellbook and level-up notice follow the player's
own earned era and trainer spells with the matching EraTalents package. Its
spellbook supports Clique bindings for learned player spells when Clique is
installed.

Questie shows group bots' quest counters automatically. Its native upstream
integration supplies progress, roster refresh, identity checks and bindings.
Use the matching bridge for the tested server integration. Database
markers can differ from Individual Progression's quest versions. See
[Questie bot progress](questie-playerbots.md).

Zygor guides, Gear Finder and Talent Advisor follow each character's tier. Its
inspect Gear Finder uses a controlled altbot's own equipment, combat profile
and progression from the equipment tab. It recommends earned sources without
granting items. The bundled Talent Advisor stays inactive for EraTalents
characters; disable the whole `ZygorGuidesViewerRM` addon and reload when
isolating talent or protected-action conflicts. See
[Zygor Individual Progression](zygor-progression.md).

## Addon forks

Each fork publishes a rolling Latest asset after its checks pass. The server's
[manifest](../versions.lock.json) pins the tested commit; Latest may be newer.
Installed addons record their commit in `SOURCE_REVISION.txt`. Their READMEs
cover installation, supported behavior, updates, provenance and licenses.

| Addon | Fork and branch | Latest asset |
| --- | --- | --- |
| MultiBot Chatless | [Syntax555/MultiBot-Chatless](https://github.com/Syntax555/MultiBot-Chatless), `main` | `MultiBot-Chatless-latest.zip` |
| DragonUI | [Syntax555/DragonUI](https://github.com/Syntax555/DragonUI), `main` | `DragonUI-latest.zip` |
| Questie-335 | [Syntax555/Questie](https://github.com/Syntax555/Questie), `335` | `Questie-335-latest.zip` (installer) |
| Zygor Guides Viewer Remaster | [Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK), `main` | `Zygor-IP-latest.zip` (installer) |
| EraTalents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents), `main` | `EraTalents-addon-latest.zip` (addon only) |

The EraTalents addon-only ZIP is for trying addon changes. Players need the
server's client pack because `Data/patch-V.mpq` must match its data generation.
Addon updates alone do not require a server build. Full UI and addon-combination
coverage is not established by source checks; see
[open validation](todo.md#gameplay-validation).

## Optional upstream addons

Install these separately. Compatibility with every HD client and addon
combination requires in-game testing; server progression remains authoritative.

| Addon | Installation and limits |
| --- | --- |
| [GearScore2](https://github.com/cozawariat/gearscore2) | Install as `Interface/AddOns/GearScore2/GearScore2.toc`; settings: `/gs2`. Use one GearScore-family addon at a time. Wrath scoring does not establish historical Vanilla/TBC recommendations. |
| [DungeonClear](https://github.com/jrad7/mod-dungeon-clear-addon) | Install as `Interface/AddOns/DungeonClear/DungeonClear.toc`; open with `/dc`. It controls server runs; formation, travel and earned access remain server rules. Spectate is disabled by default; `.dc on` can show refusals omitted by the UI. |

Dependencies retain their own terms; a viewer license does not automatically
license every bundled guide, image or library. See
[third-party notices](../THIRD_PARTY_NOTICES.md).

## Blocked interactions and Lua errors

A blocked-action message concerns protected client UI functions. Capture the
failure before changing server settings:

1. Run `/console scriptErrors 1` and `/console taintLog 2`, then `/reload`.
2. Reproduce once and record the action and complete first Lua error. Close
   WoW and keep `Logs/taint.log` and `Logs/FrameXML.log` if present.
3. Compare with only the matching EraTalents addon enabled, then add MultiBot
   and other addons one at a time, reloading after each change. Keep the
   matching MPQ and preserve SavedVariables.
4. Turn detailed logging off with `/console taintLog 0` and, if desired,
   `/console scriptErrors 0`.

Taint can spread between addons and Blizzard frames. The final named addon is
a clue; earlier log entries and a reproducible comparison establish the cause.
Missing Blizzard `Interface/FrameXML/` files also warrant checking client UI
patches.
