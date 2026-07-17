//! Runtime presentation boundary for the admitted PVP005-R6 hero Strike.
//!
//! The clip supplies pose and weapon geometry. It is immutable after loading and
//! cannot write M3 truth. The 120 Hz cleanbox may consume its measured transforms
//! in a separate authority bridge.

use crate::asset::SkinnedMeshData;
use crate::hitbox::{HitboxProxy, extract_body_proxies};
use crate::{motion, motion_retarget};
use anyhow::{Context, Result, bail};
use glam::{Mat4, Vec3};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

pub const FRAME_COUNT: usize = 64;
pub const CONTACT_FRAME: usize = 32;
pub const LEFT_HAND: usize = 25;
pub const RIGHT_HAND: usize = 33;

pub const RIGHT_GRIP_Z_M: f32 = -0.105;
pub const LEFT_GRIP_Z_M: f32 = -0.265;
const PHYSICS_SUBSTEPS_PER_FRAME: usize = 4;
const PHYSICS_DT_S: f32 = 1.0 / 120.0;
const GRIP_SPAN_M: f32 = RIGHT_GRIP_Z_M - LEFT_GRIP_Z_M;
const TARGET_GHOST_COLOR: [f32; 3] = [1.0, 0.20, 0.82];
const TRACKER_GHOST_COLOR: [f32; 3] = [0.10, 0.88, 1.0];
const RESIDUAL_COLOR: [f32; 3] = [1.0, 0.72, 0.08];
const R6K_INTERACTION_SHA256: [u8; 32] = [
    0x92, 0x1c, 0xd4, 0xc2, 0x1e, 0x83, 0x81, 0x0f, 0xd7, 0x0a, 0xb4, 0x9c, 0x36, 0xd7, 0x50, 0x0e,
    0x0c, 0x89, 0xea, 0x26, 0xa5, 0x5c, 0x5e, 0x85, 0x00, 0x7a, 0x5a, 0x0f, 0x3d, 0xa9, 0xa7, 0xe5,
];

