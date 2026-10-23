# Earned auction-house trading

Autonomous random bots sell surplus from their own bags and buy useful equipment
or supplies with their own gold. Purchases and sales use normal auction fees,
ownership checks and mail delivery. The server adds no generated auction stock
or artificial buyers.

Trading requires natural progression, earned auctions and a random bot without a
player master. As at the auction window, bots below the core's
`LevelReq.Auction` do not trade at auctioneers; they still collect auction mail
and sell surplus to vendors. Bots walk to an auctioneer or mailbox and reach
ordinary interaction range. Combat, flight, battlegrounds, dungeons, teleport,
trading and blocked movement prevent market trips.

## What bots can trade

Sellers keep quest items, needed equipment, reagents of learned class spells,
supplies and the last pet-food reserve for their own hunter pets, including
dismissed and stabled pets and pets temporarily unsummoned by a mount. Food
must match an owned pet's diet. Random bots do not craft, so they keep
profession materials only within Playerbots' ordinary stack limits; SelfBots
and altbots keep the reagents of their learned recipes.
Equipped, bound, conjured, temporary and otherwise ineligible items are not
listed. Each listing transfers an existing whole stack and pays its normal
deposit from the bot's balance. Automatic vendor selling also protects these
essentials under natural progression. Natural upkeep does not disenchant, so a
random bot with Enchanting sells outgrown bound gear that a vendor buys. In a
guild led by a player it keeps rare and better gear, as it would from
disenchanting.

Buyers select useful equipment, supplies or gathering tools (mining picks,
skinning knives and fishing poles) while reserving money for ordinary upkeep.
Bags follow the vendor bag rules: a general bag for an empty bag slot or, with a
free backpack slot, a larger one in place of the smallest general bag. Quivers,
ammo pouches and profession bags stay equipped, quivers are not bought, and no
bag is bought while the bot carries an unequipped upgrade. A won bag waits in
the mail until the backpack has room for it. Each purchase costs at most a
quarter of the current balance and must fit the available category budget. Bots
cannot buy their own or same-account auctions. They wait while an outstanding
bid or an uncollected won item exists. Other bots' auctions are eligible because
the buyer pays and the seller gives up the actual item.

A bot maintains at most 20 listings, at most two of the same item, and attempts
at most two new listings and one purchase per visit. The purchase goes to the
most useful offer: gear upgrades, then ammunition, consumables and gathering
tools; within a kind, the offer cheapest against its valuation limit. An auction
whose buyout is missing or not acceptable takes the core's minimum bid instead
when it ends within two visit intervals, unless a player leads it. Bots list for
the 12-hour duration, which `Rate.Auction.Time` scales.

An item that returns unsold or is refused a listing on two occasions is not
listed again for a week, or for three listing durations if that is longer.
Stacks returning within one listing duration count as one occasion. The bot
sells such stock to a vendor instead. A completed sale of the item clears that
record. The record is kept in server memory, so a restart forgets it.

## Pricing and travel

A bot undercuts the cheapest comparable buyout in the whole house by one copper
per item. Comparable offers have the same item and random property and belong
to another account. Without one, the buyout is three times the vendor sell price
per item. The starting bid is four fifths of the buyout and always above the
stack's vendor value.

Buyouts stay between twice the vendor sell price and the higher of the vendor's
price per item or six times the vendor sell price. A bot lists only when the
sale, after the house cut, beats vendoring the stack by at least the deposit.
A market at or below twice the vendor sell price refuses the listing. Buyers use
the same upper valuation limit. This heuristic does not reproduce every rare
item's player market value.

Solo bots from level 10, or `LevelReq.Auction` if higher, can plan a trip to a
compatible or neutral auctioneer on the same map and phase within 5,000 yards.
They need eligible surplus or at least one silver available after purchase
reserves. Nearby auctioneers and mailboxes are searched within 150 yards.

A trip has a ten-minute budget including its final approach. New plans wait
fifteen minutes. Failed routes, unavailable NPCs, timeouts and unreachable
nearby auctioneers or mailboxes postpone the visit for fifteen minutes and
return the bot to ordinary activity, including repairs, sales and training. The
last unreachable mailbox or auctioneer is then skipped for an hour, so another
can serve, and a failed turn passes to the other visit kind. On an auctioneer
turn without a nearby auctioneer, a distant market in reach comes before a
nearby mailbox. Trading depends on pathfinding and NPC availability. Bots may
vendor surplus when bags reach 80% usage or their budget cannot cover the
neutral auction house's deposit for the stack. Stock whose ordinary price cannot
repay that house's deposit and cut is vendored.

## Mail delivery

Bought and won items, sale proceeds, outbid bids and expired auctions use normal
auction mail and delivery delays. Bots visit a mailbox and process at most 20
auction receipts per visit through the core handlers. Other mail is left alone;
undelivered, expired and COD mail is skipped.

If bags are full, attachments remain in mail until space is available. Money can
be collected with full bags. A receipt is deleted only after its money and all
attachments have been retrieved successfully.

Natural progression blocks bot mail-send and mail-management shortcuts even if
`Playerbots.BotSendMailEnabled` is re-enabled. Earned auction collection has
its own ordinary mailbox path. Human mail remains available.

## Configuration

The active Playerbots file is `configs/modules/playerbots.conf`:

```ini
Playerbots.NaturalProgression = 1
Playerbots.EarnedAuctions = 1
Playerbots.EarnedAuctionInterval = 300
Playerbots.BotSendMailEnabled = 0
```

`EarnedAuctionInterval` is in seconds, clamped to 60–3,600. Auctioneer and mailbox
visits alternate with a stable per-bot stagger of up to 119 additional seconds.
Busy bots or distant markets can take longer. Set `EarnedAuctions = 0` to stop
autonomous trading; existing auctions and mail keep their normal lifecycle.

## Updates and market limits

Server updates preserve custom auction settings, databases and characters. See
the [update guide](updating.md) for automatic updates, manual installation and
configuration backups.

Existing items and money are preserved without verifying their origin; see
[realm updates](changing-expansions.md#updating-an-existing-realm). A fresh
natural-progression realm starts with normal character-creation items and no
auction-stock grants.

A fresh market can remain sparse while bots level, earn loot and gold, and
reach a town. Sellers need deposits and buyers need useful affordable listings.
There is no guaranteed stock, demand, subsidy or complete autonomous crafting
economy. AI and pathfinding limits can interrupt trading; see the
[configuration reference](configuration.md#supported-scope).
