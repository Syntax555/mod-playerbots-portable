# Client addons

Use a WoW **3.3.5a client, build 12340**. Addons for Retail or the current
Classic clients use different APIs, even when their content covers the same era.
The 3.3.5a addon interface version is `30300`.

## Matching client packages

Close WoW completely before installing or replacing client files. The
server's [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
contains the EraTalents client pack; each optional addon comes from the Latest
release of its [fork](#addon-forks).

| Package | Installation |
| --- | --- |
| [EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip) | Required for every player: historical talents, spell data and German text. Install both `Interface/AddOns/EraTalents/` and `Data/patch-V.mpq`. |
| [MultiBot Chatless](https://github.com/Syntax555/MultiBot-Chatless/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional bot controls. Install `Interface/AddOns/MultiBot/`; open with `/mb`, and settings with `/mbopt`. |
| [DragonUI](https://github.com/Syntax555/DragonUI/releases/latest/download/DragonUI-latest.zip) | Optional interface. Install both `DragonUI/` and `DragonUI_Options/` in `Interface/AddOns/`; open settings with `/dui`. With the current EraTalents package, Vanilla/TBC characters open their historical tree from DragonUI's talent key, micro-button and `/talents`, and the spellbook lists the character's own trainer spells; see [Era Talents](era-talents.md#dragonui). |
| [Questie-335 installer](https://github.com/Syntax555/Questie/releases/latest/download/Questie-335-latest.zip) | Optional quest addon with bot progress integration. Extract and run `Install-Questie.cmd`; Internet access is required. Choose the client's `Interface/AddOns/` folder; see [installation](questie-playerbots.md#installation). |
| [Zygor IP installer](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest/download/Zygor-IP-latest.zip) | Optional guide viewer that follows each character's Individual Progression tier. Extract and run `Install-Zygor.cmd`; Internet access is required. Choose the client's `Interface/AddOns/` folder; see [installation](zygor-progression.md#installation). |

Each addon folder must directly contain its matching `.toc` file. Avoid nested
archive folders and mixed files from different versions. Back up existing addon
folders before replacement; keep account and character `SavedVariables`.
See [EraTalents installation](era-talents.md#install-the-matching-client-files)
for the matching addon/MPQ generation and locale checks.

With both matching addons loaded, MultiBot's talent button opens the selected
bot in the Blizzard inspect window. EraTalents displays its own Vanilla or TBC
tree and allocated ranks there; Wrath uses the native inspect view. For an altbot
you control in your group, click historical talents to spend its earned points.
The server validates each purchase against that bot's own era and prerequisites.
Other characters remain read-only; normal inspect access and range still apply.
The separate MultiBot talent window and its Custom/Glyph tabs are not opened
through this route. On a realm with native trees (`EraTalents.Enable = 0`), the
server sends no EraTalents data and the button keeps MultiBot's talent window.
Install both updated addons together; mixed addon or MPQ generations cannot
supply a reliable historical view.

For vendor purchases, open the altbot's MultiBot inventory, select **Buy** and
click an item in the merchant window. While that inventory is visible in Buy
mode, purchases use the selected bot's own gold and inventory. The bot must be
able to interact with the vendor. Leaving Buy mode, changing bots or closing
the inventory cancels pending purchase confirmations and quantity selection.

Use the matching Questie-335 installer for the complete bot quest integration;
the ordinary upstream download does not include all local adaptations. The
installer downloads its commit of the Questie fork from GitHub and checks every
file before installing it. Its server support is included in the prebuilt
server, so no source build is needed.
Static quest locations and availability can differ under Individual Progression
or custom quest rules. See [Questie bot progress](questie-playerbots.md) for
supported behavior and remaining live validation.

## Addon forks

The adapted addons live in forks of their original projects. Every push to a
fork's branch checks the addon and replaces its asset in that fork's Latest
release, so addon changes reach players without a server build:

| Addon | Fork and branch | Latest asset |
| --- | --- | --- |
| MultiBot Chatless | [Syntax555/MultiBot-Chatless](https://github.com/Syntax555/MultiBot-Chatless), `main` | [MultiBot-Chatless-latest.zip](https://github.com/Syntax555/MultiBot-Chatless/releases/latest) |
| DragonUI | [Syntax555/DragonUI](https://github.com/Syntax555/DragonUI), `main` | [DragonUI-latest.zip](https://github.com/Syntax555/DragonUI/releases/latest) |
| Questie-335 | [Syntax555/Questie](https://github.com/Syntax555/Questie), `335` | [Questie-335-latest.zip](https://github.com/Syntax555/Questie/releases/latest), an installer |
| Zygor Guides Viewer Remaster | [Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK), `main` | [Zygor-IP-latest.zip](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest), an installer |
| EraTalents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents), `main` | [EraTalents-addon-latest.zip](https://github.com/Syntax555/azerothcore-mod-era-talents/releases/latest), the addon without the MPQ |

Each fork's README lists its changes compared to the original project. The
server pins a tested commit of each fork; a fork's Latest can be newer than the
server's pin. The EraTalents addon ZIP is meant for trying addon changes: the
merged `Data/patch-V.mpq` must match the server's data generation, so players
install the server's EraTalents client pack. Installed addons record their
commit in `SOURCE_REVISION.txt`.

## Optional upstream addons

These links identify suitable client projects and their limits. They are
installed separately; compatibility with every HD client or addon combination
requires in-game testing.

| Addon | Source and installation | Progression limits |
| --- | --- | --- |
| GearScore2 | [cozawariat/gearscore2](https://github.com/cozawariat/gearscore2), the 3.3.5a project with interface `30300`. Install as `Interface/AddOns/GearScore2/GearScore2.toc`; open settings with `/gs2`. | Treat gear scores as estimates. Wrath scoring and talent assumptions do not establish accurate Vanilla/TBC historical recommendations. Use one GearScore-family addon at a time. |
| DungeonClear | [jrad7/mod-dungeon-clear-addon](https://github.com/jrad7/mod-dungeon-clear-addon), the 3.3.5a companion interface. Install as `Interface/AddOns/DungeonClear/DungeonClear.toc`; open with `/dc`. | Controls and displays server-side runs. Party formation, travel and earned access remain server rules. Spectate is disabled in the default profile; `.dc on` in chat can expose refusal messages omitted by the UI. |

Quest addons use their own databases. Server rules and each character's
progression determine quest availability; map markers can differ when addon
data does not match. See [server adaptations](adaptations.md) for the
distribution's gameplay changes.

Install Zygor Guides Viewer Remaster with the matching Zygor IP installer; the
ordinary upstream download does not follow Individual Progression. Its guides,
Gear Finder and Talent Advisor then use each character's own tier; see
[Zygor Individual Progression](zygor-progression.md). The bundled Talent
Advisor wraps the global `LearnTalent` function and the Blizzard learn button
only while it may advise the character, which excludes EraTalents characters.
Disable the whole `ZygorGuidesViewerRM` addon and reload when isolating talent
or protected-action conflicts.

The addons in the upstream table are separate downloads. Their code, guides, images and
libraries have separate licensing terms; a public repository or viewer license
does not automatically authorize repackaging every included file. Addon-only
updates do not require compiling server modules.

## Blocked interactions and Lua errors

A client message that an addon blocked an action concerns the client's UI and
protected functions. It does not by itself identify a server configuration bug.
Capture the action and error before changing server rules:

1. Run `/console scriptErrors 1` and `/console taintLog 2`, then `/reload`.
2. Reproduce the failure once. Record the exact action and complete first Lua
   error, then close WoW and retain `Logs/taint.log` and `Logs/FrameXML.log`.
3. Compare with only the matching EraTalents addon enabled. Add MultiBot, then
   each optional addon individually, reloading after each change. Keep the
   matching EraTalents MPQ installed and preserve `SavedVariables`.
4. Turn detailed logging off with `/console taintLog 0` and, if desired,
   `/console scriptErrors 0`.

Taint can spread between addons and Blizzard frames. An addon name in the final
blocked-action message is a clue; the earlier log entries and a reproducible
addon comparison are needed to establish the cause. Missing Blizzard
`Interface/FrameXML/` files also warrant checking the HD client's UI patches.
