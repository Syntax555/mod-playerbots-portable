// Production bridge handlers are inserted by TestMultiBotNaturalProgression.py.
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <deque>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using ChatMsg = int;
constexpr char kFieldSeparator = '~';
constexpr uint32 MAX_GLYPH_SLOT_INDEX = 6, PLAYERBOT_SECURITY_ALLOW_ALL = 0;
constexpr uint32 CLASS_HUNTER = 3, UNIT_FIELD_LEVEL = 1, POWER_HAPPINESS = 4;
constexpr uint32 PET_SAVE_AS_CURRENT = 0, PET_SAVE_NOT_IN_SLOT = 3, PETSPELL_REMOVED = 2;
using Powers = uint32;
uint32 effects = 0;
struct Config { bool naturalProgression = true; } sPlayerbotAIConfig;
uint32 FixtureConfig(std::string const& key) { return key == "TwoRoundsGearInit" ? 0 : 1; }
#define PLAYERBOT_CONFIG(newName, oldName) FixtureConfig(#newName)

struct ObjectGuid { uint64 value = 7; uint64 GetCounter() const { return value; } };
struct SpellInfo { bool IsPassive() const { return false; } };
struct SpellManager { SpellInfo spell; SpellInfo const* GetSpellInfo(uint32) const { return &spell; } };
SpellManager spells;
auto* sSpellMgr = &spells;
struct PetSpell { uint32 state = 0; };
using PetSpellMap = std::map<uint32, PetSpell>;
struct Map { void AddToMap(void*) { ++effects; } };
struct Pet
{
    Map map;
    PetSpellMap m_spells{{1, {}}};
    void SetUInt32Value(uint32, uint32) { ++effects; }
    Map* GetMap() { return &map; }
    void* ToCreature() { return this; }
    void InitTalentForLevel() { ++effects; }
    void SavePetToDB(uint32) { ++effects; }
    void InitStatsForLevel(uint32) { ++effects; }
    void SetLevel(uint32) { ++effects; }
    void SetPower(uint32, uint32) { ++effects; }
    uint32 GetMaxPower(Powers) const { return 100; }
    void SetHealth(uint32) { ++effects; }
    uint32 GetMaxHealth() const { return 100; }
    void ToggleAutocast(SpellInfo const*, bool) { ++effects; }
};
struct PetStable
{
    std::optional<int> CurrentPet{1};
    std::vector<int> UnslottedPets{2};
    int const* GetUnslottedHunterPet() const { return UnslottedPets.size() == 1 ? &UnslottedPets[0] : nullptr; }
};
struct CreatureTemplate { uint32 Entry = 77; std::string Name = "Wolf"; };
struct ObjectManager
{
    CreatureTemplate creature;
    CreatureTemplate const* GetCreatureTemplate(uint32 entry) const { return entry == creature.Entry ? &creature : nullptr; }
} objectManager;
auto* sObjectMgr = &objectManager;
struct ItemTemplate { uint32 AllowableClass = 4; };
struct GlyphPropertiesEntry { uint32 SpellId, Id, TypeFlags; };
struct GlyphSlotEntry { uint32 TypeFlags = 0; };
struct GlyphPropertiesStore
{
    std::array<GlyphPropertiesEntry, 6> entries{{{90, 12, 0}, {91, 13, 1}, {92, 14, 0},
                                               {93, 15, 1}, {94, 16, 0}, {95, 17, 1}}};
    GlyphPropertiesEntry const* LookupEntry(uint32 id) const { return &entries[id >= 12 ? id - 12 : 0]; }
} sGlyphPropertiesStore;
struct GlyphSlotStore
{
    std::array<GlyphSlotEntry, 2> entries{{{0}, {1}}};
    GlyphSlotEntry const* LookupEntry(uint32 slot) const { return &entries[(slot - 1) % 2]; }
} sGlyphSlotStore;
struct ContextValue { void Set(bool) { ++effects; } };
struct Context
{
    ContextValue value;
    template<class T> ContextValue* GetValue(char const*) { return &value; }
};
struct Security { bool CheckLevelFor(uint32, bool, void*) const { return true; } };
struct PlayerbotAI
{
    bool alt = false;
    Context context;
    Security security;
    bool IsAltBot() const { return alt; }
    Context* GetAiObjectContext() { return &context; }
    Security* GetSecurity() { return &security; }
    void ResetStrategies() { ++effects; }
};
struct Player
{
    PlayerbotAI ai;
    PetStable stable;
    Pet pet;
    std::string name = "Hunterbot";
    std::vector<uint64> worn = std::vector<uint64>(17, 1);
    uint32 repairs = 0;
    uint32 GetLevel() const { return 80; }
    uint32 getClass() const { return CLASS_HUNTER; }
    uint32 getClassMask() const { return 4; }
    void* GetSession() { return this; }
    bool IsInWorld() const { return true; }
    std::string const& GetName() const { return name; }
    ObjectGuid GetGUID() const { return {}; }
    uint32 GetMapId() const { return 1; }
    uint32 GetGlyphSlot(uint8 slot) const { return slot + 1; }
    uint32 GetGlyph(uint8) const { return 12; }
    void RemoveAurasDueToSpell(uint32) { ++effects; }
    void CastSpell(Player*, uint32, bool) { ++effects; }
    void SetGlyph(uint8, uint32, bool) { ++effects; }
    void DurabilityRepairAll(bool cost, float discount, bool guild)
    {
        assert(!cost && discount == 1.0f && !guild);
        ++repairs;
        ++effects;
    }
    void SendTalentsInfoData(bool) { ++effects; }
    PetStable* GetPetStable() { return &stable; }
    void RemovePet(Pet*, uint32) { ++effects; }
    Pet* CreateTamedPetFrom(uint32 entry, uint32) { assert(entry == 77); ++effects; return &pet; }
    void SetMinion(Pet*, bool) { ++effects; }
    void PetSpellInitialize() { ++effects; }
};
Player* controlled = nullptr;
Player* FindBotByName(Player*, std::string const&) { return controlled; }
PlayerbotAI* GetBotAI(Player* bot) { return &bot->ai; }
std::string Trim(std::string const& value) { return value; }
std::string UrlEncodeField(std::string const& value) { return value; }
bool ConsumeGlyphEquipRateLimit(Player*) { return true; }
bool RegisterGlyphEquipToken(Player*, std::string const&) { return true; }
std::string glyphReply;
void SendAddonPacket(Player*, ChatMsg, std::string const& opcode, std::string const& payload)
{
    assert(opcode == "GLYPH_EQUIP_RESULT");
    glyphReply = payload;
}

