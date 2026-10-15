# fix(Core/Battlegrounds): handle empty random map candidates

`GetRandomBG()` dereferences the weighted selection result even when no battleground candidate survives template and minimum-level checks. Return the existing `BATTLEGROUND_TYPE_NONE` sentinel before selecting an empty container. `CreateNewBattleground()` already handles a missing template for this sentinel.

Validation: the extracted proposed production method passes a C++20 fixture with AddressSanitizer and UndefinedBehaviorSanitizer for an empty map list, missing map templates, minimum-level rejection, a valid candidate and a missing outer template. Empty cases never invoke the selector. The same fixture rejects the unmodified upstream method. A full upstream server build has not been run.

Base: `a64665927de9d23cf81b0b623ee7117131f0919a`.

```diff
diff --git a/src/server/game/Battlegrounds/BattlegroundMgr.cpp b/src/server/game/Battlegrounds/BattlegroundMgr.cpp
index 00c31f5..a023950 100644
--- a/src/server/game/Battlegrounds/BattlegroundMgr.cpp
+++ b/src/server/game/Battlegrounds/BattlegroundMgr.cpp
@@ -935,6 +935,9 @@ BattlegroundTypeId BattlegroundMgr::GetRandomBG(BattlegroundTypeId bgTypeId, uin
             }
         }

+        if (ids.empty())
+            return BATTLEGROUND_TYPE_NONE;
+
         return *Acore::Containers::SelectRandomWeightedContainerElement(ids, weights);
     }

```
