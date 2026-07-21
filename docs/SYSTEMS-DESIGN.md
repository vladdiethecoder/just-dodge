# Systems Design — Just Dodge

## Purpose

This document defines the full scoped game systems and how each system connects to deterministic combat, presentation readability, content production, and verification. It is design/architecture documentation only; it does not request code changes.

## System Priority Stack

Systems are prioritized by their effect on the playable duel:

1. Match loop and input commit.
2. Combat resolver and 13-action matrix.
3. AI opponent and player readability.
4. Localized injury and capability changes.
5. Motion, camera, and audio tells.
6. Replay and truth hash.
7. Armor/loadout counterplay.
8. Asset pipeline and visual identity.
9. Tutorial and local two-player usability.
10. Content scaling.
11. Rollback multiplayer.
12. Steam/launch/live support.

Any system below a failed system must wait unless it is needed to verify that failed system.

## 1. Match Loop System

### Player Experience Goal

A match is a sequence of readable dueling exchanges. The player should always know:

- what phase they are in;
- whether their intent is hidden, committed, revealed, or resolved;
- what consequence happened;
- why the next exchange is different.

### Authoritative State

```text
MatchState {
  ruleset_version,
  phase,
  frame_index,
  fighters[2],
  current_exchange,
  replay_writer,
  truth_hash,
  winner optional,
}
```

### Exchange Phases

```text
Observe:
  player reads opponent/loadout/stance/injury/camera/audio context
Plan:
  player chooses hidden action and stance
Commit:
  both actions locked; AI/human cannot change
Reveal:
  actions shown through animation/audio/UI
Resolve:
  deterministic resolver computes contact/injury/armor/stamina
Consequence:
  results are displayed and recorded
Loop:
  if no incapacitation, return to Observe
```

### Acceptance Criteria

- Player can complete a match without external explanation.
- Every exchange records both committed actions and outcome.
- Same seed + input stream produces same final truth hash.
- Player never sees opponent hidden action before commit.

## 2. Action Matrix System

### Scope

The final core combat has 13 actions:

1. Strike
2. Block
3. Grab
4. Dodge
5. Feint
6. Thrust
7. Parry
8. Riposte
9. Disengage
10. Kick / Shield Bash
11. Low Attack
12. High Attack
13. Dodge-Attack / Spin

### Data-Authored Matrix

The 13×13 matrix must be authored as data so balance is inspectable.

Each cell defines:

```text
MatrixCell {
  player_action,
  opponent_action,
  contact_type,
  initiative_result,
  hit_location_rule,
  armor_query_rule,
  injury_rule,
  tempo_delta_rule,
  next_state_flags,
  readability_note,
}
```

### Action Timing Data

```text
ActionTiming {
  action_id,
  startup_frames,
  active_frames,
  recovery_frames,
  reveal_tell_frames,
  commitment_lock_frame,
  cancel_rules[],
}
```

### Rules

- Timing is simulation-frame based.
- Presentation can interpolate between phases but cannot shift truth frames.
- Feint and riposte are special rules; they must be explicit matrix/state entries, not hidden conditionals scattered through code.

### Verification

- Exhaustive 13×13 test: every cell resolves.
- Symmetry/asymmetry audit: intentional asymmetries are documented.
- No cell returns “unknown.”
- Golden replay for at least one exchange per action.

## 3. Stance and Zone System

### Purpose

Stance gives readable pre-contact information without exposing exact hidden intent.

### Stances

- High
- Low
- Neutral

### Responsibilities

- Influence action availability or advantage.
- Provide pose/audio/camera cues.
- Support high/low attack and block logic.
- Make action reads richer without becoming UI-only guessing.

### Acceptance

- A player can identify stance visually in under 1 second.
- Stance does not reveal exact hidden action.
- High/low action outcomes are deterministic and replayable.

## 4. Tempo / Stamina System

### Purpose

Tempo prevents infinite aggression and creates consequence across exchanges.

### Truth State

```text
TempoState {
  current,
  max,
  regen_per_exchange,
  armor_modifier,
  injury_modifier,
  exhaustion_thresholds,
}
```

### Design Rules

