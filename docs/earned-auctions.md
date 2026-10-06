# Earned auction-house trading

The earned-auctions patch lets autonomous random bots trade possessions from
their own bags with gold they already own. Bots can supply the auction house
with surplus loot and buy useful equipment or supplies from humans and other
bots. AH Bot Plus stays disabled: its generated stock and artificial demand do
not supply this market.

Trading requires `AiPlayerbot.NaturalProgression = 1`, an enabled earned-auction
setting and a random bot without a player master. Fighting, dead or
otherwise busy bots do not leave their activity to trade. The bot must walk to
an auctioneer and reach normal interaction range. The loop searches for nearby
auctioneers and mailboxes within 150 yards, then can plan a bounded walking trip
to a market. No remote auction access, teleport, item creation or money top-up
is added.

Solo bots from level 10 can walk to the closest compatible or neutral auctioneer
on the same map and phase within 5,000 yards. They need tradable bag surplus or
at least one silver available for purchases after normal budget reserves. These
trips are unavailable during combat, flight, battlegrounds, dungeons, teleport,
trading or when movement is blocked. A trip has a ten-minute total budget,
including the final approach to the NPC. New trip plans wait fifteen minutes;
a failed route, unavailable NPC or timeout ends the trip, backs off further
visits and lets ordinary AI resume. Reaching a trading town still depends on
normal pathfinding, NPC availability and the bot's own possessions.

## What bots can trade

Bots inspect their actual bag contents and keep quest items, needed equipment,
needed profession materials and needed supplies. Learned-spell reagents and
the hunter's last pet-food supply are also protected. Only eligible tradable
surplus is offered for sale. Equipped, bound, conjured, temporary and otherwise
ineligible items are not listed. A listing transfers the existing whole stack
through the core's auction handler and pays the normal deposit from the bot's
money; a successful sale uses the normal auction-house cut.

Automatic vendor sales also protect required items for completed quests awaiting
turn-in, learned-spell reagents and the last pet-food supply. These protections
remain active in natural mode even with earned auctions disabled, full bags or
insufficient auction funds.

Buyers look for useful equipment, needed profession materials or supplies,
spend their own gold and preserve money for ordinary upkeep. A purchase costs
at most a quarter of the bot's current balance and must fit its available
category budget after reserves. Bots do not buy their own or their same-account
characters' auctions, and wait while an outstanding bid or uncollected auction
attachment exists. Buying uses a normal buyout rather than a generated
replacement item or free inventory upgrade. The core retains its item eligibility,
available funds, auction ownership and transaction checks. Bots can trade with
other bots because each buyer still pays and each seller gives up the listed item.

Trading is deliberately bounded. A bot can maintain at most 20 active listings
and attempts at most two new listings and one buyout during a visit. These
limits are independent of the population target; 2,500 online bots do not mean
2,500 bots trading simultaneously.

Listings last 12 hours. The initial buyout is three times the ordinary vendor
sell price per item. When the bot finds comparable current listings for the
same item and random property, it tries to undercut their unit buyout by one
copper. The result stays between twice the vendor sell price and the higher of
the vendor buy price or six times the vendor sell price. Buyers enforce that
same upper valuation limit. This is a bounded pricing heuristic; it does not
model every rare item's human market value or scan every listing on each visit.

Bots can still vendor surplus when bags reach 80% usage or the available budget
cannot cover a conservative estimate of the whole-stack auction deposit. That
preserves ordinary leveling when they cannot afford to reserve bag space or
auction fees.

## Delivery and mailbox collection

Purchased items, sale proceeds and expired listings follow the ordinary auction
mail path. Bots travel to a mailbox and process at most 20 auction-mail receipts
per visit through the core's mailbox handlers. Other mail is left alone.
Undelivered, expired and COD mail is skipped. Delivery delays remain in force.
If bags are full, the item remains in mail until the bot can make room; the loop
does not delete an attachment to force delivery or manufacture a second copy. Money
can be collected even with full bags; a receipt is deleted only after all money
and attachments have been retrieved successfully.

Natural progression now blocks legacy bot mail-send and mail-management
shortcuts in source. Re-enabling `AiPlayerbot.BotSendMailEnabled` cannot bypass
those guards. Earned auction receipt collection uses its separate normal
mailbox handling; ordinary human mail remains available.

## Configuration

Fresh installations use these settings in `configs/modules/playerbots.conf`:

```ini
AiPlayerbot.NaturalProgression = 1
AiPlayerbot.EarnedAuctions = 1
AiPlayerbot.EarnedAuctionInterval = 300
AiPlayerbot.BotSendMailEnabled = 0
```

The patched full template leaves earned auctions disabled; the portable
profile enables them. `EarnedAuctionInterval` is measured in seconds and
clamped to 60–3,600. The default of 300 limits repeated market visits. Auctioneer
and mailbox visits alternate, with a stable per-bot stagger of up to 119
additional seconds. A bot can take longer when busy, far from an auctioneer or
unable to navigate. Set `EarnedAuctions` to `0` to disable autonomous trading.
Existing auctions and delivered mail
remain subject to normal auction expiry and collection rules.

Keep these settings in `configs/modules/mod_ahbot.conf`:

```ini
AuctionHouseBot.EnableSeller = false
AuctionHouseBot.Buyer.Enabled = false
AuctionHouseBot.GUIDs = 0
```

Enabling AH Bot Plus changes the economy by adding generated supply or
artificial demand. Its settings do not configure earned Playerbots trading.

## Updating an existing realm

Install a complete server ZIP built with
`patches/mod-playerbots-earned-auctions.patch`, stop the launcher and servers,
then run the new launcher's embedded profile update once from PowerShell:

```powershell
.\startup.exe --apply-profiles
```

The command backs up changed configurations and preserves characters and
databases. Restart normally afterward. Replacing only `startup.exe` or copying
the readable files from `defaults/` cannot add the new C++ auction behavior.
Applying profiles again restores their managed defaults; make custom interval
changes after applying them.

Existing items and money are retained. There is no historical provenance ledger
that can distinguish previously generated possessions from previously earned
ones. A fresh natural-progression realm starts with ordinary character-creation
items and no auction stock grants; an older realm needs its own decision about
any earlier cheat-generated inventory or gold.

## Market and AI limits

A fresh auction house may stay sparse while bots level, earn tradable loot and
gold, and reach a trading town. A seller must afford its deposit; a buyer must
find a useful affordable listing. The patch supplies no guaranteed instant
stock, fixed demand, automatic subsidy or complete crafting economy.

This adds an auction and receipt loop to the existing AI. It does not make
every bot complete every quest, profession or raid, or prove sustained market
activity on a live realm. Pathfinding stalls, unavailable NPCs, missing supplies
and incomplete upstream AI can still interrupt progress. The existing Wrath
class-system and encounter limits remain documented in
[the configuration audit](vanilla-config-audit.md).
