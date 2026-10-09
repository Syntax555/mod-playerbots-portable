# Client addons

Use a WoW **3.3.5a client, build 12340**. Addons for Retail or the current
Classic clients use different APIs, even when their content covers the same era.
The 3.3.5a addon interface version is `30300`.

## Matching client packages

Close WoW completely before installing or replacing client files. Download the
packages from the server's [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).

| Package | Installation |
| --- | --- |
| [EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip) | Required for the default historical talents. Install both `Interface/AddOns/EraTalents/` and `Data/patch-V.mpq`. |
| [MultiBot Chatless](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional bot controls. Install `Interface/AddOns/MultiBot/`; open with `/mb`, and settings with `/mbopt`. |

Each addon folder must directly contain its matching `.toc` file. Avoid nested
archive folders and mixed files from different versions. Back up existing addon
folders before replacement; keep account and character `SavedVariables`.
See [EraTalents installation](era-talents.md#install-the-matching-client-files)
for the matching addon/MPQ generation and locale checks.

## Optional upstream addons

These links identify suitable client projects and their limits. They are
installed separately; compatibility with every HD client or addon combination
requires in-game testing.

| Addon | Source and installation | Progression limits |
| --- | --- | --- |
| Questie-335 | [Aldori15/Questie, branch `335`](https://github.com/Aldori15/Questie/tree/335). Install as `Interface/AddOns/Questie-335/Questie-335.toc`; do not rename the TOC. Bundled libraries and German localization are included. | Its quest data follows standard AzerothCore. Individual Progression and custom quest rules can change availability beyond its static database. |
| GearScore2 | [Upstream download page](https://www.curseforge.com/wow/addons/gearscore2). Choose a **3.3.5a** file and check its `.toc` for `30300`. | Treat gear scores as estimates. Wrath scoring and talent assumptions do not establish accurate Vanilla/TBC historical recommendations. Use one GearScore-family addon at a time. |
| Zygor Guides Viewer Remaster | [ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK). Install only its `ZygorGuidesViewerRM/` addon folder. | Guide routes and the bundled Wrath Talent Advisor do not follow each character's EraTalents trees or content gates. Prefer Questie for quest information during historical progression unless the guide's talent compatibility has been verified. |

The server offers **Frostmane Hold** (quest 287) without quest 420. Questie-335's
standard AzerothCore database still assumes quest 420 and may hide the available
quest; check the NPC directly.

Zygor's bundled Talent Advisor replaces the global `LearnTalent` function and
the Blizzard talent learn-button handler. Its **Enable Talent Advisor** checkbox
hides advisor features but does not remove all these hooks. Disable the whole
`ZygorGuidesViewerRM` addon and reload when isolating talent or protected-action
conflicts; the checkbox alone does not provide a clean comparison.

Optional addons remain upstream downloads. Their code, guides, images and
libraries have separate licensing terms; a public repository or viewer license
does not automatically authorize repackaging every included file. Addon-only
updates do not require compiling server modules. The server updater does not
install or update a player's client addons.

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
