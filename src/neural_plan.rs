//! Canonical live-neural plan packet and fail-closed asynchronous handoff.
//!
//! This boundary does not admit a model. ARDY and a compatible trained
//! MotionBricks interaction extension may produce packets only after their
//! separate provenance and distributional gates pass. Replay and rollback
//! record these canonical bytes and never rerun either model.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::truth::Side;

pub const NEURAL_PLAN_SCHEMA_VERSION: u16 = 1;
pub const NEURAL_JOINT_COUNT: usize = 34;
pub const MAX_NEURAL_SAMPLES: usize = 256;
pub const MAX_NEURAL_CONSTRAINTS: usize = 256;
pub const MAX_NEURAL_PROXIES: usize = 1024;
pub const ARDY_WORST_US: u32 = 500_000;
pub const MOTIONBRICKS_FEEDBACK_WORST_US: u32 = 4_000;
pub const PACKET_DECODE_WORST_US: u32 = 2_000;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NeuralModelStackV1 {
    pub ardy_source_sha256: [u8; 32],
    pub ardy_checkpoint_sha256: [u8; 32],
    /// Must identify a trained interaction-conditioning extension. The
    /// released boundary-only checkpoint is not valid in this field.
    pub motionbricks_interaction_checkpoint_sha256: [u8; 32],
    pub model_license_set_sha256: [u8; 32],
    pub source_rig_sha256: [u8; 32],
    pub normalization_sha256: [u8; 32],
    pub retargeter_sha256: [u8; 32],
    pub feedback_schema_sha256: [u8; 32],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum NeuralConstraintKind {
    Root,
    Stance,
    LeftHand,
    RightHand,
    WeaponOrientation,
    Opponent,
    PhysicsFeedback,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct QuantizedNeuralConstraintV1 {
    pub tick_offset: u16,
    pub kind: NeuralConstraintKind,
    pub subject_index: u16,
    pub position_mm: [i32; 3],
    pub rotation_6d_q15: [i16; 6],
    pub velocity_mm_s: [i32; 3],
    pub flags: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct QuantizedPoseSampleV1 {
    pub truth_tick: u64,
    pub root_position_mm: [i32; 3],
    pub root_heading_q15: [i16; 2],
    pub joint_rotation_6d_q15: Vec<[i16; 6]>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum NeuralProxyKind {
    Body,
    Weapon,
    Guard,
    Damage,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct QuantizedProxySampleV1 {
    pub truth_tick: u64,
    pub kind: NeuralProxyKind,
    pub proxy_index: u16,
    pub center_mm: [i32; 3],
    pub half_extent_mm: [u16; 3],
    pub rotation_6d_q15: [i16; 6],
}

/// Match-relevant bytes. Its SHA-256 is authoritative; request envelopes and
/// diagnostic timings are deliberately outside this value.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NeuralPlanPayloadV1 {
    pub schema_version: u16,
    pub sequence: u64,
    pub actor: Side,
    pub source_truth_tick: u64,
    pub source_truth_sha256: [u8; 32],
    pub valid_from_truth_tick: u64,
    pub valid_until_truth_tick: u64,
    pub seed: u64,
    pub models: NeuralModelStackV1,
    pub constraints: Vec<QuantizedNeuralConstraintV1>,
    pub poses: Vec<QuantizedPoseSampleV1>,
    pub proxies: Vec<QuantizedProxySampleV1>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct NeuralPlanTimingV1 {
    pub ardy_planning_us: u32,
    pub motionbricks_feedback_us: u32,
    pub packet_validation_decode_us: u32,
    pub produced_monotonic_us: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NeuralPlanPacketV1 {
    pub payload: NeuralPlanPayloadV1,
    pub timing: NeuralPlanTimingV1,
    pub payload_sha256: [u8; 32],
}

impl NeuralPlanPacketV1 {
    pub fn seal(
        payload: NeuralPlanPayloadV1,
        timing: NeuralPlanTimingV1,
    ) -> Result<Self, NeuralPlanError> {
        validate_payload(&payload)?;
        validate_timing(timing)?;
        let payload_sha256 = payload_hash(&payload)?;
        Ok(Self {
            payload,
            timing,
            payload_sha256,
        })
    }

    pub fn validate(&self) -> Result<(), NeuralPlanError> {
        validate_payload(&self.payload)?;
        validate_timing(self.timing)?;
        if self.payload_sha256 == [0; 32] {
            return Err(NeuralPlanError::MissingPayloadHash);
        }
        if payload_hash(&self.payload)? != self.payload_sha256 {
            return Err(NeuralPlanError::PayloadHashMismatch);
        }
        Ok(())
    }

    pub fn canonical_bytes(&self) -> Result<Vec<u8>, NeuralPlanError> {
        self.validate()?;
        postcard::to_stdvec(self).map_err(|_| NeuralPlanError::Serialization)
    }

    pub fn from_canonical_bytes(bytes: &[u8]) -> Result<Self, NeuralPlanError> {
        let value: Self =
            postcard::from_bytes(bytes).map_err(|_| NeuralPlanError::Serialization)?;
        value.validate()?;
        if value.canonical_bytes()?.as_slice() != bytes {
            return Err(NeuralPlanError::NonCanonicalEncoding);
        }
        Ok(value)
    }
}

fn payload_hash(payload: &NeuralPlanPayloadV1) -> Result<[u8; 32], NeuralPlanError> {
    let bytes = postcard::to_stdvec(payload).map_err(|_| NeuralPlanError::Serialization)?;
    Ok(Sha256::digest(bytes).into())
}

fn validate_payload(payload: &NeuralPlanPayloadV1) -> Result<(), NeuralPlanError> {
    if payload.schema_version != NEURAL_PLAN_SCHEMA_VERSION {
        return Err(NeuralPlanError::UnsupportedSchema(payload.schema_version));
    }
    if payload.sequence == 0 {
        return Err(NeuralPlanError::ZeroSequence);
    }
    if payload.source_truth_sha256 == [0; 32] {
        return Err(NeuralPlanError::MissingTruthHash);
    }
    if payload.valid_from_truth_tick < payload.source_truth_tick
        || payload.valid_until_truth_tick < payload.valid_from_truth_tick
    {
        return Err(NeuralPlanError::InvalidValidityInterval);
    }
    for hash in model_hashes(&payload.models) {
        if hash == &[0; 32] {
            return Err(NeuralPlanError::MissingModelReceipt);
        }
    }
    if payload.constraints.is_empty() || payload.constraints.len() > MAX_NEURAL_CONSTRAINTS {
        return Err(NeuralPlanError::InvalidLength("constraints"));
    }
    if payload.poses.is_empty() || payload.poses.len() > MAX_NEURAL_SAMPLES {
        return Err(NeuralPlanError::InvalidLength("poses"));
    }
    if payload.proxies.is_empty() || payload.proxies.len() > MAX_NEURAL_PROXIES {
        return Err(NeuralPlanError::InvalidLength("proxies"));
    }
    let mut previous_constraint = None;
    for value in &payload.constraints {
        let key = (value.tick_offset, value.kind, value.subject_index);
        if previous_constraint.is_some_and(|previous| key <= previous) {
            return Err(NeuralPlanError::NonCanonicalOrder("constraints"));
        }
        if !valid_rotation_6d(value.rotation_6d_q15) {
            return Err(NeuralPlanError::InvalidRotation);
        }
        previous_constraint = Some(key);
    }
    let mut previous_tick = None;
    for pose in &payload.poses {
        if pose.truth_tick < payload.valid_from_truth_tick
            || pose.truth_tick > payload.valid_until_truth_tick
        {
            return Err(NeuralPlanError::TickOutsideValidity("poses"));
        }
        if previous_tick.is_some_and(|previous| pose.truth_tick <= previous) {
            return Err(NeuralPlanError::NonCanonicalOrder("poses"));
        }
        if pose.joint_rotation_6d_q15.len() != NEURAL_JOINT_COUNT {
            return Err(NeuralPlanError::InvalidLength("joint_rotation_6d_q15"));
        }
        if pose
            .joint_rotation_6d_q15
            .iter()
            .any(|rotation| !valid_rotation_6d(*rotation))
        {
            return Err(NeuralPlanError::InvalidRotation);
        }
        previous_tick = Some(pose.truth_tick);
    }
    if payload.poses[0].truth_tick != payload.valid_from_truth_tick
        || payload.poses.last().map(|pose| pose.truth_tick) != Some(payload.valid_until_truth_tick)
    {
        return Err(NeuralPlanError::IncompletePoseHorizon);
    }
    let mut previous_proxy = None;
    for proxy in &payload.proxies {
        if proxy.truth_tick < payload.valid_from_truth_tick
            || proxy.truth_tick > payload.valid_until_truth_tick
        {
            return Err(NeuralPlanError::TickOutsideValidity("proxies"));
        }
        let key = (proxy.truth_tick, proxy.kind, proxy.proxy_index);
        if previous_proxy.is_some_and(|previous| key <= previous) {
            return Err(NeuralPlanError::NonCanonicalOrder("proxies"));
        }
        if proxy.half_extent_mm.contains(&0) || !valid_rotation_6d(proxy.rotation_6d_q15) {
            return Err(NeuralPlanError::InvalidProxy);
        }
        previous_proxy = Some(key);
    }
    Ok(())
}

fn model_hashes(models: &NeuralModelStackV1) -> [&[u8; 32]; 8] {
    [
        &models.ardy_source_sha256,
        &models.ardy_checkpoint_sha256,
        &models.motionbricks_interaction_checkpoint_sha256,
        &models.model_license_set_sha256,
        &models.source_rig_sha256,
        &models.normalization_sha256,
        &models.retargeter_sha256,
        &models.feedback_schema_sha256,
    ]
}

fn validate_timing(timing: NeuralPlanTimingV1) -> Result<(), NeuralPlanError> {
    if timing.ardy_planning_us > ARDY_WORST_US {
        return Err(NeuralPlanError::LatencyBudget("ardy"));
    }
    if timing.motionbricks_feedback_us > MOTIONBRICKS_FEEDBACK_WORST_US {
        return Err(NeuralPlanError::LatencyBudget("motionbricks_feedback"));
    }
    if timing.packet_validation_decode_us > PACKET_DECODE_WORST_US {
        return Err(NeuralPlanError::LatencyBudget("packet_decode"));
    }
    Ok(())
}

fn valid_rotation_6d(rotation: [i16; 6]) -> bool {
    let unit = i64::from(i16::MAX).pow(2);
    let first = rotation[..3].iter().copied().map(i64::from);
    let second = rotation[3..].iter().copied().map(i64::from);
    let first_norm: i64 = first.clone().map(|value| value * value).sum();
    let second_norm: i64 = second.clone().map(|value| value * value).sum();
    let dot: i64 = first.zip(second).map(|(left, right)| left * right).sum();
    ((unit * 3 / 4)..=(unit * 5 / 4)).contains(&first_norm)
        && ((unit * 3 / 4)..=(unit * 5 / 4)).contains(&second_norm)
        && dot.abs() <= unit / 8
}

struct BufferState {
    capacity: usize,
    next_sequence: u64,
    packets: VecDeque<NeuralPlanPacketV1>,
}

pub struct NeuralPlanProducer {
    shared: Arc<Mutex<BufferState>>,
}

pub struct NeuralPlanConsumer {
    shared: Arc<Mutex<BufferState>>,
}

pub fn neural_plan_buffer(
    capacity: usize,
) -> Result<(NeuralPlanProducer, NeuralPlanConsumer), NeuralPlanError> {
    if capacity == 0 {
        return Err(NeuralPlanError::ZeroCapacity);
    }
    let shared = Arc::new(Mutex::new(BufferState {
        capacity,
        next_sequence: 1,
        packets: VecDeque::with_capacity(capacity),
    }));
    Ok((
        NeuralPlanProducer {
            shared: Arc::clone(&shared),
        },
        NeuralPlanConsumer { shared },
    ))
}

impl NeuralPlanProducer {
    pub fn publish(
        &self,
        packet: NeuralPlanPacketV1,
        expected_source_truth_sha256: [u8; 32],
    ) -> Result<(), NeuralPlanError> {
        packet.validate()?;
        if packet.payload.source_truth_sha256 != expected_source_truth_sha256 {
            return Err(NeuralPlanError::TruthHashMismatch);
        }
        let mut state = self
            .shared
            .lock()
            .map_err(|_| NeuralPlanError::BufferPoisoned)?;
        if packet.payload.sequence != state.next_sequence {
            return Err(NeuralPlanError::SequenceGap {
                expected: state.next_sequence,
                actual: packet.payload.sequence,
            });
        }
        if state.packets.len() == state.capacity {
            return Err(NeuralPlanError::BufferFull);
        }
        state.packets.push_back(packet);
        state.next_sequence += 1;
        Ok(())
    }
}

impl NeuralPlanConsumer {
    pub fn consume(
        &self,
        truth_tick: u64,
        expected_source_truth_sha256: [u8; 32],
    ) -> Result<NeuralPlanPacketV1, NeuralPlanError> {
        let mut state = self
            .shared
            .lock()
            .map_err(|_| NeuralPlanError::BufferPoisoned)?;
        let packet = state
            .packets
            .front()
            .ok_or(NeuralPlanError::BufferUnderrun)?;
        packet.validate()?;
        if packet.payload.source_truth_sha256 != expected_source_truth_sha256 {
            return Err(NeuralPlanError::TruthHashMismatch);
        }
        if truth_tick < packet.payload.valid_from_truth_tick {
            return Err(NeuralPlanError::PacketNotReady);
        }
        if truth_tick > packet.payload.valid_until_truth_tick {
            return Err(NeuralPlanError::StalePacket);
        }
        state
            .packets
            .pop_front()
            .ok_or(NeuralPlanError::BufferUnderrun)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NeuralPlanError {
    UnsupportedSchema(u16),
    ZeroSequence,
    MissingTruthHash,
    InvalidValidityInterval,
    MissingModelReceipt,
    InvalidLength(&'static str),
    NonCanonicalOrder(&'static str),
    TickOutsideValidity(&'static str),
    IncompletePoseHorizon,
    InvalidRotation,
    InvalidProxy,
    MissingPayloadHash,
    PayloadHashMismatch,
    Serialization,
    NonCanonicalEncoding,
    LatencyBudget(&'static str),
    ZeroCapacity,
    BufferPoisoned,
    TruthHashMismatch,
    SequenceGap { expected: u64, actual: u64 },
    BufferFull,
    BufferUnderrun,
    PacketNotReady,
    StalePacket,
}

#[cfg(test)]
mod tests {
    use super::*;

    const BASIS: [i16; 6] = [i16::MAX, 0, 0, 0, i16::MAX, 0];

    fn packet(sequence: u64, source_hash: [u8; 32]) -> NeuralPlanPacketV1 {
        let models = NeuralModelStackV1 {
            ardy_source_sha256: [1; 32],
            ardy_checkpoint_sha256: [2; 32],
            motionbricks_interaction_checkpoint_sha256: [3; 32],
            model_license_set_sha256: [4; 32],
            source_rig_sha256: [5; 32],
            normalization_sha256: [6; 32],
            retargeter_sha256: [7; 32],
            feedback_schema_sha256: [8; 32],
        };
        let pose = |truth_tick| QuantizedPoseSampleV1 {
            truth_tick,
            root_position_mm: [0, 900, 0],
            root_heading_q15: [i16::MAX, 0],
            joint_rotation_6d_q15: vec![BASIS; NEURAL_JOINT_COUNT],
        };
        NeuralPlanPacketV1::seal(
            NeuralPlanPayloadV1 {
                schema_version: NEURAL_PLAN_SCHEMA_VERSION,
                sequence,
                actor: Side::Player,
                source_truth_tick: 98,
                source_truth_sha256: source_hash,
                valid_from_truth_tick: 100,
                valid_until_truth_tick: 101,
                seed: 20260714,
                models,
                constraints: vec![QuantizedNeuralConstraintV1 {
                    tick_offset: 0,
                    kind: NeuralConstraintKind::Root,
                    subject_index: 0,
                    position_mm: [0, 900, 0],
                    rotation_6d_q15: BASIS,
                    velocity_mm_s: [0; 3],
                    flags: 0,
                }],
                poses: vec![pose(100), pose(101)],
                proxies: vec![QuantizedProxySampleV1 {
                    truth_tick: 100,
                    kind: NeuralProxyKind::Body,
                    proxy_index: 0,
                    center_mm: [0, 900, 0],
                    half_extent_mm: [200, 800, 150],
                    rotation_6d_q15: BASIS,
                }],
            },
            NeuralPlanTimingV1 {
                ardy_planning_us: 100_000,
                motionbricks_feedback_us: 2_000,
                packet_validation_decode_us: 800,
                produced_monotonic_us: 55,
            },
        )
        .unwrap()
    }

    #[test]
    fn packet_round_trips_byte_identically_one_hundred_times() {
        let packet = packet(1, [9; 32]);
        let expected = packet.canonical_bytes().unwrap();
        let mut bytes = expected.clone();
        for _ in 0..100 {
            let decoded = NeuralPlanPacketV1::from_canonical_bytes(&bytes).unwrap();
            bytes = decoded.canonical_bytes().unwrap();
        }
        assert_eq!(bytes, expected);
    }

    #[test]
    fn payload_hash_covers_pose_and_proxy_truth() {
        let packet = packet(1, [9; 32]);
        let mut pose_tamper = packet.clone();
        pose_tamper.payload.poses[0].root_position_mm[0] += 1;
        assert_eq!(
            pose_tamper.validate(),
            Err(NeuralPlanError::PayloadHashMismatch)
        );
        let mut proxy_tamper = packet.clone();
        proxy_tamper.payload.proxies[0].center_mm[0] += 1;
        assert_eq!(
            proxy_tamper.validate(),
            Err(NeuralPlanError::PayloadHashMismatch)
        );
    }

    #[test]
    fn buffer_fails_closed_on_gap_hash_stale_full_and_underrun() {
        let truth_hash = [9; 32];
        let (producer, consumer) = neural_plan_buffer(1).unwrap();
        assert_eq!(
            producer.publish(packet(2, truth_hash), truth_hash),
            Err(NeuralPlanError::SequenceGap {
                expected: 1,
                actual: 2
            })
        );
        producer.publish(packet(1, truth_hash), truth_hash).unwrap();
        assert_eq!(
            producer.publish(packet(2, truth_hash), truth_hash),
            Err(NeuralPlanError::BufferFull)
        );
        assert_eq!(
            consumer.consume(99, truth_hash),
            Err(NeuralPlanError::PacketNotReady)
        );
        assert_eq!(
            consumer.consume(102, truth_hash),
            Err(NeuralPlanError::StalePacket)
        );
        assert_eq!(
            consumer.consume(100, [10; 32]),
            Err(NeuralPlanError::TruthHashMismatch)
        );
        assert_eq!(
            consumer.consume(100, truth_hash).unwrap().payload.sequence,
            1
        );
        assert_eq!(
            consumer.consume(100, truth_hash),
            Err(NeuralPlanError::BufferUnderrun)
        );
    }

    #[test]
    fn released_checkpoint_cannot_be_represented_as_missing_extension() {
        let mut packet = packet(1, [9; 32]);
        packet
            .payload
            .models
            .motionbricks_interaction_checkpoint_sha256 = [0; 32];
        assert_eq!(packet.validate(), Err(NeuralPlanError::MissingModelReceipt));
    }
}