#[derive(Debug)]
pub struct HeroStrikePresentation {
    interaction_targets: Vec<[Mat4; 34]>,
    source_frames: Vec<[Mat4; 34]>,
    armored_skin: Vec<Vec<Mat4>>,
    target_armored_world: Vec<[Mat4; 24]>,
    armored_world: Vec<[Mat4; 24]>,
    armored_parents: [i32; 24],
    armored_hands: [usize; 2],
    armored_feet: [usize; 2],
    weapon_local: Vec<Mat4>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MotionLabMetrics {
    pub max_target_error_m: f32,
    pub mean_target_error_m: f32,
    pub worst_joint: usize,
    pub planted_foot_drift_m: f32,
    pub grip_error_m: f32,
}

impl HeroStrikePresentation {
    pub fn load(assets: &Path, mesh: &SkinnedMeshData) -> Result<Self> {
        let path = assets.join("motion/pvp005_r6k/hero_strike.motionbricks.interaction.413.f32");
        let bytes = fs::read(&path)
            .with_context(|| format!("read R6K MotionBricks interaction {}", path.display()))?;
        let observed = Sha256::digest(&bytes);
        if observed.as_slice() != R6K_INTERACTION_SHA256 {
            bail!("R6K MotionBricks interaction hash mismatch");
        }
        let interaction_targets = motion::load_g1_frames(&path.to_string_lossy())
            .with_context(|| format!("load R6K MotionBricks interaction {}", path.display()))?;
        if interaction_targets.len() != FRAME_COUNT {
            bail!(
                "R6K MotionBricks interaction has {} frames; expected {FRAME_COUNT}",
                interaction_targets.len()
            );
        }
        let source_frames = track_with_coupled_articulation(&interaction_targets);
        let reference = &source_frames[0];
        let left_c0_hand = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "LeftHand")
            .context("C0 armored carrier has no LeftHand")?;
        let right_c0_hand = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "RightHand")
            .context("C0 armored carrier has no RightHand")?;
        let left_c0_foot = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "LeftFoot")
            .context("C0 armored carrier has no LeftFoot")?;
        let right_c0_foot = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "RightFoot")
            .context("C0 armored carrier has no RightFoot")?;
        let target_armored_world = interaction_targets
            .iter()
            .enumerate()
            .map(|(index, target)| -> Result<[Mat4; 24]> {
                let skin =
                    motion_retarget::retarget_g1_frame_to_armored_skin(mesh, reference, target)
                        .with_context(|| format!("retarget MotionBricks target frame {index}"))?;
                Ok(std::array::from_fn(|joint| {
                    skin[joint] * mesh.bones[joint].inverse_bind.inverse()
                }))
            })
            .collect::<Result<Vec<_>>>()?;

        let mut armored_skin = Vec::with_capacity(FRAME_COUNT);
        let mut armored_world = Vec::with_capacity(FRAME_COUNT);
        let mut weapon_local = Vec::with_capacity(FRAME_COUNT);
        let mut foot_targets = None;
        for (index, frame) in source_frames.iter().enumerate() {
            validate_source_frame(frame, index)?;
            let skin = if let Some(targets) = foot_targets {
                motion_retarget::retarget_g1_frame_to_armored_skin_with_foot_targets(
                    mesh, reference, frame, targets,
                )
            } else {
                motion_retarget::retarget_g1_frame_to_armored_skin(mesh, reference, frame)
            }
            .with_context(|| format!("retarget R6 hero Strike frame {index}"))?;
            let world: [Mat4; 24] =
                std::array::from_fn(|joint| skin[joint] * mesh.bones[joint].inverse_bind.inverse());
            foot_targets.get_or_insert([
                world[left_c0_foot].w_axis.truncate(),
                world[right_c0_foot].w_axis.truncate(),
            ]);
            armored_skin.push(skin);
            armored_world.push(world);
            weapon_local.push(weapon_from_armored_hands(
                &world,
                left_c0_hand,
                right_c0_hand,
                index,
            )?);
        }
        Ok(Self {
            interaction_targets,
            source_frames,
            armored_skin,
            target_armored_world,
            armored_world,
            armored_parents: std::array::from_fn(|index| mesh.bones[index].parent),
            armored_hands: [left_c0_hand, right_c0_hand],
            armored_feet: [left_c0_foot, right_c0_foot],
            weapon_local,
        })
    }

    pub fn source_frame(&self, index: usize) -> &[Mat4; 34] {
        &self.source_frames[index.min(FRAME_COUNT - 1)]
    }

    pub fn interaction_target(&self, index: usize) -> &[Mat4; 34] {
        &self.interaction_targets[index.min(FRAME_COUNT - 1)]
    }

    pub fn motion_lab_metrics(&self, index: usize) -> MotionLabMetrics {
        let frame = index.min(FRAME_COUNT - 1);
        let target = &self.target_armored_world[frame];
        let tracker = &self.armored_world[frame];
        let mut total_error = 0.0_f32;
        let mut max_target_error_m = 0.0_f32;
        let mut worst_joint = 0;
        for joint in 0..24 {
            let error = target[joint]
                .w_axis
                .truncate()
                .distance(tracker[joint].w_axis.truncate());
            total_error += error;
            if error > max_target_error_m {
                max_target_error_m = error;
                worst_joint = joint;
            }
        }
        let planted_foot_drift_m = self
            .armored_feet
            .into_iter()
            .map(|joint| {
                tracker[joint]
                    .w_axis
                    .truncate()
                    .distance(self.armored_world[0][joint].w_axis.truncate())
            })
            .fold(0.0_f32, f32::max);
        let grip_error_m = (tracker[self.armored_hands[1]]
            .w_axis
            .truncate()
            .distance(tracker[self.armored_hands[0]].w_axis.truncate())
            - GRIP_SPAN_M)
            .abs();
        MotionLabMetrics {
            max_target_error_m,
            mean_target_error_m: total_error / 24.0,
            worst_joint,
            planted_foot_drift_m,
            grip_error_m,
        }
    }

    pub fn motion_lab_segments(&self, index: usize, model: Mat4) -> Vec<(Vec3, Vec3, [f32; 3])> {
        let frame = index.min(FRAME_COUNT - 1);
        let target = &self.target_armored_world[frame];
        let tracker = &self.armored_world[frame];
        let target_positions: [Vec3; 24] =
            std::array::from_fn(|joint| model.transform_point3(target[joint].w_axis.truncate()));
        let tracker_positions: [Vec3; 24] =
            std::array::from_fn(|joint| model.transform_point3(tracker[joint].w_axis.truncate()));
        let mut segments = Vec::with_capacity(70);
        for (joint, parent) in self.armored_parents.into_iter().enumerate() {
            if parent < 0 {
                continue;
            }
            let parent = parent as usize;
            segments.push((
                target_positions[parent],
                target_positions[joint],
                TARGET_GHOST_COLOR,
            ));
            segments.push((
                tracker_positions[parent],
                tracker_positions[joint],
                TRACKER_GHOST_COLOR,
            ));
        }
        for joint in 0..24 {
            segments.push((
                target_positions[joint],
                tracker_positions[joint],
                RESIDUAL_COLOR,
            ));
        }
        segments
    }

    pub fn armored_skin(&self, index: usize) -> &[Mat4] {
        &self.armored_skin[index.min(FRAME_COUNT - 1)]
    }

    pub fn armored_world(&self, index: usize) -> &[Mat4] {
        &self.armored_world[index.min(FRAME_COUNT - 1)]
    }

    pub fn weapon_local(&self, index: usize) -> Mat4 {
        self.weapon_local[index.min(FRAME_COUNT - 1)]
    }

    pub fn weapon_world(&self, index: usize, actor_model: Mat4) -> Mat4 {
        actor_model * self.weapon_local(index)
    }

    pub fn body_proxies_world(&self, index: usize, actor_model: Mat4) -> Vec<HitboxProxy> {
        let mut world = self.armored_world[index.min(FRAME_COUNT - 1)];
        for joint in &mut world {
            *joint = actor_model * *joint;
        }
        extract_body_proxies(&[world])
    }
}

