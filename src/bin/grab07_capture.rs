//! Autonomous, headless Grab-07 evidence capture.
//!
//! This binary never hand-places a render scene: PlanPhase owns root movement,
//! action locks, clinch entry/exit, and the authoritative DuelWorld path. A
//! second DuelWorld is an observation-only mirror used to retain the two public
//! 120 Hz `SharedPhysicsStep`s that PlanPhase deliberately reduces internally.

use std::{
    fmt::Write as _,
    fs,
    path::{Path, PathBuf},
    process::Command,
};

use glam::{Mat4, Quat, Vec3, Vec3Swizzles, vec3};
use image::{ImageBuffer, Rgba};
use just_dodge::{
    asset::{self, SkeletalAnimation, SkinnedMeshData},
    cleanbox,
    duel_physics::{BilateralContact, Fighter},
    duel_world::DuelWorld,
    intent::{
        AirState, ClinchIntent, Intent, PlanEvent, PlanPhase, PlanSnapshot, PlanStatus,
        StrikeVariant,
    },
    renderer,
    truth::{Action, Side},
};
use sha2::{Digest, Sha256};

const MANNEQUIN_SKIN: &str = "source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin";
const WALK_ANIMATION: &str = "source/meshy/c0_base_fighter/rigged_001/cooked/walking.anim";
const RUN_ANIMATION: &str = "source/meshy/c0_base_fighter/rigged_001/cooked/running.anim";
const MOTION: &str = "motion/pvp005_candidates/grab/grab_07.413.f32";
const WIDTH: u32 = 1280;
const HEIGHT: u32 = 720;

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum CapturePhase {
    Tell,
    Approach,
    FirstContact,
    SecureGrab,
    Consequence,
    Release,
    Recovery,
}

