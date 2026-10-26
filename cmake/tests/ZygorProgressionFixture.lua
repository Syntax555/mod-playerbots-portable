-- Runs Zygor Guides Viewer's Individual Progression layer from the patched
-- production files. The WoW client API, the bridge and the other addons are
-- recording doubles; replies follow the bridge's IP_PROGRESS_V1 wire format.
-- TestZygorProgression.py sets SOURCE to the patched addon directory and
-- ERA_SOURCE to the prepared EraTalents client addon.
local ROOT = assert(SOURCE, "SOURCE is required")
local ERA = assert(ERA_SOURCE, "ERA_SOURCE is required")

local function check(condition, message)
	if not condition then error("FIXTURE FAILED: " .. message, 2) end
end

local function read(path)
	local file = assert(io.open(ROOT .. "/" .. path, "rb"))
	local text = file:read("*a")
	file:close()
	return (text:gsub("^\239\187\191", ""))
end

local function compile(text, name, env)
	local chunk = assert(loadstring(text, "@" .. name))
	if env then setfenv(chunk, env) end
	return chunk
end

local function run(path, env)
	return compile(read(path), path, env)()
end

-- The text of path from first up to, not including, last.
local function section(path, first, last)
	local text = read(path)
	local a = assert(text:find(first, 1, true), path .. " lacks " .. first)
	local b = assert(text:find(last, a + 1, true), path .. " lacks " .. last)
	return text:sub(a, b - 1)
end

------------------------------------------------------------------------
-- Client doubles
------------------------------------------------------------------------

tinsert, tremove, wipe = table.insert, table.remove, function(t) for k in pairs(t) do t[k] = nil end return t end
QUEST_MONSTERS_KILLED = "Enemies slain: %d/%d"

local now = 1000
function GetTime() return now end
function GetLocale() return "enUS" end
function time() return math.floor(now) end
function InCombatLockdown() return false end

local player = {name = "Testchar", race = "Scourge", level = 60}
function UnitName(unit) if unit == "player" then return player.name end end
function UnitRace() return "Undead", player.race end
function UnitLevel() return player.level end
function UnitClass() return "Mage", "MAGE" end
function UnitFactionGroup() return "Horde" end

local group = {raid = 0, party = 0}
function GetNumRaidMembers() return group.raid end
function GetNumPartyMembers() return group.party end