fn track_with_coupled_articulation(targets: &[[Mat4; 34]]) -> Vec<[Mat4; 34]> {
    let parents = motion::MotionPipeline::G1_PARENTS;
    let mut positions: [Vec3; 34] =
        std::array::from_fn(|joint| targets[0][joint].w_axis.truncate());
    let mut rotations: [glam::Quat; 34] = std::array::from_fn(|joint| {
        let (_, rotation, _) = targets[0][joint].to_scale_rotation_translation();
        rotation
    });
    let mut root_velocity = Vec3::ZERO;
    let rest_lengths: [f32; 34] = std::array::from_fn(|joint| {
        let parent = parents[joint];
        if parent < 0 {
            0.0
        } else {
            positions[joint].distance(positions[parent as usize])
        }
    });
    let mut output = Vec::with_capacity(targets.len());
    for target in targets {
        let target_positions: [Vec3; 34] =
            std::array::from_fn(|joint| target[joint].w_axis.truncate());
        let target_rotations: [glam::Quat; 34] = std::array::from_fn(|joint| {
            let (_, rotation, _) = target[joint].to_scale_rotation_translation();
            rotation
        });
        for _ in 0..PHYSICS_SUBSTEPS_PER_FRAME {
            let acceleration = ((target_positions[0] - positions[0]) * 90.0 - root_velocity * 18.0)
                .clamp_length_max(45.0);
            root_velocity = (root_velocity + acceleration * PHYSICS_DT_S).clamp_length_max(6.0);
            positions[0] += root_velocity * PHYSICS_DT_S;
            rotations[0] = bounded_rotation_step(rotations[0], target_rotations[0], 0.10);

            for joint in 1..34 {
                let parent = parents[joint] as usize;
                let current_segment = positions[joint] - positions[parent];
                let target_segment = target_positions[joint] - target_positions[parent];
                let direction = if current_segment.length_squared() <= 1.0e-10 {
                    target_segment.normalize_or_zero()
                } else if target_segment.length_squared() <= 1.0e-10 {
                    current_segment.normalize()
                } else {
                    bounded_direction_step(
                        current_segment.normalize(),
                        target_segment.normalize(),
                        0.12,
                    )
                };
                positions[joint] = positions[parent] + direction * rest_lengths[joint];
                rotations[joint] =
                    bounded_rotation_step(rotations[joint], target_rotations[joint], 0.10);
            }
        }
        output.push(std::array::from_fn(|joint| {
            Mat4::from_rotation_translation(rotations[joint], positions[joint])
        }));
    }
    output
}

fn bounded_direction_step(current: Vec3, target: Vec3, max_angle_rad: f32) -> Vec3 {
    let angle = current.angle_between(target);
    if !angle.is_finite() || angle <= max_angle_rad {
        return target;
    }
    let correction = glam::Quat::from_rotation_arc(current, target);
    glam::Quat::IDENTITY
        .slerp(correction, max_angle_rad / angle)
        .mul_vec3(current)
        .normalize()
}

fn bounded_rotation_step(
    current: glam::Quat,
    target: glam::Quat,
    max_angle_rad: f32,
) -> glam::Quat {
    let angle = current.angle_between(target);
    if !angle.is_finite() || angle <= max_angle_rad {
        target
    } else {
        current.slerp(target, max_angle_rad / angle).normalize()
    }
}

