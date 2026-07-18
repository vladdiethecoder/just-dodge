# Anime-Cinematic Neural Combat Stylization Pipeline

**Date:** 2026-07-17  
**Status:** research recommendation / presentation and training plan; not an admitted runtime feature.  
**Scope:** make a neural, physics-executed combat performance read as deliberate anime animation—not as raw realistic mocap—without allowing visual polish to create contacts, injuries, or outcomes.

## Outcome

Use a **two-lane stylization stack**:

1. **Pre-physics, learned pose style**: train an interaction-conditioned MotionBricks extension to express a continuous anime-style latent in its root and pose predictions; the active ragdoll tracks the resulting target under its existing bounded physics rules.
2. **Post-physics, event-locked presentation**: render stepped timing, trajectory-derived smears/afterimages, impact frames, camera impulses, VFX, and audio only from sampled skeleton history and real `ImpactEventV1` records.

The first lane changes *how a lawful intent is expressed*. The second changes only *how the already-simulated action is photographed*. Neither may turn a whiff into a hit or overwrite physics.

---

## 1. Project anchors and non-negotiable boundary

The repository already has the correct authority direction:

```text
public state / intent / geometry
  -> ARDY proposal -> MotionBricks target window -> sealed MotionPlanPacketV1
  -> active-ragdoll motor targets -> deterministic articulated physics
  -> sampled skeleton + measured ImpactEventV1
  -> anime presentation graph -> wgpu draw commands
```

Relevant anchors:

- `docs/quality/ADVERSARIAL_VISUAL_CONTRACT.md:45-65`: asynchronous packets, presentation-only interpolation, packet/replay provenance, and mandatory visual gates.
- `docs/design/ONLINE_MOTIONBRICKS_INTERACTION_SOLVER.md:30-46`: released MotionBricks exposes only sparse boundary conditioning and **cannot** currently consume interaction state or mid-horizon changes. Anime conditioning therefore requires a trained extension; it is not a post-decode IK patch.
- `src/motion_plan.rs:182-200`: `MotionPlanPacketV1` is the neural-to-controller boundary.
- `src/motion_plan.rs:355-382`: `ImpactEventV1` has a truth tick, contact ID, point, impulse, energy, relative velocity, material bits, severity, and sides. This is the correct sole source for impact presentation.
- `src/main.rs:1386-1457`: the current camera nudge and eight-line burst are useful proofs of wiring, but are fixed phase-driven presentation rather than an extensible impact graph.
- `src/renderer.rs`: the present wgpu renderer has skinned joint buffers, depth, debug lines, and per-actor model state. It does **not** yet have render-target history, velocity buffers, instanced ghosts, toon/outline, or a particle system.

### Hard rule

Never use a presentation effect to alter physics time, root position, motor target, collision proxy, damage, contact window, or replay result. In particular, global `dt = 0` hit-stop is forbidden. The 120 Hz/60 Hz truth world must continue exactly as recorded; only a render-local sampling clock may pause or slow.

---

## 2. Translate 2D/anime principles into 3D neural target and presentation controls

Anime combat is not simply "more motion." It selectively makes poses, rhythm, silhouettes, and impact evidence legible. The table converts that grammar into controls that do not require a hand-authored action bank.

