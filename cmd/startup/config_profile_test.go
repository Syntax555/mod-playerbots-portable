package main

import (
	"strings"
	"testing"
)

func TestFreshPlayerbotsProfile(t *testing.T) {
	source := "# Playerbots.MinRandomBots = 500\r\nPlayerbots.MinRandomBots=500\r\nPlayerbots.BotCheats = \"food,taxi,raid\"\r\nPlayerbots.RandombotStartingLevel = 55\r\nCustom.Value = \"keep=me\"\r\n"
	merged, err := applyConfigProfile("playerbots.conf.dist", source)
	if err != nil {
		t.Fatal(err)
	}
	required := []string{
		"# Playerbots.MinRandomBots = 500\r\n",
		"Playerbots.MinRandomBots = 2500\r\n",
		"Playerbots.MaxRandomBots = 2500\r\n",
		"Playerbots.NaturalProgression = 1\r\n",
		"Playerbots.RandombotStartingLevel = 1\r\n",
		"Playerbots.BotCheats = \"\"\r\n",
		"Playerbots.RandomBotFixedLevel = 0\r\n",
		"Playerbots.RandomBotXPRate = 1.0\r\n",
		"Playerbots.AutoEquipUpgradeLoot = 1\r\n",
		"Playerbots.AllowLearnTrainerSpells = 1\r\n",
		"Playerbots.DisabledWithoutRealPlayer = 1\r\n",
		"Playerbots.DisabledWithoutRealPlayerLoginDelay = 30\r\n",
		"Playerbots.DisabledWithoutRealPlayerLogoutDelay = 60\r\n",
		"Playerbots.BotActiveAlone = 100\r\n",
		"Playerbots.botActiveAloneSmartScale = 1\r\n",
		"Playerbots.botActiveAloneSmartScaleDiffLimitfloor = 50\r\n",
		"Playerbots.botActiveAloneSmartScaleDiffLimitCeiling = 200\r\n",
		"Playerbots.botActiveAloneSmartScaleWhenMinLevel = 1\r\n",
		"Playerbots.botActiveAloneSmartScaleWhenMaxLevel = 80\r\n",
		"Playerbots.RandomBotMaxLevel = 80\r\n",
		"Playerbots.RandomBotMaps = 0,1,530,571\r\n",
		"Playerbots.ApplyInstanceStrategies = 1\r\n",
		"Playerbots.AutoAvoidAoe = 1\r\n",
		"Playerbots.VanillaBattlegroundsOnly = 0\r\n",
		"Playerbots.EarnedEraBattlegrounds = 1\r\n",
		"Playerbots.LimitTalentsExpansion = 0\r\n",
		"Playerbots.RandomBotJoinBG = 1\r\n",
		"Playerbots.RandomBotAutoJoinBG = 0\r\n",
		"Playerbots.RandomBotAutoJoinWSBrackets = 0,1,2,3,4,5,6,7,8,9\r\n",
		"Playerbots.RandomBotAutoJoinABBrackets = 0,1,2,3,4,5,6,7,8\r\n",
		"Playerbots.RandomBotAutoJoinAVBrackets = 0,1,2,3\r\n",
		"Playerbots.RandomBotAutoJoinBGEYCount = 1\r\n",
		"Playerbots.RandomBotAutoJoinBGICCount = 1\r\n",
		"Playerbots.RandomBotAutoJoinBGRatedArena2v2Count = 0\r\n",
		"Playerbots.RandomBotAutoJoinBGRatedArena3v3Count = 0\r\n",
		"Playerbots.RandomBotAutoJoinBGRatedArena5v5Count = 0\r\n",
		"Playerbots.RandomBotArenaTeam2v2Count = 0\r\n",
		"Playerbots.RandomBotArenaTeam3v3Count = 0\r\n",
		"Playerbots.RandomBotArenaTeam5v5Count = 0\r\n",
		"Playerbots.EnableGreet = 1\r\n",
		"Playerbots.GreetRealPlayersOnly = 1\r\n",
		"Playerbots.RandomBotEmote = 0\r\n",
		"Playerbots.ToxicLinksRepliesChance = 0\r\n",
		"Playerbots.ThunderfuryRepliesChance = 0\r\n",
		"Custom.Value = \"keep=me\"\r\n",
	}
	for _, setting := range required {
		if !strings.Contains(merged, setting) {
			t.Errorf("missing %q", setting)
		}
	}
	if strings.Contains(strings.ReplaceAll(merged, "\r\n", ""), "\n") {
		t.Error("profile changed CRLF line endings")
	}
	if strings.Count(merged, "Playerbots.MaxRandomBots =") != 1 {
		t.Error("appended duplicate setting")
	}
	again, err := applyConfigProfile("playerbots.conf.dist", merged)
	if err != nil {
		t.Fatal(err)
	}
	if again != merged {
		t.Error("reapplying profile changes the result")
	}
}

