//! Local-only presentation playback for one admitted BONES-SEED Dodge source.
//!
//! This module does not own action selection, truth, collision, roots, replay,
//! or physics. It maps an already-authoritative opponent Dodge snapshot to a
//! prevalidated C0 skinning frame when an explicitly supplied local source file
//! is available.

use std::fs;
use std::path::Path;

use glam::{Mat4, Vec3};

use crate::asset;
const FRAME_FLOATS: usize = 413;
const G1_JOINTS: usize = 34;
/// Measured zero-based active interval of `ib_dodge_back_L_001__A437`.
///
/// The source's `[308:413]` channels contain no contact labels. The interval
/// begins at the first sustained root-relative pose departure from rest and
/// ends at the first 30-frame recovered-pose window. The landing at frame 262
/// is insufficient: torso and arm recovery remains more than 5 cm from rest
/// until frame 470.
const DODGE_SOURCE_ACTIVE_START: usize = 21;
const DODGE_SOURCE_ACTIVE_END_EXCLUSIVE: usize = 470;
const DODGE_SOURCE_ACTIVE_FRAME_COUNT: usize =
    DODGE_SOURCE_ACTIVE_END_EXCLUSIVE - DODGE_SOURCE_ACTIVE_START;
pub const DODGE_PRESENTATION_TICKS: u32 = 80;

pub struct DodgePresentation {
    skins: Vec<Vec<Mat4>>,
}

impl DodgePresentation {
    pub fn load(
        path: &Path,
        mesh: &asset::SkinnedMeshData,
        target_reference: &[Mat4],
    ) -> std::io::Result<Self> {
        let bytes = fs::read(path)?;
        let frame_bytes = FRAME_FLOATS * std::mem::size_of::<f32>();
        if bytes.is_empty() || bytes.len() % frame_bytes != 0 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Dodge source is not a non-empty little-endian [N,413] f32 stream",
            ));
        }
        let mut source_frames = bytes
            .chunks_exact(frame_bytes)
            .map(decode_source_world)
            .collect::<std::io::Result<Vec<_>>>()?;
        active_source_range(source_frames.len())?;
        let source_reference = source_frames[0];
        let (_, _, source_reference_root) = source_reference[0].to_scale_rotation_translation();
        for source_world in &mut source_frames {
            let (_, root_rotation, _) = source_world[0].to_scale_rotation_translation();
            // Root placement is cleanbox-owned. Preserve this source's pose
            // rotations while preventing its capture-space translation from
            // moving the rendered opponent independently of the duel world.
            source_world[0] = Mat4::from_rotation_translation(root_rotation, source_reference_root);
        }
        let skins = source_frames
            .iter()
            .map(|world| {
                asset::calibrated_g1_skin_matrices(world, &source_reference, mesh, target_reference)
            })
            .collect::<std::io::Result<Vec<_>>>()?;
        Ok(Self { skins })
    }

    /// Returns a source-derived skinning pose for an already-authoritative
    /// Commit→Consequence presentation tick. The caller owns action/phase
    /// selection; this maps only the measured active source span.
    pub fn skin_for_tick(&self, tick: u32) -> &[Mat4] {
        let index = active_source_index_for_tick(tick);
        &self.skins[index]
    }
}

fn active_source_range(source_frame_count: usize) -> std::io::Result<std::ops::Range<usize>> {
    if source_frame_count < DODGE_SOURCE_ACTIVE_END_EXCLUSIVE {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!(
                "Dodge source has {source_frame_count} frames but active interval [{DODGE_SOURCE_ACTIVE_START},{DODGE_SOURCE_ACTIVE_END_EXCLUSIVE}) requires at least {DODGE_SOURCE_ACTIVE_END_EXCLUSIVE}"
            ),
        ));
    }
    Ok(DODGE_SOURCE_ACTIVE_START..DODGE_SOURCE_ACTIVE_END_EXCLUSIVE)
}

fn active_source_index_for_tick(tick: u32) -> usize {
    let presentation_tick = tick.min(DODGE_PRESENTATION_TICKS - 1) as usize;
    DODGE_SOURCE_ACTIVE_START
        + presentation_tick * (DODGE_SOURCE_ACTIVE_FRAME_COUNT - 1)
            / (DODGE_PRESENTATION_TICKS - 1) as usize
}

fn decode_source_world(bytes: &[u8]) -> std::io::Result<[Mat4; G1_JOINTS]> {
    let values = bytes
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes(chunk.try_into().expect("four-byte f32")))
        .collect::<Vec<_>>();
    if values.len() != FRAME_FLOATS || values.iter().any(|value| !value.is_finite()) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "non-finite [413] source frame",
        ));
    }
    let root = Vec3::from_slice(&values[0..3]);
    let mut world = [Mat4::IDENTITY; G1_JOINTS];
    for (joint, target) in world.iter_mut().enumerate() {
        let position = if joint == 0 {
            root
        } else {
            root + Vec3::from_slice(&values[5 + (joint - 1) * 3..8 + (joint - 1) * 3])
        };
        let offset = 104 + joint * 6;
        let x = Vec3::from_slice(&values[offset..offset + 3]).normalize_or_zero();
        let y_input = Vec3::from_slice(&values[offset + 3..offset + 6]);
        let y = (y_input - x * x.dot(y_input)).normalize_or_zero();
        let z = x.cross(y).normalize_or_zero();
        if x.length_squared() < 0.999 || y.length_squared() < 0.999 || z.length_squared() < 0.999 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("degenerate G1 6D rotation for joint {joint}"),
            ));
        }
        *target = Mat4::from_cols(
            x.extend(0.0),
            y.extend(0.0),
            z.extend(0.0),
            position.extend(1.0),
        );
    }
    Ok(world)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sampling_clamps_to_the_last_source_skin() {
        let mut skins = vec![vec![Mat4::IDENTITY]; DODGE_SOURCE_ACTIVE_END_EXCLUSIVE];
        skins[DODGE_SOURCE_ACTIVE_START][0] = Mat4::IDENTITY;
        skins[DODGE_SOURCE_ACTIVE_END_EXCLUSIVE - 1][0] = Mat4::from_scale(Vec3::splat(2.0));
        let presentation = DodgePresentation { skins };
        assert_eq!(presentation.skin_for_tick(0)[0], Mat4::IDENTITY);
        assert_eq!(
            presentation.skin_for_tick(DODGE_PRESENTATION_TICKS)[0],
            Mat4::from_scale(Vec3::splat(2.0))
        );
    }

    #[test]
    fn active_source_interval_has_locked_endpoints() {
        assert_eq!(active_source_range(470).unwrap(), 21..470);
        assert_eq!(active_source_index_for_tick(0), 21);
        assert_eq!(active_source_index_for_tick(79), 469);
        assert_eq!(active_source_index_for_tick(80), 469);
        for tick in 0..DODGE_PRESENTATION_TICKS {
            assert!(
                active_source_range(470)
                    .unwrap()
                    .contains(&active_source_index_for_tick(tick))
            );
        }
    }

    #[test]
    fn active_source_interval_rejects_short_streams() {
        let error = active_source_range(469).unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::InvalidData);
        assert!(error.to_string().contains("[21,470)"));
    }
}
