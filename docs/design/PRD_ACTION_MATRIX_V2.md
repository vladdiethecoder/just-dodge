# PRD: 9-Action Universal Combat Matrix (MotionBricks-Only Expansion)

## 1. Purpose

Expand Just Dodge from the current 3-action prototype to a **9-action universal combat matrix** driven entirely by MotionBricks’ **full condition-to-pose pipeline**. All fighters share the same 9 actions; character identity comes from weapon archetype + armor weight loadouts. No prebaked animation clips, no motion fallbacks, and no oversized hitboxes.

## 2. Locked Design Decisions

| Decision | Value | Rationale |
|---|---|---|
| Action count | 9 universal actions | Validates the YOMI read loop without the 13-action authoring burden; canon remains 13 for later. |
| Character identity | Weapon + armor loadout only | Keeps the matrix readable; 4 weapons × 3 armors = 12 distinct builds. |
| Motion engine | Full MotionBricks root + pose + VQVAE pipeline | Encoder-only seeds bypass the generative model; the demo proves the full pipeline is the correct runtime path. |
| Primitive source | Real combat/weapon mocap, filtered/finetuned | No hand-authored joint-rotation seeds. Primitives are target *constraints*, not final clips. |
| Hitbox rule | Geometry-accurate proxies from generated pose | Perfect visual parity; ghost hits are build-blocking defects. |
| Fallbacks | None | Missing motion or broken parity blocks the build. |

## 3. Research Snapshot