fn validate_source_frame(frame: &[Mat4; 34], index: usize) -> Result<()> {
    for (joint, matrix) in frame.iter().enumerate() {
        if !matrix.is_finite() || matrix.determinant() <= 0.0 {
            bail!("R6 hero Strike frame {index} joint {joint} is non-rigid");
        }
    }
    Ok(())
}

fn weapon_from_armored_hands(
    world: &[Mat4; 24],
    left_hand_index: usize,
    right_hand_index: usize,
    frame_index: usize,
) -> Result<Mat4> {
    let right_hand = world[right_hand_index].w_axis.truncate();
    let left_hand = world[left_hand_index].w_axis.truncate();
    let hand_span = right_hand - left_hand;
    if hand_span.length_squared() < 1.0e-8 {
        bail!("R6 armored frame {frame_index} has coincident grip hands");
    }
    let blade = hand_span.normalize();
    let mut width = world[right_hand_index].x_axis.truncate();
    width -= blade * blade.dot(width);
    if width.length_squared() < 1.0e-8 {
        width = Vec3::Y.cross(blade);
    }
    if width.length_squared() < 1.0e-8 {
        width = Vec3::X;
    }
    width = width.normalize();
    let thickness = blade.cross(width).normalize();
    let pommel = right_hand - blade * RIGHT_GRIP_Z_M;
    let weapon = Mat4::from_cols(
        width.extend(0.0),
        thickness.extend(0.0),
        blade.extend(0.0),
        pommel.extend(1.0),
    );
    if !weapon.is_finite() || (weapon.determinant() - 1.0).abs() > 1.0e-4 {
        bail!("R6 armored frame {frame_index} produced a non-rigid W0 socket");
    }
    Ok(weapon)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::asset;
    use crate::motion_retarget::armored_pose_receipt;

    fn load() -> (HeroStrikePresentation, SkinnedMeshData) {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let mesh = asset::load_skinned(
            &root
                .join("assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin")
                .to_string_lossy(),
        )
        .unwrap();
        let presentation = HeroStrikePresentation::load(&root.join("assets"), &mesh).unwrap();
        (presentation, mesh)
    }

    fn transform_point(matrix: Mat4, point: Vec3) -> Vec3 {
        matrix.transform_point3(point)
    }

    #[test]
    fn admitted_clip_loads_retarges_and_moves_before_contact() {
        let (presentation, _) = load();
        assert_eq!(presentation.source_frames.len(), FRAME_COUNT);
        assert_eq!(presentation.armored_skin.len(), FRAME_COUNT);
        assert!(
            presentation
                .armored_skin
                .iter()
                .all(|skin| skin.len() == 24 && skin.iter().all(Mat4::is_finite))
        );
        let receipts: std::collections::BTreeSet<u64> = (0..8)
            .map(|frame| armored_pose_receipt(presentation.armored_skin(frame)))
            .collect();
        assert!(receipts.len() >= 6, "first-eight-frame tell is static");
    }

    #[test]
    fn w0_socket_is_rigid_and_matches_both_conditioned_hands() {
        let (presentation, mesh) = load();
        let left_hand = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "LeftHand")
            .unwrap();
        let right_hand = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "RightHand")
            .unwrap();
        for index in 0..FRAME_COUNT {
            let weapon = presentation.weapon_local(index);
            let right = transform_point(weapon, Vec3::Z * RIGHT_GRIP_Z_M);
            let left = transform_point(weapon, Vec3::Z * LEFT_GRIP_Z_M);
            let right_error = right.distance(
                presentation.armored_world[index][right_hand]
                    .w_axis
                    .truncate(),
            );
            let left_error = left.distance(
                presentation.armored_world[index][left_hand]
                    .w_axis
                    .truncate(),
            );
            assert!(
                right_error < 0.01,
                "right grip frame {index}, error={right_error}"
            );
            assert!(
                left_error < 0.01,
                "left grip frame {index}, error={left_error}"
            );
        }
    }

    #[test]
    fn moving_target_joints_do_not_freeze_and_c0_feet_remain_planted() {
        let (presentation, mesh) = load();
        for joint in 1..34 {
            let target_anchor = presentation.interaction_targets[0][joint].w_axis.truncate();
            let target_motion = presentation
                .interaction_targets
                .iter()
                .map(|frame| frame[joint].w_axis.truncate().distance(target_anchor))
                .fold(0.0_f32, f32::max);
            if target_motion > 0.020 {
                let output_anchor = presentation.source_frames[0][joint].w_axis.truncate();
                let output_motion = presentation
                    .source_frames
                    .iter()
                    .map(|frame| frame[joint].w_axis.truncate().distance(output_anchor))
                    .fold(0.0_f32, f32::max);
                assert!(
                    output_motion > 0.005,
                    "moving G1 target joint {joint} froze at {output_motion}m"
                );
            }
        }
        for name in ["LeftFoot", "RightFoot"] {
            let joint = mesh
                .bones
                .iter()
                .position(|bone| bone.name == name)
                .unwrap();
            let anchor = presentation.armored_world[0][joint].w_axis.truncate();
            let drift = presentation
                .armored_world
                .iter()
                .map(|frame| frame[joint].w_axis.truncate().distance(anchor))
                .fold(0.0_f32, f32::max);
            assert!(drift < 0.010, "C0 {name} drifted {drift}m");
        }
    }

    #[test]
    fn motionbricks_interaction_targets_are_followed_by_length_constrained_articulation() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("assets");
        let targets = motion::load_g1_frames(
            &root
                .join("motion/pvp005_r6k/hero_strike.motionbricks.interaction.413.f32")
                .to_string_lossy(),
        )
        .unwrap();
        assert_eq!(targets.len(), FRAME_COUNT);
        let physical = track_with_coupled_articulation(&targets);
        let parents = motion::MotionPipeline::G1_PARENTS;
        let reference_lengths: [f32; 34] = std::array::from_fn(|joint| {
            let parent = parents[joint];
            if parent < 0 {
                0.0
            } else {
                physical[0][joint]
                    .w_axis
                    .truncate()
                    .distance(physical[0][parent as usize].w_axis.truncate())
            }
        });
        for frame in &physical {
            for joint in 1..34 {
                if reference_lengths[joint] <= 1.0e-4 {
                    continue;
                }
                let length = frame[joint]
                    .w_axis
                    .truncate()
                    .distance(frame[parents[joint] as usize].w_axis.truncate());
                assert!(
                    (length - reference_lengths[joint]).abs() < 0.005,
                    "joint {joint} changed articulated length by {}m",
                    (length - reference_lengths[joint]).abs()
                );
            }
        }
    }

    #[test]
    fn armored_head_faces_with_torso_on_every_frame() {
        let (presentation, mesh) = load();
        let head = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "Head")
            .unwrap();
        let head_front = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "headfront")
            .unwrap();
        let torso = mesh
            .bones
            .iter()
            .position(|bone| bone.name == "Spine02")
            .unwrap();
        for (frame, world) in presentation.armored_world.iter().enumerate() {
            let torso_forward = world[torso].z_axis.truncate().normalize();
            let head_forward =
                (world[head_front].w_axis.truncate() - world[head].w_axis.truncate()).normalize();
            assert!(
                head_forward.dot(torso_forward) >= 0.70,
                "frame {frame} head points behind torso"
            );
        }
    }

    #[test]
    fn motion_lab_metrics_are_finite_and_expose_target_tracker_error() {
        let (presentation, _) = load();
        for frame in [0, CONTACT_FRAME, FRAME_COUNT - 1] {
            let metrics = presentation.motion_lab_metrics(frame);
            assert!(metrics.max_target_error_m.is_finite());
            assert!(metrics.mean_target_error_m.is_finite());
            assert!(metrics.planted_foot_drift_m.is_finite());
            assert!(metrics.grip_error_m.is_finite());
            assert!(metrics.max_target_error_m >= metrics.mean_target_error_m);
            assert!(metrics.worst_joint < 24);
            assert!(metrics.planted_foot_drift_m < 0.010);
            assert!(metrics.grip_error_m < 0.005);
        }
    }

    #[test]
    fn motion_lab_segments_preserve_both_ghosts_and_all_residuals() {
        let (presentation, _) = load();
        let model = Mat4::from_translation(Vec3::new(2.0, 0.0, -3.0));
        let segments = presentation.motion_lab_segments(CONTACT_FRAME, model);
        assert_eq!(segments.len(), 70);
        assert!(segments.iter().all(|(a, b, color)| {
            a.is_finite() && b.is_finite() && color.iter().all(|channel| channel.is_finite())
        }));
        assert_eq!(segments[0].2, TARGET_GHOST_COLOR);
        assert_eq!(segments[1].2, TRACKER_GHOST_COLOR);
        assert_eq!(segments.last().unwrap().2, RESIDUAL_COLOR);
    }
}