| 2D principle | Target-side expression (learned / controller-tracked) | Presentation-side expression (render only) | Do not do |
|---|---|---|---|
| **Readable key pose / line of action** | Train for a larger pose-space separation between Guard, Windup, Contact, and Recovery; expose head/chest/hand/weapon constraints and a line-of-action feature. | Briefly favor the silhouette at anticipation/contact: rim, outline/value separation, camera framing. | Rotate or teleport the executed skeleton after physics merely to improve a screen silhouette. |
| **Anticipation** | Condition duration and pre-contact pose on a phase curve; load hips/spine opposite the strike while feet/COM remain feasible. | Small pre-hit vacuum/speed-line suppression; no contact flash before measured impact. | Spawn sparks, hit-stop, or damage sound from `DesiredContactV1`. |
| **Fast spacing / slow pose** | Learn phase-aware velocity and jerk profiles: linger in readable setup, traverse the in-between rapidly, settle in recoil. | Sample on ones during fast transition, on twos/threes during holds; enable short camera/exposure pulse only at a real impact. | Lower deterministic simulation rate or mutate packet sample times. |
| **Overshoot and settle** | Include controlled wrist/weapon/spine overshoot and recovery features in targets; physics may attenuate them. | Decaying afterimage/ribbon and small secondary particles from observed velocity. | Add a fake second collision or a second impulse. |
| **Squash/stretch and smears** | Prefer body/weapon path, arc, and pose exaggeration in the target; use explicit authorized assist only for an actual special-art mechanic. | Render a temporary, velocity-derived proxy/mesh; never deform collision or the accepted body mesh. | Scale the body collider or weapon sweep volume. |
| **Impact frame / hold** | Train a stable impact-adjacent pose but let the solver determine whether contact occurs. | Freeze the *rendered actor pose* for a few display frames, color flash, ink burst, audio transient—all keyed by `contact_id`. | Freeze physics, input, netcode, or all gameplay actors. |
| **Follow-through / drag** | Train phase-continuous end-effector and root targets; active ragdoll supplies physical lag. | Weapon ribbon, hair/cloth secondary sim, then sparse ghost copies from sampled history. | Play a fixed recovery clip. |

### Recommended style vocabulary

Do not use a discrete `anime_move_17` class. Use a normalized continuous `AnimeStyleV1` descriptor, supplied by a reference encoder during training and represented as a versioned vector at inference:

```text
[anticipation_fraction,
 hold_fraction,
 contact_snap,
 spacing_sharpness,
 overshoot_amount,
 settle_decay,
 silhouette_extension,
 torso_counter_rotation,
 hip_drop,
 weapon_arc_bias,
 airborne_assist_request,
 camera_energy,
 linework_density,
 afterimage_density]
```

Only the first ten can affect target generation; they must be bounded and conditioned on action/geometry. The last four are presentation preferences and must not enter the controller or truth packet. A production receipt includes style-encoder/model/version/reference hashes, never a title, episode, character, clip, or reusable pose ID.

---

## 3. Concrete real-time wgpu presentation pipeline

### 3.1 Data flow and cadence

Run truth and presentation independently:

```text
120 Hz deterministic physics
  -> immutable sampled pose / weapon transforms / contact events
  -> render snapshot ring (previous 6–8 poses, transforms, velocity estimates)
  -> presentation clock + event state (not simulation state)
  -> scene, ghost, smear, particle, line, impact-composite passes
```

- The renderer may interpolate two sampled physical poses at display rate, but records the source truth ticks.
- A local presentation freeze means `render_pose_time` remains at the last sampled pose for `N` display frames. It does **not** stop receiving or recording truth snapshots.
- At resume, interpolate/snap according to an explicitly tested policy. For an anime impact, a one-frame snap is intentional; do not conceal a large truth gap with generic motion blur.
- All effect instances carry `source_contact_id: Option<u64>` or `source_truth_tick`; an orphaned impact effect is a test failure.

### 3.2 Recommended passes, in order

1. **Depth/ID/velocity prepass**
   - Output linear depth, actor/object ID, world normal, and per-pixel velocity from current versus prior *sampled* skinned transforms.
   - This makes screen-space effects local to a striking limb/weapon instead of blurring the whole fight.
2. **Opaque toon/silhouette pass**
   - Quantized diffuse bands, controlled rim, and a stable outline derived from depth/normal/ID discontinuities.
   - Keep the palette/value hierarchy readable before adding effects; effects cannot repair an unreadable Windup.
3. **Trajectory smear pass**
   - Draw transient geometry from observed transforms. See variants below.
4. **Afterimage pass**
   - Draw 2–5 instanced, skinned historical palettes with premultiplied alpha, palette ramp, and optional dither. Depth-test against the current world, normally no depth write.
5. **Impact/VFX pass**
   - Instanced sparks, debris, speed lines, shock rings, ink splats, and material-specific burst shapes, all created from one `ImpactEventV1`.
6. **Composite pass**
   - At an impact, use an extremely short localized flash, radial line mask, optional chromatic split, and controlled bloom. The full screen should not become a permanent noisy filter.
