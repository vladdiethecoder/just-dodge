# MotionBricks Retargeting Plan — Just Dodge

## Purpose

MotionBricks provides a compact neural motion source. Just Dodge retargets that source onto a richer combat mannequin without allowing animation to mutate combat truth.

The combat resolver remains authoritative. Motion output is presentation data: rotations, root motion, keypoints, and style bias derived from already-committed combat and injury state.

## Motion Clip Export Shape

A MotionBricks motion clip is documented as:

```text
/motion_clip/
├── joint_pos.csv       ← 29-joint positions (IsaacLab ordering)
├── joint_vel.csv       ← 29-joint velocities
├── body_quat.csv       ← root orientation (quaternion)
├── body_pos.csv        ← root world position
├── body_lin_vel.csv    ← root linear velocity
└── body_ang_vel.csv    ← root angular velocity
```

Per-frame runtime output should expose:

```text
Per Frame Output:
├── Joint Local Rotations     → quaternion or 6D rotation per joint
├── Root Linear Velocity      → vec3 (global space)
├── Root Angular Velocity     → vec3 (global space)
└── Keypoints                 → contact points (hands, feet) for grounding
```

## Retargeting Map

```text
MotionBricks (29 joints)          Just Dodge Mannequin (~120 bones)
─────────────────────────         ──────────────────────────
Root                         →    Pelvis
Spine (simplified)           →    L1 → L5 → T6–T12 → C1–C7 (interpolated)
L/R Shoulder                 →    Clavicle → Scapula → Shoulder
L/R Elbow                    →    Elbow + Forearm twist
L/R Wrist                    →    Wrist
[NO FINGER DATA]             →    Finger joints = custom sim layer
L/R Hip                      →    Hip
L/R Knee                     →    Knee
L/R Ankle                    →    Ankle + Subtalar
[NO TOE DATA]                →    Toe joints = custom sim layer
```

## Runtime Layering

```text
┌─────────────────────────────────────────────────────┐
│                  JUST DODGE ENGINE                  │
│                                                     │
│  MotionBricks Neural Backend                        │
│       ↓ joint_rotations[29] + root_velocity         │
│                                                     │
│  ── RETARGETING LAYER ──────────────────────────    │
│  Map 29 → ~120 bones via:                           │
│    • Direct mapping for major joints                │
│    • Procedural IK for fingers/toes                 │
│    • Spline interpolation for spine segments        │
│                                                     │
│  ── INJURY / DAMAGE LAYER ─────────────────────     │
│  Per-joint constraint modifiers:                    │
│    • Broken finger → clamp finger ROM               │
│    • Sprained ankle → add noise + limit eversion    │
│    • Cracked rib → bias torso style weight          │
│    • Dislocated shoulder → hard ROM limit           │
│                                                     │
│  ── PHYSICS / COLLISION LAYER ─────────────────     │
│  Per-bone hitboxes + ragdoll fallback               │
│  Contact keypoints → foot/hand IK grounding         │
│                                                     │
│  ── RENDER LAYER ──────────────────────────────     │
│  Skinned mesh                                       │
│  Muscle deformation → driven by joint angles        │
└─────────────────────────────────────────────────────┘
```

## Conceptual Update Loop

This is design pseudocode, not a source file contract:

```cpp
MotionBricksOutput mb = motionbricks_sidecar.query({
    velocity: player_input.velocity,
    heading:  player_input.heading,
    style:    injury_system.get_style_weights(),
    intent:   combat_system.get_current_intent()
});

for (int i = 0; i < 29; i++) {
    major_bones[mb_to_skeleton_map[i]].local_rotation = mb.joint_rotations[i];
}

finger_ik.solve(weapon_grip_pose, injury_system.finger_damage);
spine_interpolator.fill(major_bones[SPINE_BASE], major_bones[SPINE_TOP]);
toe_ik.solve(ground_contact, foot_bones);
injury_system.clamp_joint_roms(skeleton);
```

## Truth Isolation Requirements

- Combat action IDs, frame counts, hit locations, injury values, and match results are computed before presentation.
- MotionBricks may read committed intent and injury state.
- MotionBricks output may drive rendering, IK, pose readability, audio cues, and replay visualization.
- MotionBricks output must not choose actions, change matchup results, alter injury magnitude, or alter truth hashes.
- Finger and toe behavior is a custom layer because the 29-joint source has no finger/toe data.
- Spine detail is interpolated because the MotionBricks source provides a simplified spine.

## Prototype Gate

Motion retargeting passes only if players can identify opponent intent from pose, timing, and audio before contact. A prettier mannequin is not progress unless it improves readable YOMI decisions.