func TestFreshWorldProfileKeepsEarnedStartsAndRewards(t *testing.T) {
	merged, err := applyConfigProfile("worldserver.conf.dist", "[worldserver]\nMaxPlayerLevel = 80\nBattleground.Arathi.CapturePoints = 2000\nBattleground.Alterac.Reinforcements = 0\n")
	if err != nil {
		t.Fatal(err)
	}
	assignments, err := parseConfigAssignments(merged)
	if err != nil {
		t.Fatal(err)
	}
	values := make(map[string]string, len(assignments))
	for _, assignment := range assignments {
		values[assignment.key] = assignment.value
	}
	for key, expected := range map[string]string{
		"Expansion":                                     "2",
		"MaxPlayerLevel":                                "80",
		"StartPlayerLevel":                              "1",
		"StartPlayerMoney":                              "0",
		"CharacterCreating.Disabled.RaceMask":           "0",
		"CharacterCreating.Disabled.ClassMask":          "0",
		"Battleground.Arathi.CapturePoints":             "1600",
		"Battleground.Alterac.Reinforcements":           "600",
		"Battleground.Override.LowLevels.MinPlayers":    "0",
		"Battleground.Override.LowLevels.MinPlayers.WS": "0",
		"Battleground.Override.LowLevels.MinPlayers.AB": "0",
		"Battleground.Override.LowLevels.MinPlayers.AV": "0",
		"Battleground.GiveXPForKills":                   "0",
		"Rate.Honor":                                    "1",
	} {
		if values[key] != expected {
			t.Errorf("%s = %q, want %q", key, values[key], expected)
		}
	}
}

func TestConfigProfileUnknownModuleUnchanged(t *testing.T) {
	source := "# My unrelated module\nCustom = 42\n"
	result, err := applyConfigProfile("unrelated.conf.dist", source)
	if err != nil {
		t.Fatal(err)
	}
	if result != source {
		t.Error("unrelated module configuration was modified")
	}
}

func TestMergeProfileExactKeysAndQuotedValues(t *testing.T) {
	source := " # Enable = 99\n Enabled = 99\nEnable\t= 99\nEqual = \"a=b\"\n"
	merged, err := mergeConfigProfile(source, "[worldserver]\nEnable = 1\nEqual = \"c=d\"\n")
	if err != nil {
		t.Fatal(err)
	}
	if merged != " # Enable = 99\n Enabled = 99\nEnable = 1\nEqual = \"c=d\"\n" {
		t.Errorf("wrong exact-key merge: %q", merged)
	}
}

func TestProfilesAreWellFormed(t *testing.T) {
	entries, err := configProfiles.ReadDir("profiles")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		t.Run(entry.Name(), func(t *testing.T) {
			data, err := configProfiles.ReadFile("profiles/" + entry.Name())
			if err != nil {
				t.Fatal(err)
			}
			assignments, err := parseConfigAssignments(string(data))
			if err != nil {
				t.Fatal(err)
			}
			if len(assignments) == 0 {
				t.Error("profile contains no settings")
			}
		})
	}
}

func TestMalformedProfileRejected(t *testing.T) {
	for _, profile := range []string{"Invalid", "[other-section]\nValid = 1", " = 1", "Valid =", "Valid = 1\nValid = 2"} {
		if _, err := mergeConfigProfile("", profile); err == nil {
			t.Errorf("accepted %q", profile)
		}
	}
}
