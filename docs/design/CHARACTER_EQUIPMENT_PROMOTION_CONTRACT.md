# Character, Equipment, Grip, and Visual Promotion Contract

**Status:** Canonical cross-PRD contract. Fail closed.
**Authority:** `GAME_CANON.md` controls product intent. `../quality/ADVERSARIAL_VISUAL_CONTRACT.md` and its versioned threshold file control visual measurements. This document defines the character/equipment mechanism and evidence boundary; it does not weaken either authority.

## Why this contract exists

The July 20 adversarial audit proved that a plausible front render can conceal catastrophic parent-space, skin-weight, topology, armor-clearance, weapon-grip, camera, and engine-import failures. A still image is diagnostic evidence only. It cannot promote a body, rig, armor component, weapon attachment, motion stack, camera, or complete fighter.

The audit and its 1,000 traceable cells are recorded in `../JUST_DODGE_ADVERSARIAL_VISUAL_AUDIT.md`. Its failed captures remain negative evidence and may not be relabelled as successful candidates.

## Authority and data flow

```text
deterministic combat truth
  -> condition packet + contact constraints + equipment state
  -> live ARDY/MotionBricks proposal
  -> validated, quantized plan packet
  -> active-ragdoll motors + truth-owned contact solver
  -> one synchronized pose sample
  -> body skin, armor links/skin, weapon socket, proxies and rendering
```

Rendering, rig controls, neural motion, DCC meshes, thumbnails, cameras and AOVs never decide action, contact, damage, injury, armor failure or outcome. A pose-derived quantity may affect truth only through the versioned, hash-bound packet/contact contract defined by combat truth. There is no independent renderer-to-truth readback.

## One canonical character authority

Each promoted fighter has exactly one canonical anatomical carrier, one canonical deform skeleton, one bind-pose definition and one versioned mapping into the runtime skeleton.

Required invariants:

- no duplicate body, armature, armature modifier, deform path or parent chain;
- applied object transforms and explicit parent inverses/local matrices;
- finite inverse binds and deterministic bone order/IDs;
- anatomical joint centers and finger segment lengths checked in orthographic views;
- zero unweighted deform vertices;
- at most four normalized influences per rendered vertex unless the versioned cooker contract explicitly proves another limit;
- no cross-limb influence outside declared twist/bridging regions;
- forearm, upper-arm, thigh and calf twist distributed by declared deform bones, not by accidental parent rotation;
- source rigs remain adapters; only the admitted runtime mapping is authoritative.

## Attachment classes

Every visible component declares exactly one attachment class. Combining classes implicitly is forbidden.

### 1. Deforming body or soft layer

Skin to declared deform bones with normalized sparse weights. This class is for anatomy, undersuit, flexible straps, leather, cloth or other components that must deform continuously.

Acceptance requires zero unweighted vertices, the influence limit, weight-sum error within the threshold contract, no cross-limb contamination, volume preservation and the complete stress-pose suite.

### 2. Rigid or articulated armor

Breastplates, pauldrons, couters, poleyns, vambraces, greaves, sabatons and rigid helmet/gorget sections are separate semantic objects or plate clusters. They use explicit sockets, pivots, local frames and bounded hinge/spherical constraints where articulation is required. A rigid plate may not be smeared across a joint merely because nearest-surface weight transfer produces a plausible still.

Truth owns stable plate IDs, coverage, material/SDF state, constraints and contact proxies. The rendered triangle mesh is presentation. Flexible connectors may use sparse skinning or offline-derived deterministic correctives, but never floating neural state in truth.

### 3. Weapon mechanism

Blade, guard, grip and pommel remain semantically named even when exported as one draw object. The weapon uses a calibrated right- or left-hand socket with an explicit grip frame, handle centerline, radius, usable length and guard clearance. Rigid weapon pieces use socket/constraint transforms, not deform weights.

## Genuine grip contract

A weapon is not "held" because its origin is near a wrist. A promoted grip must prove:

- handle center and orientation remain inside the declared palm/grip envelope;
- palm, thumb and required finger segments establish declared contact with the handle without stretched, fused, duplicated or collapsed geometry;
- wrist volume and anatomical segment lengths remain valid;
- guard, pommel and blade do not penetrate the hand, forearm, body or armor beyond the locked threshold;
- socket position/orientation error stays within the quality threshold across neutral, anticipation, active contact, recovery, block, thrust, slash, clinch and injury-constrained poses;
- weapon path, hand pose, rendered mesh and collision/contact proxies derive from the same admitted packet sample;
- the grip responds causally to weapon diameter/orientation and hand/armor constraints rather than selecting an authored pose, baked clip or pose-bank entry.

A generic open hand, a rigidly attached sword with no contact, or a single attractive close-up fails this contract.

## Armor fit and clearance contract

The body carrier is the fit authority. Each armor component declares coverage region, underlayer, neighboring pieces, nominal clearance, thickness, material and permitted range of motion.

Promotion requires:

- no fused body/armor source geometry;
- no floating plate, accidental opening, unfinished seam or hidden body protrusion;
- no visible body/armor, armor/armor or armor/weapon interpenetration in the approved pose suite;
- stable silhouette and readable class under neutral, grazing and gameplay lighting;
- body-hiding masks only where the component fully covers the body through every admitted pose and LOD;
- identical component identity and attachment semantics after GLB export, clean re-import, cooker conversion and live runtime load.

## Camera and player-view contract

The player camera is evidence, not an exception. It must use the approved eye/camera rig and prove that neither body, hair, armor nor weapon obscures the opponent or essential tells. Near-body culling or dedicated first-person presentation geometry is allowed only as truth-isolated presentation derived from the same pose packet.

Any capture from behind or inside the avatar, any body/weapon camera intersection, or any hidden opponent tell blocks the player-camera gate. A developer orbit camera cannot substitute.

## Required evidence package

Run the permanent visual contract at raw, Blender-authority, cooked and live-runtime stages. At minimum preserve:

- all fixed views and lighting/FOV/LOD variants required by `ADVERSARIAL_VISUAL_CONTRACT.md`;
- clay, beauty, silhouette, wireframe, normals/face orientation, object/material IDs, UV/texel density, weights, skeleton/socket and collision/proxy AOVs;
- neutral plus the complete declared stress-pose set;
- weapon-grip macro views and handle-contact measurements;
- body/armor and armor/weapon pair-clearance reports;
- 360-degree deformation playback and actual first-person strips;
- GLB validation, clean re-import, cooker verification and live engine captures;
- exact source, DCC, script, exporter, cooker, runtime, threshold and commit hashes;
- independent AI findings followed by the named human visual/game-feel decision.

A front still, thumbnail, contact sheet, machine-only verdict or generated ground-truth label cannot close promotion.

## Promotion state machine

```text
raw_candidate
  -> dcc_candidate
  -> mechanically_verified
  -> cooked_verified
  -> live_runtime_verified
  -> human_review_pending
  -> promoted
```

A candidate may move only one state at a time. Every state transition names the exact immutable evidence packet. A source, mesh, rig, weight, material, socket, proxy, exporter, cooker, runtime or threshold change invalidates downstream states. Rejected evidence remains rejected; it is never overwritten by a later candidate.

Two failed repairs sharing one root cause stop that method. Roll back or quarantine it, preserve measurements, and require a materially different falsifier before further mutation.

## Current blocking evidence

As of the July 20 audit:

- bone-parent attempts contain duplicated/collapsed or stretched hand/arm geometry and invalid weapon relationships;
- the Mixamo-body/full-kit canaries do not prove a valid combat grip;
- armor fit, reverse topology, deformation stability, engine import and actual first-person readability remain unproven where only front stills exist;
- the prior first-person captures place the camera behind/inside the body and therefore do not satisfy the player-view gate.

These are explicit blockers, not polish notes. No character or kit named by those captures is promoted.