- Tempo gates next selection; it does not cancel committed active actions mid-animation.
- Disengage restores tempo.
- Heavy armor drains more tempo.
- Injury can reduce regen or cap.

### Readability

Tempo changes must be readable through breathing, posture, speed, and minimal UI. Hidden numeric stamina without feedback is not acceptable.

## 5. Localized Injury System

### Purpose

Replace abstract HP with combat-capability consequences.

### Body Regions

- Head
- Neck
- Torso
- Spine
- Left/right arms
- Left/right hands
- Left/right legs
- Left/right feet

### Truth State

```text
InjuryState {
  region_id,
  structural_damage,
  pain/shock,
  bleed optional,
  capability_modifiers[],
  incapacitation_flags[],
}
```

### Capability Modifiers

- arm speed decrease;
- grip failure;
- dodge disabled or slowed;
- locomotion limp;
- vision blur;
- stamina regeneration penalty;
- stance restrictions;
- weapon drop.

### Resolver Flow

```text
contact event
  → armor coverage query
  → armor absorption / failure
  → residual force
  → injury region update
  → capability delta
  → presentation cues
```

### Acceptance

- A player can explain at least one tactical adaptation caused by injury.
- Injury is visible/audible enough to guide decisions.
- Injury does not feel like arbitrary hidden HP.

## 6. Armor and Loadout System

### Purpose

Armor creates readable counterplay by changing protection, ROM, speed, noise, and failure patterns.

### Loadout Classes

- Ascetic
- Duelist
- Sentinel
- Juggernaut
- Mystic
- Warden

### Armor Piece Truth

```text
ArmorPieceTruth {
  piece_id,
  slot,
  material,
  covered_bones[],
  integrity,
  mass_kg,
  resistances,
  rom_clamp,
  noise_level,
  persistent_damage_state,
  destructible,
}
```

### Persistent Damage

Persistent damage is an authored truth record:

```text
DamageEvent {
  event_id,
  exchange_index,
  frame_index,
  impact_point,
  force,
  damage_type,
  contact_angle,
  material_response,
  visual_write_request,
}
```

### Material Families

- Cloth/Silk: XPBD/PBD later; simplified tear state first.
- Leather: mass-spring/plasticity later; simplified cuts/creases first.
- Chainmail: ring constraint graph later; simplified ring gap state first.
- Plate: FEM later; simplified dent/threshold state first.
- Rune-Marble: brittle fracture later; simplified crack/shatter state first.
- Warden bone: brittle organic fracture later; simplified fused fracture state first.

### Gate

Armor is not allowed to pass because it looks cool. It passes only if players change action/weapon/loadout decisions for readable reasons.

## 7. AI System

### Purpose

AI exists to create fair, readable dueling pressure in local single-player.

### AI Constraints

- AI commits before reveal.
- AI uses same action set and rules as player.
- AI cannot inspect hidden player intent.
- AI must be deterministic under seed.
- Lower difficulty means intentional readable mistakes, not random stupidity.

### Personalities

```text
Aggressive:
  biases Strike, Thrust, Kick; weak to bait/parry
Defensive:
  biases Block, Parry, Disengage; weak to Grab/Feint
Trickster:
  biases Feint, Dodge-Attack, stance shifts; weak to fast commitment
Mirror:
  adapts to player frequency; weak to mixed strategies
Injured/Desperate:
  changes risk tolerance based on capability loss
```

### AI State

```text
AiState {
  personality,
  rng_seed,
  memory_window,
  player_action_histogram,
  own_injury_awareness,
  player_injury_awareness,
  mistake_rate,
}
```

### Verification

- Replaying the same match yields identical AI choices.
- Each personality produces a distinguishable action distribution.
- Human player changes strategy against each personality in playtest.

## 8. Motion and Animation System

### Purpose

Motion communicates hidden intent after reveal and makes consequences legible. Motion is not authoritative truth.

### Sources

- Current authored keyframe constraints in `src/combat.rs`.
- MotionBricks VQVAE/transformer ONNX artifacts.
- SKM1 mannequin. ANM1 baked clips are removed as a source (owner ruling 2026-07-19: no baked clips in any mode).
- Future action reference clips.