impl CapturePhase {
    const fn name(self) -> &'static str {
        match self {
            Self::Tell => "tell",
            Self::Approach => "approach",
            Self::FirstContact => "first_contact",
            Self::SecureGrab => "secure_grab",
            Self::Consequence => "consequence",
            Self::Release => "release",
            Self::Recovery => "recovery",
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum ScriptStage {
    Grab,
    Secure,
    Resolve,
    AfterExit,
}

#[derive(Clone)]
struct PoseSample {
    snapshot: PlanSnapshot,
    physics_tick: u64,
}

struct CaptureOutput {
    capture_jsonl: String,
    findings_jsonl: String,
    phase_spans: Vec<(CapturePhase, u64, u64)>,
    contact_substeps: Vec<u64>,
    worst: PoseSample,
    worst_depth: f32,
    secure_grab: Option<PoseSample>,
    final_truth_hash: u64,
}

struct PresentationAssets {
    mesh: SkinnedMeshData,
    reference_skin: Vec<Mat4>,
    walk_skins: Vec<Vec<Mat4>>,
    run_skins: Vec<Vec<Mat4>>,
}

impl PresentationAssets {
    fn load(assets_root: &Path) -> Self {
        let mesh = asset::load_skinned(
            assets_root
                .join(MANNEQUIN_SKIN)
                .to_str()
                .expect("UTF-8 mannequin path"),
        )
        .expect("Grab-07 requires c0_base_fighter c0_skin8.bin");
        assert_eq!(
            mesh.bones.len(),
            24,
            "debug mannequin must retain C0's 24-bone rig"
        );
        let local: Vec<Mat4> = mesh.bones.iter().map(|bone| bone.rest_local).collect();
        let reference_skin = asset::reference_pose_skin_matrices(&mesh, &local)
            .expect("C0 reference pose must skin");
        let walk = asset::load_skeletal_animation(
            assets_root
                .join(WALK_ANIMATION)
                .to_str()
                .expect("UTF-8 walk path"),
        )
        .expect("Grab-07 requires C0 walking animation");
        let run = asset::load_skeletal_animation(
            assets_root
                .join(RUN_ANIMATION)
                .to_str()
                .expect("UTF-8 run path"),
        )
        .expect("Grab-07 requires C0 running animation");
        Self {
            walk_skins: animation_skins(&mesh, &walk),
            run_skins: animation_skins(&mesh, &run),
            mesh,
            reference_skin,
        }
    }

    fn skin_for(&self, intent: Option<Intent>, truth_frame: u64) -> Vec<Mat4> {
        match intent {
            Some(Intent::Move { .. }) => sample_skin(&self.walk_skins, truth_frame)
                .unwrap_or_else(|| self.reference_skin.clone()),
            Some(Intent::Dodge { .. }) => sample_skin(&self.run_skins, truth_frame)
                .unwrap_or_else(|| self.reference_skin.clone()),
            Some(intent) => placeholder_skin(&self.mesh, intent),
            None => self.reference_skin.clone(),
        }
    }
}

fn animation_skins(mesh: &SkinnedMeshData, animation: &SkeletalAnimation) -> Vec<Vec<Mat4>> {
    assert_eq!(
        animation.bone_count,
        mesh.bones.len(),
        "ANM1 bone count mismatch"
    );
    animation
        .frames
        .iter()
        .map(|frame| {
            let mut root_locked = frame.clone();
            root_locked[0].w_axis = mesh.bones[0].rest_local.w_axis;
            asset::retarget_world_animation_frame(mesh, mesh, &root_locked)
                .expect("C0 animation must retarget to itself")
        })
        .collect()
}

fn sample_skin(frames: &[Vec<Mat4>], truth_frame: u64) -> Option<Vec<Mat4>> {
    (!frames.is_empty()).then(|| frames[truth_frame as usize % frames.len()].clone())
}

fn placeholder_skin(mesh: &SkinnedMeshData, intent: Intent) -> Vec<Mat4> {
    let mut local: Vec<Mat4> = mesh.bones.iter().map(|bone| bone.rest_local).collect();
    let find = |name| mesh.bones.iter().position(|bone| bone.name == name);
    let (Some(left), Some(right), Some(spine)) = (find("LeftArm"), find("RightArm"), find("Spine"))
    else {
        return asset::reference_pose_skin_matrices(mesh, &local).expect("reference skin");
    };
    match intent {
        Intent::Grab | Intent::Clinch { .. } => {
            rotate_local(&mut local, left, Quat::from_rotation_x(-0.72));
            rotate_local(&mut local, right, Quat::from_rotation_x(-0.72));
            rotate_local(&mut local, spine, Quat::from_rotation_y(0.12));
        }
        Intent::Strike { .. } => {
            rotate_local(&mut local, right, Quat::from_rotation_x(-0.95));
            rotate_local(&mut local, left, Quat::from_rotation_x(0.30));
        }
        Intent::Block => {
            rotate_local(&mut local, left, Quat::from_rotation_x(-1.05));
            rotate_local(&mut local, right, Quat::from_rotation_x(-1.05));
        }
        Intent::Feint => rotate_local(&mut local, right, Quat::from_rotation_x(-0.42)),
        Intent::Cancel => rotate_local(&mut local, spine, Quat::from_rotation_y(-0.18)),
        Intent::Idle | Intent::Move { .. } | Intent::Dodge { .. } => {}
    }
    asset::reference_pose_skin_matrices(mesh, &local).expect("placeholder pose must skin")
}

fn rotate_local(local: &mut [Mat4], index: usize, delta: Quat) {
    let (scale, rotation, translation) = local[index].to_scale_rotation_translation();
    local[index] =
        Mat4::from_scale_rotation_translation(scale, (rotation * delta).normalize(), translation);
}

fn side_index(side: Side) -> usize {
    match side {
        Side::Player => 0,
        Side::Opponent => 1,
    }
}

fn root_vec(snapshot: &PlanSnapshot, side: Side) -> Vec3 {
    let root = snapshot.roots[side_index(side)];
    vec3(
        root.x_mm as f32 / 1000.0,
        root.y_mm as f32 / 1000.0,
        root.z_mm as f32 / 1000.0,
    )
}

fn fighter_model(root: Vec3, opponent: Vec3) -> Mat4 {
    let facing = (opponent - root).xz().normalize_or_zero();
    Mat4::from_translation(root)
        * Mat4::from_rotation_y(facing.x.atan2(facing.y))
        * renderer::skinned_correct_model()
}

fn action_for(intent: Option<Intent>) -> Action {
    match intent.unwrap_or(Intent::Idle) {
        Intent::Strike {
            variant: StrikeVariant::Thrust,
        } => Action::Thrust,
        Intent::Strike {
            variant: StrikeVariant::Slash,
        } => Action::Strike,
        Intent::Block
        | Intent::Move { .. }
        | Intent::Feint
        | Intent::Cancel
        | Intent::Idle
        | Intent::Clinch { .. } => Action::Block,
        Intent::Dodge { .. } => Action::Dodge,
        Intent::Grab => Action::Grab,
    }
}

fn phase_intent(stage: ScriptStage, side: Side, clinched: bool) -> Intent {
    if !clinched {
        return match stage {
            ScriptStage::Grab => {
                if side == Side::Player {
                    Intent::Grab
                } else {
                    Intent::Idle
                }
            }
            ScriptStage::AfterExit => Intent::Idle,
            ScriptStage::Secure | ScriptStage::Resolve => Intent::Idle,
        };
    }
    match stage {
        ScriptStage::Secure => Intent::Clinch {
            sub: if side == Side::Player {
                ClinchIntent::Hold
            } else {
                ClinchIntent::Throw
            },
        },
        ScriptStage::Resolve => Intent::Clinch {
            sub: if side == Side::Player {
                ClinchIntent::Tech
            } else {
                ClinchIntent::Throw
            },
        },
        ScriptStage::Grab | ScriptStage::AfterExit => Intent::Clinch {
            sub: ClinchIntent::Hold,
        },
    }
}

fn lock_open_intents(phase: &mut PlanPhase, stage: ScriptStage) -> Vec<PlanEvent> {
    let clinched = phase.clinch().is_some();
    let mut events = Vec::new();
    for side in [Side::Player, Side::Opponent] {
        if phase.can_submit_intent(side) {
            let mut result = phase
                .submit_intent(side, phase_intent(stage, side, clinched))
                .expect("script must submit only available valid intents");
            events.append(&mut result);
        }
    }
    events
}

fn has_event(events: &[PlanEvent], predicate: impl Fn(&PlanEvent) -> bool) -> bool {
    events.iter().any(predicate)
}

fn json_string(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('"');
    for character in value.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            character if character.is_control() => {
                write!(&mut out, "\\u{:04x}", character as u32).expect("write String");
            }
            character => out.push(character),
        }
    }
    out.push('"');
    out
}

