package main

import (
	"context"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"
)

func newPhaseRealm(t *testing.T) string {
	t.Helper()
	directory := t.TempDir()
	for _, name := range []string{"worldserver.conf", "individualProgression.conf", "playerbots.conf"} {
		vanilla, _ := parseRealmPhase("vanilla")
		content, err := applyConfigProfileForPhase(name, "[worldserver]\r\nCustom.Value = \"retain=me\"\r\nCharacterDatabaseInfo = \"host;3307;user;password;custom_characters\"\r\n", vanilla)
		if err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(directory, "configs", "modules", name)
		if name == "worldserver.conf" {
			path = filepath.Join(directory, "configs", name)
		}
		writePhaseTestFile(t, path, content)
	}
	writePhaseTestFile(t, filepath.Join(directory, "mysql", "data", "progress.ibd"), "earned characters and progression")
	writePhaseTestFile(t, filepath.Join(directory, "configs", "authserver.conf"), "Custom.Auth = preserve\n")
	return directory
}

func writePhaseTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
}

func readPhaseTestFile(t *testing.T, path string) string {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(content)
}

func TestConfigValueMatchesAzerothCoreParser(t *testing.T) {
	content := "# MaxPlayerLevel = 10\r\n[MaxPlayerLevel = 70]\r\n[worldserver]\r\n  MaxPlayerLevel = \"60\"  \r\n" +
		"MaxPlayerLevel = 80\r\nWorldServerPort=8085\r\nBindIP = \"192.168.1.10\"\r\nEmpty =\r\n"
	for _, test := range []struct {
		key, raw string
		exists   bool
		number   int
		invalid  bool
	}{
		{key: "MaxPlayerLevel", raw: `"60"`, exists: true, number: 60},
		{key: "WorldServerPort", raw: "8085", exists: true, number: 8085},
		{key: "BindIP", raw: `"192.168.1.10"`, exists: true, invalid: true},
		{key: "Empty", raw: "", exists: true, invalid: true},
		{key: "Missing"},
	} {
		if raw, exists := configValue(content, test.key); raw != test.raw || exists != test.exists {
			t.Errorf("configValue(%s) = %q, %v; want %q, %v", test.key, raw, exists, test.raw, test.exists)
		}
		number, exists, err := configInt(content, test.key)
		if exists != test.exists || (err != nil) != test.invalid || number != test.number {
			t.Errorf("configInt(%s) = %d, %v, %v; want %d, %v, invalid %v", test.key, number, exists, err, test.number, test.exists, test.invalid)
		}
	}
}