### Runtime Layers

```text
Truth event
  → Motion request
  → authored/MotionBricks clip selection
  → retarget G1 34 joints to mannequin 24+ bones
  → procedural spine/finger/toe/weapon IK
  → injury/armor ROM presentation clamps
  → skinned render matrices
```

### Readability Requirements

- Every action has a unique first-six-frame tell after reveal.
- Contact frame is visually obvious.
- Recovery shows vulnerability.
- Injuries change posture/pace visibly.
- Motion never makes two actions indistinguishable for aesthetic smoothness.

### Fallback Policy

If real-time MotionBricks inference fails latency or artifact gates:

1. Keep the MotionBricks runtime path alive; inference runs as an async buffered plan service so the 120 Hz truth tick never waits on it.
2. Prebaked action clips are forbidden (owner ruling 2026-07-19); latency or stability problems are solved in the inference path, never by clip substitution.
3. Keep truth/presentation boundary unchanged.
4. Do not block combat fun on neural inference; presentation holds the last validated pose while truth continues.

## 9. Camera System

### Current

`src/main.rs` has an orbital camera with drag/zoom, useful for asset inspection.

### Target Cameras

```text
PlayerCamera:
  first-person duel view, tuned for opponent tells and weapon arcs
DuelReadableCamera:
  optional shoulder/offset camera if first-person hides intent
ReplayCamera:
  deterministic replay inspection camera
FightFilmCamera:
  cinematic presentation-only camera
DeveloperCamera:
  free/orbital/debug; not allowed in Player mode
```

### Gate

If first-person camera hides opponent tells, camera design must change before more content is added. Camera readability beats genre purity.

## 10. Renderer / Visual Identity System

### Responsibilities

- draw fighters, armor, weapons, and arena;
- preserve silhouette readability;
- provide material identity;
- visualize injury and armor damage;
- support visual QA capture;
- keep player mode clean.

### Current Visual Stack

- textured static arena assets;
- checkerboard procedural ground;
- static + skinned mannequin paths;
- simple directional lighting;
- no material pipeline beyond base textures and simple normal-independent lighting;
- no UI/player HUD implementation in current inspected source.

### Target Visual Readability Tiers

1. Fighter identity: player/opponent always distinguishable.
2. Action pose: action can be identified after reveal.
3. Weapon/armor attachment: no floating equipment.
4. Contact: hit/block/parry/grab clearly visible.
5. Consequence: injury/armor damage readable.
6. Camera/framing: combat state clear without debug overlays.
7. Material/lighting: supports silhouettes and state reads.

## 11. Audio System

### Required Cues

- action wind-up;
- reveal confirmation;
- block/parry/hit/grab/contact;
- material-specific armor sound;
- stamina/breathing;
- injury/vulnerability;
- replay/fight-film transitions.

### Rules

- Audio is information-bearing, not only polish.
- If two actions look similar, audio may differentiate them only if it is fair and early enough.
- Audio cues need deterministic event sources.

## 12. UI / UX System

### Player Mode UI

Allowed:

- minimal match phase state;
- selected action confirmation before commit if needed;
- readable health/injury/tempo affordance;
- tutorial prompts;
- menu/options.

Forbidden:

- debug overlays;
- evidence overlays;
- placeholder panels;
- raw action IDs unless intentionally tutorialized;
- visual scoring labels.

### Developer Mode UI

Allowed:

- truth hash;
- frame timing;
- active action IDs;
- matrix cell ID;
- replay cursor;
- draw calls;
- skeleton/attachment overlays;
- QA capture controls.

### Presentation Mode UI

Allowed:

- curated clean labels for report captures only;
- build/version watermark if needed;
- no gameplay-debug clutter.

## 13. Replay and Fight Film System

### Replay

Replay is deterministic and inspectable:

- initial seed;
- ruleset version;
- input stream;
- optional cached truth events for comparison;
- final truth hash.

### Fight Film

Fight Film is presentation-only:

- reads replay/truth events;
- chooses camera cuts;
- highlights reads and consequences;
- cannot affect truth;
- must not replace interactive playtesting.