fn fmt_vec3(value: Vec3) -> String {
    format!("[{:.9},{:.9},{:.9}]", value.x, value.y, value.z)
}

/// Serialize glam's column-major matrix as an explicitly documented row-major
/// JSON array.  Keeping the layout at the capture boundary avoids making every
/// offline consumer guess how `Mat4::to_cols_array` is ordered.
fn fmt_mat4_row_major(value: Mat4) -> String {
    let columns = value.to_cols_array();
    format!(
        "[{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9}]",
        columns[0],
        columns[4],
        columns[8],
        columns[12],
        columns[1],
        columns[5],
        columns[9],
        columns[13],
        columns[2],
        columns[6],
        columns[10],
        columns[14],
        columns[3],
        columns[7],
        columns[11],
        columns[15],
    )
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn sha256_file(path: &Path) -> String {
    sha256_bytes(&fs::read(path).unwrap_or_else(|_| panic!("read {}", path.display())))
}

fn root_hash(snapshot: &PlanSnapshot, side: Side) -> String {
    let root = snapshot.roots[side_index(side)];
    sha256_bytes(format!("{}:{}:{}", root.x_mm, root.y_mm, root.z_mm).as_bytes())
}

fn contact_json(contact: &BilateralContact, player_grab: bool) -> String {
    let attacker = if contact.attacker == Fighter::Player {
        "grabber"
    } else {
        "opponent"
    };
    let defender = if contact.defender == Fighter::Player {
        "grabber"
    } else {
        "opponent"
    };
    // Cleanbox exposes the reaching collision body as a generic weapon edge. In
    // this capture that edge is the locked `Intent::Grab` OBB, so retain that
    // provenance in the stable pair name rather than claiming triangle contact.
    let attacker_proxy = if player_grab && contact.attacker == Fighter::Player {
        "hand_proxy"
    } else {
        "interaction_proxy"
    };
    let defender_proxy = if contact.defender_role == just_dodge::hitbox::ProxyRole::Body {
        "body_proxy"
    } else {
        "guard_proxy"
    };
    let geometry = &contact.geometry;
    format!(
        "{{\"attacker\":{},\"defender\":{},\"attacker_proxy\":{},\"defender_proxy\":{},\"point_m\":{},\"normal\":{},\"depth_m\":{:.9},\"time_of_impact\":{:.9},\"mesh_pair\":{}}}",
        json_string(attacker),
        json_string(defender),
        geometry.attacker_proxy,
        geometry.defender_proxy,
        fmt_vec3(geometry.point),
        fmt_vec3(geometry.normal),
        geometry.depth,
        geometry.time_of_impact,
        json_string(&format!(
            "{attacker}:{attacker_proxy}<->{defender}:{defender_proxy}"
        )),
    )
}

fn finding_json(
    contact: &BilateralContact,
    physics_tick: u64,
    revision: &str,
    mesh_hash: &str,
) -> String {
    let player_grab = contact.attacker == Fighter::Player;
    let pair = if player_grab {
        "grabber:hand_proxy<->opponent:body_proxy"
    } else {
        "opponent:interaction_proxy<->grabber:body_proxy"
    };
    let geometry = &contact.geometry;
    // The OBB detector reports overlap depth directly. A negative signed value
    // is the Mesh Doctor convention for penetration. CCD-only contact has 0.
    format!(
        concat!(
            "{{\"artifact_sha256\":{},\"revision\":{},\"clip\":\"grab07\",\"physics_tick\":{},",
            "\"subframe\":0.0,\"lod\":\"debug_mannequin_obb\",\"object_pair\":{},\"mesh_pair\":{},",
            "\"triangle_ids\":[0,0],\"barycentric\":[1.0,0.0,0.0],\"world_point\":{},\"local_point\":{},",
            "\"normal\":{},\"signed_depth_m\":{:.9},\"area_m2\":0.0,\"duration_ticks\":1}}"
        ),
        json_string(mesh_hash),
        json_string(revision),
        physics_tick,
        json_string("grabber<->opponent"),
        json_string(pair),
        fmt_vec3(geometry.point),
        fmt_vec3(geometry.point),
        fmt_vec3(geometry.normal),
        -geometry.depth,
    )
}

fn capture_record(
    snapshot: &PlanSnapshot,
    phase: CapturePhase,
    physics_tick: u64,
    contacts: &[BilateralContact],
) -> String {
    let player_grab = snapshot.locked[0] == Some(Intent::Grab) || snapshot.clinch.is_some();
    let contact_values: Vec<String> = contacts
        .iter()
        .map(|contact| contact_json(contact, player_grab))
        .collect();
    let max_depth = contacts
        .iter()
        .map(|contact| contact.geometry.depth)
        .fold(0.0_f32, f32::max);
    let rms_depth = if contacts.is_empty() {
        0.0
    } else {
        (contacts
            .iter()
            .map(|contact| contact.geometry.depth.powi(2))
            .sum::<f32>()
            / contacts.len() as f32)
            .sqrt()
    };
    let roots = format!(
        "[{{\"x_mm\":{},\"y_mm\":{},\"z_mm\":{}}},{{\"x_mm\":{},\"y_mm\":{},\"z_mm\":{}}}]",
        snapshot.roots[0].x_mm,
        snapshot.roots[0].y_mm,
        snapshot.roots[0].z_mm,
        snapshot.roots[1].x_mm,
        snapshot.roots[1].y_mm,
        snapshot.roots[1].z_mm,
    );
    format!(
        concat!(
            "{{\"schema\":\"grab07-capture-v1\",\"physics_tick\":{},\"render_frame\":{},\"substep_within_frame\":{},",
            "\"truth_frame\":{},\"phase\":{},\"roots\":{},\"intents\":[{},{}],\"clinch\":{},\"contact_observed\":{},",
            "\"contacts\":[{}],\"max_penetration_depth_m\":{:.9},\"rms_penetration_depth_m\":{:.9},",
            "\"grabber_root\":{},\"opponent_root\":{}}}"
        ),
        physics_tick,
        physics_tick / 2,
        physics_tick % 2,
        snapshot.truth_frame,
        json_string(phase.name()),
        roots,
        json_string(&format!("{:?}", snapshot.locked[0])),
        json_string(&format!("{:?}", snapshot.locked[1])),
        json_string(&format!("{:?}", snapshot.clinch)),
        snapshot.last_contact_observed,
        contact_values.join(","),
        max_depth,
        rms_depth,
        json_string(&root_hash(snapshot, Side::Player)),
        json_string(&root_hash(snapshot, Side::Opponent)),
    )
}

fn simulate(revision: &str, mesh_hash: &str) -> CaptureOutput {
    let mut phase = PlanPhase::new();
    let mut observer = DuelWorld::new();
    let mut script = ScriptStage::Grab;
    let mut phase_label = CapturePhase::Tell;
    let mut release_started = None::<u64>;
    let mut capture_lines = Vec::new();
    let mut finding_lines = Vec::new();
    let mut contact_substeps = Vec::new();
    let mut worst_depth = -1.0_f32;
    let mut worst = None::<PoseSample>;
    let mut secure_grab_sample = None::<PoseSample>;

    for truth_tick in 0..96_u64 {
        if phase.status() == PlanStatus::Planning {
            let lock_events = lock_open_intents(&mut phase, script);
            if has_event(&lock_events, |event| {
                matches!(event, PlanEvent::Locked { .. })
            }) {
                observer.clear_weapon_history();
            }
        }
        assert!(
            matches!(phase.status(), PlanStatus::Executing { .. }),
            "script failed to lock"
        );
        let step_events = phase
            .step_truth_tick()
            .expect("PlanPhase truth tick must advance");
        let snapshot = phase.snapshot();
        let player_root = root_vec(&snapshot, Side::Player);
        let opponent_root = root_vec(&snapshot, Side::Opponent);
        let player_action = action_for(snapshot.locked[0]);
        let opponent_action = action_for(snapshot.locked[1]);
        let player_first = cleanbox::action_frame(Fighter::Player, player_action, player_root, 0);
        let opponent_first =
            cleanbox::action_frame(Fighter::Opponent, opponent_action, opponent_root, 0);
        let player_second = cleanbox::action_frame(Fighter::Player, player_action, player_root, 1);
        let opponent_second =
            cleanbox::action_frame(Fighter::Opponent, opponent_action, opponent_root, 1);
        let observed = observer
            .step_truth_tick(
                (snapshot.truth_frame.saturating_sub(1)) as u32,
                just_dodge::duel_world::DuelWorldTarget {
                    player: player_first.as_target(),
                    opponent: opponent_first.as_target(),
                },
                just_dodge::duel_world::DuelWorldTarget {
                    player: player_second.as_target(),
                    opponent: opponent_second.as_target(),
                },
            )
            .expect("observer DuelWorld must mirror PlanPhase targets");

        if truth_tick >= 2 && phase_label == CapturePhase::Tell {
            phase_label = CapturePhase::Approach;
        }
        if (!observed.first.contacts.is_empty() || !observed.second.contacts.is_empty())
            && phase_label <= CapturePhase::Approach
        {
            phase_label = CapturePhase::FirstContact;
        }
        if has_event(&step_events, |event| {
            matches!(event, PlanEvent::ClinchEnter { .. })
        }) {
            script = ScriptStage::Secure;
            phase_label = CapturePhase::SecureGrab;
        }
        if snapshot
            .combos
            .iter()
            .any(|combo| matches!(combo.air, AirState::Launched { .. }))
            && phase_label == CapturePhase::SecureGrab
        {
            script = ScriptStage::Resolve;
            phase_label = CapturePhase::Consequence;
        }
        if has_event(&step_events, |event| {
            matches!(event, PlanEvent::ClinchExit { .. })
        }) {
            script = ScriptStage::AfterExit;
            phase_label = CapturePhase::Release;
            release_started = Some(truth_tick);
        }
        if phase_label == CapturePhase::Release
            && release_started.is_some_and(|start| truth_tick >= start + 2)
        {
            phase_label = CapturePhase::Recovery;
        }

        for observed_step in [&observed.first, &observed.second] {
            let physics_tick = observed_step.physics_tick;
            let pose = PoseSample {
                snapshot: snapshot.clone(),
                physics_tick,
            };
            if phase_label == CapturePhase::SecureGrab && secure_grab_sample.is_none() {
                secure_grab_sample = Some(pose.clone());
            }
            capture_lines.push(capture_record(
                &snapshot,
                phase_label,
                physics_tick,
                &observed_step.contacts,
            ));
            for contact in &observed_step.contacts {
                finding_lines.push(finding_json(contact, physics_tick, revision, mesh_hash));
                if contact_substeps.last().copied() != Some(physics_tick) {
                    contact_substeps.push(physics_tick);
                }
                if contact.geometry.depth > worst_depth {
                    worst_depth = contact.geometry.depth;
                    worst = Some(pose.clone());
                }
            }
        }

        if phase_label == CapturePhase::Recovery
            && release_started.is_some_and(|start| truth_tick >= start + 5)
        {
            break;
        }
    }

    let worst = worst.expect("autonomous grab must yield observed DuelWorld contact");
    let labels: Vec<CapturePhase> = capture_lines
        .iter()
        .map(|line| {
            if line.contains("\"phase\":\"tell\"") {
                CapturePhase::Tell
            } else if line.contains("\"phase\":\"approach\"") {
                CapturePhase::Approach
            } else if line.contains("\"phase\":\"first_contact\"") {
                CapturePhase::FirstContact
            } else if line.contains("\"phase\":\"secure_grab\"") {
                CapturePhase::SecureGrab
            } else if line.contains("\"phase\":\"consequence\"") {
                CapturePhase::Consequence
            } else if line.contains("\"phase\":\"release\"") {
                CapturePhase::Release
            } else {
                CapturePhase::Recovery
            }
        })
        .collect();
    let mut spans = Vec::new();
    let mut cursor = 0usize;
    for expected in [
        CapturePhase::Tell,
        CapturePhase::Approach,
        CapturePhase::FirstContact,
        CapturePhase::SecureGrab,
        CapturePhase::Consequence,
        CapturePhase::Release,
        CapturePhase::Recovery,
    ] {
        let start = cursor;
        while cursor < labels.len() && labels[cursor] == expected {
            cursor += 1;
        }
        assert!(
            cursor > start,
            "Grab-07 must produce nonempty {} span",
            expected.name()
        );
        spans.push((expected, start as u64, (cursor - 1) as u64));
    }
    assert_eq!(cursor, labels.len(), "capture must not regress phase order");
    assert!(
        capture_lines
            .iter()
            .zip(labels.iter())
            .any(|(line, label)| *label == CapturePhase::SecureGrab && line.contains("hand_proxy")),
        "secure grab must contain a measured hand-proxy-to-body contact",
    );

    CaptureOutput {
        capture_jsonl: format!("{}\n", capture_lines.join("\n")),
        findings_jsonl: format!("{}\n", finding_lines.join("\n")),
        phase_spans: spans,
        contact_substeps,
        worst,
        worst_depth,
        secure_grab: secure_grab_sample,
        final_truth_hash: phase.truth_hash(),
    }
}

fn fixed_cameras() -> [(&'static str, Vec3, Vec3, Vec3, f32); 5] {
    [
        (
            "first_person",
            vec3(0.0, 2.35, 4.8),
            vec3(0.0, 0.95, 0.0),
            Vec3::Y,
            58.0,
        ),
        (
            "front",
            vec3(0.0, 2.25, 5.4),
            vec3(0.0, 0.95, 0.0),
            Vec3::Y,
            52.0,
        ),
        (
            "side",
            vec3(5.4, 2.15, 0.0),
            vec3(0.0, 0.95, 0.0),
            Vec3::Y,
            52.0,
        ),
        (
            "top",
            vec3(0.0, 6.2, 0.02),
            vec3(0.0, 0.0, 0.0),
            -Vec3::Z,
            48.0,
        ),
        (
            "three_quarter",
            vec3(4.2, 3.1, 4.2),
            vec3(0.0, 0.95, 0.0),
            Vec3::Y,
            52.0,
        ),
    ]
}

fn readback_png(device: &wgpu::Device, queue: &wgpu::Queue, texture: &wgpu::Texture, path: &Path) {
    let bytes_per_row = (WIDTH * 4).next_multiple_of(256);
    let buffer = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("Grab-07 readback"),
        size: (bytes_per_row * HEIGHT) as u64,
        usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
        mapped_at_creation: false,
    });
    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
    encoder.copy_texture_to_buffer(
        wgpu::TexelCopyTextureInfo {
            texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        wgpu::TexelCopyBufferInfo {
            buffer: &buffer,
            layout: wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(bytes_per_row),
                rows_per_image: Some(HEIGHT),
            },
        },
        wgpu::Extent3d {
            width: WIDTH,
            height: HEIGHT,
            depth_or_array_layers: 1,
        },
    );
    queue.submit([encoder.finish()]);
    let slice = buffer.slice(..);
    slice.map_async(wgpu::MapMode::Read, |_| {});
    device
        .poll(wgpu::PollType::wait_indefinitely())
        .expect("readback poll");
    let data = slice.get_mapped_range().expect("mapped capture readback");
    let mut image = ImageBuffer::<Rgba<u8>, Vec<u8>>::new(WIDTH, HEIGHT);
    for y in 0..HEIGHT {
        for x in 0..WIDTH {
            let offset = (y * bytes_per_row + x * 4) as usize;
            image.put_pixel(
                x,
                y,
                Rgba([
                    data[offset],
                    data[offset + 1],
                    data[offset + 2],
                    data[offset + 3],
                ]),
            );
        }
    }
    drop(data);
    buffer.unmap();
    image
        .save(path)
        .unwrap_or_else(|_| panic!("save {}", path.display()));
}