### Your Only Move Is Hustle
- **Loop:** WEGO simultaneous reveal. Both players lock one action, the game resolves it frame-by-frame.
- **Input:** Menu-driven, no execution barrier.
- **Actions:** 5 characters with 20+ options each; high/low/throw guard triangle; parry, dodge, burst, DI.
- **Replay:** First-class, auto-recorded, shareable, frame-steppable.
- **Takeaway for Just Dodge:** expose frame data and prediction ghosts; keep reads clean; replay is core, not polish. ([YOMI Hustle Wiki](https://yomi-hustle.fandom.com/wiki/Your_Only_Move_is_Hustle), [Mizuumi How to Play](https://wiki.gbl.gg/w/YomiHustle/How_to_play))

### For Honor
- **Loop:** Real-time 3D melee with 3-direction guard (top/left/right).
- **Actions:** Light, heavy, guard-break, feint, dodge, zone, bash, parry, deflect.
- **Stamina:** attacks/feints/dodges cost stamina; out-of-stamina is dangerous.
- **Meta problem:** Turtle meta from parry being too rewarding; fixed by reducing parry reward and raising chip damage.
- **Takeaway for Just Dodge:** simultaneous reveal removes the reaction window that creates turtling; directional guard is readable but must not become execution-heavy. ([Art of Battle](https://forhonor.fandom.com/wiki/Art_of_Battle), [Ubisoft Meta Changes](https://www.ubisoft.com/en-us/game/for-honor/news-updates/1IZoiczWorTTTsrEYprgzR/public-test-meta-changes))

### OATHYARD (internal predecessor)
- Proved: truth isolation, deterministic truth hashes, 13-action matrix, MotionBricks presentation, simultaneous-reveal loop, replay evidence, deterministic AI.
- Lessons applied: no renderer-driven development, no placeholder UI in player mode, PresentationBricks must have `truth_mutation=false`, hold loops for every action.

## 4. Missing Features vs. OATHYARD (Current Gap)

| Feature | OATHYARD | Current `src/` | Gap severity |
|---|---|---|---|
| 9+ action matrix | 13 actions implemented | 3 stub actions | High |
| Full MotionBricks inference | Root + pose + VQVAE wired | VQVAE encoder/decoder only; root/pose models loaded but unused | High |
| Combat primitive library | Real mocap target primitives | Hand-authored joint-rotation seeds | High |
| Geometry-accurate hitbox proxies | Proven | None | High |
| Deep armor/material simulation | Proven | Not implemented | High |
| Localized injury | Proven | Not implemented | High |
| Simultaneous-reveal input/commit | Proven | Real-time WASD + intent logging only | High |
| Deterministic AI | Proven | Not implemented | Medium |
| Replay/fight film | Proven | Telemetry JSONL only | Medium |

## 5. The 9 Actions

| ID | Action | Beats | Loses To | Role |
|---|---|---|---|---|
| 01 | **Strike** | Grab, Feint, Lunge, Bash | Block, Riposte, DodgeAttack | Fast committed attack |
| 02 | **Block** | Strike, Thrust, Lunge | Grab, Feint, Bash | Defensive shell; enables Riposte |
| 03 | **Grab** | Block, Feint, Riposte | Strike, Thrust, DodgeAttack, Lunge, Bash | Clinch/break |
| 04 | **Thrust** | Grab, Feint, DodgeAttack, Lunge, Bash | Strike, Block, Riposte | Committed forward pierce |
| 05 | **Feint** | Block, DodgeAttack, Riposte | Strike, Thrust, Grab, Bash, Lunge | Fake-out punish |
| 06 | **DodgeAttack** | Strike, Grab, Lunge | Thrust, Feint, Block, Riposte, Bash | Evade + whiff punish |
| 07 | **Bash** | Block, Feint, DodgeAttack, Grab, Lunge | Strike, Thrust, Riposte | Guard-break / stagger |
| 08 | **Riposte** | Strike, Thrust, Bash, Lunge | Feint, DodgeAttack, Grab | Follow-up only |
| 09 | **Lunge** | Grab, Feint, DodgeAttack | Strike, Block, Thrust, Bash, Riposte | Closing committed attack |

### 5.1 Base 9×9 Matchup Matrix

Rows = player action **A**, columns = opponent action **B**. Each cell shows the outcome for **A**.

| A \ B | Strike | Block | Grab | Thrust | Feint | DodgeAttack | Bash | Riposte | Lunge |
|---|---|---|---|---|---|---|---|---|---|
| **Strike** | Clash | Beat | Hit | Hit | Hit | B-Hit | Hit | B-Hit | Hit |
| **Block** | Beat | Clash | B-GrabSuccess | Beat | B-FeintPunish | Whiff | B-BashSuccess | Whiff | Beat |
| **Grab** | B-Hit | GrabSuccess | GrabTech | B-Hit | GrabSuccess | B-Hit | B-BashSuccess | GrabSuccess | B-Hit |
| **Thrust** | B-Hit | Beat | Hit | Clash | Hit | Hit | Hit | B-Hit | Hit |
| **Feint** | B-Hit | FeintPunish | B-GrabSuccess | B-Hit | Whiff | FeintPunish | B-BashSuccess | FeintPunish | B-Hit |
| **DodgeAttack** | Hit | Whiff | Hit | B-Hit | B-FeintPunish | Whiff | B-BashSuccess | B-Hit | B-Hit |
| **Bash** | B-Hit | BashSuccess | BashSuccess | B-Hit | BashSuccess | BashSuccess | Clash | B-Hit | BashSuccess |
| **Riposte** | RiposteHit | Whiff | B-GrabSuccess | RiposteHit | B-FeintPunish | B-Hit | RiposteHit | Clash | RiposteHit |
| **Lunge** | B-Hit | Beat | Hit | B-Hit | Hit | Hit | B-BashSuccess | B-Hit | Clash |

Legend:
- **Hit / B-Hit:** attacker lands; `B-Hit` means the opponent lands.
- **Beat:** defender wins; attacker loses tempo/stamina, no health damage.
- **Clash:** both attacks/defenses collide; mutual stamina loss.
- **Whiff:** no contact; minor stamina loss.
- **GrabSuccess / B-GrabSuccess:** grab lands; `B-` means opponent grabs.
- **BashSuccess / B-BashSuccess:** bash lands; breaks guard or catches evasion.
- **FeintPunish / B-FeintPunish:** feint baits a defensive action and punishes.
- **RiposteHit:** riposte counter lands.
- **GrabTech:** both grabs neutralize each other.

## 6. Weapon Archetypes

Weapon identity modifies timing, range, force, damage type, and weapon-proxy geometry. The base matrix above assumes **Longsword** ranges.

| Archetype | Range | Speed | Force | Damage Types | Reads |
|---|---|---|---|---|---|
| **Longsword** | Medium | Medium | Medium | Slash + Pierce | Versatile; balanced tell |
| **Spear** | Long | Slow | Medium-High | Pierce | Tip-focused tell; dominates distance |
| **Dagger** | Short | Fast | Low | Pierce + Slash | Subtle, close-range tell |
| **Mace** | Short-Medium | Slow | High | Blunt + Bash | Heavy wind-up; armor-breaking |

### 6.1 Per-Action Timing Overrides (multipliers on base frames)

| Action | Longsword | Spear | Dagger | Mace |
|---|---|---|---|---|
| Strike | 1.0 / 1.0 / 1.0 | 1.2 / 1.1 / 1.0 | 0.7 / 0.8 / 1.0 | 1.3 / 1.0 / 1.2 |
| Thrust | 1.0 / 1.0 / 1.0 | 0.8 / 1.2 / 1.0 | 0.8 / 0.8 / 1.0 | 1.2 / 1.0 / 1.2 |
| Bash | 1.0 / 1.0 / 1.0 | 1.1 / 1.0 / 1.0 | 0.9 / 0.8 / 0.8 | 0.9 / 1.1 / 1.3 |
| Lunge | 1.0 / 1.0 / 1.0 | 0.9 / 1.1 / 1.0 | 0.8 / 0.9 / 1.0 | 1.1 / 1.0 / 1.2 |
| Riposte | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | 0.8 / 0.9 / 1.0 | 1.0 / 1.0 / 1.2 |

*(Format: startup / active / recovery multiplier.)*

### 6.2 Range Validity

Distance bands modify whether an action can even connect:

| Archetype | Too Close | Optimal | Too Far |
|---|---|---|---|
| Dagger | OK | OK | Whiff |
| Longsword | OK | OK | Minor whiff penalty |
| Spear | Severe whiff penalty | OK | OK |
| Mace | OK | OK | Whiff |

## 7. Armor Weights

Armor is independent of weapon and modifies protection, stamina, mobility, and noise.

| Weight | Stamina Cost | Stamina Regen | Speed | Protection | Noise | ROM |
|---|---|---|---|---|---|---|
| **Light** | ×0.9 | ×1.15 | ×1.10 | Low | Low | Full |
| **Medium** | ×1.0 | ×1.0 | ×1.0 | Medium | Medium | Minor shoulder/hip |
| **Heavy** | ×1.25 | ×0.85 | ×0.85 | High | High | Shoulder, hip, knee |

Armor does **not** change the action matrix; it changes tempo economy, effective force absorption, and MotionBricks ROM constraints.

## 8. Loadout Identity = Character

A fighter is defined by `(weapon, armor, cosmetic)`. Examples:

| Build | Weapon | Armor | Play Identity |
|---|---|---|---|
| Duelist | Longsword | Light | Fast reads, punishes mistakes |
| Hoplite | Spear | Medium | Distance control, reactive |
| Assassin | Dagger | Light | Close-range aggression |
| Warden | Mace | Heavy | Tanky, armor-breaking |
| Sentinel | Longsword | Heavy | Turtle-breaker, slow but protected |

No unique moves. Variety comes from timing, range, force, protection, and the YOMI reads those create.

## 9. MotionBricks Integration — Full Condition-to-Pose Pipeline

The current Rust code uses only VQVAE encoder/decoder on a hand-authored seed. The correct path is the same three-stage pipeline the interactive demo uses:

```text
Context frames (last 4 frames of current pose)
    +
Target primitive (4-frame peak window from combat mocap)
    ↓
Root backbone → predicted token count + global root trajectory
    ↓
Pose backbone → sampled pose tokens conditioned on root + target
    ↓
VQVAE decoder → reconstructed local/global pose features
    ↓
Parse → 34-joint world matrices → retarget → hitbox proxies
```

### 9.1 Combat Primitive Library

- Each primitive is a **4-frame target constraint** in MotionBricks feature space for one `(action, weapon, stance)` cell.
- Primitives come from **real combat/weapon mocap**, not authored rotations.
- Source pipeline: acquire mocap → retarget to G1Skeleton34 → compute MotionBricks features → segment by label → extract peak window.
- Primitive count for 9 actions × 4 weapons × 3 stances = **108 primitives** minimum. Stance variants may share the same primitive with rotation transforms if the mocap is symmetric; author duplicate only when needed.

### 9.2 Runtime Inference Steps

1. **Build context:** last `num_frames_per_token` frames of the fighter’s current pose (from idle, previous action, or recovery).
2. **Select primitive:** lookup `(action, weapon, stance)` from the primitive library.
3. **Apply weapon profile:** adjust target root displacement, heading change, and timing.
4. **Compute root trajectory:** use a critical-damping spring model (matching the demo) or an authored displacement curve to connect context root to target root.
5. **Normalize features** with dataset stats.
6. **Root backbone ONNX** (`motionbricks_root_backbone.onnx`) predicts `pred_num_tokens` and global root trajectory.
7. **Pose backbone ONNX** (`motionbricks_pose_backbone.onnx`) iteratively samples pose tokens.
8. **VQVAE decoder ONNX** reconstructs pose features.
9. **Unnormalize and parse** into 34-joint world matrices.
10. **Retarget + IK** to the mannequin skeleton; apply injury/ROM clamps.
11. **Generate hitbox proxies** from the skinned mesh.

### 9.3 No Prebaked Clips, No Fallbacks

- Primitives are **target constraints**, not final animation clips.
- Every displayed frame is generated at runtime by the model stack.
- If any model artifact is missing, corrupt, or produces non-finite output, the build/match fails. There is no procedural or authored clip fallback.

## 10. Hitbox Parity

- Hitbox proxies are generated from the **skinned mannequin mesh vertices** each active frame, not from abstract capsules or animation events.
- Weapon proxies are generated from the weapon mesh transformed by the hand/wrist joints.
- Proxy geometry must match the rendered mesh within a deterministic tolerance.
- A parity checker compares proxy AABB/vertex set to the rendered mesh and reports mismatches as build-blocking defects.
- No oversized hitboxes, no phantom range, no ghost hits.

## 11. Data & Finetuning Pipeline

### 11.1 Data Acquisition

| Source | Content | License Notes |
|---|---|---|
| CMU MoCap Database | Boxing, kicking, limited weapon-like motion | Free with attribution |
| Mixamo | Sword/shield/axe animations, blocks, stabs, swings | Royalty-free for embedded use; raw files cannot be redistributed |
| MoCap Online / Motus Digital | Ninja, sword, martial-arts packs | Commercial license included |
| BONES-SEED | MotionBricks’ 350k production corpus | Check [bones.studio/datasets](https://bones.studio/datasets) |

**Staged approach:**
1. **MVP:** Mine/filter CMU + Mixamo for the 9 actions across 4 weapons.
2. **Production:** Purchase focused MoCap Online packs for final fidelity.

### 11.2 Retargeting & Feature Extraction

1. Import source FBX/BVH into Blender/MotionBuilder.
2. Retarget to G1Skeleton34 T-pose (SOMA retargeter or project-local bone map).
3. Compute MotionBricks features: `ric_data`, `global_rot_data`, `local_vel`, `foot_contacts`, root.
4. Normalize with per-dataset `mean.npy` / `std.npy`.

### 11.3 Dataset Construction

Create `CombatMotionDataset` returning:

```python
{
  "keyid": int,
  "action": ActionId,
  "weapon": WeaponId,
  "stance": StanceId,
  "motion": Tensor[T, 414],  # normalized global rep
}
```

Target: ≥5–10 clips per `(action, weapon, stance)` cell for first playable; ≥20 per cell for production.

### 11.4 Model Adaptation

1. **Zero-shot validation:** Encode combat clips through the pretrained VQVAE, extract primitives, and run the pretrained pose/root models. Exposes quality gaps quickly.
2. **Finetuning:** Continue training pretrained VQVAE + pose + root on the combat dataset with low learning rate. This is the expected production path.
3. **From-scratch model:** Only if finetuning cannot reach fidelity; requires the largest dataset.

### 11.5 Primitive Extraction

- After adaptation, encode each labeled clip through the VQVAE.
- Extract the 4-frame window representing the action’s peak commitment.
- Store target pose features, target root trajectory, and metadata.
- Export updated ONNX artifacts for the game.

## 12. Staged Validation Gates

Every `(action, weapon, stance)` cell must pass:

1. **Generates valid frames** — no NaN/Inf, deterministic across runs.
2. **Unique 6-frame tell** — a human/QA agent can distinguish it from any other action in the first 6 frames.
3. **Hitbox parity** — proxy geometry matches rendered mesh within tolerance.
4. **Deterministic repeatability** — same seed + inputs produce identical frames and truth hash.
5. **Martial-arts quality** — weight transfer, hip drive, and recovery look authentic; no mannequin freezing.

No cell enters the playable matrix until it passes all five gates.

## 13. Implementation Phases (Agent-Swarm Friendly)

| Phase | Goal | Parallel Work Packages | Exit Gate |
|---|---|---|---|
| **0 — Data** | Acquire and retarget combat mocap to G1 | Agent A: source/ license audit; Agent B: retargeting pipeline; Agent C: feature extraction | Dataset with ≥5 clips per cell |
| **1 — Primitives** | Build primitive library and export ONNX | Agent A: VQVAE encoding/peak extraction; Agent B: ONNX export of full backbones; Agent C: stats/normalization | All 108 primitives + ONNX artifacts |
| **2 — Rust Inference** | Wire root + pose + VQVAE in Rust | Agent A: root backbone runtime; Agent B: pose backbone token sampling; Agent C: decoder + parsing | One action generates valid frames |
| **3 — Matrix** | Implement 9×9 resolver + timing data | Agent A: RON matrix + contact types; Agent B: weapon timing overrides; Agent C: armor/tempo modifiers | Unit tests cover every matrix cell |
| **4 — Hitbox Parity** | Geometry-accurate proxies + parity checker | Agent A: skinned-mesh proxy extraction; Agent B: weapon proxy; Agent C: parity report + QA capture | All cells pass parity gate |
| **5 — Systems** | AI, replay, injury, armor | Agent A: deterministic AI; Agent B: replay/fight film; Agent C: localized injury + armor truth | First playable duel end-to-end |

## 14. Dependencies

- `PRD_COMBAT_TRUTH.md` — state machine, resolver caller.
- `PRD_MOTION.md` — full condition-to-pose pipeline, retargeting.
- `PRD_ARMOR.md` — loadout protection, material thresholds.
- `PRD_INJURY.md` — localized consequences from matrix results.
- `PRD_STANCE_TEMPO.md` — stance availability and tempo gating.
- `PRD_AI.md` — AI uses the same matrix.
- `PRD_REPLAY.md` — records inputs and truth events.

## 15. Open Questions

1. Exact mocap source and license for redistribution — needs a provenance manifest before repo commit.
2. Whether to use the full-backbone ONNX files or reimplement embedding layers from `.npy` weights.
3. Whether stance variants need 108 distinct primitives or can share mirrored primitives.
4. Final timing numbers per weapon after MotionBricks motion analysis.

## 16. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** 9-action universal matrix, loadout-only identity, full MotionBricks condition-to-pose pipeline.
- **Rationale:** User canon: MotionBricks is the sole motion engine; no prebaked clips; perfect hitbox parity; combat eclecticism through weapon/armor loadouts.
- **Blocker:** Combat mocap acquisition/license + retargeting to G1Skeleton34 must finish before primitives can be built.
- **Status:** ACTIVE.
- **Next:** Write implementation plan and dispatch Phase 0/1 agents in parallel.