7. **UI/audio submission**
   - UI marks/foley use the same contact ID and truth tick. Accessibility settings independently suppress shake, flash, blur, and distortion without changing combat.

### 3.3 Smear implementations (ship in this order)

**A. Weapon ribbon — first production slice**

- Sample blade base/tip at `t-1` and `t`; build a quad/strip `[base_prev, tip_prev, tip_now, base_now]` plus two width-expanded side strips.
- Width = `clamp(speed * k, min_width, max_width)`; alpha/ink ramp fades along normalized path length.
- Use the observed socket/weapon transform, not an attack label. Clip the ribbon against depth; retain a coarse blue-noise/dither edge so it reads as drawing rather than transparent glass.
- Emit only when angular or tip speed crosses a measured threshold, and only for 2–4 presentation frames.

**B. Limb smear proxy — second slice**

- Create a camera-facing capsule/cone between historical and current hand/foot/wrist anchors. It is a separate `SmearInstance`, not a scaled skinned mesh.
- Mask it by actor ID/depth so it cannot cross foreground geometry. Bind it to a source bone/path tick, duration, palette, and optional contact ID.
- Use it sparingly: only commitment transition/impact, never continuously during locomotion.

**C. Screen-space velocity smear — polish slice**

- Use actor/object ID, depth, and velocity buffers to gather along the motion direction only for a tagged actor/weapon mask.
- Clamp length, stop at depth discontinuities, and quantize/dither the result. Generic full-scene motion blur is the wrong aesthetic because it erases the key silhouette rather than emphasizing it.

### 3.4 Impact frame and afterimage policy

| Event severity (from measured energy/impulse/severity) | Render freeze | Camera impulse | Ghosts | Impact frame | Example VFX |
|---|---:|---:|---:|---:|---|
| Whiff / no `ImpactEventV1` | none | none or path-only | optional path ghost | none | air ribbon only |
| Light | 1 display frame | tiny, directional | 0–1 | localized 1-frame | 4–8 sparks/ink flecks |
| Medium | 2 display frames | short band-limited kick | 1–2 | localized 1-frame + ring | 12–24 sparks, short arc |
| Heavy | 3–5 display frames | directional translation/rotation, clamped | 2–4 | one-frame high-contrast silhouette/flash | shock ring, debris, strong material burst |

These are initial hypotheses, not gameplay constants. Tune in milliseconds and pixels on target hardware, retain an accessibility multiplier, and cap concurrent effect instances. A heavy effect must still be readable with flash/shake/afterimages disabled.

### 3.5 Rust-facing API sketch

Keep this in a renderer-only crate/module; it must have no mutable reference to `Match`, physics, or plan packets.

```rust
pub struct RenderPoseSample {
    pub truth_tick: u64,
    pub actor: Side,
    pub joint_palette: Vec<glam::Mat4>,
    pub weapon_base_world: glam::Vec3,
    pub weapon_tip_world: glam::Vec3,
}

pub struct PresentationImpact {
    pub contact_id: u64,
    pub truth_tick: u64,
    pub point_world: glam::Vec3,
    pub impulse_world: glam::Vec3,
    pub energy_mj: u32,
    pub severity_q16: u16,
    pub material_failure_bits: u16,
}

pub enum AnimeFxKind { WeaponRibbon, LimbSmear, Ghost, InkBurst, ShockRing, CameraKick }

pub struct AnimeFxInstance {
    pub kind: AnimeFxKind,
    pub source_contact_id: Option<u64>,
    pub source_truth_tick: u64,
    pub age_frames: u8,
    pub lifetime_frames: u8,
    pub actor: Side,
    pub palette_index: u8,
}
```

`PresentationImpact` is created by a pure conversion from `ImpactEventV1`; its `contact_id` must be deduplicated. `RenderPoseSample` comes from sampled execution after retargeting. The GPU receives POD/instanced versions of these structures; no WGSL stage reads simulation state or computes game outcomes.

Suggested first files, once implementation is authorized:

