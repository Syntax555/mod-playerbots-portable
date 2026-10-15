# fix(Core/Player): prevent talent reset cost underflow

`resetTalentsCost()` converts negative elapsed months to `uint64` for future persisted timestamps and subtracts monthly decay before clamping the unsigned reset cost. Large elapsed reductions can wrap to a positive `int32`, producing a cost above the ordinary reset range. Ignore negative elapsed time and clamp the reduction before subtraction; retain the ten-gold minimum and existing reset increments.

Validation: the proposed production method passes a C++20 native-method fixture with AddressSanitizer and UndefinedBehaviorSanitizer for normal `1, 5, 10, ... 50` gold increments, one-month decay, long inactivity and a future timestamp. The same fixture rejects the unmodified upstream method. A full upstream server build has not been run.

Base: `a64665927de9d23cf81b0b623ee7117131f0919a`.

```diff
diff --git a/src/server/game/Entities/Player/Player.cpp b/src/server/game/Entities/Player/Player.cpp
index 138e7ea..ef5a2ba 100644
--- a/src/server/game/Entities/Player/Player.cpp
+++ b/src/server/game/Entities/Player/Player.cpp
@@ -3861,13 +3861,14 @@ uint32 Player::resetTalentsCost() const
         return 10 * GOLD;
     else
     {
-        uint64 months = (GameTime::GetGameTime().count() - m_resetTalentsTime) / MONTH;
+        auto now = GameTime::GetGameTime().count();
+        uint64 months = now > m_resetTalentsTime ? (now - m_resetTalentsTime) / MONTH : 0;
         if (months > 0)
         {
             // This cost will be reduced by a rate of 5 gold per month
-            int32 new_cost = int32(m_resetTalentsCost - 5 * GOLD * months);
-            // to a minimum of 10 gold.
-            return (new_cost < 10 * GOLD ? 10 * GOLD : new_cost);
+            // Clamp the elapsed reduction before subtracting the persisted unsigned cost.
+            uint64 reduction = std::min<uint64>(m_resetTalentsCost, 5 * GOLD * months);
+            return std::max<uint32>(10 * GOLD, m_resetTalentsCost - uint32(reduction));
         }
         else
         {
```
