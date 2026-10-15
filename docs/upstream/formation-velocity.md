# fix(Core/Movement): guard near-zero formation velocities

Formation catch-up scaling can produce a positive velocity at or below `0.01f` when the follower is already close to the projected destination. `LaunchMovement()` only falls back for exactly zero, while `MoveSplineInitArgs::Validate()` requires `velocity > 0.01f`. The resulting spline is rejected. Use the existing native walking-speed fallback for the whole rejected range.

Validation: the existing [native formation fixture](https://github.com/Syntax555/mod-playerbots-portable/blob/main/cmake/tests/TestFormationMovement.py) compiles and runs the original and proposed production movement methods with the real spline validator under AddressSanitizer and UndefinedBehaviorSanitizer. It covers positive near-zero velocities, ordinary following, speed caps, immobilization and spline lifecycle. A full upstream server build has not been run.

Base: `a64665927de9d23cf81b0b623ee7117131f0919a`.

```diff
diff --git a/src/server/game/Movement/MovementGenerators/FormationMovementGenerator.cpp b/src/server/game/Movement/MovementGenerators/FormationMovementGenerator.cpp
index 1a96860..698e6dc 100644
--- a/src/server/game/Movement/MovementGenerators/FormationMovementGenerator.cpp
+++ b/src/server/game/Movement/MovementGenerators/FormationMovementGenerator.cpp
@@ -153,7 +153,8 @@ void FormationMovementGenerator::LaunchMovement(Creature* owner, Unit* target)
         _hasPredictedDestination = false;
     }

-    if (velocity == 0.0f)
+    // Spline validation also rejects near-zero catch-up velocities.
+    if (velocity <= 0.01f)
         velocity = target->GetSpeed(MOVE_WALK);

     Movement::MoveSplineInit init(owner);
```