- `src/anime_presentation.rs`: bounded history ring, deterministic event-to-effect translation, deduplication, and unit tests that prove it does not mutate truth.
- `src/renderer.rs` (or a renderer submodule during a renderer refactor): effect buffers/pipelines and a velocity/ID/depth pass.
- `assets/shaders/anime_effects.wgsl`: ribbon, ghosts, impact line/ink shaders; keep source in WGSL for wgpu backend parity.
- `tests/anime_presentation.rs`: no effect for a whiff; exactly one effect graph for duplicate contact ID; presentation state leaves truth hashes unchanged; every impact child references an existing event.

---

## 4. Physics-driven combat juice: bind it to the measured event, not the intent

### Event graph

```text
ImpactEventV1(contact_id, tick, point, impulse, energy, material, severity)
  -> presentation classification (pure, bounded, deterministic)
  -> [camera impulse, render-pose hold, VFX batch, audio batch, controller-gain softening]
```

- **Controller gain softening** is only valid if it is a declared physical consequence of the measured event and part of the deterministic physics/replay contract. It is not a visual effect and must be separately tested.
- Camera shake is directional: project the measured impulse into camera right/up/forward, use band-limited noise or a critically damped impulse, and clamp translation/rotation. `src/main.rs` currently uses a phase-indexed pattern; replace it only with this event-derived path.
- Scale effects from log-bucketed measured energy/impulse and material bits. Do not infer strength from `Action`, `DesiredContactV1`, or a neural prediction.
- Spawn VFX at actual contact point and orient shock rings/debris by contact normal/impulse. If the solver has no normal yet, expose it in a future event version rather than inventing one in rendering.
- Keep impact effects separately disableable. Camera shake, flashes, chromatic distortion, motion blur, and screen clutter require accessibility controls; none may alter timing/input/physics.

### Why presentation-only hit-stop is essential here

A fighting game can use global simulation hit-stop, but Just Dodge has deterministic two-agent physics, asynchronous packet validity, and replay. Pausing only one actor or the entire solver would modify collision timing and invalidate the strict truth boundary. The safe equivalent is:

1. continue all truth ticks and snapshot capture;
2. hold selected rendered pose(s) and camera for 1–5 display frames;
3. enqueue the effect with the event ID;
4. resume presentation from recorded truth snapshots.

This produces the perceptual punctuation without changing the physical exchange.

---

## 5. Condition a neural model for exaggerated anime poses

### What does not work

- **Do not post-decode rotate limbs toward an anime pose.** It violates the project’s conditioned-generation rule, destabilizes the active ragdoll, and makes contact/retarget errors untraceable.
- **Do not send a text prompt such as “anime punch” to released MotionBricks.** The released public wrapper has no verified interaction/text channel and only carries four start/four end frames.
- **Do not train on anime video as if it were accurate 3D physics.** Perspective cheats, cuts, omitted limbs, held drawings, and smears are valuable supervision but are not automatically joint targets or contact truth.
- **Do not style on an action label alone.** It produces a small named-action library rather than context-dependent emergent combat.

### Training representation

Add three trainable inputs to the planned interaction extension, with the same temporal sequence supplied to the root and pose backbones:

```text
interaction_continuous: [B, T, C]   # existing live geometry/state/intent plan
style_latent:           [B, T, 64]  # continuous reference-derived or annotated vector
phase_features:         [B, T, 12]  # guard/windup/commit/contact-permitted/recovery + timing curve
style_valid:             [B, T]     # source confidence / masking
```

`style_latent` is generated by an offline encoder trained on content-preserving motion windows. For a first experiment it may be a supervised descriptor computed from motion/2D labels rather than a large learned model. Its dimensions should include:

- normalized limb extension, elbow/knee openness, torso/head counter-rotation, root lean, and weapon arc curvature;
- anticipation/hold/commit/recovery duration fractions;
- speed and jerk distribution by phase, overshoot amplitude, settle decay, and contact-adjacent pose delta;
- 2D silhouette area, line-of-action angle, hand/weapon screen-space arc, and left/right asymmetry under canonical cameras;
- physical tracking difficulty: COM margin, foot slip, torque saturation, grip residual, and required authorized-assist indicator.