fn render_views(assets_root: &Path, pose: &PoseSample, images: &Path) {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::VULKAN,
        flags: wgpu::InstanceFlags::default(),
        memory_budget_thresholds: wgpu::MemoryBudgetThresholds::default(),
        backend_options: wgpu::BackendOptions::default(),
        display: None,
    });
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        compatible_surface: None,
        ..Default::default()
    }))
    .expect("Grab-07 requires a headless Vulkan adapter");
    let (device, queue) =
        pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default()))
            .expect("Grab-07 request headless device");
    let config = wgpu::SurfaceConfiguration {
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        format: wgpu::TextureFormat::Bgra8UnormSrgb,
        width: WIDTH,
        height: HEIGHT,
        present_mode: wgpu::PresentMode::Fifo,
        alpha_mode: wgpu::CompositeAlphaMode::Auto,
        view_formats: vec![],
        color_space: wgpu::SurfaceColorSpace::Auto,
        desired_maximum_frame_latency: 2,
    };
    unsafe {
        std::env::set_var("JUST_DODGE_C0_SKIN", assets_root.join(MANNEQUIN_SKIN));
        std::env::set_var("JUST_DODGE_C0_FLAT_COLOR", "1");
    }
    let presentation = PresentationAssets::load(assets_root);
    let mut renderer = renderer::Renderer::new(
        &device,
        &queue,
        &config,
        renderer::SceneProfile::FlatArena,
        assets_root,
    );
    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("Grab-07 offscreen color"),
        size: wgpu::Extent3d {
            width: WIDTH,
            height: HEIGHT,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: config.format,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
        view_formats: &[],
    });
    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let player_root = root_vec(&pose.snapshot, Side::Player);
    let opponent_root = root_vec(&pose.snapshot, Side::Opponent);
    let player_model = fighter_model(player_root, opponent_root);
    let opponent_model = fighter_model(opponent_root, player_root);
    let player_skin = presentation.skin_for(pose.snapshot.locked[0], pose.snapshot.truth_frame);
    let opponent_skin = presentation.skin_for(pose.snapshot.locked[1], pose.snapshot.truth_frame);
    fs::create_dir_all(images).expect("create view image directory");

    for (name, eye, target, up, fov) in fixed_cameras() {
        let pv = Mat4::perspective_lh(fov.to_radians(), WIDTH as f32 / HEIGHT as f32, 0.1, 100.0)
            * Mat4::look_at_lh(eye, target, up);
        renderer.update_camera(&queue, &pv);
        renderer.upload_debug_mvp(&queue, &pv);
        renderer.update_contact_shadows(&queue, &pv, player_root, opponent_root);
        renderer.update_skinned_model(&queue, 0, &pv, player_model);
        renderer.update_skinned_model(&queue, 1, &pv, opponent_model);
        renderer.update_skin_joints_indexed(&queue, 0, &player_skin);
        renderer.update_skin_joints_indexed(&queue, 1, &opponent_skin);
        let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("Grab-07 render encoder"),
        });
        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("Grab-07 FlatArena both mannequins pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    depth_slice: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color {
                            r: 0.025,
                            g: 0.035,
                            b: 0.055,
                            a: 1.0,
                        }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                    view: &renderer.depth_view,
                    depth_ops: Some(wgpu::Operations {
                        load: wgpu::LoadOp::Clear(1.0),
                        store: wgpu::StoreOp::Store,
                    }),
                    stencil_ops: None,
                }),
                timestamp_writes: None,
                occlusion_query_set: None,
                multiview_mask: None,
            });
            renderer.render(&mut pass);
            for skinned in &renderer.skinned {
                pass.set_pipeline(&renderer.skin_pipeline);
                pass.set_bind_group(0, &skinned.uniform_bind_group, &[]);
                pass.set_bind_group(1, &skinned.texture_bind_group, &[]);
                pass.set_bind_group(2, &skinned.joint_bind_group, &[]);
                pass.set_vertex_buffer(0, skinned.vertex_buffer.slice(..));
                pass.set_index_buffer(skinned.index_buffer.slice(..), wgpu::IndexFormat::Uint32);
                pass.draw_indexed(0..skinned.index_count, 0, 0..1);
            }
            renderer.render_debug_overlay(&mut pass);
        }
        queue.submit([encoder.finish()]);
        let state = images.join(format!("{name}_BEFORE.png"));
        readback_png(&device, &queue, &texture, &state);
        fs::copy(&state, images.join(format!("{name}_beauty.png"))).expect("copy beauty layer");
    }
}