local sent = {}
function SendAddonMessage(prefix, message, channel, target)
	check(prefix == "MBOT", "addon messages use the bridge prefix")
	check(#message <= 255, "addon message exceeds the client limit: " .. message)
	sent[#sent + 1] = {message = message, channel = channel, target = target}
end

local known = {}
function IsSpellKnown(id) return known[id] == true end

function hooksecurefunc(owner, name, hook)
	if type(owner) == "string" then owner, name, hook = _G, owner, name end
	local original = owner[name]
	owner[name] = function(...)
		local results = {original(...)}
		hook(...)
		return unpack(results)
	end
end

SlashCmdList = {}
local notified = 0
local libraries = {
	["AceConfigRegistry-3.0"] = {NotifyChange = function() notified = notified + 1 end},
	["AceAddon-3.0"] = {NewAddon = function(_, name)
		local addon = {name = name}
		function addon:RegisterEvent() end
		function addon:Print(text) addon.printed = (addon.printed or 0) + 1 end
		function addon:ScheduleTimer(fn) fn() end
		return addon
	end},
}
function LibStub(name, silent)
	local library = libraries[name]
	check(library or silent, "unexpected library " .. tostring(name))
	return library
end

function ZygorGuidesViewer_L()
	return setmetatable({coords = "%s,%s"}, {__index = function(_, key) return key end})
end
function TableKeys(t) local keys = {} for key in pairs(t or {}) do keys[#keys + 1] = key end return keys end
function GetRealZoneText() return "Test Zone" end

ZygorGuidesViewer = {
	L = ZygorGuidesViewer_L(), LM = {},
	db = {profile = {}, char = {}},
	startups = {}, registeredguides = {}, events = {},
	questsbyid = {}, completedQuests = {}, recentlyCompletedGoals = {}, recentlyStickiedGoals = {},
	BZL = {}, BSZL = {}, BFL = {}, StandingNamesEngRev = {}, dailyQuests = {}, instantQuests = {},
	StepProto_mt = {}, GoalProto_mt = {},
}
ZGV = ZygorGuidesViewer
local prints, frames, guides = {}, 0, {}

function ZGV:AddEvent(event, handler)
	self.events[event] = self.events[event] or {}
	table.insert(self.events[event], handler)
end
local function fire(event, ...)
	for _, handler in ipairs(ZGV.events[event] or {}) do handler(ZGV, event, ...) end
end

local repeating, oneshots = {}, {}
function ZGV:ScheduleRepeatingTimer(fn, interval)
	repeating[#repeating + 1] = {fn = fn, interval = interval, last = now}
end
function ZGV:ScheduleTimer(fn, delay)
	oneshots[#oneshots + 1] = {fn = fn, at = now + delay}
end
local function advance(seconds)
	local target = now + seconds
	while now < target do
		now = math.min(target, now + 0.25)
		for index = #oneshots, 1, -1 do
			if oneshots[index].at <= now then table.remove(oneshots, index).fn() end
		end
		for _, timer in ipairs(repeating) do
			if now - timer.last >= timer.interval then timer.last = now; timer.fn() end
		end
	end
end

function ZGV:Print(text) prints[#prints + 1] = tostring(text) end
function ZGV:Debug() end
function ZGV:UpdateFrame() frames = frames + 1 end
function ZGV:GetQuestName() return nil end
function ZGV:GetTranslatedNPC() return nil end
function ZGV:RaceClassMatch() return true end
function ZGV:RegisterGuide(title, data)
	guides[title] = data
	table.insert(self.registeredguides, {title = title, rawdata = data})
end
function ZGV:GetGuideByTitle(title)
	for _, guide in ipairs(self.registeredguides) do
		if guide.title == title then return guide end
	end
end
ZGV.Frame = {}
ZGV.DIR = "Interface\\AddOns\\ZygorGuidesViewerRM"
-- The viewer's quest log events, which the module hooks at startup.
function ZGV:NewQuestEvent() end
function ZGV:LostQuestEvent() end
function ZGV:CompletedQuestEvent() end
function ZGV:IsQuestPossible() return true end
ZGV.db.char.permaCompletedDailies = {}

------------------------------------------------------------------------
-- Production files
------------------------------------------------------------------------

run("Parser.lua")
run("Step.lua")
run("Goal.lua")
run("IndividualProgression.lua")
check(ZGV.IP, "IndividualProgression.lua defines ZGV.IP")
local IP = ZGV.IP
local R = IP.REASON
check(ZGV.ConditionEnv.iptier, "guides can test the earned tier")
check(#ZGV.startups == 1 and ZGV.startups[1][1] == "Individual Progression", "the module registers its startup")
check(type(SlashCmdList.ZYGORIP) == "function" and SLASH_ZYGORIP1 == "/zygorip", "the status command exists")

local function message(index) return sent[index] and sent[index].message end
local function lastMessage() return message(#sent) end
local function server(text, sender)
	fire("CHAT_MSG_ADDON", "MBOT", text, "WHISPER", sender or player.name)
end
local function stateText(fields)
	local s = {ip = 1, strict = 1, stored = 7, effective = 7, limit = 0, era = 0, next = 8, nextMet = 0,
		account = "N", gm = 0, maxLevel = 80}
	for key, value in pairs(fields or {}) do s[key] = value end
	return table.concat({"IP_STATE", IP.watchToken or "?", "1", s.ip, s.strict, s.stored, s.effective, s.limit,
		s.era, s.next, s.nextMet, s.account, s.gm, s.maxLevel}, "~")
end
local function sendState(fields) server(stateText(fields)) end

-- Pending requests of one kind in the order they were sent.
local function pending(kind)
	local found = {}
	for index = 1, #sent do
		local token, rest = (message(index) or ""):match("^GET~" .. kind .. "~(zip%d+)~?(.*)$")
		if token and IP.requests[token] then found[#found + 1] = {token = token, rest = rest} end
	end
	return found
end

-- Frames a list reply in chunks within the 255-byte addon message budget, as the bridge does.
local function framed(kind, token, entries, count)
	server(kind .. "_BEGIN~" .. token .. "~" .. #entries)
	local chunk = {}
	local function flush()
		if #chunk > 0 then server(kind .. "~" .. token .. "~" .. table.concat(chunk, ",")) end
		chunk = {}
	end
	for _, entry in ipairs(entries) do
		if #(kind .. "~" .. token .. "~" .. table.concat(chunk, ",") .. "," .. entry) > 250 then flush() end
		chunk[#chunk + 1] = entry
	end
	flush()
	server(kind .. "_END~" .. token .. "~" .. (count or #entries))
end

-- Answers every pending IP_QUESTS request; codes maps a quest to its reply.
local function answerQuests(codes)
	for _, request in ipairs(pending("IP_QUESTS")) do
		local entries = {}
		for id in request.rest:gmatch("%d+") do
			entries[#entries + 1] = id .. ":" .. (codes[tonumber(id)] or "A")
		end
		framed("IP_QUESTS", request.token, entries)
	end
end

local function answerAccess(entries)
	if #pending("IP_ACCESS") == 0 then IP:RequestAccess(true) end
	for _, request in ipairs(pending("IP_ACCESS")) do framed("IP_ACCESS", request.token, entries) end
end

local function resetState()
	IP.state, IP.access, IP.accessAt = nil, nil, nil
	IP.quests, IP.queued, IP.inflight, IP.requests, IP.warned = {}, {}, {}, {}, {}
end

------------------------------------------------------------------------
-- Bridge discovery and state
------------------------------------------------------------------------

check(IP:Status() == "pending", "the state is unknown before the server answers")
check(IP:TierCheck(1) == "unknown", "an unknown state never unlocks a tier")
check(not IP:HasTier(0), "an unknown state reports no tier")

ZGV.startups[1][2](ZGV)
check(lastMessage() == "HELLO~1" and sent[#sent].channel == "WHISPER" and sent[#sent].target == player.name,
	"the client probes the bridge by whispering itself")

-- Without an answer the client retries a few times and then reports no bridge.
advance(3)
check(IP.bridge == nil and IP:Status() == "pending", "one lost HELLO is retried")
advance(30)
check(lastMessage() == "HELLO~1" and IP.helloRetries == 2, "the probe repeats after 30 seconds")
advance(33)
check(IP.helloRetries == 3, "the probe repeats a third time")
advance(3)
check(IP.bridge == "absent" and IP:Status() == "absent", "a realm without a bridge is reported as absent")
check(IP:TierCheck(18) == "ok" and not IP:Applies(), "automatic mode keeps ordinary behaviour without a bridge")
ZGV.db.profile.ip_mode = "on"
check(IP:Applies() and IP:TierCheck(1) == "unknown", "the On mode keeps later content locked without a bridge")
ZGV.db.profile.ip_mode = "off"
check(IP:Status() == "off" and IP:TierCheck(18) == "ok", "the Off mode lifts every gate")
ZGV.db.profile.ip_mode = nil
local probes = #sent
advance(120)
check(#sent == probes, "an absent bridge is not probed again without a refresh")

-- A bridge without the capability is unsupported.
IP.bridge, IP.helloRetries = nil, 0
IP:Probe()
server("CAPS_BEGIN")
server("CAPS~QUEST_PROGRESS_V1,BOT_SUMMON")
server("CAPS_END")
check(IP.bridge == "unsupported" and IP:Status() == "absent", "a bridge without IP_PROGRESS_V1 is unsupported")

-- Capabilities from other senders are ignored.
IP.bridge, IP.helloRetries = nil, 0
IP:Probe()
server("CAPS~IP_PROGRESS_V1", "Otherplayer")
server("CAPS_END", "Otherplayer")
check(IP.helloPending and IP.bridge == nil, "another player's addon messages are ignored")

group.party = 2
IP.helloPending = false
IP:Probe()
check(sent[#sent].channel == "PARTY" and sent[#sent].target == nil, "a grouped character reaches the bridge through PARTY")
group.party = 0
server("CAPS_BEGIN")
server("CAPS~QUEST_PROGRESS_V1,IP_PROGRESS_V1")
server("CAPS_END")
check(IP.bridge == "ready", "the advertised capability readies the bridge")
check(lastMessage() == "GET~IP_STATE~" .. IP.watchToken .. "~WATCH", "the client watches its own state")
check(not lastMessage():find(player.name, 1, true), "requests never name a character")

-- Malformed and foreign state is ignored.
local invalid = {
	{account = "Q"}, {stored = 7, effective = 8}, {limit = 6, effective = 7}, {era = 3}, {stored = 19},
	{ip = 2}, {gm = 2}, {strict = 2}, {nextMet = 2}, {next = 19}, {maxLevel = -1}, {effective = "x"},
}
for _, fields in ipairs(invalid) do
	sendState(fields)
	check(IP.state == nil, "malformed state is rejected")
end
server(stateText():gsub("~80$", ""))
check(IP.state == nil, "state with missing fields is rejected")
server((stateText():gsub("^IP_STATE~[^~]+", "IP_STATE~zip999")))
check(IP.state == nil, "state for another token is ignored")
server(stateText(), "Otherplayer")
check(IP.state == nil, "state from another sender is ignored")

sendState()
check(IP.state and IP.state.effective == 7 and IP:Gated(), "the server state is applied")
check(prints[#prints]:find("tier 7", 1, true), "the first state is reported once")
check(#pending("IP_ACCESS") == 1, "an active state asks for instance access")

-- The watch lease is renewed before the server's 180 second expiry.
local before = #sent
advance(61)
local renewed = false
for index = before + 1, #sent do
	if message(index) == "GET~IP_STATE~" .. IP.watchToken .. "~WATCH" then renewed = true end
end
check(renewed, "the watch is renewed within 60 seconds")

-- Tier gates follow the effective tier and the realm ceiling.
check(IP:TierCheck(7) == "ok" and IP:TierCheck(8) == "locked", "content follows the effective tier")
check(IP:HasTier(7) and not IP:HasTier(8), "HasTier reports the earned tier")
check(ZGV.ConditionEnv.iptier(7) and not ZGV.ConditionEnv.iptier(8), "guide conditions see the earned tier")
check(IP:LevelCap() == 60, "Vanilla characters stop gaining experience at 60")
sendState({stored = 12, effective = 10, limit = 10, era = 1, next = 12})
check(IP:TierCheck(10) == "ok" and IP:TierCheck(12) == "locked", "the realm ceiling clamps the usable tier")
check(IP:LevelCap() == 70, "TBC characters stop gaining experience at 70")
sendState({stored = 13, effective = 13, era = 2, next = 14, maxLevel = 70})
check(IP:LevelCap() == 70, "the realm level cap bounds the era cap")
sendState({stored = 0, effective = 0, era = 0, next = 1, account = "B"})
check(not IP:Gated() and IP:TierCheck(18) == "ok", "gates do not apply to bot accounts")
sendState({stored = 0, effective = 0, era = 0, next = 1, account = "X"})
check(IP:TierCheck(18) == "ok", "gates do not apply to excluded accounts")
sendState({stored = 0, effective = 0, era = 0, next = 1, gm = 1})
check(IP:TierCheck(18) == "ok", "game master mode bypasses the gates")
sendState({ip = 0, stored = 0, effective = 0, era = 255, next = 0, strict = 0})
check(IP:Status() == "inactive" and not IP:Applies() and IP:TierCheck(18) == "ok", "realms without Individual Progression are ungated")
check(not IP:HasTier(0), "an inactive realm reports no tier")

------------------------------------------------------------------------
-- Status display
------------------------------------------------------------------------

sendState({stored = 5, effective = 5, next = 6, era = 0})
local status = IP:StatusText()
check(status:find("tier 5 (Vanilla)", 1, true) and status:find("Next milestone: tier 6", 1, true)
	and status:find("C'Thun", 1, true), "the status names the tier and the next milestone")
check(status:find("level 60", 1, true), "the status names the experience cap")
sendState({stored = 7, effective = 7, next = 8, nextMet = 1})
status = IP:StatusText()
check(status:find("Into the Breach", 1, true) and status:find("already turned in", 1, true), "a turned-in quest milestone is explained")
sendState({stored = 7, effective = 7, limit = 7, next = 8})
check(IP:StatusText():find("above the realm ceiling", 1, true), "a milestone above the ceiling is explained")
sendState({stored = 18, effective = 18, era = 2, next = 0})
check(IP:StatusText():find("complete", 1, true), "the completed chain is reported")
sendState({stored = 3, effective = 3, era = 255, next = 0, strict = 0})
check(IP:StatusText():find("Custom progression chain", 1, true), "a custom chain does not show default milestones")
check(IP.TEXT.deDE.status_active and IP.TEXT.deDE.reason.TIER, "German text exists")
for key in pairs(IP.TEXT.enUS) do
	if key ~= "title" and key ~= "era0" and key ~= "era1" and key ~= "era2" and key ~= "access_U" and key ~= "locked_instance" and key ~= "quest_status" then
		check(IP.TEXT.deDE[key] ~= nil, "German text covers " .. key)
	end
end
for key in pairs(IP.TEXT.enUS.reason) do check(IP.TEXT.deDE.reason[key], "German text covers reason " .. key) end

------------------------------------------------------------------------
-- Quests
------------------------------------------------------------------------

sendState({stored = 7, effective = 7, era = 0, next = 8})
answerAccess({})
before = #sent
check(not IP:IsQuestBlocked(9001), "an unknown quest is not hidden")
check(IP.queued[9001], "an unknown quest is queued")
IP:IsQuestBlocked(9001)
for id = 9002, 9050 do IP:IsQuestBlocked(id) end
advance(0.5)
local batches = pending("IP_QUESTS")
check(#batches == 2, "49 quests are asked in two batches")
local asked = 0
for _, request in ipairs(batches) do
	local count = select(2, request.rest:gsub("%d+", ""))
	check(count <= 32, "a batch carries at most 32 quests")
	asked = asked + count
	check(#("GET~IP_QUESTS~" .. request.token .. "~" .. request.rest) <= 240, "a batch fits one addon message")
end
check(asked == 50, "every queued quest is asked once")
check(not IP.queued[9001] and IP.inflight[9001], "a sent quest is in flight")
IP:IsQuestBlocked(9001)
check(not IP.queued[9001], "a quest in flight is not asked again")

-- A reply that lost a packet is asked again instead of stored.
local first = batches[1]
local entries = {}
for id in first.rest:gmatch("%d+") do entries[#entries + 1] = id .. ":L10000:+8" end
framed("IP_QUESTS", first.token, entries, #entries + 1)
check(IP.quests[9001] == nil and IP.queued[9001], "an incomplete reply is requeued")
advance(0.5)
answerQuests({[9001] = "L10000:+8", [9002] = "L8", [9003] = "L20000", [9004] = "L4", [9005] = "L1000",
	[9006] = "R", [9007] = "L4000", [9008] = "L200", [9009] = "L10", [9010] = "L80", [9011] = "L40000",
	[9012] = "L10000:-13", [9013] = "L8000"})
check(IP:IsQuestBlocked(9001), "a progression marker condition hides a quest")
check(IP:DescribeQuest(9001):find("needs tier 8", 1, true), "the needed tier is explained")
check(IP:DescribeQuest(9012):find("retired at tier 13", 1, true), "a retired quest is explained")
check(not IP:IsQuestBlocked(9002), "a level that ordinary play reaches keeps the quest")
check(IP:IsQuestBlocked(9003), "a quest giver hidden by progression hides the quest")
check(IP:IsQuestBlocked(9004), "another race's quest is hidden")
check(IP:IsQuestBlocked(9005), "a breadcrumb whose follow-up is taken is hidden")
check(not IP:IsQuestBlocked(9006), "a rewarded quest is not hidden")
check(not IP:IsQuestBlocked(9007), "a repeatable quest waiting for its reset is kept")
check(IP:IsQuestBlocked(9008), "an exclusive alternative already taken is hidden")
check(IP:IsQuestBlocked(9009), "an outleveled quest is hidden")
check(not IP:IsQuestBlocked(9010), "a missing previous quest keeps the step")
check(not IP:IsQuestBlocked(9011), "a full quest log keeps the step")
check(not IP:IsQuestBlocked(9013), "quest conditions that play can satisfy keep the step")
check(IP:DescribeQuest(9002) == "level too low", "the reason is explained")

ZGV.questsbyid[9001] = {complete = false}
check(not IP:IsQuestBlocked(9001), "a quest already in the log keeps being tracked")
ZGV.questsbyid[9001] = nil
ZGV.completedQuests[9001] = true
check(not IP:IsQuestBlocked(9001), "a completed quest is not hidden")
ZGV.completedQuests[9001] = nil

-- Quest log changes refresh answers without dropping the old ones first.
ZGV:NewQuestEvent("Other", 1)
check(IP:IsQuestBlocked(9001), "an outdated answer stays in use until it is replaced")
advance(0.5)
local stale = pending("IP_QUESTS")
check(#stale == 1, "an outdated answer is asked again")
IP:InvalidateQuests()
framed("IP_QUESTS", stale[1].token, {"9001:A"})
check(IP:IsQuestBlocked(9001), "an answer from before an invalidation is not stored")
advance(0.5)
answerQuests({[9001] = "A"})
check(not IP:IsQuestBlocked(9001), "the fresh answer replaces the outdated one")

-- Reputation and skill changes drop only answers that named them.
IP.quests[9100] = {status = "L", reasons = R.REPUTATION, generation = IP.generation, at = now}
IP.quests[9101] = {status = "L", reasons = R.TIER, generation = IP.generation, at = now}
fire("UPDATE_FACTION")
check(IP.quests[9100] == nil and IP.quests[9101] ~= nil, "a reputation change drops reputation answers only")
local generation = IP.generation
fire("PLAYER_LEVEL_UP", 61)
check(IP.generation == generation + 1, "a level-up refreshes every answer")
IP.quests[9102] = {status = "L", reasons = R.REPEAT, generation = IP.generation, at = now}
IP:Quest(9102)
check(not IP.queued[9102], "a fresh reset answer is used")
now = now + 601
IP:Quest(9102)
check(IP.queued[9102], "a reset answer expires")
advance(0.5)
answerQuests({})

-- A rate-limited request is asked again.
IP:Quest(9200)
advance(0.5)
local limited = pending("IP_QUESTS")[1]
server("ERR~GET~IP_QUESTS~" .. limited.token .. "~RATE_LIMIT")
check(IP.queued[9200] and not IP.requests[limited.token], "a rate-limited request is requeued")
advance(0.5)
answerQuests({})
-- A request without an answer times out instead of staying in flight.
IP:Quest(9201)
advance(0.5)
check(IP.inflight[9201], "the request is in flight")
advance(11)
check(not IP.inflight[9201], "an unanswered request times out")
answerQuests({})

-- A long skip spreads its batches below the bridge's rate limit.
for id = 20001, 20400 do IP:Quest(id) end
before = #sent
advance(0.5)
check(#pending("IP_QUESTS") <= 6, "one flush sends at most six batches")
advance(1)
advance(1)
local spread = 0
for _, request in ipairs(pending("IP_QUESTS")) do spread = spread + select(2, request.rest:gsub("%d+", "")) end
check(spread >= 400, "later flushes send the remaining batches")
for id = 20001, 20400 do check(not IP.queued[id], "every queued quest is asked") end
answerQuests({})

-- Steps and goals from the real Step and Goal prototypes.
IP.quests[9300] = {status = "L", reasons = R.TIER, tier = 9, generation = IP.generation, at = now}
IP.quests[9301] = {status = "A", reasons = 0, generation = IP.generation, at = now}
local function goal(fields) return setmetatable(fields, ZGV.GoalProto_mt) end
local function step(goals)
	local s = setmetatable({goals = goals, parentGuide = {}}, ZGV.StepProto_mt)
	for _, g in ipairs(goals) do g.parentStep = s end
	return s
end
local blocked = step({goal({action = "goto", x = 1, y = 1}), goal({action = "accept", questid = 9300, quest = "Locked"})})
check(not blocked:AreRequirementsMet(), "a step whose quests are all unavailable is skipped")
check(blocked:IsComplete() == true, "the skipped step completes immediately")
check(not blocked.goals[2]:IsVisible() and blocked.goals[1]:IsVisible(), "the unavailable quest goal is hidden")
local mixed = step({goal({action = "accept", questid = 9300}), goal({action = "accept", questid = 9301})})
check(mixed:AreRequirementsMet(), "a step with an available quest remains")
check(not mixed.goals[1]:IsVisible() and mixed.goals[2]:IsVisible(), "only the unavailable goal is hidden")
local travel = step({goal({action = "goto", x = 1, y = 1})})
check(travel:AreRequirementsMet(), "a step without quests is not affected")
local unknown = step({goal({action = "accept", questid = 9400})})
check(unknown:AreRequirementsMet(), "a step with an unknown quest remains")
sendState({stored = 7, effective = 7, gm = 1, next = 8})
check(blocked:AreRequirementsMet(), "game master mode shows every quest")
sendState({stored = 7, effective = 7, next = 8})
answerAccess({})
IP.quests[9300] = {status = "L", reasons = R.TIER, tier = 9, generation = IP.generation, at = now}
check(not blocked:AreRequirementsMet(), "the gate returns with the normal account state")

------------------------------------------------------------------------
-- Guides, regions and instances
------------------------------------------------------------------------

local function guide(title, text, fields)
	local g = {title = title, title_short = title, rawdata = text}
	for key, value in pairs(fields or {}) do g[key] = value end
	return g
end
check(IP:GuideRequirement(guide("a", "step\n\tgoto Hellfire Peninsula,50,50\n")).tier == 8, "Outland needs tier 8")
check(IP:GuideRequirement(guide("b", ".talk Kael|goto Isle of Quel'Danas,48,30")).tier == 12, "Quel'Danas needs tier 12")
check(IP:GuideRequirement(guide("c", "goto Borean Tundra,1,1\ngoto Dalaran/1 55,40")).tier == 13, "Northrend needs tier 13")
check(IP:GuideRequirement(guide("d", "goto Orgrimmar/0 55.69,40\ngoto 53.1,44.2")).tier == 0, "Kalimdor needs no tier")
check(IP:GuideRequirement(guide("e", "goto Ghostlands,40,40")).tier == 8, "an Undead needs tier 8 for the TBC race zones")
player.race = "BloodElf"
check(IP:GuideRequirement(guide("f", "goto Ghostlands,40,40")).tier == 0, "Blood Elves start in their own zones")
player.race = "Draenei"
check(IP:GuideRequirement(guide("g", "goto Eversong Woods,40,40")).tier == 0, "Draenei enter the TBC race zones")
player.race = "Scourge"
check(IP:GuideRequirement(guide("h", "", {headerdata = {maps = {"Netherstorm"}}})).tier == 8, "gold route maps count")

local outland = guide("Leveling Guides\\Hellfire Peninsula (60-62)", "goto Hellfire Peninsula,50,50", {type = "leveling", startlevel = 58})
local check1, reason1 = IP:GuideCheck(outland)
check(check1 == "locked" and reason1:find("tier 8", 1, true), "an Outland guide is locked before tier 8")
local capped = guide("Leveling Guides\\Winterspring (60-61)", "goto Winterspring,50,50", {type = "leveling", startlevel = 60})
local check2, reason2 = IP:GuideCheck(capped)
check(check2 == "locked" and reason2:find("level 60", 1, true), "a leveling guide past the experience cap is locked")
check(IP:GuideCheck(guide("Leveling Guides\\Winterspring (58-60)", "goto Winterspring,50,50", {type = "leveling", startlevel = 58})) == "ok",
	"a guide below the cap is available")
check(IP:GuideCheck(guide("Dungeon Guides\\Molten Core", "goto Molten Core,1,1", {startlevel = 60})) == "unknown",
	"an instance guide waits for the server's access answer")

answerAccess({"409:A---", "532:G---", "229:R---", "309:D---"})
check(IP:GuideCheck(guide("Dungeon Guides\\Molten Core", "goto Molten Core,1,1", {startlevel = 60})) == "ok",
	"the level cap concerns leveling guides only")
local karazhan = guide("Dungeon Guides\\Karazhan", "goto Deadwind Pass,40,70\ngoto Karazhan,50,50")
local check3, reason3 = IP:GuideCheck(karazhan)
check(check3 == "locked" and reason3:find("progression", 1, true), "a progression-gated instance locks its guide")
check(IP:GuideCheck(guide("x", "goto Blackrock Spire,1,1")) == "ok", "a missing key belongs to the guide's steps")
check(IP:GuideCheck(guide("y", "goto Molten Core,1,1")) == "ok", "an accessible instance keeps its guide")
check(IP:InstanceCheck(309) == "locked", "a disabled instance is not accessible")
check(IP:InstanceCheck(999) == "unknown", "an unreported map is unknown")
check(IP:GuideLine(karazhan):find("Individual Progression", 1, true), "the guide browser explains a lock")
check(IP:GuideLine(guide("z", "goto Durotar,1,1")) == nil, "an available guide has no lock line")
IP:WarnGuide(outland)
local warnings = #prints
check(prints[warnings]:find("not available to this character yet", 1, true), "loading a locked guide warns")
IP:WarnGuide(outland)
check(#prints == warnings, "the warning is shown once")

sendState({stored = 8, effective = 8, era = 1, next = 9})
answerAccess({})
check(IP:GuideCheck(outland) == "ok", "tier 8 opens Outland")
check(IP:GuideCheck(guide("Leveling Guides\\Nagrand (70)", "goto Nagrand,1,1", {type = "leveling", startlevel = 70})) == "locked",
	"TBC characters stop at level 70 before Wrath")
IP.state = nil
check(IP:GuideCheck(outland) == "unknown", "an unknown state locks later guides")
sendState({stored = 8, effective = 8, era = 1, next = 9})
answerAccess({})

-- The guide chain holds before a next guide this character cannot follow.
local viewer = section("ZygorGuidesViewer.lua", "function me:SkipStep(delta,fast)", "function me:Print(s)")
local viewerEnv = setmetatable({me = ZGV}, {__index = _G})
compile(viewer, "ZygorGuidesViewer.lua:SkipStep", viewerEnv)()
local loaded = {}
ZGV.completioninterval, ZGV.completionintervallong = 0, 1
function ZGV:InlineButtonsEnabled() return false end
function ZGV:SetGuide(title)
	loaded[#loaded + 1] = title
	self.CurrentGuide = self:GetGuideByTitle(title)
	self.CurrentGuideName = title
	self.CurrentStepNum = 1
	self.CurrentStep = self.CurrentGuide.steps[1]
end
function ZGV:FocusStepQuiet(index)
	self.CurrentStepNum = index
	self.CurrentStep = self.CurrentGuide.steps[index]
end
function ZGV:FocusStep(index) self:FocusStepQuiet(index) end
local northrend = guide("Leveling Guides\\Borean Tundra (68-70)", "goto Borean Tundra,50,50", {type = "leveling", startlevel = 68})
northrend.steps = {step({goal({action = "goto", x = 1, y = 1})})}
local current = guide("Leveling Guides\\Nagrand (67-68)", "goto Nagrand,50,50", {next = northrend.title})
current.steps = {step({goal({action = "goto", x = 1, y = 1})})}
table.insert(ZGV.registeredguides, current)
table.insert(ZGV.registeredguides, northrend)
ZGV.CurrentGuide, ZGV.CurrentGuideName, ZGV.CurrentStepNum = current, current.title, 1
ZGV.CurrentStep = current.steps[1]
ZGV:SkipStep(1)
check(#loaded == 0, "the chain does not switch to Northrend before tier 13")
check(ZGV.CurrentStep.finish and ZGV.CurrentGuide == current, "the chain holds on a finish step")
check(ZGV.CurrentStep.goals[1].text:find("Borean Tundra", 1, true) and ZGV.CurrentStep.goals[1].text:find("tier 13", 1, true),
	"the hold step names the next guide and the tier it needs")
ZGV:SkipStep(1)
check(#loaded == 0 and ZGV.pause, "skipping again stays on the hold step")
sendState({stored = 13, effective = 13, era = 2, next = 14})
answerAccess({})
ZGV:SkipStep(1)
check(loaded[1] == northrend.title, "the chain continues once the tier is earned")

------------------------------------------------------------------------
-- Milestone guide
------------------------------------------------------------------------

local milestones = guides[IP.L.milestone_guide]
check(milestones, "the milestone chain is registered as a guide")
local parsed = assert(ZGV:ParseEntry(milestones))
check(#parsed.steps == 18, "the milestone guide has one step per milestone and the ceiling note")
sendState({stored = 5, effective = 5, era = 0, next = 6})
answerAccess({})
local function stepFor(tier)
	for _, s in ipairs(parsed.steps) do
		if s.goals[1].text and s.goals[1].text:find("Tier " .. tier .. ":", 1, true) then return s end
	end
end
check(parsed.steps[1] == stepFor(1), "the guide starts with the first milestone, which the viewer always shows")
check(stepFor(5):IsComplete() == true and stepFor(6):IsComplete() == false, "milestone steps follow the server's tier")
check(stepFor(11) == nil, "tier 11 has no milestone")
local note = parsed.steps[1].goals[2]
check(note and note.text == IP.L.milestone_none and not note:IsVisible(), "the not-reported note hides once the server reports the tier")
sendState({stored = 7, effective = 7, limit = 7, era = 0, next = 8})
answerAccess({})
check(not stepFor(8):AreRequirementsMet() and parsed.steps[#parsed.steps]:AreRequirementsMet(),
	"milestones above the ceiling are replaced by the ceiling note")
IP.state = nil
check(stepFor(1):IsComplete() == false, "an unknown state completes no milestone")
check(note:IsVisible() and stepFor(1):AreRequirementsMet(), "the note explains incomplete milestones until the server reports")

-- Milestone names follow the client's language without breaking the guide syntax.
libraries["LibBabble-Zone-3.0"] = {GetUnstrictLookupTable = function() return {["Molten Core"] = "Geschmolzener Kern"} end}
local translatedNPC, questName = ZGV.GetTranslatedNPC, ZGV.GetQuestName
function ZGV:GetTranslatedNPC(id) if id == 11502 then return "Ragnaros der Feuerfuerst" end end
function ZGV:GetQuestName(id) if id == 8743 then return "Gong|schlagen//jetzt" end end
local localized = IP:MilestoneGuide()
local reparsed = assert(ZGV:ParseEntry(localized))
check(localized:find("Ragnaros der Feuerfuerst in Geschmolzener Kern", 1, true), "boss and zone names are localized")
check(localized:find("Gong/schlagen/jetzt", 1, true) and #reparsed.steps == 18, "localized names cannot inject guide syntax")
libraries["LibBabble-Zone-3.0"] = nil
ZGV.GetTranslatedNPC, ZGV.GetQuestName = translatedNPC, questName

------------------------------------------------------------------------
-- Quest automation
------------------------------------------------------------------------

sendState({stored = 7, effective = 7, era = 0, next = 8})
answerAccess({})
local accepted, completed, rewarded, selected = 0, 0, 0, 0
local title = "Into the Breach"
function GetTitleText() return title end
function QuestDetailAcceptButton_OnClick() accepted = accepted + 1 end
function IsQuestCompletable() return true end
function CompleteQuest() completed = completed + 1 end
function GetNumQuestChoices() return 0 end
function GetQuestReward() rewarded = rewarded + 1 end
function GetNumAvailableQuests() return 1 end
function GetAvailableTitle() return title end
function SelectAvailableQuest() selected = selected + 1 end
function GetNumActiveQuests() return 0 end
run("QuestAutoAccept.lua")
ZGV.db.profile.autoaccept, ZGV.db.profile.autoturnin = true, true
local function autoStep(questid, name)
	local g = goal({action = "accept", questid = questid, quest = name})
	ZGV.CurrentStep = step({g, goal({action = "turnin", questid = questid, quest = name})})
	IP.quests[questid] = {status = "A", reasons = 0, generation = IP.generation, at = now}
end
autoStep(10259, title)
local notices = #prints
ZGV:QUEST_DETAIL()
ZGV:QUEST_GREETING()
ZGV:QUEST_PROGRESS()
ZGV:QUEST_COMPLETE()
check(accepted == 0 and selected == 0 and completed == 0 and rewarded == 0, "a progression transition quest stays manual")
check(#prints == notices + 1 and prints[#prints]:find("decides your progression", 1, true), "the player is told once")
for _, id in ipairs({8743, 108743, 108744}) do check(IP:IsManualQuest(id), "quest " .. id .. " stays manual") end
title = "Ordinary Quest"
autoStep(9500, title)
ZGV:QUEST_DETAIL()
ZGV:QUEST_COMPLETE()
check(accepted == 1 and rewarded == 1, "ordinary quests keep the automation")

------------------------------------------------------------------------
-- Gear Finder, vendors, crafting and best-in-slot lists
------------------------------------------------------------------------

local gearEnv = setmetatable({}, {__index = _G})
gearEnv.ZGV, gearEnv.ZygorGuidesViewer = ZGV, ZGV
ZGV.ItemScore = {playerlevel = 60, playerclass = "MAGE"}
gearEnv.ItemScore = ZGV.ItemScore
gearEnv.GearFinder = {CurrentExpansion = 2, FUTURE_DUNGEONS_LIMIT = 5, PAST_DUNGEONS_LIMIT = 10}
ZGV.ItemScore.GearFinder = gearEnv.GearFinder
gearEnv.IsQuestFlaggedCompleted = function() return true end
run("Dungeons.lua", gearEnv)
run("Data-WOTLK/Dungeons.lua", gearEnv)
local finder = "Item-GearFinder.lua"
local helpers = section(finder, "local function GF_IsPhaseActive", "local function GF_GetFactionVendor")
	.. section(finder, "local function GF_NormalizeProfessionName", "local function GF_CompactMapKeys")
	.. section(finder, "local function GF_IsValidVendorSource", "local function GF_HasAnySourceEnabled")
	.. section(finder, "local function GF_GetDungeonLeafName", "local function GF_ResolveFooterImage")
	.. section(finder, "local function GF_GetDungeonData", "GearFinder.UpgradeQueue = {")
	.. "\nreturn {phase=GF_IsPhaseActive, vendor=GF_IsValidVendorSource, craft=GF_IsValidCraftedItem}"
local gear = compile(helpers, finder, gearEnv)()
local dungeons = ZGV.Dungeons.hardcoded_dungeons
ZGV.db.profile.gear_1, ZGV.db.profile.gear_2, ZGV.db.profile.gear_3, ZGV.db.profile.gear_4, ZGV.db.profile.gear_14 = true, true, true, true, true
ZGV.db.profile.gear_5, ZGV.db.profile.gear_6 = true, true

-- Every Gear Finder instance resolves to a server map except outdoor bosses. The Gear Finder passes
-- the objects Dungeons.lua builds from the hardcoded data, not the hardcoded rows.
for ident in pairs(dungeons) do
	local dungeon = ZGV.Dungeons[ident]
	check(dungeon and dungeon.instancename == nil, "Dungeons.lua objects carry no instance name")
	local map, difficulty = IP:DungeonMap(ident, dungeon)
	if dungeon.name == "World Bosses" or ident == "quests" then
		check(map == nil, "outdoor sources have no instance map")
	else
		check(map, "Gear Finder dungeon " .. tostring(ident) .. " has a server map")
		check(difficulty >= 0 and difficulty <= 3, "difficulty slot is valid")
	end
end
check(select(2, IP:DungeonMap(2159, ZGV.Dungeons[2159])) == 2 and select(2, IP:DungeonMap(3456, ZGV.Dungeons[3456])) == 2,
	"40-player Onyxia and Naxxramas use the 10-player heroic slot")
check(select(2, IP:DungeonMap("533_10", ZGV.Dungeons["533_10"])) == 0 and select(2, IP:DungeonMap("631_25H", ZGV.Dungeons["631_25H"])) == 3,
	"Wrath raid sizes map to their difficulty slots")
check(select(2, IP:DungeonMap("9111H", ZGV.Dungeons["9111H"])) == 1, "heroic idents use the heroic slot")
check(IP:DungeonMap(2557, ZGV.Dungeons[2557]) == 429 and IP:DungeonMap(796, ZGV.Dungeons[796]) == 189
	and IP:DungeonMap(2102, ZGV.Dungeons[2102]) == 349 and IP:DungeonMap(2018, ZGV.Dungeons[2018]) == 329,
	"wing names map to their instance")

sendState({stored = 7, effective = 7, era = 0, next = 8})
answerAccess({"409:A---", "309:G---", "532:----", "533:--A-"})
ZGV.ItemScore.playerlevel = 60
local valid, future, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon(2717)
check(valid, "Molten Core loot is current at tier 7: " .. tostring(comment))
valid, future, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon(9120)
check(not valid and future and comment:find("tier 8", 1, true) and comment:find("next tier", 1, true),
	"Karazhan is the next tier's source: " .. tostring(comment))
valid, future, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon(1977)
check(not valid and future and comment:find("progression", 1, true), "a progression-gated raid is a future source")
valid, future = gearEnv.GearFinder:IsValidDungeon(3456)
check(valid, "40-player Naxxramas is checked in its own difficulty slot")
answerAccess({"429:A---", "189:R---"})
ZGV.ItemScore.playerlevel = 31
valid, _, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon(2557)
check(valid, "a Dire Maul wing is a current source: " .. tostring(comment))
ZGV.ItemScore.playerlevel = 25
valid, future, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon(796)
check(not valid and future and not comment:find("not verified", 1, true), "a Scarlet Monastery wing waits for its access requirement: " .. tostring(comment))
ZGV.ItemScore.playerlevel = 60
valid, future, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon(0)
check(not valid and not future, "an unverified outdoor source is neither current nor future: " .. tostring(comment))
sendState({stored = 13, effective = 13, era = 2, next = 14})
answerAccess({"533:A---", "603:A---"})
ZGV.ItemScore.playerlevel = 80
valid, future, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon("603_10")
check(not valid and future and comment:find("tier 14", 1, true), "Ulduar opens at tier 14: " .. tostring(comment))
valid = gearEnv.GearFinder:IsValidDungeon("533_10")
check(valid, "Wrath Naxxramas is current at tier 13")
valid, future, _, _, _, _, comment = gearEnv.GearFinder:IsValidDungeon("724_10")
check(not valid and future and comment:find("later tier", 1, true), "the Ruby Sanctum is a long-term source: " .. tostring(comment))
check(gear.phase("wotlk1") and not gear.phase("wotlk2"), "Gear Finder phases follow the earned tier")
IP.access = nil
valid, future = gearEnv.GearFinder:IsValidDungeon("533_10")
check(not valid and not future, "unknown access is not a current source")
answerAccess({"533:D---"})
valid, future = gearEnv.GearFinder:IsValidDungeon("533_10")
check(not valid and not future, "a disabled instance is not a source")

local emblem = {key = "emblem_heroism", expansionLevel = 2, items = {}}
sendState({stored = 8, effective = 8, era = 1, next = 9})
answerAccess({})
ZGV.ItemScore.playerlevel = 70
local ok, why = gear.vendor(emblem)
check(not ok and why:find("tier 13", 1, true), "Wrath currency vendors wait for tier 13")
sendState({stored = 13, effective = 13, era = 2, next = 14})
check(gear.vendor(emblem), "Wrath currency vendors open at tier 13")

local tbcSource = {expansionLevel = 1, minLevel = 1}
sendState({stored = 7, effective = 7, era = 0, next = 8})
check(not gear.craft(tbcSource, {recipeSource = "Trainer", minLevel = 1}), "TBC crafts wait for tier 8")
sendState({stored = 8, effective = 8, era = 1, next = 9})
check(gear.craft(tbcSource, {recipeSource = "Trainer", minLevel = 1}), "trainer recipes of an earned era are reachable")
ok, why = gear.craft(tbcSource, {recipeSource = "Raid Drop", recipeSpellID = 12345, minLevel = 1})
check(not ok and why:find("not verified", 1, true), "an unverified recipe source is not reachable")
known[12345] = true
check(gear.craft(tbcSource, {recipeSource = "Raid Drop", recipeSpellID = 12345, minLevel = 1}), "a known recipe is reachable")
known[12345] = nil

local scoreEnv = setmetatable({ItemScore = ZGV.ItemScore, ZGV = ZGV}, {__index = _G})
compile(section("Item-ItemScore.lua", "local BIS_CATEGORY_ORDER = {", "function ItemScore:IsEquippedBIS"), "Item-ItemScore.lua", scoreEnv)()
function ZGV.ItemScore:GetResolvedBuild() return 1 end
ZGV.ItemScore.BISData = {MAGE = {[1] = {pre_raid = {[1] = {100}}, t7 = {[1] = {101}}, t8 = {[1] = {102}}, rs = {[1] = {105}}}}}
sendState({stored = 12, effective = 12, era = 1, next = 13})
check(ZGV.ItemScore:GetBISAnnotation(101, 1, 1, "MAGE") == nil, "Wrath lists stay silent before tier 13")
sendState({stored = 13, effective = 13, era = 2, next = 14})
local note = ZGV.ItemScore:GetBISAnnotation(101, 1, 1, "MAGE")
check(note and note.category == "t7" and not note.future, "T7 is current at tier 13")
note = ZGV.ItemScore:GetBISAnnotation(102, 1, 1, "MAGE")
check(note and note.future, "T8 is a future list at tier 13")
sendState({stored = 17, effective = 17, era = 2, next = 18})
check(not ZGV.ItemScore:GetBISAnnotation(105, 1, 1, "MAGE").future, "the Ruby Sanctum list is current at tier 17")
IP.state = nil
check(ZGV.ItemScore:GetBISAnnotation(100, 1, 1, "MAGE") == nil, "an unknown state shows no list")

------------------------------------------------------------------------
-- Gear Advisor talent state
------------------------------------------------------------------------

-- EraTalents' real initial state, protocol parser and tree helpers with its generated Mage trees.
local function readEra(path)
	local file = assert(io.open(ERA .. "/" .. path, "rb"))
	local text = file:read("*a")
	file:close()
	return text
end
EraTalents = nil
for _, path in ipairs({"Locales.lua", "Comms.lua", "TalentUI.lua", "data/generated/MageVanilla.lua",
	"data/generated/DruidVanilla.lua", "data/generated/DruidTBC.lua"}) do
	compile(readEra(path), path)()
end
local ET = EraTalents
local eraMain = readEra("EraTalents.lua")
compile("local ET = EraTalents\n" .. assert(eraMain:match('ET%.PREFIX = "%u+"')) .. "\n"
	.. assert(eraMain:match("ET%.state = %b{}")), "EraTalents.lua")()
local fire
for _, node in ipairs(EraTalentsData[0][8].talents) do
	if node.tab == 2 and node.maxRank >= 5 then fire = node break end
end
check(fire and EraTalentsData[0][8].className == "MAGE", "the generated Vanilla Mage tree has a five-rank Fire talent")

local nativeSpent, nativeFree, nativeTab, nativeHideRank = 0, 0, 1, 0
function GetNumTalentTabs() return 3 end
function GetTalentTabInfo(tab) return "Tree", "", tab == nativeTab and nativeSpent or 0 end
function UnitCharacterPoints() return nativeFree end
function GetActiveTalentGroup() return 1 end
compile(section("Item-ItemScore.lua", "ItemScore.LevelingBuildFallback = {", "function ItemScore:GetGearRoleBuild"),
	"Item-ItemScore.lua", scoreEnv)()
run("Data-WOTLK/Item-Statweights.lua", scoreEnv)
-- Wrath's return contract: tier is third, allocated rank is fifth. Talent identity comes from links.
function GetNumTalents() return 30 end
function GetTalentLink(_, index) return "|Htalent:" .. (index == 7 and 794 or index == 11 and 801 or (1000 + index)) .. ":0|h" end
function GetTalentInfo(_, index, inspect, pet, group)
	check(not inspect and not pet and group == 1, "native role reads the active player's talent group")
	return "Localized talent", "icon", 2, 3, index == 7 and nativeHideRank or (index == 11 and 2 or 0), 3
end
function ZGV.ItemScore:IsKnownWeightClass(token) return self.rules[token] ~= nil end
local function talentState() return ZGV.ItemScore:GetTalentState("MAGE", 15) end

-- Native trees stay empty for an era character; without EraTalents' data that is final, not loading.
sendState({stored = 0, effective = 0, era = 0, next = 1})
local gearState = talentState()
check(gearState.preTalentState and not gearState.uncertain, "empty native trees before Wrath do not retry the spec detection")
ET.ParseSync(ET.state, "SYNC 0 1 3 " .. fire.id .. ":5")
gearState = talentState()
check(gearState.totalPoints == 5 and gearState.bestTree == fire.tab and gearState.availablePoints == 3, "historical points select the gear tree")
check(not gearState.uncertain and not gearState.preTalentState, "a historical build is certain")
check(ZGV.ItemScore:DetectActiveBuild("MAGE", 15) == fire.tab, "the Gear Advisor uses the historical primary tree")
-- Wrath trees and an unreported realm keep the native talent API and its retry while it loads.
ET.ParseSync(ET.state, "SYNC 2 0 0")
sendState({stored = 13, effective = 13, era = 2, next = 14})
check(talentState().uncertain, "empty native Wrath trees are still loading")
sendState({stored = 0, effective = 0, era = 0, next = 1})
IP.state = nil
check(talentState().uncertain, "an unreported realm keeps the native retry")
nativeSpent = 7
check(talentState().totalPoints == 7 and not talentState().uncertain, "native points keep the native build")
nativeSpent = 0

-- Druid rules split Feral into two gear profiles; the third talent tab is Restoration, profile four.
local druidBuilds = ZGV.ItemScore.rules.DRUID
check(druidBuilds[2].name == "Feral DPS" and druidBuilds[3].name == "Feral TANK"
	and druidBuilds[4].name == "Restoration", "Druid gear profiles have a separate tank entry")
local druidTank, druidCat
for era = 0, 1 do
	local nodes = {}
	for _, node in ipairs(EraTalentsData[era][11].talents) do nodes[node.name] = node end
	local hide, ferocity, aggression, resto = nodes["Thick Hide"], nodes["Ferocity"], nodes["Feral Aggression"], nodes["Improved Mark of the Wild"]
	check(hide and hide.tab == 2 and hide.maxRank >= 2 and ferocity.maxRank == 5 and aggression.maxRank == 5
		and resto.tab == 3, "generated Druid talents keep canonical English names next to localized metadata")
	druidTank = "SYNC " .. era .. " 1 3 " .. ferocity.id .. ":5," .. hide.id .. ":2"
	druidCat = "SYNC " .. era .. " 1 3 " .. ferocity.id .. ":5," .. aggression.id .. ":2"
	ET.ParseSync(ET.state, druidTank)
	check(ZGV.ItemScore:DetectActiveBuild("DRUID", 60) == 3, "historical Thick Hide selects the tank heuristic")
	ET.ParseSync(ET.state, druidCat)
	check(ZGV.ItemScore:DetectActiveBuild("DRUID", 60) == 2, "historical Feral without Thick Hide selects DPS")
	ET.ParseSync(ET.state, "SYNC " .. era .. " 1 3 " .. resto.id .. ":2")
	check(ZGV.ItemScore:DetectActiveBuild("DRUID", 60) == 4, "historical Restoration selects healing weights")
end
ET.ParseSync(ET.state, "SYNC 2 0 0")
nativeSpent, nativeTab, nativeHideRank = 7, 2, 0
check(ZGV.ItemScore:DetectActiveBuild("DRUID", 80) == 2, "a tier or Primal Fury rank is not Thick Hide")
nativeHideRank = 2
check(ZGV.ItemScore:DetectActiveBuild("DRUID", 80) == 3, "native Thick Hide is found by talent identity and fifth rank return")
nativeTab = 3
check(ZGV.ItemScore:DetectActiveBuild("DRUID", 80) == 4, "native Restoration selects healing weights")
nativeSpent = 0
GetPrimaryTalentTree = function() return 3 end
check(ZGV.ItemScore:DetectActiveBuild("DRUID", 80) == 4, "native primary-tree fallback keeps Restoration healing weights")
GetPrimaryTalentTree, nativeSpent = nil, 7
local nativeLink = GetTalentLink
GetTalentLink, nativeTab = nil, 2
check(ZGV.ItemScore:DetectActiveBuild("DRUID", 80) == 2, "a missing native talent link keeps a conservative Feral baseline")
GetTalentLink, nativeSpent, nativeTab = nativeLink, 0, 1

-- Historical points arrive without native talent events; a changed SYNC rescores gear once.
local refreshes = 0
ZGV.ItemScore.Initialised, ZGV.ItemScore.playerclass = true, "MAGE"
local delayedRefresh = ZGV.ItemScore.DelayedRefreshUserData
function ZGV.ItemScore:DelayedRefreshUserData() refreshes = refreshes + 1 end
IP:WatchEraTalents()
ET.OnAddonMsg(ET.PREFIX, "SYNC 0 1 3 " .. fire.id .. ":5")
check(refreshes == 1, "historical points rescore gear")
ET.OnAddonMsg(ET.PREFIX, "SYNC 0 1 3 " .. fire.id .. ":5")
check(refreshes == 1, "an unchanged SYNC does not restart the Gear Finder")
ET.OnAddonMsg(ET.PREFIX, "SYNC 0 1 2 " .. fire.id .. ":6")
check(refreshes == 2, "spending a historical point rescores gear")
ZGV.ItemScore.playerclass = "DRUID"
ET.OnAddonMsg(ET.PREFIX, druidTank)
local beforeRoleChange = refreshes
ET.OnAddonMsg(ET.PREFIX, druidCat)
check(refreshes == beforeRoleChange + 1, "a historical role change rescores even with identical tab totals and free points")
ET.OnAddonMsg(ET.PREFIX, druidCat)
check(refreshes == beforeRoleChange + 1, "an unchanged historical role does not rescore")
ZGV.ItemScore.playerclass = "MAGE"
ZGV.ItemScore.DelayedRefreshUserData, ZGV.ItemScore.Initialised = delayedRefresh, nil
ET.ParseSync(ET.state, "SYNC 0 0 0")

------------------------------------------------------------------------
-- Talent Advisor
------------------------------------------------------------------------

local learned = {}
local function blizzardLearn(...) learned[#learned + 1] = {...} end
LearnTalent = blizzardLearn
function GetUnspentTalentPoints() return 1 end
function GetTalentTabInfo() return "Fire", "", 10 end
function GetTalentInfo() return "Talent", "", 1, 1, 0, 5, false, true end
function GetTalentPrereqs() return nil end
PLAYER_TALENTS_PER_TIER = 5
function TalentFrame_LoadUI() end
function ResetGroupPreviewTalentPoints() end
local opened = 0
function PlayerTalentFrame_Open() opened = opened + 1 end
local learnScript = function() end
PlayerTalentFrame = {IsVisible = function() return false end}
PlayerTalentFrameLearnButton = {
	GetScript = function() return learnScript end,
	SetScript = function(_, _, script) learnScript = script end,
}
ZygorTalentAdvisor_L = ZygorGuidesViewer_L
GameTooltip = {SetTalent = function() end, AddLine = function() end}
ZygorTalentAdvisorPopout = {Hide = function() end, IsShown = function() return false end}
function ZygorTalentAdvisorPopout_Update() end
function ZygorTalentAdvisorPopout_Popout() opened = opened + 1 end
run("ZygorTalentAdvisor/ZygorTalentAdvisor.lua")
local ZTA = ZygorTalentAdvisor
ZTA.db = {profile = {popup = 3}, char = {}}
ZTA.Log = {Add = function() end}
ZTA.currentBuild.player = {}
ZTA.suggestion.player = {{tab = 1, talent = 1}}
-- Build loading, build counting and frame painting are outside this fixture.
function ZTA:ReloadBuilds() end
function ZTA:PlayTalented() end
function ZTA:CountBuildTalents() return {}, {} end
function ZTA:GetTalentsSpent() return {} end
ZTA.currentBuildTitle.player = "Fixture build"
StaticPopupDialogs = {ZYGORTALENTADVISOR_WARNING = {}}
function StaticPopup_Show() return nil end
run("TalentAdvisorCompat.lua")
check(LearnTalent == blizzardLearn, "loading the advisor does not wrap LearnTalent")

sendState({stored = 7, effective = 7, era = 0, next = 8})
ZGV:TalentAdvisorProgressionChanged()
check(not ZTA:IsAdvisorEnabled(), "the advisor is inactive before the Wrath era")
check(LearnTalent == blizzardLearn, "LearnTalent stays native before the Wrath era")
ZTA:OnNewTalents(false)
ZTA.db.profile.popup = 2
ZTA:OnNewTalents(false)
ZTA.db.profile.popup = 3
ZTA:LearnSuggestedTalents(false)
ZTA:CHARACTER_POINTS_CHANGED(nil, 1)
check(#learned == 0 and opened == 0, "no talent is learned or suggested for an era character")
check(learnScript ~= ZygorTalentAdvisor_PlayerTalentFrameLearnButton_OnClick, "the learn button stays native")

sendState({stored = 13, effective = 13, era = 2, next = 14})
EraTalents = {state = {isEraChar = true}}
ZGV:TalentAdvisorProgressionChanged()
check(not ZTA:IsAdvisorEnabled() and LearnTalent == blizzardLearn, "EraTalents' historical trees keep the advisor out")
EraTalents.state.isEraChar = false
ZGV:TalentAdvisorProgressionChanged()
check(ZTA:IsAdvisorEnabled() and LearnTalent ~= blizzardLearn, "Wrath characters get the advisor")
check(learnScript == ZygorTalentAdvisor_PlayerTalentFrameLearnButton_OnClick, "the advisor takes the learn button")
LearnTalent(1, 1, false, 2)
check(#learned == 1 and learned[1][4] == 2, "the wrapper passes the talent group to the client")
ZTA.suggestion.player = {{tab = 2, talent = 3}}
EraTalents.state.isEraChar = true
LearnTalent(1, 1, false, 1)
check(#learned == 2 and learned[2][1] == 1, "an era change before the refresh leaves the client's call unchanged")
EraTalents.state.isEraChar = false
ZTA.suggestion.player = {{tab = 1, talent = 1}}
IP.state = nil
ZGV:TalentAdvisorProgressionChanged()
check(not ZTA:IsAdvisorEnabled() and LearnTalent == blizzardLearn, "an unknown era restores the native LearnTalent")
check(learnScript ~= ZygorTalentAdvisor_PlayerTalentFrameLearnButton_OnClick, "an unknown era restores the learn button")
sendState({stored = 0, effective = 0, era = 0, next = 1, account = "B"})
ZGV:TalentAdvisorProgressionChanged()
check(ZTA:IsAdvisorEnabled(), "accounts outside the gates keep the advisor")
EraTalents = nil
sendState({ip = 0, stored = 0, effective = 0, era = 255, next = 0, strict = 0})
ZGV:TalentAdvisorProgressionChanged()
check(ZTA:IsAdvisorEnabled(), "realms without Individual Progression keep the advisor")

------------------------------------------------------------------------
-- Options and refresh
------------------------------------------------------------------------

local refreshed = #sent
SlashCmdList.ZYGORIP("refresh")
check(message(refreshed + 1) == "GET~IP_STATE~" .. IP.watchToken .. "~WATCH", "the refresh command asks the server again")
local options = read("Options.lua")
check(options:find('ip_mode = "auto"', 1, true), "the mode defaults to automatic")
check(options:find("ZGV.IP:StatusText()", 1, true), "the progress options show the status")

print("Zygor Individual Progression fixture passed")
