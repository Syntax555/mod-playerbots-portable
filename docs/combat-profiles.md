# Combat profiles and equipment

MultiBot's **Select combat profile** menu offers **Automatic** and the bot's
class specializations. An active SelfBot has the selector in its compact
toolbar. Install the matching [MultiBot addon](addons.md) and server.

Choose a profile while the character is alive, outside combat and not being
teleported. The choice refreshes native class strategies, role support and
owned bag equipment. It does not spend talents, switch dual-specialization
slots, teach abilities or grant equipment. Controlled altbot and SelfBot talent
points remain for their owner to spend.

**Automatic** reads the current talent distribution, including Vanilla/TBC
EraTalents trees. A manual choice persists across relogs and AI resets; choose
Automatic to follow talents again. Selecting the current choice reapplies it.
Travel, loot, formation and instance strategies are retained.

## Class support

Profiles select existing Playerbots strategies and their healing, cleansing,
blessing, totem, pet and positioning support. The primary native strategies are:

| Class | Profile → native combat strategy |
| --- | --- |
| Warrior | Arms → `arms`; Fury → `fury`; Protection → `prot` |
| Paladin | Holy → `holy`; Protection → `prot`; Retribution → `ret` |
| Hunter | Beast Mastery → `bm`; Marksmanship → `mm`; Survival → `surv` |
| Rogue | Assassination → `assassin`; Combat → `combat`; Subtlety → `assassin` |
| Priest | Discipline → `disc`; Holy → `holy heal`; Shadow → `shadow` |
| Death Knight | Blood → `blood` with tank assistance; Frost → `frost`; Unholy → `unholy` |
| Shaman | Elemental → `ele`; Enhancement → `enh`; Restoration → `resto` |
| Mage | Arcane → `arcane`; Fire → `fire`; Frost → `frost` |
| Warlock | Affliction → `affli`; Demonology → `demo`; Destruction → `destro` |
| Druid | Balance → `balance`; Feral Cat → `cat`; Feral Bear → `bear`; Restoration → `resto` |

These are native mappings, not separate newly implemented rotations. Subtlety
shares assassination's rotation. Automatic Fury uses Arms until Whirlwind is
learned; automatic Fire can select `frostfire` when Frostfire Bolt and Ice Shards
are known. A feral druid without Cat Form uses Bear support. Shared damage
buttons can look alike even when the underlying strategies differ.

Ungrouped healing SelfBots retain native solo damage support: holy damage for
priests, elemental for shamans and retribution for paladins. Grouped SelfBots
use the selected healing rotation. Their profile still determines role and gear
preferences. Random Death Knights are disabled by the portable profile; the
class mapping remains available for eligible controlled characters.

## Equipment

The effective profile drives native specialization, role and item scoring.
Applying it checks usable equipment already in bags. Protection warriors and
paladins prefer an owned one-handed weapon and shield when both are usable.
Normal level, skill, armor, weapon and inventory checks still apply. The check
does not buy items, learn weapon skills or retrieve bank items.

General-purpose bags fill an empty bag slot or upgrade the smallest normal bag
across all four slots. Quivers, ammunition pouches and profession bags remain
equipped. The core still checks bag contents and whether the swap is possible.

Ordinary new-loot equipping follows `Playerbots.AutoEquipUpgradeLoot = 1`.
Loot rolls use the same native item classification; random-property variants
are scored by their own stats. The portable setting
`Playerbots.LootNeedRollLevel = 2` allows Need on a suitable upgrade, subject to
the core's loot-method restrictions. Zygor uses the selected profile with its
own stat-priority weights for source suggestions. Neither scoring system
guarantees the optimal equipment for every encounter.

## Random bots and historical talents

Random bots use the configured PvE specialization mix and spend earned,
unspent points. Authored Vanilla/TBC build orders cover the nine historical
classes, with separate stable cat/bear choices. Existing allocations remain;
leveling adds points without free respecs. Trainer prices, learned abilities,
paid respecs and each character's earned era remain authoritative. See
[historical talents](era-talents.md).

Source fixtures cover profile selection, native strategy mappings, ownership
and equipment gates. Live coverage across every class, era and gear combination
remains [outstanding](todo.md#gameplay-validation).