func TestRealmSettingsAcceptQuotedNumbers(t *testing.T) {
	directory := t.TempDir()
	writePhaseTestFile(t, filepath.Join(directory, "configs", "worldserver.conf"), "MaxPlayerLevel = \"70\"\n")
	if phase, err := loadRealmPhase(directory); err != nil || phase.name != "tbc" {
		t.Fatalf("quoted level cap read as %+v (%v)", phase, err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	closed, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	closedPort := closed.Addr().(*net.TCPAddr).Port
	closed.Close()
	world := filepath.Join(directory, "configs", "worldserver.conf")
	writePhaseTestFile(t, world, fmt.Sprintf("WorldServerPort = \"%d\"\n", listener.Addr().(*net.TCPAddr).Port))
	writePhaseTestFile(t, filepath.Join(directory, "configs", "authserver.conf"), fmt.Sprintf("RealmServerPort = \"%d\"\n", closedPort))
	if err := ensureRealmStopped(directory); err == nil || !strings.Contains(err.Error(), "is listening") {
		t.Fatalf("quoted listening port was not checked: %v", err)
	}
	writePhaseTestFile(t, world, fmt.Sprintf("WorldServerPort = \"%d\"\n", closedPort))
	if err := ensureRealmStopped(directory); err != nil {
		t.Fatalf("quoted port blocked a stopped realm: %v", err)
	}
}

func TestConfiguredListener(t *testing.T) {
	directory := t.TempDir()
	auth := filepath.Join(directory, "configs", "authserver.conf")
	for _, test := range []struct {
		name, content string
		hosts         []string
		port          int
		invalid       bool
	}{
		{name: "missing config", hosts: []string{"127.0.0.1", "::1"}, port: 3724},
		{name: "default port", content: "BindIP = \"127.0.0.1\"\n", hosts: []string{"127.0.0.1", "::1"}, port: 3724},
		{name: "custom port", content: "RealmServerPort = 3725\n", hosts: []string{"127.0.0.1", "::1"}, port: 3725},
		{name: "quoted port", content: "RealmServerPort = \"3726\"\n", hosts: []string{"127.0.0.1", "::1"}, port: 3726},
		{name: "LAN address", content: "BindIP = \"192.168.1.10\"\nRealmServerPort = 3727\n", hosts: []string{"127.0.0.1", "::1", "192.168.1.10"}, port: 3727},
		{name: "all IPv4 addresses", content: "BindIP = \"0.0.0.0\"\n", hosts: []string{"127.0.0.1", "::1"}, port: 3724},
		{name: "all IPv6 addresses", content: "BindIP = \"::\"\n", hosts: []string{"127.0.0.1", "::1"}, port: 3724},
		{name: "invalid port", content: "RealmServerPort = 70000\n", invalid: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			os.Remove(auth)
			if test.content != "" {
				writePhaseTestFile(t, auth, test.content)
			}
			hosts, port, err := configuredListener(directory, "authserver.conf", "RealmServerPort", 3724)
			if (err != nil) != test.invalid || port != test.port || !slices.Equal(hosts, test.hosts) {
				t.Fatalf("listener = %v, %d, %v; want %v, %d, invalid %v", hosts, port, err, test.hosts, test.port, test.invalid)
			}
		})
	}
}

// A realm bound to one address only answers there, not on 127.0.0.1.
func TestRealmChecksUseConfiguredBindAddress(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.2:0")
	if err != nil {
		t.Skipf("second loopback address unavailable: %v", err)
	}
	defer listener.Close()
	port := listener.Addr().(*net.TCPAddr).Port
	if acceptsConnection([]string{"127.0.0.1"}, port, 200*time.Millisecond) {
		t.Skip("loopback addresses share listeners on this system")
	}
	directory := t.TempDir()
	writePhaseTestFile(t, filepath.Join(directory, "configs", "worldserver.conf"), "WorldServerPort = 1\n")
	writePhaseTestFile(t, filepath.Join(directory, "configs", "authserver.conf"), fmt.Sprintf("BindIP = \"127.0.0.2\"\nRealmServerPort = %d\n", port))
	if err := ensureRealmStopped(directory); err == nil || !strings.Contains(err.Error(), "authserver.conf is listening") {
		t.Fatalf("realm listening on its bind address was not detected: %v", err)
	}
	opts := startupOptions{port: 3306, authPort: 3724}
	hosts, err := applyConfiguredPorts(directory, &opts)
	if err != nil || opts.authPort != port {
		t.Fatalf("configured authserver port = %d, %v; want %d", opts.authPort, err, port)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := waitForAuthServerReady(ctx, nil, hosts, opts.authPort, 3*time.Second); err != nil {
		t.Fatalf("authserver on its configured address was not ready: %v", err)
	}
}

func TestApplyConfiguredPortsFollowsActiveConfig(t *testing.T) {
	directory := t.TempDir()
	auth := filepath.Join(directory, "configs", "authserver.conf")
	writePhaseTestFile(t, auth, "LoginDatabaseInfo = \"127.0.0.1;3310;acore;acore;acore_auth\"\nRealmServerPort = 3725\n")
	// Runs without the original flags must still use the ports the configs name.
	opts := startupOptions{port: 3306, authPort: 3724}
	if _, err := applyConfiguredPorts(directory, &opts); err != nil || opts.port != 3310 || opts.authPort != 3725 {
		t.Fatalf("ports = %d/%d, %v; want 3310/3725", opts.port, opts.authPort, err)
	}
	// An explicit MySQL port is honored; the servers' port cannot be overridden.
	opts = startupOptions{port: 3320, portSet: true, authPort: 3730, authPortSet: true}
	if _, err := applyConfiguredPorts(directory, &opts); err != nil || opts.port != 3320 || opts.authPort != 3725 {
		t.Fatalf("explicit ports = %d/%d, %v; want 3320/3725", opts.port, opts.authPort, err)
	}
	// A database on another host does not choose the port of the local server.
	writePhaseTestFile(t, auth, "LoginDatabaseInfo = \"db.example;3311;acore;acore;acore_auth\"\n")
	opts = startupOptions{port: 3306, authPort: 3724}
	if _, err := applyConfiguredPorts(directory, &opts); err != nil || opts.port != 3306 || opts.authPort != 3724 {
		t.Fatalf("remote database ports = %d/%d, %v; want 3306/3724", opts.port, opts.authPort, err)
	}
}

func TestExpansionTransitionsPreserveCharactersAndSurviveProfileUpdates(t *testing.T) {
	directory := newPhaseRealm(t)
	for _, target := range []struct {
		name, level, limit, maps, raceMask, classMask string
	}{
		{"tbc", "70", "12", "0,1,530", "0", "32"},
		{"wotlk", "80", "0", "0,1,530,571", "0", "0"},
		{"individual", "80", "0", "0,1,530,571", "0", "0"},
	} {
		phase, _ := parseRealmPhase(target.name)
		originals := make(map[string]string)
		for _, relative := range []string{"worldserver.conf", "modules/playerbots.conf", "modules/individualProgression.conf"} {
			path := filepath.Join(directory, "configs", filepath.FromSlash(relative))
			originals[path] = readPhaseTestFile(t, path)
		}
		backups, err := setRealmPhase(directory, phase)
		if err != nil {
			t.Fatal(err)
		}
		for path, original := range originals {
			found := false
			for _, backup := range backups {
				if strings.HasPrefix(backup, path+".backup.") {
					found = true
					if readPhaseTestFile(t, backup) != original {
						t.Fatalf("backup did not preserve %s", path)
					}
				}
			}
			if !found && readPhaseTestFile(t, path) != original {
				t.Fatalf("missing backup for %s", path)
			}
		}
		// A future profile migration must retain the chosen expansion.
		if _, err := migrateConfigProfiles(directory); err != nil {
			t.Fatal(err)
		}
		for relative, expected := range map[string]map[string]string{
			"worldserver.conf":                   {"Expansion": "2", "MaxPlayerLevel": target.level, "CharacterCreating.Disabled.RaceMask": target.raceMask, "CharacterCreating.Disabled.ClassMask": target.classMask, "Rate.XP.Kill": "1", "StartPlayerLevel": "1", "Battleground.Arathi.CapturePoints": "1600", "Battleground.Alterac.Reinforcements": "600"},
			"modules/individualProgression.conf": {"IndividualProgression.Enable": "1", "IndividualProgression.ProgressionLimit": target.limit, "IndividualProgression.BotAccountsMaxLevel": target.level, "IndividualProgression.StartingProgression": "0", "IndividualProgression.BotAccountsRegex": "\"\""},
			"modules/playerbots.conf":            {"AiPlayerbot.RandomBotMaxLevel": target.level, "AiPlayerbot.RandomBotMaps": target.maps, "AiPlayerbot.NaturalProgression": "1", "AiPlayerbot.DisableRandomLevels": "1", "AiPlayerbot.DisableDeathKnightLogin": "1", "AiPlayerbot.BotCheats": "\"\"", "AiPlayerbot.EarnedEraBattlegrounds": "1", "AiPlayerbot.VanillaBattlegroundsOnly": "0", "AiPlayerbot.LimitTalentsExpansion": "0", "AiPlayerbot.RandomBotAutoJoinBG": "0", "AiPlayerbot.RandomBotAutoJoinBGEYCount": "1", "AiPlayerbot.RandomBotAutoJoinBGICCount": "1", "AiPlayerbot.RandomBotArenaTeam2v2Count": "0"},
		} {
			content := readPhaseTestFile(t, filepath.Join(directory, "configs", filepath.FromSlash(relative)))
			for key, want := range expected {
				if actual, exists := configValue(content, key); !exists || actual != want {
					t.Errorf("%s: %s = %q; want %q", target.name, key, actual, want)
				}
			}
			for _, retained := range []string{"Custom.Value = \"retain=me\"\r\n", "CharacterDatabaseInfo = \"host;3307;user;password;custom_characters\"\r\n"} {
				if !strings.Contains(content, retained) {
					t.Fatalf("lost custom setting or CRLF: %s", relative)
				}
			}
		}
		if readPhaseTestFile(t, filepath.Join(directory, "mysql", "data", "progress.ibd")) != "earned characters and progression" ||
			readPhaseTestFile(t, filepath.Join(directory, "configs", "authserver.conf")) != "Custom.Auth = preserve\n" {
			t.Fatal("changed characters or auth config")
		}
		if backups, err := setRealmPhase(directory, phase); err != nil || len(backups) != 0 {
			t.Fatalf("repeating phase selection is not idempotent: %v, %v", backups, err)
		}
	}
}

func TestExpansionRejectsDowngradesAndMissingConfigWithoutChanges(t *testing.T) {
	for _, failure := range []string{"downgrade", "missing"} {
		t.Run(failure, func(t *testing.T) {
			directory := newPhaseRealm(t)
			target, _ := parseRealmPhase("tbc")
			if failure == "downgrade" {
				writePhaseTestFile(t, filepath.Join(directory, "configs", realmPhaseFile), "wotlk\n")
			} else {
				os.Remove(filepath.Join(directory, "configs", "modules", "playerbots.conf"))
			}
			world := filepath.Join(directory, "configs", "worldserver.conf")
			before := readPhaseTestFile(t, world)
			if backups, err := setRealmPhase(directory, target); err == nil || len(backups) != 0 {
				t.Fatalf("accepted %s or wrote backups: %v %v", failure, backups, err)
			}
			if readPhaseTestFile(t, world) != before {
				t.Fatal("changed config after rejected switch")
			}
		})
	}
}

func TestExpansionRejectsListeningRealm(t *testing.T) {
	directory := newPhaseRealm(t)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	world := filepath.Join(directory, "configs", "worldserver.conf")
	before := readPhaseTestFile(t, world) + fmt.Sprintf("WorldServerPort = %d\r\n", listener.Addr().(*net.TCPAddr).Port)
	writePhaseTestFile(t, world, before)
	target, _ := parseRealmPhase("tbc")
	if _, err := setRealmPhase(directory, target); err == nil || !strings.Contains(err.Error(), "stop startup.exe") {
		t.Fatalf("did not reject a listening realm: %v", err)
	}
	if readPhaseTestFile(t, world) != before {
		t.Fatal("changed running realm config")
	}
}

func TestLegacyExpansionInferenceAndInvalidState(t *testing.T) {
	directory := newPhaseRealm(t)
	for _, name := range []string{"tbc", "wotlk"} {
		phase, _ := parseRealmPhase(name)
		for _, relative := range []string{"worldserver.conf", "modules/individualProgression.conf", "modules/playerbots.conf"} {
			path := filepath.Join(directory, "configs", filepath.FromSlash(relative))
			content, _ := mergeConfigProfile(readPhaseTestFile(t, path), phase.profile(filepath.Base(relative)))
			writePhaseTestFile(t, path, content)
		}
		if actual, err := loadRealmPhase(directory); err != nil || actual.name != name {
			t.Fatalf("legacy %s inferred as %+v (%v)", name, actual, err)
		}
		if _, err := migrateConfigProfiles(directory); err != nil {
			t.Fatal(err)
		}
		if actual, _ := loadRealmPhase(directory); actual.name != name {
			t.Fatal("profile update reverted legacy expansion")
		}
	}
	world := filepath.Join(directory, "configs", "worldserver.conf")
	content, _ := mergeConfigProfile(readPhaseTestFile(t, world), "MaxPlayerLevel = 60")
	writePhaseTestFile(t, world, content)
	if _, err := migrateConfigProfiles(directory); err == nil {
		t.Fatal("accepted conflicting legacy caps")
	}
	wrath, _ := parseRealmPhase("wotlk")
	if _, err := setRealmPhase(directory, wrath); err != nil {
		t.Fatalf("could not repair partial legacy upgrade: %v", err)
	}
	if actual, _ := configValue(readPhaseTestFile(t, world), "MaxPlayerLevel"); actual != "80" {
		t.Fatal("partial upgrade was not aligned to Wrath")
	}
	writePhaseTestFile(t, filepath.Join(directory, "configs", realmPhaseFile), "not-an-expansion\n")
	if _, err := loadRealmPhase(directory); err == nil {
		t.Fatal("ignored malformed saved phase")
	}
}

func TestMissingConfigUsesSavedPhase(t *testing.T) {
	directory := t.TempDir()
	writePhaseTestFile(t, filepath.Join(directory, "configs", realmPhaseFile), "tbc\n")
	base := t.TempDir()
	for _, relative := range []string{"worldserver.conf.dist", "modules/playerbots.conf.dist", "modules/individualProgression.conf.dist"} {
		writePhaseTestFile(t, filepath.Join(base, "configs", filepath.FromSlash(relative)), "[worldserver]\nExpansion = 2\n")
	}
	if err := ensureConfigFiles(base, directory, "mysql/bin/mysql.exe", defaultTestOptions()); err != nil {
		t.Fatal(err)
	}
	world := readPhaseTestFile(t, filepath.Join(directory, "configs", "worldserver.conf"))
	if actual, _ := configValue(world, "MaxPlayerLevel"); actual != "70" {
		t.Fatalf("missing config recreated Vanilla cap: %s", actual)
	}
}

func TestFreshRealmDefaultsToPersistentIndividualProgression(t *testing.T) {
	directory, base := t.TempDir(), t.TempDir()
	for _, relative := range []string{"worldserver.conf.dist", "modules/playerbots.conf.dist", "modules/individualProgression.conf.dist"} {
		writePhaseTestFile(t, filepath.Join(base, "configs", filepath.FromSlash(relative)), "[worldserver]\nExpansion = 2\n")
	}
	if err := ensureConfigFiles(base, directory, "mysql/bin/mysql.exe", defaultTestOptions()); err != nil {
		t.Fatal(err)
	}
	if phase, err := loadRealmPhase(directory); err != nil || phase.name != "individual" {
		t.Fatalf("fresh mode = %+v (%v)", phase, err)
	}
	if _, err := migrateConfigProfiles(directory); err != nil {
		t.Fatal(err)
	}
	for relative, expected := range map[string]map[string]string{
		"worldserver.conf":                   {"MaxPlayerLevel": "80", "StartPlayerLevel": "1", "StartPlayerMoney": "0", "MinDualSpecLevel": "80", "CharacterCreating.Disabled.RaceMask": "0"},
		"modules/individualProgression.conf": {"IndividualProgression.ProgressionLimit": "0", "IndividualProgression.StartingProgression": "0", "IndividualProgression.TbcRacesUnlockProgression": "8", "IndividualProgression.tbcRacesStartingProgression": "0", "IndividualProgression.DeathKnightUnlockProgression": "13", "IndividualProgression.BotAccountsRegex": "\"\"", "IndividualProgression.ExcludedAccountsRegex": "\"\""},
		"modules/playerbots.conf":            {"AiPlayerbot.RandomBotMaxLevel": "80", "AiPlayerbot.RandombotStartingLevel": "1", "AiPlayerbot.RandomBotFixedLevel": "0", "AiPlayerbot.SyncLevelWithPlayers": "0", "AiPlayerbot.DisableDeathKnightLogin": "1", "AiPlayerbot.EarnedEraBattlegrounds": "1", "AiPlayerbot.VanillaBattlegroundsOnly": "0", "AiPlayerbot.LimitTalentsExpansion": "0", "AiPlayerbot.RandomBotAutoJoinBG": "0", "AiPlayerbot.RandomBotAutoJoinBGEYCount": "1", "AiPlayerbot.RandomBotAutoJoinBGICCount": "1", "AiPlayerbot.RandomBotArenaTeam2v2Count": "0"},
	} {
		content := readPhaseTestFile(t, filepath.Join(directory, "configs", filepath.FromSlash(relative)))
		for key, want := range expected {
			if actual, _ := configValue(content, key); actual != want {
				t.Errorf("%s: %s = %q; want %q", relative, key, actual, want)
			}
		}
	}
}

func TestIndividualSelectionRestoresEarnedUnlocksAndRetainsLegacyCeilingUntilSelected(t *testing.T) {
	directory := newPhaseRealm(t)
	if _, err := migrateConfigProfiles(directory); err != nil {
		t.Fatal(err)
	}
	if phase, _ := loadRealmPhase(directory); phase.name != "vanilla" {
		t.Fatal("profile migration opened an existing Vanilla realm without selection")
	}
	for relative, unsafe := range map[string]string{
		"worldserver.conf":                   "StartPlayerLevel = 60\nStartPlayerMoney = 10000000\n",
		"modules/playerbots.conf":            "AiPlayerbot.RandombotStartingLevel = 60\nAiPlayerbot.RandomBotFixedLevel = 60\nAiPlayerbot.SyncLevelWithPlayers = 1\nAiPlayerbot.DisableDeathKnightLogin = 0\n",
		"modules/individualProgression.conf": "IndividualProgression.StartingProgression = 8\nIndividualProgression.tbcRacesStartingProgression = 8\nIndividualProgression.TbcRacesUnlockProgression = 0\nIndividualProgression.BotAccountsRegex = \"RNDBOT.*\"\nIndividualProgression.DisableDefaultProgression = 1\n",
	} {
		path := filepath.Join(directory, "configs", filepath.FromSlash(relative))
		content, err := mergeConfigProfile(readPhaseTestFile(t, path), unsafe)
		if err != nil {
			t.Fatal(err)
		}
		writePhaseTestFile(t, path, content)
	}
	individual, _ := parseRealmPhase("individual")
	if _, err := setRealmPhase(directory, individual); err != nil {
		t.Fatal(err)
	}
	for relative, expected := range map[string]map[string]string{
		"worldserver.conf":                   {"MaxPlayerLevel": "80", "StartPlayerLevel": "1", "StartPlayerMoney": "0"},
		"modules/playerbots.conf":            {"AiPlayerbot.RandombotStartingLevel": "1", "AiPlayerbot.RandomBotFixedLevel": "0", "AiPlayerbot.SyncLevelWithPlayers": "0", "AiPlayerbot.DisableDeathKnightLogin": "1", "AiPlayerbot.EarnedEraBattlegrounds": "1", "AiPlayerbot.VanillaBattlegroundsOnly": "0", "AiPlayerbot.LimitTalentsExpansion": "0", "AiPlayerbot.RandomBotAutoJoinBG": "0", "AiPlayerbot.RandomBotAutoJoinBGEYCount": "1", "AiPlayerbot.RandomBotAutoJoinBGICCount": "1", "AiPlayerbot.RandomBotArenaTeam2v2Count": "0"},
		"modules/individualProgression.conf": {"IndividualProgression.StartingProgression": "0", "IndividualProgression.tbcRacesStartingProgression": "0", "IndividualProgression.TbcRacesUnlockProgression": "8", "IndividualProgression.BotAccountsRegex": "\"\"", "IndividualProgression.DisableDefaultProgression": "0"},
	} {
		content := readPhaseTestFile(t, filepath.Join(directory, "configs", filepath.FromSlash(relative)))
		for key, want := range expected {
			if actual, _ := configValue(content, key); actual != want {
				t.Errorf("%s = %q; want %q", key, actual, want)
			}
		}
	}
	if readPhaseTestFile(t, filepath.Join(directory, "mysql", "data", "progress.ibd")) != "earned characters and progression" {
		t.Fatal("individual selection changed saved progression")
	}
}

func TestExpansionCLIValidation(t *testing.T) {
	for _, name := range []string{"individual", "vanilla", "TBC", "wotlk", "wrath"} {
		if _, err := parseArgs([]string{"--set-expansion", name}); err != nil {
			t.Fatal(err)
		}
	}
	if options, err := parseArgs([]string{"--show-expansion"}); err != nil || !options.showExpansion {
		t.Fatalf("show expansion parse: %v %v", options, err)
	}
	for _, arguments := range [][]string{{"--set-expansion", ""}, {"--set-expansion", "tcb"}, {"--set-expansion", "tbc", "extra"}, {"--set-expansion", "tbc", "--apply-profiles"}, {"--set-expansion", "tbc", "--show-expansion"}, {"--show-expansion", "--init-only"}} {
		if _, err := parseArgs(arguments); err == nil {
			t.Fatalf("accepted invalid expansion command: %v", arguments)
		}
	}
}

func TestNewPhaseFileRollsBackOnFailedTransaction(t *testing.T) {
	directory := t.TempDir()
	marker := filepath.Join(directory, realmPhaseFile)
	blocked := filepath.Join(directory, "blocked.conf")
	os.Mkdir(blocked, 0755)
	updates := []profileUpdate{
		{path: marker, updated: []byte("tbc\n"), mode: 0644, create: true},
		{path: blocked, original: []byte("old"), updated: []byte("new"), backup: filepath.Join(directory, "blocked.backup"), mode: 0644},
	}
	if _, err := applyProfileUpdates(updates); err == nil {
		t.Fatal("accepted failed transaction")
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("phase file survived rollback")
	}
}