@STRUCTS@

bool ResolveBridgeGlyph(uint32 itemId, BridgeGlyphInfo& out)
{
    static ItemTemplate proto;
    assert(itemId >= 100 && itemId < 106);
    out = {&sGlyphPropertiesStore.entries[itemId - 100], &proto};
    return true;
}
struct PlayerbotFactory
{
    explicit PlayerbotFactory(Player*, uint32) { ++effects; }
    void InitAttunementQuests() { ++effects; }
    void InitBags(bool) { ++effects; }
    void InitAmmo() { ++effects; }
    void InitFood() { ++effects; }
    void InitReagents() { ++effects; }
    void InitConsumables() { ++effects; }
    void InitPotions() { ++effects; }
    void InitTalentsTree(bool) { ++effects; }
    void InitPet() { ++effects; }
    void InitPetTalents() { ++effects; }
    void InitSkills() { ++effects; }
    void InitClassSpells() { ++effects; }
    void InitAvailableSpells() { ++effects; }
    void InitReputation() { ++effects; }
    void InitSpecialSpells() { ++effects; }
    void InitMounts() { ++effects; }
    void InitGlyphs(bool) { ++effects; }
    void InitKeyring() { ++effects; }
    void ApplyEnchantAndGemsNew() { ++effects; }
    static void DestroyEquippedGear(Player* bot) { ++effects; bot->worn[0] = 0; }
    static void AutoGear(Player* bot, uint32, uint32, bool, bool) { ++effects; bot->worn[0] = 2; }
};
std::vector<uint64> AutogearWornSnapshot(Player* bot) { return bot->worn; }
bool ResolveAutogearTarget(Player*, std::string const&, Player*& bot, uint32& quality, uint32& ilvl, std::string&)
{
    bot = controlled;
    quality = 1;
    ilvl = 1;
    return true;
}
bool ResolveAutogearOptions(Player*, std::string const&, uint32, uint32, uint32, uint32& quality, uint32& ilvl, std::string&)
{
    quality = 1;
    ilvl = 1;
    return true;
}
bool ConsumeAutogearBotCooldown(uint64) { return true; }
std::string autogearReply;
bool autogearOk = false;
void SendAutogearReply(Player*, ChatMsg, char const*, std::string const&, bool ok, std::string const& reason,
                       uint32 = 0, uint32 = 0)
{
    autogearOk = ok;
    autogearReply = reason;
}


