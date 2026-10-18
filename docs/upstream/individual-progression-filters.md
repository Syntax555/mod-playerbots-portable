# fix: skip account lookups for empty progression filters

At the recorded base revision, empty bot and exclusion regex options disable their filters, but `isBotAccount()`, `isExcludedAccount()` and `CanAccountCreateCharacter()` still look up account names and compile empty regexes. Skip each disabled filter and skip character-creation account lookup when both filters are empty. Configured matching and ordinary progression checks stay effective.

This reference patch targets the pre-cache API. The pinned module includes
[the merged account cache](https://github.com/ZhengPeiRu21/mod-individual-progression/pull/1308);
[the runtime patch](../../patches/mod-individual-progression-empty-account-filters.patch)
applies the empty-filter guards to its shared numeric account overloads.

Validation: the three extracted proposed production methods pass a C++20 fixture with AddressSanitizer and UndefinedBehaviorSanitizer for null players, both empty filters (zero account queries), each configured filter, matching and nonmatching names, failed account lookup, and progression checks on character creation. The same fixture rejects the unmodified upstream methods. A full upstream server build has not been run.

Base: `c87e666fc034978cffbb287f1be5e53df522539d`.

```diff
diff --git a/src/IndividualProgression.cpp b/src/IndividualProgression.cpp
index 0d9516b..50b0438 100644
--- a/src/IndividualProgression.cpp
+++ b/src/IndividualProgression.cpp
@@ -371,7 +371,7 @@ bool IndividualProgression::isAttuned(Player* player)

 bool IndividualProgression::isExcludedAccount(Player* player)
 {
-    if (!player)
+    if (!player || sIndividualProgression->excludedAccountsRegex.empty())
         return false;

     std::string accountName;
@@ -383,7 +383,7 @@ bool IndividualProgression::isExcludedAccount(Player* player)

 bool IndividualProgression::isBotAccount(Player* player)
 {
-    if (!player)
+    if (!player || sIndividualProgression->botAccountsRegex.empty())
         return false;

     std::string accountName;
diff --git a/src/IndividualProgressionPlayer.cpp b/src/IndividualProgressionPlayer.cpp
index d35f8d7..83ebcc7 100644
--- a/src/IndividualProgressionPlayer.cpp
+++ b/src/IndividualProgressionPlayer.cpp
@@ -1336,13 +1336,16 @@ public:
         }

         // Check if the account is a bot or excluded from progression
-        std::string accountName;
-        bool accountNameFound = AccountMgr::GetName(accountId, accountName);
-        std::regex botAccountsRegex(sIndividualProgression->botAccountsRegex);
-        std::regex excludedAccountsRegex(sIndividualProgression->excludedAccountsRegex);
-
-        if (accountNameFound && (std::regex_match(accountName, botAccountsRegex) || std::regex_match(accountName, excludedAccountsRegex)))
-            return true;
+        if (!sIndividualProgression->botAccountsRegex.empty() || !sIndividualProgression->excludedAccountsRegex.empty())
+        {
+            std::string accountName;
+            if (AccountMgr::GetName(accountId, accountName) &&
+                ((!sIndividualProgression->botAccountsRegex.empty() &&
+                  std::regex_match(accountName, std::regex(sIndividualProgression->botAccountsRegex))) ||
+                 (!sIndividualProgression->excludedAccountsRegex.empty() &&
+                  std::regex_match(accountName, std::regex(sIndividualProgression->excludedAccountsRegex)))))
+                return true;
+        }

         uint8 highestProgression = sIndividualProgression->GetAccountProgression(accountId);
         bool allowed = true;
```
