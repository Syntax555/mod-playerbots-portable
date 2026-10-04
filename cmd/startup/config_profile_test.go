package main

import (
	"strings"
	"testing"
)

func TestFreshPlayerbotsProfile(t *testing.T) {
	source := "# AiPlayerbot.MinRandomBots = 500\r\nAiPlayerbot.MinRandomBots=500\r\nAiPlayerbot.BotCheats = \"food,taxi,raid\"\r\nAiPlayerbot.RandombotStartingLevel = 55\r\nCustom.Value = \"keep=me\"\r\n"
	merged, err := applyConfigProfile("playerbots.conf.dist", source)
	if err != nil {
		t.Fatal(err)
	}
	required := []string{
		"# AiPlayerbot.MinRandomBots = 500\r\n",
		"AiPlayerbot.MinRandomBots = 2500\r\n",
		"AiPlayerbot.MaxRandomBots = 2500\r\n",
		"AiPlayerbot.NaturalProgression = 1\r\n",
		"AiPlayerbot.RandombotStartingLevel = 1\r\n",
		"AiPlayerbot.BotCheats = \"\"\r\n",
		"AiPlayerbot.RandomBotFixedLevel = 0\r\n",
		"AiPlayerbot.RandomBotXPRate = 1.0\r\n",
		"AiPlayerbot.AutoEquipUpgradeLoot = 1\r\n",
		"AiPlayerbot.AllowLearnTrainerSpells = 1\r\n",
		"AiPlayerbot.DisabledWithoutRealPlayer = 0\r\n",
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
	if strings.Count(merged, "AiPlayerbot.MaxRandomBots =") != 1 {
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