std::string ToUpper(std::string const& value) { return value; }
bool IsValidRequestToken(std::string const&) { return true; }
bool ConsumeGroupOrderRateLimit(Player*) { return true; }
bool RegisterGroupOrderToken(Player*, std::string const&) { return true; }
bool ResolveHunterPetControlBot(Player*, std::string const&, Player*& bot, PlayerbotAI*& ai, std::string&)
{
    bot = controlled;
    ai = &bot->ai;
    return true;
}
std::string petManageReply;
void SendHunterPetManageAck(Player*, ChatMsg, std::string const&, std::string const&, std::string const&,
                           uint32, std::string const&, std::string const& reason)
{
    petManageReply = reason;
}
bool ApplyHunterPetManage(Player*, PlayerbotAI*, std::string const& action, std::string const&,
                         uint32&, std::string&, std::string& reason)
{
    assert(action == "RENAME" || action == "CALL" || action == "DISMISS" || action == "ABANDON");
    ++effects;
    reason = "OK";
    return true;
}
void RestoreHunterPetAutoCallStrategy(Player*, PlayerbotAI*) { ++effects; }

@FUNCTIONS@

int main()
{
    for (bool natural : {true, false})
    {
        sPlayerbotAIConfig.naturalProgression = natural;
        Player requester, bot;
        controlled = &bot;
        effects = 0;
        RunGlyphEquipCommand(&requester, 0, bot.name, "glyph", {100, 101, 102, 103, 104, 105});
        assert(glyphReply.find(natural ? "~ERR~NATURAL_PROGRESSION~" : "~OK~OK~") != std::string::npos);
        assert(natural ? effects == 0 : effects > 0);

        for (bool alt : {false, true})
        {
            bot.ai.alt = alt;
            effects = 0;
            bot.repairs = 0;
            std::string reason;
            assert(ApplyMaintenanceToBot(&bot, &bot.ai, reason) == !natural);
            assert(reason == (natural ? "NATURAL_PROGRESSION" : "APPLIED"));
            assert(natural ? effects == 0 : effects > 0);
            assert(bot.repairs == (natural ? 0 : 1));
        }

        for (bool reset : {false, true})
        {
            effects = 0;
            bot.worn.assign(17, 1);
            AutogearRequesterState state;
            state.plan.token = "gear";
            state.plan.botName = bot.name;
            state.plan.botGuid = bot.GetGUID().GetCounter();
            state.plan.botMap = state.plan.requesterMap = 1;
            state.plan.quality = state.plan.qualityCap = state.plan.ilvl = state.plan.ilvlCap = 1;
            state.plan.worn = bot.worn;
            state.plan.reset = reset;
            state.plan.created = std::chrono::steady_clock::now();
            ApplyPreparedAutogear(&requester, 0, state, "gear");
            assert(autogearOk == !natural);
            assert(autogearReply == (natural ? "NATURAL_PROGRESSION" : "COMPLETED"));
            assert(natural ? effects == 0 : effects > 0);
            assert(bot.worn[0] == (natural ? 1 : 2));
            uint32 const beforeReplay = effects;
            ApplyPreparedAutogear(&requester, 0, state, "gear");
            assert(effects == beforeReplay);
        }

        for (std::string const action : {"RENAME", "CALL", "DISMISS"})
        {
            effects = 0;
            RunHunterPetManageCommand(&requester, 0, bot.name, "pet", action,
                                      action == "RENAME" ? "Wolf" : "");
            assert(petManageReply == (natural ? "NATURAL_PROGRESSION" : "OK"));
            assert(natural ? effects == 0 : effects > 0);
        }

        effects = 0;
        RunHunterPetManageCommand(&requester, 0, bot.name, "abandon", "ABANDON", "");
        assert(petManageReply == "OK" && effects > 0);

        effects = 0;
        uint32 entry = 0;
        std::string name, reason;
        assert(CreateManagedHunterPet(&bot, 77, entry, name, reason) == !natural);
        assert(reason == (natural ? "NATURAL_PROGRESSION" : "OK"));
        assert(natural ? effects == 0 : effects > 0);
        assert(natural ? entry == 0 && name.empty() : entry == 77 && name == "Wolf");
        if (natural)
            assert(bot.stable.CurrentPet == 1 && bot.stable.UnslottedPets == std::vector<int>{2});
    }
    std::cout << "Compiled MultiBot glyph, AutoGear, maintenance and hunter-pet grant/rename/call/dismiss gates passed\n";
}