### Verification

- Replay hash stable with renderer enabled/disabled.
- Replay viewer supports frame stepping and contact inspection.
- Fight Film can be regenerated from replay input.

## 14. Networking / Rollback System

Networking is late-stage.

### Prerequisites

- local deterministic simulation;
- replay input stream stable;
- truth hash stable;
- input abstraction supports remote source;
- fixed-step simulation independent of rendering.

### Rollback Requirements

- state snapshot/restore;
- input prediction;
- remote input delay management;
- desync detection by truth hash;
- deterministic asset/ruleset version matching.

### Gate

No rollback implementation until local vertical slice is fun and stable.

## 15. Save / Persistence System

Even if the main match is short, persistent systems may include:

- settings;
- unlocks/progression;
- replay library;
- fighter/loadout presets;
- persistent armor damage if used outside single match.

Save data must version:

- schema;
- ruleset;
- asset manifest;
- armor damage state;
- replay compatibility.

## 16. Tutorial System

Tutorial goal: teach the read, not buttons alone.

### Tutorial Sequence

1. Strike/Block/Grab triangle.
2. Commit/reveal timing.
3. Stance and high/low reads.
4. Feint/dodge/thrust expansion.
5. Injury consequence.
6. Armor/loadout counterplay.
7. Replay review of one exchange.

### Acceptance

A first-time player completes a full match and can explain why they won or lost at least one exchange.

## 17. Content Systems

### Fighters

Minimum content-complete target:

- 3+ fighters;
- distinct silhouettes;
- distinct base speed/tempo/injury tolerance;
- clear loadout identity.

### Weapons

Minimum target:

- 6+ weapons;
- distinct damage family and timing;
- counterplay against armor classes;
- readable wind-up/contact audio.

### Arenas

Minimum target:

- 3+ arenas;
- lighting/readability variations;
- no arena effect that hides YOMI reads;
- no procedural clutter before combat readability is stable.

## 18. Tooling Systems

Required tooling:

- asset extractor/verifier;
- asset manifest generator;
- truth hash test;
- replay analyzer;
- packaged build script;
- visual QA capture runner;
- agentic playtest runner;
- performance budget reporter;
- documentation drift checker.

Current tooling already covers:

- GLB extraction;
- FBX static extraction;
- FBX skinned extraction;
- SKM1/ANM1 verification;
- MotionBricks ONNX/backbone export.

## 19. Performance Budgets

Initial targets:

- 60 fps at 1080p for playable loop.
- Input-to-commit feedback < 3 frames.
- Replay hash test under 1 second for small golden matches.
- Launch to menu < 5 seconds.
- Match replay < 100 KB for short duels.
- Motion inference must not stall input commit or reveal timing.

Future budgets:

- MotionBricks action generation: action-level precompute is acceptable if real-time generation is too slow.
- Renderer frame time: reserve budget for fighter readability over environment detail.
- Texture memory: 4096² textures must be justified by close-up readability, not asset vanity.

## 20. System Gates Summary

| System | Earliest Phase | Gate |
|---|---:|---|
| 3-action loop | First playable | unaided match completion |
| 13-action matrix | Vertical slice | returning player intentionally uses 6+ actions |
| Motion readability | Vertical slice | 80%+ action identification in blind test |
| Armor/loadouts | Vertical slice/content | player changes choices for readable reasons |
| AI personalities | Vertical slice | strategies differ per personality |
| Replay | First playable | truth hash stable |
| Fight Film | Vertical slice | regenerates from replay, truth unchanged |
| Tutorial | Content | first-time player learns triangle unaided |
| Multiplayer | Post-vertical slice | 100+ remote matches, no desyncs |
| Launch | Final | QA suite and player evidence pass |

## 21. Non-Negotiables

- Do not replace gameplay with automation.
- Do not replace AI with scripts.
- Do not replace interaction with replay.
- Do not add visual systems that make the game less readable.
- Do not claim readiness without executable play evidence.
- Do not allow presentation systems to mutate deterministic truth.
- Do not advance on screenshots alone.
- Do not let placeholder UI survive into Player mode.
