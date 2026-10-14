"""Check sparse MultiBot preset discovery against the native config lookup.

Production bridge and ConfigMgr functions decide fallback values and logging.
Fixtures supply configuration, environment overrides and log recording hooks;
no realm or talent purchase is started.
"""

from pathlib import Path
import argparse
import os
import subprocess
import tempfile

from FixtureSupport import function, prepared_core


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, help='prepared core source directory')
parser.add_argument('--bridge', type=Path, help='bridge source override')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
bridge_path = args.bridge or core / 'modules/mod-multibot-bridge/src/MultiBotBridge.cpp'
bridge = bridge_path.read_text()
config = (core / 'src/common/Configuration/Config.cpp').read_text()

fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
template<class T> using Optional = std::optional<T>;
enum class ConfigSeverity { Warn, Error, Fatal };
struct ConfigPolicy
{
    ConfigSeverity missingOptionSeverity = ConfigSeverity::Warn;
    ConfigSeverity criticalOptionSeverity = ConfigSeverity::Fatal;
};
uint32 missingLogs = 0;
uint32 environmentLogs = 0;
uint32 criticalLogs = 0;
template<class... Args>
void LogWithSeverity(ConfigSeverity severity, Args const&...)
{
    ++missingLogs;
    if (severity == ConfigSeverity::Fatal)
        ++criticalLogs;
}
template<class... Args> void RecordEnvironment(Args const&...) { ++environmentLogs; }
#define LOG_INFO(...) RecordEnvironment(__VA_ARGS__)

class ConfigMgr
{
public:
    std::map<std::string, std::string> _configOptions;
    std::set<std::string> _criticalConfigOptions;
    std::map<std::string, std::string> environment;
    std::string _filename = "configs/worldserver.conf";
    std::vector<std::string> _moduleConfigFiles = {"MultiBotBridge.conf", "playerbots.conf"};
    ConfigPolicy _policy;
    mutable uint32 addKeyCalls = 0;
    std::string GetEnvVarName(std::string const& name) const { return name; }
    Optional<std::string> GetEnvFromCache(std::string const& name, std::string const&) const
    {
        auto const found = environment.find(name);
        if (found != environment.end())
            return found->second;
        return {};
    }
    void AddKey(std::string const&, std::string const&, char const*, bool, bool) const { ++addKeyCalls; }
    template<class T> T GetValueDefault(std::string const& name, T const& def, bool showLogs = true) const;
    template<class T> T GetOption(std::string const& name, T const& def, bool showLogs = true) const;
};
ConfigMgr configMgr;
ConfigMgr* sConfigMgr = &configMgr;
struct Player
{
    uint8 classId = 8;
    uint32 level = 10;
    uint8 getClass() const { return classId; }
    uint32 GetLevel() const { return level; }
};
struct TalentSpecEntryData
{
    uint32 index = 0;
    std::string name;
    std::string build;
};
std::string BuildTalentLinkPointSummary(std::string const& link) { return link; }
bool BuildLevelAdjustedTalentSpecTabs(Player*, uint32, std::array<uint32, 3>&) { return false; }
std::string FormatTalentSpecPointSummary(std::array<uint32, 3> const&) { return ""; }

@PRODUCTION@

int main()
{
    Player player;
    configMgr._configOptions["AiPlayerbot.PremadeSpecName.8.0"] = " arcane pve \t";
    configMgr._configOptions["AiPlayerbot.PremadeSpecLink.8.0.80"] = " 230005-0-0 \n";
    configMgr._configOptions["AiPlayerbot.PremadeSpecName.8.2"] = "\t frost pve ";
    configMgr._configOptions["AiPlayerbot.PremadeSpecLink.8.2.60"] = "0-0-230005";
    configMgr._configOptions["AiPlayerbot.PremadeSpecName.8.1"] = "";
    configMgr._configOptions["AiPlayerbot.PremadeSpecName.8.30"] = " custom preset ";

    auto const entries = BuildTalentSpecEntries(&player);
    assert(entries.size() == 3);
    assert(entries[0].index == 0 && entries[0].name == "arcane pve");
    assert(entries[1].index == 2 && entries[1].name == "frost pve");
    assert(entries[2].index == 30 && entries[2].name == "custom preset");
    assert(GetPremadeSpecLink(8, 0, 10) == "230005-0-0");
    assert(GetPremadeSpecLink(8, 2, 10) == "0-0-230005");
    assert(GetPremadeSpecLink(8, 30, 10).empty());
    assert(BuildTalentSpecEntries(nullptr).empty());
    assert(missingLogs == 0 && criticalLogs == 0 && environmentLogs == 0);

    // Native environment precedence still applies to these quiet lookups.
    configMgr.environment["AiPlayerbot.PremadeSpecName.8.0"] = " environmental preset ";
    configMgr.environment["AiPlayerbot.PremadeSpecName.8.1"] = " environment-only preset ";
    auto const overridden = BuildTalentSpecEntries(&player);
    assert(overridden.size() == 4);
    assert(overridden[0].name == "environmental preset");
    assert(overridden[1].index == 1 && overridden[1].name == "environment-only preset");
    assert(missingLogs == 0 && environmentLogs == 0 && configMgr.addKeyCalls == 0);

    // Required and ordinary config reads retain their existing diagnostics.
    assert(configMgr.GetOption<std::string>("Unrelated.Missing", "default") == "default");
    assert(missingLogs == 1 && criticalLogs == 0);
    configMgr._criticalConfigOptions.insert("Unrelated.Required");
    assert(configMgr.GetOption<std::string>("Unrelated.Required", "required-default") == "required-default");
    assert(missingLogs == 2 && criticalLogs == 1);
    configMgr.environment["Unrelated.Environment"] = "override";
    assert(configMgr.GetOption<std::string>("Unrelated.Environment", "default") == "override");
    assert(environmentLogs == 1 && configMgr.addKeyCalls == 1);
    std::cout << "Sparse preset discovery and native config diagnostics passed\n";
}
'''

production = '\n\n'.join([
    'template<>\n' + function(config, 'std::string ConfigMgr::GetValueDefault<std::string>'),
    'template<class T>\n' + function(config, 'T ConfigMgr::GetOption('),
    function(bridge, 'std::string Trim('),
    function(bridge, 'std::string GetPremadeSpecConfigString('),
    function(bridge, 'std::string GetPremadeSpecLink('),
    function(bridge, 'std::vector<TalentSpecEntryData> BuildTalentSpecEntries('),
])
compiler = os.environ.get('CXX', 'c++')
with tempfile.TemporaryDirectory(prefix='multibot-presets-') as directory:
    directory = Path(directory)
    for name, body, expect_success in [
        ('production', production, True),
        ('verbose-optional-lookup', production.replace('GetOption<std::string>(key, "", false)',
                                                      'GetOption<std::string>(key, "")'), False),
    ]:
        if not expect_success and body == production:
            raise AssertionError('Expected optional-lookup mutation was not applied')
        source = directory / f'{name}.cpp'
        executable = directory / (name + ('.exe' if os.name == 'nt' else ''))
        source.write_text(fixture.replace('@PRODUCTION@', body))
        subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        str(source), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], text=True, capture_output=True)
        if expect_success:
            if result.returncode:
                raise AssertionError(result.stderr or result.stdout)
            print(result.stdout.strip())
        elif result.returncode == 0:
            raise AssertionError('Verbose optional lookup mutation passed unexpectedly')
        else:
            print('Reverted optional lookup rejected by regression fixture')
