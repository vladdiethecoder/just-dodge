# Research Synthesis: YOMI Hustle, For Honor, and Just Dodge

## Sources

- [Your Only Move is Hustle — YOMI Hustle Wiki](https://yomi-hustle.fandom.com/wiki/Your_Only_Move_is_Hustle)
- [Your Only Move Is HUSTLE — Steam Store](https://store.steampowered.com/app/2212330/Your_Only_Move_Is_HUSTLE/)
- [Characters — Unofficial YOMI Hustle Wiki](https://unoffcialyomihustlewiki.miraheze.org/wiki/Characters)
- [YOMI Hustle hustles your next move — CVHS Olympian](https://cvhsolympian.com/entertainment/2025/09/12/yomi-hustle-hustles-your-next-move/)
- [Motion-Matching in Ubisoft's For Honor — Game Anim](https://www.gameanim.com/2016/05/03/motion-matching-ubisofts-honor/)
- [Art of Battle — For Honor Wiki](https://forhonor.fandom.com/wiki/Art_of_Battle)
- [For Honor Info Hub — General Info / Frame Data](https://forhonorinfohub.com/generalinfo)
- [Public Test – Meta Changes — Ubisoft](https://www.ubisoft.com/en-us/game/for-honor/news-updates/1IZoiczWorTTTsrEYprgzR/public-test-meta-changes)
- [Season 2 - Gear Stats Revamp — Ubisoft](https://www.ubisoft.com/en-us/game/for-honor/news-updates/KlOwEJjTxqQtGOQVe4gCO/season-2-gear-stats-revamp)
- [Rock Paper Guard Breaks — Game Developer](https://www.gamedeveloper.com/design/rock-paper-guard-breaks-a-mechanics-deep-dive-into-for-honor)

## YOMI Hustle Findings

### Core Loop
- Turn-based frame-by-frame fighting game. Both players simultaneously choose their next action from a menu, then the game resolves a short real-time segment.
- No execution barrier: every move is selected from an accessible menu rather than performed with precise inputs.
- Live frame data, hitbox display, and after-image visualization are built-in, making every exchange readable and analyzable.
- Replay is a first-class feature: every match is recorded and can be replayed at full speed or analyzed frame-by-frame.

### Roster & Actions
- Five base characters: Ninja, Cowboy, Wizard, Robot, Mutant.
- Each character has a "large menu with over 20 different attack options" varying in speed, power, and combo potential.
- Characters have hard counters (e.g., Cowboy is described as a counter to Wizard).
- Strong mod support via Steam Workshop; custom characters can be allowed or banned in multiplayer.

### Modes & Expression
- PvP, vs CPU, sandbox "choreography" mode, and online lobbies.
- Deep character customization (sliders, color wheel).
- Marketed as: "No training mode required."

### Relevance to Just Dodge
- Confirms that a simultaneous-reveal, menu-driven fighting game can be deep and commercially viable.
- Just Dodge deliberately narrows the action count to a 13-action matrix to keep each action physically distinct and matchup-unique.
- Replay, hitbox visualization, and frame-data readability are not optional polish; they are core to the genre promise.

## For Honor Findings

### Core Loop
- Real-time 3D melee dueling with a three-direction guard/stance system (top, left, right).
- Actions: Light Attack, Heavy Attack, Guard Break, Parry, Feint, Dodge (with I-frames), Zone Attack.
- Stamina, Revenge meter, Hyper Armor/Uninterruptible Stance, Deflect, Superior Block, Bleed, and environmental hazards.

### Frame Data Culture
- Competitive play is built on precise frame counts:
  - Parry window: 300–100 ms before impact.
  - Guard Break: 400 ms (300 ms after a feint).
  - Counter Guard Break window: 300 ms.
  - Light parry stagger: 900 ms; Heavy parry stagger: 600 ms.
  - Dodge I-frames: 166–300 ms.
- Frame advantage/disadvantage, chain links, recovery cancels, and hit/block stun levels are all documented by the community.

### Animation & Trajectory
- Motion matching drives locomotion, not combat moves.
- Combat is state-machine based; animators mark animation events at significant moments (e.g., sword connects).
- Trajectory is simulated; animation is "a cosmetic detail on top" of the simulated point.
- Character center-of-mass is clamped to ~15 cm around the simulated point.

### Armor & Damage
- For Honor does **not** simulate deep materials. Damage reduction is a gear stat:
  - Weapon parts carry Attack.
  - Armor parts carry Defense.
  - Defense Penetration reduces the opponent's Defense stat.
  - Damage reduction perks, feats, and revenge buffs modify outcomes.
- Armor visuals are distinct but the combat model is stat-based.

### Known Meta Problems
- **Turtle / Defensive Meta:** defense was stronger than offense because parry rewarded too much, guard break was too dominant, and chip damage was negligible.
- Ubisoft's Public Test Meta Changes addressed this by:
  - Reducing parry reward (no guaranteed GB).
  - Standardizing GB vulnerability on all attacks to 0–100 ms.
  - Pausing stamina regen on block/dodge.
  - Raising chip damage to 18%.
  - Making Out-of-Stamina more dangerous.

### Relevance to Just Dodge
- For Honor proves that readable stances, weighty attacks, and frame-precise combat create a satisfying melee feel.
- Just Dodge must match or exceed For Honor's visual/physical readability while avoiding its turtle-meta problem. The simultaneous-reveal loop is the chosen solution: there is no post-commit reaction, so defensive play cannot degenerate into pure reaction.
- For Honor's stat-based armor is a ceiling Just Dodge must break: the design requires deep material simulation (PBD cloth/leather, chainmail constraints, plate FEM, brittle fracture).
- For Honor's animation-event timing validates Just Dodge's plan to derive hitbox active frames from MotionBricks poses, but Just Dodge goes further by making the pose itself the source of geometry-accurate proxies.

## Comparative Design Table

| Dimension | YOMI Hustle | For Honor | Just Dodge (planned) |
|---|---|---|---|
| **Time structure** | Turn-based, simultaneous reveal per short segment | Real-time continuous | Turn-based, simultaneous reveal per exchange |
| **Input model** | Menu selection | Real-time stick/button inputs | Menu/commit one action per exchange |
| **Action count** | 5 characters, 20+ options each | Hero-specific chains/movesets | 13-action matrix shared by all fighters |
| **Stance/guard** | Positioning + move selection | 3-direction guard | 3-direction guard tied to action matrix |
| **Motion engine** | Hand-drawn/Godot animation | Motion matching + state machine clips | MotionBricks generative motion only |
| **Hitboxes** | Visible, exact 2D shapes | Animation-event driven 3D arcs | Geometry-accurate proxies from MotionBricks pose |
| **Armor model** | None / HP only | Stat-based Defense / Defense Penetration | Deep material simulation (PBD, FEM, fracture) |
| **Injury model** | HP / knockback | HP + stamina + bleed | Localized tissue injury, capability loss |
| **Replay** | First-class, built-in | Available | Deterministic fight film + replay theater |
| **Turtle meta risk** | Low (no reaction after commit) | High (historic problem) | Low by design |
| **Mod support** | Extensive Workshop support | Limited cosmetic | De-scoped before vertical slice |
| **Networking** | Online lobbies | P2P/server | De-scoped before vertical slice |

## Implications for Just Dodge

1. **Keep the 13-action matrix tight.** YOMI shows that 20+ options per character can work, but Just Dodge's promise is physical fidelity. Each action must be visually and mechanically distinct; 13 is the ceiling, not a starting point for bloat.

2. **Make frame data visible from day one.** The hitbox display, active frames, and after-image preview are core to the genre. They must be implemented as presentation features reading from truth, not as post-launch debug tools.

3. **Avoid the turtle meta through loop design, not balance patches.** Simultaneous reveal removes the reaction window that makes For Honor's defense oppressive. Do not add parry-on-reaction mechanics that reintroduce turtle play.

4. **Armor must be materially deep to differentiate from For Honor.** A stat-based armor system would make Just Dodge look like a lesser For Honor. PBD cloth/leather, chainmail ring networks, plate FEM, and brittle fracture are required differentiators.

5. **MotionBricks must carry the full combat motion burden.** For Honor separates locomotion (motion matching) from combat (state machine clips). Just Dodge has no such separation: every stance, idle, attack, block, hit reaction, and injury pose must come from MotionBricks or the design collapses.

6. **Replay is not a stretch goal.** The simultaneous-reveal loop produces "I knew you would do that" moments; replay must capture and present them with exact truth reconstruction.

## OATHYARD vs. Just Dodge: Missing / Incomplete Features

Lessons from `docs/LESSONS-FROM-OATHYARD.md` show that OATHYARD already proved:
- Truth isolation and deterministic truth hashes.
- MotionBricks-based animation.
- The simultaneous-reveal YOMI loop.
- Replay evidence.
- A 13-action matrix.
- Deterministic AI.

What is **not yet present** in the current `src/` baseline versus the locked design:

| Feature | OATHYARD status | Current Just Dodge `src/` | Gap severity |
|---|---|---|---|
| Truth-isolated combat state | Proven | Only placeholder opponent timer in `main.rs` | High |
| 13-action matrix | Implemented | Only 3 stub actions in `combat.rs` | High |
| MotionBricks driving every action | Proven | Only idle/walk clip loaded; actions not wired | High |
| Geometry-accurate hitbox proxies | Proven | No hitbox system in renderer/combat | High |
| Deep armor/material simulation | Proven | Not implemented | High |
| Localized injury system | Proven | Not implemented | High |
| Simultaneous-reveal input/commit | Proven | Real-time WASD + intent logging only | High |
| Replay/fight film | Proven | Telemetry JSONL only | Medium |
| Deterministic AI | Proven | Not implemented | Medium |
| PresentationBricks `truth_mutation` flag | Proven | Not implemented | Medium |

The codebase is currently a rendering and MotionBricks-loading baseline, not a playable loop. The design is sound and research-backed; the next stage is to implement the 3-action prototype loop inside the truth-isolated architecture before expanding to 13 actions.

## Open Questions Answered by Research

- **Does YOMI Hustle really have 13 actions?** No — it has 5 characters with 20+ options each. Just Dodge's 13-action matrix is a deliberate, smaller universal set.
- **Does For Honor have deep material simulation?** No — it is stat-based. Just Dodge's material simulation is a deliberate overreach.
- **How does For Honor avoid hitbox/visual mismatch?** It doesn't always; community frame-data resources exist precisely because players care about phantom range and hitbox accuracy. Just Dodge's parity mandate is a direct response to this pain point.
- **Does For Honor use rollback?** Public sources do not detail its netcode. The lesson for Just Dodge is to defer networking until the local simulation is deterministic and fun.

## Next Design Step

The research supports the locked canon. No canon amendments are required. The next step is implementation of the 3-action prototype (Strike / Block / Grab) with:
1. A truth-isolated combat state machine.
2. MotionBricks-generated poses for each action.
3. Geometry-accurate hitbox proxies from those poses.
4. A simultaneous-reveal input/commit phase.
5. Deterministic resolution and replay recording.
