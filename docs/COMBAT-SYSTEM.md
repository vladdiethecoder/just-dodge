# Combat System Design — Just Dodge

## 1. Design Intent

The combat system must feel like a real duel: tense, readable, and punishing. Every exchange is a single simultaneous reveal. There is no blocking after you see the attack — your choice is made before the steel moves.

## 2. The 13 Actions

| ID | Action | Beats | Loses To | Notes |
|---|---|---|---|---|
| 01 | Strike | Grab, Feint (on read) | Block, Parry, Thrust | Fast, committed |
| 02 | Block | Strike, Thrust | Grab, Kick, Feint | Can riposte if timed |
| 03 | Grab | Block | Strike, Dodge, Thrust | Closes distance |
| 04 | Dodge | Strike, Grab, Low | Feint, Thrust | Creates whiff punish |
| 05 | Feint | Block, Dodge | Strike, Thrust | Cancels into punish |
| 06 | Thrust | Dodge, Feint, Grab | Block, Parry | Committed forward |
| 07 | Parry | Strike, Thrust | Grab, Feint, Kick | High skill, big reward |
| 08 | Riposte | (follow-up) | — | Only after Block/Parry |
| 09 | Disengage | — | — | Reset, costs tempo |
| 10 | Kick | Block, Parry | Strike, Dodge | Slow, breaks guard |
| 11 | Low Attack | High Block | Low Block, Dodge | Must be blocked low |
| 12 | High Attack | Low Block | High Block, Dodge | Must be blocked high |
| 13 | Dodge-Attack | Predictable Strike/Grab | Thrust, Feint | High risk, high reward |

## 3. Matchup Resolution

The resolver takes two committed actions and produces:
- **Contact type:** hit, block, parry, whiff, grab, clash, no-contact
- **Attacker / Defender roles:** based on action aggression priority
- **Injury distribution:** which body parts receive damage
- **Capability deltas:** reduced arm speed, limping, stunned, etc.
- **Next-state flags:** riposte available, disengaged, grounded, etc.

### Example Resolution Table (simplified)

| Player \ Opponent | Strike | Block | Grab | Dodge | Feint | Thrust |
|---|---|---|---|---|---|---|
| Strike | clash / trade | blocked | player hit | whiff | player hit / feint-punish | player hit |
| Block | player riposte | reset | opponent grab | reset | opponent feint-punish | blocked |
| Grab | opponent hit | player grab | grapple | whiff | opponent hit | opponent hit |
| Dodge | whiff-punish | reset | whiff-punish | reset | opponent feint-punish | opponent hit |
| Feint | player feint-punish | player feint-punish | whiff | player feint-punish | reset | player hit |
| Thrust | opponent hit | blocked | player hit | player hit | player hit | clash / trade |

Full 13×13 matrix is authored as data, not hard-coded logic.

## 4. Timing Model

Each action has phases:

1. **Startup** — committed, visible tell, cancellable only by specific actions (Feint).
2. **Active** — hitbox is live; contact can occur.
3. **Recovery** — vulnerable if whiffed.
4. **Neutral** — ready for next exchange.

Timing is measured in simulation frames (60 fps target). Example:
- Strike: 8 startup / 4 active / 12 recovery
- Thrust: 16 startup / 6 active / 20 recovery
- Parry: 4 startup / 6 active / 20 recovery

## 5. Localized Injury System

Body parts track cumulative injury:
- **Head:** low threshold, high impact on vision/stamina.
- **Torso:** moderate threshold, affects stamina regeneration.
- **Arms:** reduce attack speed / disable weapon use.
- **Legs:** reduce movement / disable dodging.

Injury is the result of the resolver, not the cause. The resolver uses action matchup + hit location to assign damage.

## 6. Stance & Zones

- **High stance:** favors High Attack, Parry, Block high.
- **Low stance:** favors Low Attack, Dodge, Block low.
- **Neutral stance:** no bonuses or penalties.

Stance is chosen during the planning phase and is visible to the opponent as a subtle pose cue. This adds YOMI: do you stance-switch to hide intent, or stay predictable to bait a read?

## 7. Stamina / Tempo

- A simple tempo meter prevents infinite aggression.
- Disengage restores tempo.
- Overcommitting (whiffing heavy attacks) drains tempo heavily.
- Tempo does not stop actions mid-animation; it gates what you can select next.

## 8. Distance & Position

- Duelists start at optimal engagement distance.
- Grab and Thrust advance; Disengage retreats; Dodge sidesteps.
- Distance affects which actions are valid (e.g., Grab too far = whiff).
- Position is deterministic; no physics-driven ragdolls during combat resolution.

## 9. AI Design

AI is deterministic and readable, not omniscient.

- **Personality profiles:** Aggressive, Defensive, Trickster, Mirror.
- **Memory:** tracks player's last N actions and weights counter-actions.
- **Mistakes:** intentionally makes bad reads at lower difficulties.
- **No cheating:** AI commits before reveal just like the player.

## 10. Replay & Fight Film

- Replay records initial seed + both input streams.
- Fight Film is a presentation-only cinematic cut of the replay.
- Both use the same deterministic simulation; truth hash must match.
- Replay viewer supports frame stepping and contact inspection.

## 11. MotionBricks Integration

MotionBricks in Just Dodge interpolates between static poses derived from action states.

- Each action maps to a base pose (weapon position, body lean, guard height).
- Transitions between actions are interpolated over a fixed duration.
- Impact frames hold a pose + camera shake + audio.
- Idle/breathing loops add life without affecting truth.
- All interpolation is presentation-only; the resolver uses discrete action IDs and frame counts.

## 12. Readability Requirements

Every action must be identifiable before contact by:
- Weapon/hand position
- Body lean and foot placement
- Audio wind-up signature
- Stance height

If two actions look identical in the first 6 frames, the design fails.

## 13. Truth Isolation Checklist

- [ ] Matchup matrix produces identical results with renderer enabled and disabled.
- [ ] Injury values identical across all quality settings.
- [ ] Replay hash identical on different machines given same inputs.
- [ ] Camera shake, animation interpolation, and VFX never feed back into simulation.
- [ ] AI decision timing does not vary with frame rate.
