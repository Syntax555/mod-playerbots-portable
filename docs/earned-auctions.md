# Earned auction-house trading

Autonomous random bots sell surplus from their own bags and buy useful equipment
or supplies with their own gold. Purchases and sales use normal auction fees,
ownership checks and mail delivery. AH Bot Plus seller and buyer remain disabled.

Trading requires natural progression, earned auctions and a random bot without
a player master. Bots walk to an auctioneer or mailbox and reach ordinary
interaction range. Combat, flight, battlegrounds, dungeons, teleport, trading
and blocked movement prevent market trips.

## What bots can trade

Sellers keep quest items, needed equipment, profession materials, learned-spell
reagents, supplies and the hunter's last pet food. Equipped, bound, conjured,
temporary and otherwise ineligible items are not listed. Each listing transfers
an existing whole stack and pays its normal deposit from the bot's balance.
Automatic vendor selling also protects these essentials in natural mode.

Buyers select useful equipment, profession materials or supplies while reserving
money for ordinary upkeep. Each purchase costs at most a quarter of the current
balance and must fit the available category budget. Bots cannot buy their own
or same-account auctions. They wait while an outstanding bid or uncollected
auction attachment exists. Other bots' auctions are eligible because the buyer
pays and the seller gives up the actual item.

A bot maintains at most 20 listings and attempts at most two new listings and
one buyout per visit. Auctions last 12 hours.

## Pricing and travel

The initial buyout is three times the ordinary vendor sell price per item. For
comparable listings with the same item and random property, a bot tries to
undercut the unit buyout by one copper. Prices stay between twice the vendor
sell price and the higher of vendor buy price or six times vendor sell price.
Buyers use the same upper valuation limit. This heuristic does not reproduce
every rare item's player market value.

Solo bots from level 10 can plan a trip to a compatible or neutral auctioneer on
the same map and phase within 5,000 yards. They need eligible surplus or at least
one silver available after purchase reserves. Nearby auctioneers and mailboxes
are searched within 150 yards.

A trip has a ten-minute budget including its final approach. New plans wait
fifteen minutes; failed routes, unavailable NPCs and timeouts end the trip and
return the bot to ordinary activity. Trading depends on pathfinding and NPC
availability. Bots may vendor surplus when bags reach 80% usage or their budget
cannot cover a conservative whole-stack deposit estimate.

## Mail delivery

Bought items, sale proceeds and expired auctions use normal auction mail and
delivery delays. Bots visit a mailbox and process at most 20 auction receipts
per visit through the core handlers. Other mail is left alone; undelivered,
expired and COD mail is skipped.

If bags are full, attachments remain in mail until space is available. Money can
be collected with full bags. A receipt is deleted only after its money and all
attachments have been retrieved successfully.

Natural mode blocks legacy bot mail-send and mail-management shortcuts even if
`AiPlayerbot.BotSendMailEnabled` is re-enabled. Earned auction collection has
its own ordinary mailbox path. Human mail remains available.

## Configuration

The active Playerbots file is `configs/modules/playerbots.conf`:

```ini
AiPlayerbot.NaturalProgression = 1
AiPlayerbot.EarnedAuctions = 1
AiPlayerbot.EarnedAuctionInterval = 300
AiPlayerbot.BotSendMailEnabled = 0
```

`EarnedAuctionInterval` is in seconds, clamped to 60–3,600. Auctioneer and mailbox
visits alternate with a stable per-bot stagger of up to 119 additional seconds.
Busy bots or distant markets can take longer. Set `EarnedAuctions = 0` to stop
autonomous trading; existing auctions and mail keep their normal lifecycle.

Keep synthetic trading disabled in `configs/modules/mod_ahbot.conf`:

```ini
AuctionHouseBot.EnableSeller = false
AuctionHouseBot.Buyer.Enabled = false
AuctionHouseBot.GUIDs = 0
```

AH Bot Plus adds generated supply or artificial demand when enabled. It does
not configure earned Playerbots trading.

## Updates and market limits

Install the complete server package from
[Latest](https://github.com/Syntax555/mod-playerbots-portable/releases/latest).
With the launcher and servers stopped, run:

```powershell
.\startup.exe --apply-profiles
```

The command backs up managed configuration changes and preserves databases and
characters. Apply custom auction intervals afterward; applying profiles again
restores their defaults. Updating only `startup.exe` cannot update server logic.

Existing items and money are retained. There is no provenance ledger to separate
previously generated possessions from earned ones on an older realm. A fresh
natural-progression realm starts with normal character-creation items and no
auction-stock grants.

A fresh market can remain sparse while bots level, earn loot and gold, and
reach a town. Sellers need deposits and buyers need useful affordable listings.
There is no guaranteed stock, demand, subsidy or complete autonomous crafting
economy. AI and pathfinding limits can interrupt trading; see the
[configuration reference](vanilla-config-audit.md#supported-scope).
