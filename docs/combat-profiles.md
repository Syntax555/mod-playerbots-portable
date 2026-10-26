# Combat profiles and equipment

MultiBot's **Select combat profile** button offers **Automatic** and the
specializations available for that bot's class. Install the matching MultiBot
addon and server. This menu changes combat behavior and equipment preferences;
it does not buy talents, switch dual-specialization slots or grant abilities.

In automatic mode, Playerbots reads the character's current talent distribution,
including its Vanilla or TBC EraTalents tree. A specialization change refreshes
the class strategies and role support outside combat. This includes tank or
damage assistance, positioning, healing, cleansing, blessings, totems and pets
where the existing class AI supports them. A manually selected profile remains
selected across relogs and AI resets. Select **Automatic** to follow talents
again. Selecting the current profile reapplies it and checks carried equipment.

The choice applies to controlled altbots and active SelfBots. It leaves their
talent points for their owner to spend. A manually chosen profile still needs
the character's normally learned abilities and appropriate equipment; selecting
a role does not supply them. Travel, loot, formation and instance strategies
are retained when the class profile changes.

Profiles reuse the available Playerbots class rotations. Its rogue AI uses the
same native assassination rotation for assassination and subtlety profiles.

## Equipment

The same profile drives Playerbots' specialization and role queries used by its
item scoring. After applying a profile outside combat, the bot checks equipment
already in its bags with the native equipment rules and stat weights. Protection
warriors and paladins prefer an owned, usable one-handed weapon and shield when
both are available. Weapons, armor restrictions, levels, skills and inventory
space still follow the core's normal checks.

The operation does not create items or gold, buy vendor equipment, learn weapon
skills or retrieve items from the bank. Ordinary automatic equipping of new loot
continues to follow the server's existing setting. The native stat weights are
an equipment heuristic, not a guarantee of the optimal raid loadout for every
encounter or talent combination.

## Random bots and historical talents

Random bots retain the configured PvE specialization mix and spend only their
earned, unspent talent points. Authored build orders cover all nine historical
classes in Vanilla and TBC, with separate feral cat and bear choices. The chosen
feral role remains stable when both builds include Thick Hide.

The TBC feral orders use a 0/44/17 PvE distribution, with different leveling
priorities for cat and bear. The build reference is the
[TBC feral PvE guide](https://www.wowhead.com/tbc/guide/classes/druid/feral/dps-talent-builds-pve).
TBC Shadow priests prioritize Shadowform at 31 spent points and Vampiric Touch
at 41. Existing allocations are retained; ordinary leveling adds points rather
than granting free respecs. Other authored builds retain their existing PvE
priorities. Build quality depends on level, available spells, gear and content;
these orders are not a claim that one distribution is best in every situation.

Normal trainer prices, paid respecs, learned abilities and each character's own
earned era remain authoritative. See [historical talents](era-talents.md).