### Model modification

1. Encode a style reference/descriptor into `z_style` (64–128 dimensions), then project it per token/frame.
2. Add a learned phase/time embedding and interaction embedding to **both** MotionBricks root and pose transformers before their prediction blocks.
3. Start with low-rank adapter/FiLM modulation on attention/MLP layers; this is less destructive than retraining the VQVAE vocabulary. Style-SALAD provides a relevant mechanism: global style embedding -> hypernetwork -> LoRA updates, with a contrastive style space. It is evidence for an offline experiment, not a drop-in MotionBricks runtime module.
4. Produce pose/root targets as usual; retain deterministic argmax token decode for truth-facing validation.
5. Train the active-ragdoll tracker on the same target distribution, including perturbation/recovery. If tracking erases the exaggeration, the right fix is tracker training or explicitly authorized assistive-actuator research—not render cheats.

### Data pipeline

```text
licensed mocap / stunt / simulation / original animation
  -> retarget + contacts + dynamics labels                 (strong 3D supervision)
licensed anime / game cinematics / hand-drawn fight footage
  -> shot segmentation + 2D body/weapon tracks + camera/flow
  -> confidence-scored 3D lift + rig/ground/interaction fit (weak 3D supervision)
  -> separate timing / pose / silhouette / smear / camera / VFX labels
  -> source-disjoint train / validation / held-out titles-fights
  -> style-conditioned MotionBricks extension + tracker training
```

Anime footage should chiefly supervise **timing, projected silhouette, arcs, pose contrast, camera grammar, and presentation labels**. Admit it as 3D target supervision only when rig/camera fit, contact/support checks, and inverse-dynamics residuals pass. Preserve smears and impact frames as labels for the presentation lane rather than forcing them into the skeleton.

### Losses and constraints

Use a content/style crossing protocol, not one monolithic realism loss:

```text
L = L_motion_reconstruction
  + λc L_interaction_constraint
  + λp L_phase_timing
  + λs L_style_contrastive
  + λ2d L_silhouette_and_arc
  + λf L_physics_trackability
  + λd L_style_content_disentanglement
```

- `L_interaction_constraint`: root/effector/weapon/grip/legality constraints only; never a label that says contact must succeed.
- `L_phase_timing`: preserve intended anticipation/commit/recovery ratios and hold placement.
- `L_silhouette_and_arc`: differentiable or offline rendered canonical-camera comparison, weighted by source confidence.
- `L_physics_trackability`: reject torque saturation, falls, foot slip, invalid ROM, grip loss, and unauthorized root assistance.
- `L_style_content_disentanglement`: same interaction with two styles must preserve valid task constraints; same style with varied interactions must preserve style descriptors.

For truly impossible moves (air dash, abrupt mid-air redirect), use a separately declared **authorized assistive impulse envelope**. Neural Assistive Impulses is relevant evidence that impulse-space assistance is more numerically stable than raw force spikes for exaggerated physics tracking. It is not a justification to teleport or to guarantee a hit. The impulse request, bounds, applied values, and downstream solver result require replay receipts.

---

## 6. Useful game references, with evidentiary limits

### Arc System Works / Dragon Ball FighterZ lineage

The strongest primary implementation source found is Junya C. Motomura’s **GDC 2015 Guilty Gear Xrd** talk. Arc System Works describes the goal as rebuilding a classic 2D fighter in a full 3D framework while retaining its 2D character. This is a strong design precedent for:

- artistically controlled camera-space silhouette rather than physically neutral viewing;
- selective posing/timing/material/lighting decisions that make 3D read like a drawing;
- treating the 3D rig as a means to a 2D-readable final image.

The reviewed source is for Xrd, not a complete technical disclosure of Dragon Ball FighterZ. Therefore do **not** claim undocumented DBFZ internals as fact. The practical transfer is to give Just Dodge a camera-aware *presentation* lens and canonical silhouette tests, while the actual executed skeleton and contact remain physics-derived.

### Genshin Impact