fn phase_json(
    output: &CaptureOutput,
    revision: &str,
    executable_hash: &str,
    mesh_hash: &str,
) -> String {
    let spans: Vec<String> = output
        .phase_spans
        .iter()
        .map(|(phase, start, end)| {
            format!(
                "{{\"phase\":{},\"start_physics_tick\":{},\"end_physics_tick\":{}}}",
                json_string(phase.name()),
                start,
                end
            )
        })
        .collect();
    format!(
        "{{\"schema\":\"grab07-phases-v1\",\"executable_revision\":{},\"executable_sha256\":{},\"mesh_sha256\":{},\"opponent_root_offset\":[1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0],\"phases\":[{}]}}\n",
        json_string(revision),
        json_string(executable_hash),
        json_string(mesh_hash),
        spans.join(",")
    )
}

fn cameras_json(revision: &str, executable_hash: &str, mesh_hash: &str) -> String {
    let cameras: Vec<String> = fixed_cameras()
        .iter()
        .map(|(name, eye, target, up, fov)| {
            format!(
                "{{\"name\":{},\"eye_m\":{},\"target_m\":{},\"up\":{},\"fov_deg\":{:.3}}}",
                json_string(name),
                fmt_vec3(*eye),
                fmt_vec3(*target),
                fmt_vec3(*up),
                fov
            )
        })
        .collect();
    format!(
        "{{\"schema\":\"grab07-cameras-v1\",\"executable_revision\":{},\"executable_sha256\":{},\"mesh_sha256\":{},\"opponent_root_offset\":[1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0],\"cameras\":[{}]}}\n",
        json_string(revision),
        json_string(executable_hash),
        json_string(mesh_hash),
        cameras.join(",")
    )
}

