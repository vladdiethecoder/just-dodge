# Lessons from OATHYARD — Applied to Just Dodge

## 1. Truth Isolation Is Non-Negotiable

OATHYARD kept a canonical truth hash (`f17c8f76b9dfae86`) stable across renderer, UI, animation, and asset changes. Just Dodge must do the same.

**Applied:**
- Combat simulation runs in a deterministic subsystem.
- Presentation layer reads state; it never writes back.
- Every build runs a truth-hash regression test.
- Any change that alters the hash is documented and proven intentional.

## 2. Renderer-Driven Development Is a Trap

OATHYARD had periods where screenshots looked better but the game was not more fun to play. This was recognized and corrected with a game-driven pivot.

**Applied:**
- No renderer, shader, asset, or animation work unless it improves the playable exchange.
- Every visual change requires a gameplay justification.
- Playtest recordings, not screenshots, are the primary progress metric.

## 3. Presentation Bricks Are Allowed If truth_mutation=false

OATHYARD used PresentationBricks to improve readability without breaking the physical model.

**Applied:**
- MotionBricks interpolation, camera shake, VFX, and audio are all PresentationBricks.
- Each brick has a `truth_mutation` flag that must be `false`.
- A validation tool checks that no brick mutates combat state.

## 4. The YOMI Loop Must Loop Back

OATHYARD converted a queue/timeline system into a single-action-per-turn YOMI loop by returning `Consequence` to `Observe` instead of `MatchResult`.

**Applied:**
- Just Dodge is designed as YOMI from the start.
- Player commits exactly one action per exchange.
- Opponent generates one fresh action per exchange.
- Hidden intent resets every loop.

## 5. Opponent Identity and Loadout Must Be Visible

OATHYARD required that opponent fighter, weapon, and armor appear in UI and scene, not as blank panels.

**Applied:**
- Opponent loadout is part of the match setup state from day one.
- UI labels and 3D scene must stay synchronized.
- Asset validator ensures every loadout has required metadata.

## 6. No Placeholder UI in Player Mode

OATHYARD forbade debug HUD and placeholder UI during gameplay.

**Applied:**
- Separate modes: Developer, Presentation, Player.
- Player mode shows only diegetic or final UI.
- Debug overlays are gated behind a dev flag.

## 7. Executable-First Verification

OATHYARD's goal was a packaged executable that a player could run without repo access.

**Applied:**
- Every stage ends with a packaged build test on a clean machine.
- `./bin/just-dodge` or equivalent must run the full loop.
- No acceptance based on editor-only play.

## 8. Capture/Video Is Verification Support, Not Progress

OATHYARD explicitly rejected using capture matrices or screenshots as substitutes for gameplay.

**Applied:**
- Recordings are for post-playtest review only.
- Progress is measured by how the game feels to play, not by how it looks in stills.
- No score inflation or visual-readiness claims.

## 9. AI Must Be Deterministic and Readable

OATHYARD's AI countered the player's last action using the matchup matrix and adapted by injury.

**Applied:**
- AI personalities use the same deterministic resolver.
- AI makes mistakes at lower difficulties.
- AI never sees the player's hidden intent before reveal.

## 10. Root-Cause Fixes Over Fragile Hacks

OATHYARD corrected visual legibility through the tone-map and lighting chain, not shader tint hacks.

**Applied:**
- When readability fails, fix the root cause: pose, timing, camera, lighting, or audio.
- No shader compensations for design problems.
- Every hack is ticketed for a proper fix before release.

## 11. MotionBricks Need Hold Loops

OATHYARD discovered that interpolating into a pose and stopping makes fighters look like mannequins.

**Applied:**
- Every action pose has a tiny hold loop or idle drift.
- Contact frames hold plus VFX/audio.
- Recovery transitions back to idle or next action smoothly.

## 12. Vertical Slice Before Vertical Climb

OATHYARD reached Stage 2 (First Playable) before attempting deeper systems.

**Applied:**
- Just Dodge locks Stage 0 and Stage 1 before expanding to 13 actions.
- No networking, no progression, no Steam until local gameplay is great.

## Anti-Patterns to Avoid

- Adding screenshot tooling instead of fixing gameplay.
- Claiming demo readiness before the executable is fun.
- Replacing interaction with replay or automation.
- Disabling tests to pass a gate.
- Skipping verification because "it looks right."