miHoYo’s **GDC 2021 “Crafting an Anime Style Open World”** explicitly frames Genshin as a non-realistic anime world and covers character/stage design, pipeline, and anime-style NPR composition/execution. It supports the broader lesson: anime feel is a system-wide value hierarchy, character readability, composition, and non-photoreal rendering direction—not a single cel-shader effect.

Transfer to combat:

- create stable value grouping, silhouette contrast, material/color language, and readable VFX hierarchy before increasing temporal effects;
- make Windup/recovery readable at combat FOV before any flash, shake, bloom, or speed line;
- reserve bright/high-contrast effects for actual consequence events, so an onlooker can parse what happened.

The public source does not establish Genshin’s specific combat-animation implementation, so it must not be cited as proof of a particular hit-stop, smear, or neural-motion technique.

### Hi-Fi Rush

Hi-Fi Rush’s observable and publicly described differentiator is **global audiovisual rhythm synchronization**: character, enemies, environment, and feedback visibly move to a shared beat, with beat-oriented cues for player action. The transferable mechanism is a presentation rhythm lattice:

- retain free 120 Hz physical simulation and responsive movement;
- expose a beat phase to idle secondary motion, dust puffs, camera sway, color pulses, and non-contact cut timing;
- place an impact’s presentation punctuation at the next suitable display/beat subdivision only if it remains tied to its actual event tick;
- never delay, fabricate, or quantize a physical contact to satisfy music.

This yields coherence and intentionality without turning Just Dodge into a rhythm-rule combat game.

---

## 7. Three staged pipelines

### Pipeline A — Event-locked anime impact pass (first shippable experiment)

**Inputs:** executed skeleton/weapon history + `ImpactEventV1`.  
**Outputs:** directional camera kick, render-pose hold, weapon ribbon, burst lines/particles, optional afterimages/audio.  
**No model retraining. No truth mutation.**

1. Build a bounded `AnimePresentationState` with 8 pose samples per actor and a contact-ID dedupe set.
2. Convert a real impact to severity/material buckets. Whiff creates no impact frame/flash/shake.
3. Replace phase-derived `impact_camera_offset()` with a camera-space projection of event impulse.
4. Add weapon ribbon and ID/depth-tested shock-line pass; add ghosts only after current frame readability passes.
5. Capture presentation-on/off from identical replay packets; verify equal truth/replay hashes and one-to-one event/effect IDs.

**Keep gate:** in a 20-clip blind test, judges identify Windup vs Contact vs Recovery more accurately with the pass than without; zero orphan effect IDs; zero truth-hash changes; accessibility-off pass remains readable.

### Pipeline B — Stepped pose/silhouette film pass

**Inputs:** deterministic replay and its actual execution samples.  
**Outputs:** selective on-twos/on-threes, camera/composite retime, silhouette/outline, measured-path smears/afterimages.

1. Keep simulation samples at 120 Hz and camera truth at source tick.
2. Attach a render-only `PresentationTimingTrack` whose holds and step rate are bounded to declared windows (anticipation, impact, recovery); source tick range and replay hash are recorded.
3. Use ID/depth/velocity AOVs to protect silhouette; avoid full-frame blur.
4. Make every VFX/audio instance contact-locked; a speed-line-only whiff is allowed if it comes from a real weapon path and does not look like a hit.
5. Emit a contact sheet and video plus an effect provenance manifest.

**Keep gate:** no contact is hidden by camera/effect layers; all effect/contact boundaries map to an actual source tick; visual gate requirements remain satisfied with presentation disabled.

### Pipeline C — Learned anime motion adapter + physics tracker

**Inputs:** interaction sequence, continuous style latent, phase features, history, morphology/injury/weapon/geometry.  
**Outputs:** normal sealed transient motion plan -> active ragdoll -> measured execution.

1. Build source-disjoint, provenance-backed data shards and first train a descriptor/encoder on timing/pose/silhouette—not direct episode-to-pose imitation.
2. Add sequence style/phase conditioning to MotionBricks root + pose backbones and train a low-rank adapter baseline.
3. Train/validate on crossed content × style examples, perturbations, different weapons/stances/ranges/injuries, and unknown style references.
4. Train the tracker on the adapter’s target distribution; reject styles it cannot track rather than silently falling back to realistic motion.
5. Only after offline QA passes, export the adapted models and carry model/style/normalization receipts in motion requests/accepted packets.

