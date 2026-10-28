# Earned auction-house trading

Autonomous random bots sell surplus from their own bags and buy useful items
with their own gold. Normal auction deposits, fees, ownership checks and mail
delivery apply. The server generates neither auction stock nor artificial
buyers. SelfBots and player-controlled companions do not run this market loop.

## Configuration

The portable defaults in `configs/modules/playerbots.conf` are:

```ini
Playerbots.NaturalProgression = 1
Playerbots.EarnedAuctions = 1
Playerbots.EarnedAuctionInterval = 300
Playerbots.BotSendMailEnabled = 0
```

`EarnedAuctionInterval` is in seconds, clamped to 60–3,600. Auctioneer and mailbox
visits alternate, with up to 119 seconds of stable per-bot staggering. Busy bots
and travel can take longer. Set `Playerbots.EarnedAuctions = 0` to stop trading;
existing auctions and mail keep their ordinary lifecycle. Updates preserve
custom settings; see [updating](updating.md).

## What bots trade

Sellers keep needed equipment, quest items, supplies, learned class-spell
reagents and the last suitable food reserve for owned hunter pets, including
stabled or temporarily unsummoned pets. Random bots do not craft; profession
materials follow native stack reserves. Human-controlled characters keep their
learned-recipe reagents. Equipped, bound, conjured, temporary and other
ineligible items are not listed. A listing transfers an existing whole stack
and pays its deposit.

Buyers seek gear upgrades, ammunition, consumables, bags and gathering tools.
They reserve upkeep money; a purchase costs at most a quarter of the current
balance and must fit its category budget. Bags fill an empty slot or replace
the smallest general bag when backpack space permits. Specialized bags remain
equipped; quivers are not bought, and a carried unequipped bag upgrade prevents
another purchase.

Bots cannot buy their own or same-account auctions. Outstanding bids or
uncollected won items normally pause purchases; a won item blocked by a unique
ownership limit does not. Other bots' listings are eligible: the buyer pays for
the actual item the seller gives up.

| Limit | Value |
| --- | --- |
| Active listings per bot | 20 |
| Listings of one item and random property | 2 |
| New listings per visit | 2 |
| Purchases per visit | 1 |
| Auction duration | 12 hours, scaled by `Rate.Auction.Time` |

Buyers prefer upgrades, then ammunition, consumables and gathering tools, using
relative value within each category. If buyout is unavailable or too expensive,
they can place the core's minimum bid on auctions ending within two visit
intervals, unless a player holds the leading bid.

## Pricing and unsold stock

Bots undercut the cheapest comparable buyout from another account by one copper
per item; comparable items share the item ID and random property. Without a
comparable offer, buyout is three times vendor sell value. The starting bid is
at least four fifths of buyout and above vendor value.

Buyout stays between twice vendor sell value and the higher of vendor purchase
price per item or six times vendor sell value. A sale after the house cut must
beat vendoring by at least the deposit. Buyers use the same upper valuation.
This heuristic cannot reproduce every rare item's player market value.

After two unsold returns or listing refusals, that item variant is vendored
instead of relisted for a week, or three listing durations if longer. Returns within one
listing duration count once; a completed sale clears the record. Restarting
forgets this in-memory record. Bots can also vendor surplus when bags reach
80% usage or deposits are unaffordable or uneconomic. Natural upkeep does not
disenchant; ordinary surplus protection also applies to vendor sales.

## Travel and mail delivery

Bots walk to auctioneers and mailboxes and use normal interaction range.
Auctioneer trading respects `LevelReq.Auction`. Solo bots can plan market trips
from level 10, or the configured auction level if higher, to a compatible or
neutral auctioneer on the same map and phase within 5,000 yards. They need
eligible surplus or at least one silver after reserves. Nearby searches cover
150 yards. Combat, flight, battlegrounds, dungeons, teleporting, trading and
blocked movement prevent trips.

A trip has ten minutes including its final approach; new plans and failed trips
wait fifteen minutes. An unreachable auctioneer or mailbox is skipped for an
hour so another can serve. Failure returns the bot to ordinary repairs, sales,
training and travel. Availability still depends on navigation and NPCs.

Mailboxes process at most 20 auction receipts per visit through normal core
handlers. Other mail, COD, undelivered and expired mail are left alone. Full
bags leave attachments in mail while permitting money collection. A receipt is
deleted only after all attachments and money are retrieved. Won items blocked
by ownership limits remain until ordinary collection becomes possible.

Natural progression refuses bot mail-send and mail-management shortcuts even
if `Playerbots.BotSendMailEnabled` is re-enabled. Earned auction collection uses
the ordinary mailbox path; human mail remains available.

## Market limits

A fresh market can remain sparse while bots level, earn loot and gold, and
reach towns. No stock, demand, subsidies or autonomous crafting economy are
guaranteed. Existing items and money are preserved without checking their
origin; see [realm updates](changing-expansions.md#updating-an-existing-realm).
AI and pathfinding limits can interrupt trading; see
[supported scope](configuration.md#supported-scope). Source fixtures cover
market rules, not a fully observed long-running player economy.