fn worst_json(output: &CaptureOutput) -> String {
    let snapshot = &output.worst.snapshot;
    format!(
        concat!(
            "{{\"schema\":\"grab07-worst-substep-v1\",\"physics_tick\":{},\"render_frame\":{},\"truth_frame\":{},",
            "\"max_obb_overlap_m\":{:.9},\"roots_mm\":[[{},{},{}],[{},{},{}]],\"locked\":[{},{}],\"clinch\":{}}}\n"
        ),
        output.worst.physics_tick,
        output.worst.physics_tick / 2,
        snapshot.truth_frame,
        output.worst_depth,
        snapshot.roots[0].x_mm,
        snapshot.roots[0].y_mm,
        snapshot.roots[0].z_mm,
        snapshot.roots[1].x_mm,
        snapshot.roots[1].y_mm,
        snapshot.roots[1].z_mm,
        json_string(&format!("{:?}", snapshot.locked[0])),
        json_string(&format!("{:?}", snapshot.locked[1])),
        json_string(&format!("{:?}", snapshot.clinch)),
    )
}

fn pose_bones_json(mesh: &SkinnedMeshData) -> String {
    mesh.bones
        .iter()
        .enumerate()
        .map(|(index, bone)| {
            format!(
                concat!(
                    "{{\"index\":{},\"name\":{},\"parent_index\":{},",
                    "\"rest_local_matrix_row_major\":{},",
                    "\"inverse_bind_matrix_row_major\":{}}}"
                ),
                index,
                json_string(&bone.name),
                bone.parent,
                fmt_mat4_row_major(bone.rest_local),
                fmt_mat4_row_major(bone.inverse_bind),
            )
        })
        .collect::<Vec<_>>()
        .join(",")
}

