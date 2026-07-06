// Pseudocode — your engine's skeleton update loop

MotionBricksOutput mb = motionbricks_sidecar.query({
    velocity: player_input.velocity,
    heading:  player_input.heading,
    style:    injury_system.get_style_weights(), // ← emergent from damage
    intent:   combat_system.get_current_intent() // ← strike, guard, grapple
});

for (int i = 0; i < 29; i++) {
    major_bones[mb_to_skeleton_map[i]].local_rotation = mb.joint_rotations[i];
}

// Procedural layers on top
finger_ik.solve(weapon_grip_pose, injury_system.finger_damage);
spine_interpolator.fill(major_bones[SPINE_BASE], major_bones[SPINE_TOP]);
toe_ik.solve(ground_contact, foot_bones);

// Apply injury constraints
injury_system.clamp_joint_roms(skeleton);