**Keep gate:** held-out style improves pre-contact style/silhouette scores without regressions in contact legality, tracker falls, torque saturation, foot drift, grip error, plan latency, or replay determinism. A style swap must not alter outcome under identical packet/physics inputs.

---

## 8. Falsifiers and acceptance metrics

Reject or revise the relevant lane if any of these occur:

1. **Truth leakage:** presentation-on and presentation-off replay from identical packets produce different truth/contact/injury hashes.
2. **Fake-impact leakage:** a whiff gets flash/hit-stop/impact sound, or an impact effect lacks an existing `contact_id`.
3. **Readability failure:** blinded observers cannot classify pre-contact intent/phase from the actual combat camera, even if the effect-heavy final image looks impressive.
4. **Style-content entanglement:** changing style moves a weapon outside legal constraints, changes selected intent/outcome, or alters the relevant physics event for fixed controller input.
5. **Tracker collapse:** style improvement is accompanied by unacceptable falls, foot slip, grip/ROM error, torque saturation, or persistent visual target/execution divergence.
6. **Temporal artifact:** step/ghost/smear history causes camera-cut discontinuity, limb/weapon duplication outside its declared duration, TAA-like trails, or obscures decisive contact.
7. **Memorization:** a held-out title/fight/style produces a near-duplicate skeletal window, camera sequence, or source-specific design. Runtime has no source clip IDs or pose-cache lookups.

Report at minimum: pre-contact phase/intent accuracy, silhouette separation, style descriptor distance, 2D arc error, target-to-sim pose/grip/foot/COM residuals, motor saturation/fall rate, p50/p95 packet and render costs, effect count/frame, orphan-effect count, and presentation-on/off truth hash comparison.

---

## Primary and project sources

1. **MotionBricks** — Wang et al., 2026, project page: https://nvlabs.github.io/motionbricks/ . It documents a modular latent backbone, smart primitives, style-commanded locomotion examples, and the current preview-release status. It does not by itself prove anime/combat conditioning.
2. **Unpaired Motion Style Transfer from Video to Animation** — Aberman et al., SIGGRAPH 2020, https://arxiv.org/abs/2005.05751 . Separates content/style latents, uses AdaIN, and can obtain style from 2D video keypoints; useful for the offline style-encoder/data approach.
3. **Stylized Text-to-Motion Generation via Hypernetwork-Driven Low-Rank Adaptation** — Jeon et al., SIGGRAPH 2026, https://arxiv.org/abs/2605.13333 . Provides the reference-style embedding -> hypernetwork LoRA mechanism; validate independently before adoption.
4. **MaskedMimic: Unified Physics-Based Character Control Through Masked Motion Inpainting** — Tessler et al., SIGGRAPH Asia 2024, https://arxiv.org/abs/2409.14393 . Evidence for one physics controller accepting partial/keyframe/object/text control, not proof of combat outcome control.
5. **Neural Assistive Impulses: Synthesizing Exaggerated Motions for Physics-based Characters** — Wang and Benes, 2026, https://arxiv.org/abs/2604.05394 . Relevant only for explicitly authorized, bounded nonphysical special-art assistance.
6. **GuiltyGearXrd’s Art Style: The X Factor Between 2D and 3D** — Motomura, Arc System Works, GDC 2015: https://gdcvault.com/play/1022031/GuiltyGearXrd-s-Art-Style-The . Primary visual-art direction precedent; not a DBFZ implementation specification.
7. **Genshin Impact: Crafting an Anime Style Open World** — Cai, miHoYo, GDC 2021: https://gdcvault.com/play/1027539/-Genshin-Impact-Crafting-an . Primary source for non-realistic/anime composition, design, and NPR pipeline framing; not a public combat-animation internals disclosure.
8. `docs/quality/ADVERSARIAL_VISUAL_CONTRACT.md`, `docs/design/ONLINE_MOTIONBRICKS_INTERACTION_SOLVER.md`, `src/motion_plan.rs`, `src/main.rs`, and `src/renderer.rs` in this repository.