fn fighter_pose_json(role: &str, model: Mat4, skin: &[Mat4], mesh: &SkinnedMeshData) -> String {
    assert_eq!(
        skin.len(),
        mesh.bones.len(),
        "capture skin/bone count mismatch"
    );
    let game_skin = skin
        .iter()
        .map(|matrix| fmt_mat4_row_major(*matrix))
        .collect::<Vec<_>>()
        .join(",");
    let world_skin = skin
        .iter()
        .map(|matrix| fmt_mat4_row_major(model * *matrix))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        concat!(
            "{{\"role\":{},\"root_model_matrix_row_major\":{},",
            "\"skin_matrices_game_space_row_major\":[{}],",
            "\"world_skin_matrices_row_major\":[{}],\"bones\":[{}]}}"
        ),
        json_string(role),
        fmt_mat4_row_major(model),
        game_skin,
        world_skin,
        pose_bones_json(mesh),
    )
}

/// The offline geometry worker consumes this exact skinning stream.  `skin`
/// matches the renderer contract (`joint_world_game * inverse_bind`) and
/// `world_skin` includes the fighter model transform used by the renderer.
/// Matrices are explicitly row-major in JSON, while the runtime itself uses
/// glam's column-major `Mat4` values.
fn sample_pose_json(
    sample: &PoseSample,
    presentation: &PresentationAssets,
    mesh_hash: &str,
) -> String {
    let snapshot = &sample.snapshot;
    let player_root = root_vec(snapshot, Side::Player);
    let opponent_root = root_vec(snapshot, Side::Opponent);
    let player_model = fighter_model(player_root, opponent_root);
    let opponent_model = fighter_model(opponent_root, player_root);
    let player_skin = presentation.skin_for(snapshot.locked[0], snapshot.truth_frame);
    let opponent_skin = presentation.skin_for(snapshot.locked[1], snapshot.truth_frame);
    format!(
        concat!(
            "{{\"schema\":\"grab07-worst-substep-pose-v1\",",
            "\"physics_tick\":{},\"render_frame\":{},\"truth_frame\":{},",
            "\"matrix_layout\":\"row_major\",",
            "\"skin_matrix_semantics\":\"skin_game=joint_world_game_space*inverse_bind; world_skin=root_model*skin_game\",",
            "\"source_skin\":{},\"source_skin_sha256\":{},\"fighters\":[{},{}]}}\n"
        ),
        sample.physics_tick,
        sample.physics_tick / 2,
        snapshot.truth_frame,
        json_string(MANNEQUIN_SKIN),
        json_string(mesh_hash),
        fighter_pose_json("player", player_model, &player_skin, &presentation.mesh),
        fighter_pose_json(
            "opponent",
            opponent_model,
            &opponent_skin,
            &presentation.mesh
        ),
    )
}

