# Prototype Plans — Just Dodge

## Prototype 1: Paper YOMI Triangle

**Question:** Is the 3-action simultaneous-reveal triangle fun and readable?
**Duration:** 1 hour.
**Method:** Index cards, 2 players, 3 actions (Strike / Block / Grab), first to 3 wins.
**Success Criterion:** Both players report at least one "I read you" moment and want a rematch.

### Rules

1. Both players pick one card face-down.
2. Count "one, two, three, reveal."
3. Resolve:
   - Strike beats Grab
   - Block beats Strike
   - Grab beats Block
   - Same action = reset, no damage
4. Winner scores one point.
5. First to 3 points wins the duel.

### Playtest Protocol

- Play at least 10 matches.
- Switch opponents if possible.
- Track:
  - moments of tension,
  - moments of confusion,
  - emergent reads or patterns,
  - desire to play again.

### Report Template

See `docs/reports/PROTOTYPE_01_PAPER_YOMI.md`.

## Prototype 2: Shape Prototype (Custom Engine)

**Question:** Does the digital 3-action simultaneous-reveal feel good in a minimal custom engine?
**Duration:** 2–3 weeks.
**Method:** Rust + wgpu, two colored triangles, 3 actions, simple AI, text UI.
**Success Criterion:** A first-time player plays 5 consecutive matches without asking how to play.

### Scope

- Window via `winit`.
- Rendering via `wgpu`: two triangles and text.
- Input: 3 keys for Strike, Block, Grab.
- AI: random or counters last player action.
- Simultaneous reveal with 1-second countdown.
- Color change: red = Strike, blue = Block, green = Grab.
- Health bar, win/loss, restart key.
- No 3D models, no physics engine, no sounds (optional beeps), no particles, no menus.

### Build Steps

1. `cargo init` and add `winit`, `wgpu`, `glam`.
2. Open a window.
3. Render two triangles.
4. Add keyboard input.
5. Add combat state machine.
6. Implement 3×3 matchup resolver.
7. Add text rendering for health and state.
8. Add restart on R.
9. Play 50 matches and log.

### Playtest Protocol

- Play 50 matches.
- Record each match result and one-line feeling.
- Note any action that feels useless or unclear.

### Report Template

See `docs/reports/PROTOTYPE_02_SHAPE_PROTOTYPE.md`.

## Prototype 3: 13-Action Matrix

**Question:** Does expanding to 13 actions add depth without overwhelming the player?
**Duration:** 2 weeks.
**Method:** Extend shape prototype with full action set and matchup matrix.
**Success Criterion:** A returning player uses at least 6 different actions intentionally across 10 matches.

### Scope

- All 13 actions selectable.
- Full matchup resolver.
- Localized body-part injury (text only).
- Simple AI personality.
- Action timing differences visible as delay before reveal.

### Gate

If players stick to only 3 actions, the matrix is too complex and must be simplified.

## Prototype 4: Motion Readability

**Question:** Can the player identify the opponent's action before contact from pose + audio + camera alone?
**Duration:** 2 weeks.
**Method:** Replace triangles with basic humanoid mesh + weapon; add procedural pose interpolation and audio tells.
**Success Criterion:** In a blind test, player correctly guesses opponent action 80%+ of the time in the first 8 frames after reveal.

### Scope

- One fighter model.
- One weapon model.
- MotionBricks-style interpolation between action poses.
- MotionBricks 29-joint output retargeted to the richer mannequin skeleton through direct mapping, spine interpolation, and finger/toe IK.
- Distinct audio wind-up per action.
- First-person camera reacts to wind-up.
- No particles, no full animation clips.

### Gate

Motion passes only if readability improves. It does not pass for looking better while making opponent intent harder to read.

## Prototype 5: Armor and Damage Readability

**Question:** Do armor classes, material failure, and localized injury create readable counterplay without hiding the YOMI loop behind stat math?
**Duration:** 2 weeks.
**Method:** Add documented armor slots, integrity states, material resistance, ROM clamps, noise, and residual-force injury routing to the playable vertical-slice loop.
**Success Criterion:** A returning player can explain why they changed weapon/action choice against at least three armor classes after 10 matches.

### Scope

- Armor slots mapped to bones/joints.
- Six loadout identities: Ascetic, Duelist, Sentinel, Juggernaut, Mystic, Warden.
- Integrity states: Pristine, Worn, Damaged, Compromised, Destroyed.
- Persistent damage state: event log, deformation map, crack network, and chainmail ring state survive save/load.
- Material response for cloth, leather, chainmail, plate, Rune-Marble, and Warden bone.
- Weapon damage families: slash, pierce, blunt, cleave, wrap, bash.
- ROM, stamina, speed, and noise modifiers.
- No expensive FEM/cloth/fracture implementation until the simplified deterministic model proves fun.

### Gate

If armor choices are perceived as hidden numbers or pure visuals, cut/simplify the system before adding solver complexity.

## Prototype 6: AI Personalities

**Question:** Does adaptive deterministic AI feel fair and varied?
**Duration:** 1 week.
**Method:** Implement 3 AI personalities and test against each.
**Success Criterion:** Player changes strategy noticeably against each personality.

## Prototype 7: Network Rollback (Late)

**Question:** Can remote 1v1 maintain the deterministic combat feel?
**Duration:** 3 weeks.
**Method:** Input prediction + rollback on the existing deterministic sim.
**Success Criterion:** 20 matches against a remote opponent with no desyncs and <3 rollback frames perceived.

## Prototype Kill/Continue Rules

- **KILL:** The prototype fails its success criterion and no clear pivot exists.
- **PIVOT:** The prototype reveals a better design direction; write a new prototype plan.
- **CONTINUE:** The prototype passes; move to the next stage and rewrite production code cleanly.