fn worst_pose_json(
    output: &CaptureOutput,
    presentation: &PresentationAssets,
    mesh_hash: &str,
) -> String {
    sample_pose_json(&output.worst, presentation, mesh_hash)
}

fn prepare_output(out: &Path) {
    fs::create_dir_all(out).expect("create Grab-07 output directory");
    for name in [
        "capture.jsonl",
        "findings.jsonl",
        "phases.json",
        "cameras.json",
        "receipt.json",
        "determinism.json",
        "worst_substep.json",
        "worst_substep_pose.json",
    ] {
        let _ = fs::remove_file(out.join(name));
    }
    let _ = fs::remove_dir_all(out.join("images"));
}

fn build_receipt(out: &Path) {
    let status = Command::new("python3")
        .arg("tools/qa/build_grab07_receipt.py")
        .arg("--run-dir")
        .arg(out)
        .status()
        .expect("launch Grab-07 receipt builder");
    assert!(status.success(), "Grab-07 receipt builder failed");
}

fn main() {
    let mut no_determinism = false;
    let mut out_dir = None::<PathBuf>;
    for argument in std::env::args().skip(1) {
        if argument == "--no-determinism" {
            no_determinism = true;
        } else if out_dir.is_none() {
            out_dir = Some(PathBuf::from(argument));
        } else {
            panic!("usage: grab07_capture [--no-determinism] [OUT_DIR]");
        }
    }
    let out = out_dir.unwrap_or_else(|| PathBuf::from("qa_runs/grab07_promotion"));
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let assets = manifest.join("assets");
    let mesh_hash = sha256_file(&assets.join(MANNEQUIN_SKIN));
    let motion_hash = sha256_file(&assets.join(MOTION));
    let revision = String::from_utf8(
        Command::new("git")
            .args(["rev-parse", "HEAD"])
            .current_dir(&manifest)
            .output()
            .expect("git revision")
            .stdout,
    )
    .expect("git revision UTF-8")
    .trim()
    .to_owned();
    let executable_hash =
        sha256_file(&std::env::current_exe().expect("current capture executable"));

    let first = simulate(&revision, &mesh_hash);
    let second = simulate(&revision, &mesh_hash);
    assert_eq!(
        first.final_truth_hash, second.final_truth_hash,
        "two fresh PlanPhase runs must have identical truth_hash"
    );
    assert_eq!(
        first.capture_jsonl, second.capture_jsonl,
        "two fresh capture traces must be byte-identical"
    );
    assert_eq!(
        first.findings_jsonl, second.findings_jsonl,
        "two fresh contact findings must be byte-identical"
    );
    let presentation = PresentationAssets::load(&assets);
    let first_pose_json = worst_pose_json(&first, &presentation, &mesh_hash);
    let second_pose_json = worst_pose_json(&second, &presentation, &mesh_hash);
    assert_eq!(
        first_pose_json, second_pose_json,
        "two fresh worst-substep pose exports must be byte-identical"
    );

    prepare_output(&out);
    fs::write(out.join("capture.jsonl"), &first.capture_jsonl).expect("write capture.jsonl");
    fs::write(out.join("findings.jsonl"), &first.findings_jsonl).expect("write findings.jsonl");
    fs::write(
        out.join("phases.json"),
        phase_json(&first, &revision, &executable_hash, &mesh_hash),
    )
    .expect("write phases.json");
    fs::write(
        out.join("cameras.json"),
        cameras_json(&revision, &executable_hash, &mesh_hash),
    )
    .expect("write cameras.json");
    fs::write(out.join("worst_substep.json"), worst_json(&first))
        .expect("write posed worst-substep state");
    fs::write(out.join("worst_substep_pose.json"), first_pose_json)
        .expect("write posed worst-substep skin matrices");
    if let Some(secure_grab) = &first.secure_grab {
        fs::write(
            out.join("secure_grab_pose.json"),
            sample_pose_json(secure_grab, &presentation, &mesh_hash),
        )
        .expect("write posed secure-grab skin matrices");
    }
    render_views(&assets, &first.worst, &out.join("images"));
    build_receipt(&out);

    let secure = first
        .phase_spans
        .iter()
        .find(|(phase, _, _)| *phase == CapturePhase::SecureGrab)
        .expect("secure span");
    assert!(
        !first.contact_substeps.is_empty(),
        "capture must retain 120 Hz contact substeps"
    );
    println!("GRAB07_CAPTURE=PASS output={}", out.display());
    println!("GRAB07_TRUTH_HASH={:016x}", first.final_truth_hash);
    println!("GRAB07_DETERMINISTIC_RERUN=PASS");
    println!("GRAB07_SECURE_GRAB={}..{}", secure.1, secure.2);
    println!("GRAB07_CONTACT_SUBSTEPS={:?}", first.contact_substeps);
    println!(
        "GRAB07_WORST_SUBSTEP={} depth_m={:.9}",
        first.worst.physics_tick, first.worst_depth
    );
    println!(
        "GRAB07_ASSET_HASHES mesh={} motion={}",
        mesh_hash, motion_hash
    );
    if !no_determinism {
        println!(
            "GRAB07_NOTE=Run tools/qa/verify_grab07_determinism.py with --no-determinism for external receipt-byte G6 evidence"
        );
    }
}
