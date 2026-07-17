"""Typed, fail-closed ARDY -> MotionBricks offline interaction contract.

This module deliberately authorizes only *offline* MotionBricks generation.  It
binds an ARDY proposal, sparse SO(3) forward-kinematics targets, the exact model
receipts, and a local authorization certificate.  It does not represent contact,
injury, force, or any other deterministic-combat outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np

PROPOSAL_SCHEMA = "just-dodge.motionbricks.interaction-forward/v1"
CERTIFICATE_SCHEMA = "just-dodge.motionbricks.interaction-certificate/v1"
AUTHORIZATION_SCOPE = "offline_motionbricks_generation"
OUTCOME_AUTHORITY = "deterministic_physics_only"
JOINT_COUNT = 34
SHA256_LENGTH = 64


def canonical_json(value: object) -> bytes:
    """Return the one supported representation for identity hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def strict_json_load(raw: str) -> Any:
    """Decode JSON while rejecting duplicate keys and non-finite constants."""
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.loads(raw, object_pairs_hook=reject_pairs, parse_constant=reject_constant)


def _require_exact_keys(value: Mapping[str, Any], required: set[str], label: str) -> None:
    observed = set(value)
    if observed != required:
        missing = sorted(required - observed)
        unexpected = sorted(observed - required)
        raise ValueError(f"{label}: required keys mismatch; missing={missing} unexpected={unexpected}")


def _string(value: Any, label: str, *, max_length: int = 160) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError(f"{label} must be a non-empty string <= {max_length} chars")
    return value


def _sha256(value: Any, label: str) -> str:
    value = _string(value, label, max_length=SHA256_LENGTH)
    if len(value) != SHA256_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _finite_vector(value: Any, count: int, label: str) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != count:
        raise ValueError(f"{label} must contain exactly {count} numeric values")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} contains a non-finite value")
    return result


def _so3_matrix(value: Any, label: str) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be a 3x3 matrix")
    matrix = np.asarray([_finite_vector(row, 3, label) for row in value], dtype=np.float64)
    if not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-5, rtol=0.0):
        raise ValueError(f"{label} is not orthonormal")
    determinant = float(np.linalg.det(matrix))
    if not math.isclose(determinant, 1.0, abs_tol=1e-5, rel_tol=0.0):
        raise ValueError(f"{label} determinant must be +1, observed {determinant}")
    return tuple(tuple(float(item) for item in row) for row in matrix)


def _matrix4(value: Any, label: str) -> tuple[tuple[float, float, float, float], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        raise ValueError(f"{label} must be a 4x4 matrix")
    matrix = tuple(_finite_vector(row, 4, label) for row in value)
    _so3_matrix([row[:3] for row in matrix[:3]], f"{label}.rotation")
    if not np.allclose(np.asarray(matrix[3]), np.asarray([0.0, 0.0, 0.0, 1.0]), atol=1e-6):
        raise ValueError(f"{label} must use homogeneous final row [0, 0, 0, 1]")
    return tuple(tuple(float(item) for item in row) for row in matrix)


@dataclass(frozen=True)
class So3FkTargetV1:
    """One global forward-kinematics target. Rotation is a proper SO(3) matrix."""

    frame_offset: int
    joint_index: int
    position_m: tuple[float, float, float]
    rotation_matrix: tuple[tuple[float, ...], ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "So3FkTargetV1":
        _require_exact_keys(
            value,
            {"frame_offset", "joint_index", "position_m", "rotation_matrix"},
            "fk_target",
        )
        frame_offset = value["frame_offset"]
        joint_index = value["joint_index"]
        if not isinstance(frame_offset, int) or isinstance(frame_offset, bool) or frame_offset < 0:
            raise ValueError("fk_target.frame_offset must be a non-negative integer")
        if not isinstance(joint_index, int) or isinstance(joint_index, bool) or not 0 <= joint_index < JOINT_COUNT:
            raise ValueError(f"fk_target.joint_index must be in [0, {JOINT_COUNT})")
        return cls(
            frame_offset=frame_offset,
            joint_index=joint_index,
            position_m=_finite_vector(value["position_m"], 3, "fk_target.position_m"),
            rotation_matrix=_so3_matrix(value["rotation_matrix"], "fk_target.rotation_matrix"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "frame_offset": self.frame_offset,
            "joint_index": self.joint_index,
            "position_m": list(self.position_m),
            "rotation_matrix": [list(row) for row in self.rotation_matrix],
        }


@dataclass(frozen=True)
class InteractionForwardProposalV1:
    """ARDY proposal consumed by the offline-only MotionBricks bridge."""

    proposal_id: str
    ardy_source_sha256: str
    ardy_checkpoint_sha256: str
    motionbricks_interaction_checkpoint_sha256: str
    normalization_sha256: str
    source_rig_sha256: str
    seed: int
    action: str
    weapon: str
    stance: str
    horizon_frames: int
    context_frame: tuple[tuple[tuple[float, float, float, float], ...], ...] | None
    fk_targets: tuple[So3FkTargetV1, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InteractionForwardProposalV1":
        _require_exact_keys(
            value,
            {
                "schema",
                "proposal_id",
                "ardy_source_sha256",
                "ardy_checkpoint_sha256",
                "motionbricks_interaction_checkpoint_sha256",
                "normalization_sha256",
                "source_rig_sha256",
                "seed",
                "action",
                "weapon",
                "stance",
                "horizon_frames",
                "context_frame",
                "fk_targets",
                "outcome_authority",
                "runtime_admitted",
                "proposal_sha256",
            },
            "interaction proposal",
        )
        if value["schema"] != PROPOSAL_SCHEMA:
            raise ValueError("unsupported interaction proposal schema")
        if value["outcome_authority"] != OUTCOME_AUTHORITY:
            raise ValueError("proposal must preserve deterministic physics outcome authority")
        if value["runtime_admitted"] is not False:
            raise ValueError("proposal must be offline-only and runtime_admitted=false")
        seed = value["seed"]
        horizon_frames = value["horizon_frames"]
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64:
            raise ValueError("seed must be a u64")
        if not isinstance(horizon_frames, int) or isinstance(horizon_frames, bool) or not 1 <= horizon_frames <= 256:
            raise ValueError("horizon_frames must be in [1, 256]")
        context_raw = value["context_frame"]
        if context_raw is None:
            context = None
        else:
            if not isinstance(context_raw, Sequence) or len(context_raw) != JOINT_COUNT:
                raise ValueError(f"context_frame must contain exactly {JOINT_COUNT} joint matrices")
            context = tuple(_matrix4(item, f"context_frame[{index}]") for index, item in enumerate(context_raw))
        targets_raw = value["fk_targets"]
        if not isinstance(targets_raw, Sequence) or isinstance(targets_raw, (str, bytes)) or not targets_raw:
            raise ValueError("fk_targets must be a non-empty sequence")
        targets = tuple(So3FkTargetV1.from_dict(item) for item in targets_raw)
        keys = [(target.frame_offset, target.joint_index) for target in targets]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("fk_targets must be canonically ordered and unique by frame/joint")
        if any(target.frame_offset >= horizon_frames for target in targets):
            raise ValueError("fk_target frame_offset lies outside horizon_frames")
        proposal = cls(
            proposal_id=_string(value["proposal_id"], "proposal_id"),
            ardy_source_sha256=_sha256(value["ardy_source_sha256"], "ardy_source_sha256"),
            ardy_checkpoint_sha256=_sha256(value["ardy_checkpoint_sha256"], "ardy_checkpoint_sha256"),
            motionbricks_interaction_checkpoint_sha256=_sha256(
                value["motionbricks_interaction_checkpoint_sha256"],
                "motionbricks_interaction_checkpoint_sha256",
            ),
            normalization_sha256=_sha256(value["normalization_sha256"], "normalization_sha256"),
            source_rig_sha256=_sha256(value["source_rig_sha256"], "source_rig_sha256"),
            seed=seed,
            action=_string(value["action"], "action", max_length=48),
            weapon=_string(value["weapon"], "weapon", max_length=48),
            stance=_string(value["stance"], "stance", max_length=48),
            horizon_frames=horizon_frames,
            context_frame=context,
            fk_targets=targets,
        )
        if _sha256(value["proposal_sha256"], "proposal_sha256") != proposal.digest:
            raise ValueError("proposal_sha256 does not bind the canonical proposal")
        return proposal

    @property
    def digest(self) -> str:
        return sha256_json(self._unsealed_dict())

    def _unsealed_dict(self) -> dict[str, object]:
        return {
            "schema": PROPOSAL_SCHEMA,
            "proposal_id": self.proposal_id,
            "ardy_source_sha256": self.ardy_source_sha256,
            "ardy_checkpoint_sha256": self.ardy_checkpoint_sha256,
            "motionbricks_interaction_checkpoint_sha256": self.motionbricks_interaction_checkpoint_sha256,
            "normalization_sha256": self.normalization_sha256,
            "source_rig_sha256": self.source_rig_sha256,
            "seed": self.seed,
            "action": self.action,
            "weapon": self.weapon,
            "stance": self.stance,
            "horizon_frames": self.horizon_frames,
            "context_frame": None
            if self.context_frame is None
            else [[list(row) for row in matrix] for matrix in self.context_frame],
            "fk_targets": [target.to_dict() for target in self.fk_targets],
            "outcome_authority": OUTCOME_AUTHORITY,
            "runtime_admitted": False,
        }

    def to_dict(self) -> dict[str, object]:
        value = self._unsealed_dict()
        value["proposal_sha256"] = self.digest
        return value


@dataclass(frozen=True)
class OfflineGenerationCertificateV1:
    """Content-addressed authorization for one proposal and one model receipt set."""

    certificate_id: str
    proposal_sha256: str
    generator_sha256: str
    ardy_source_sha256: str
    ardy_checkpoint_sha256: str
    motionbricks_interaction_checkpoint_sha256: str
    normalization_sha256: str
    source_rig_sha256: str
    seed: int

    @classmethod
    def issue(cls, proposal: InteractionForwardProposalV1, certificate_id: str, generator_sha256: str) -> "OfflineGenerationCertificateV1":
        return cls(
            certificate_id=_string(certificate_id, "certificate_id"),
            proposal_sha256=proposal.digest,
            generator_sha256=_sha256(generator_sha256, "generator_sha256"),
            ardy_source_sha256=proposal.ardy_source_sha256,
            ardy_checkpoint_sha256=proposal.ardy_checkpoint_sha256,
            motionbricks_interaction_checkpoint_sha256=proposal.motionbricks_interaction_checkpoint_sha256,
            normalization_sha256=proposal.normalization_sha256,
            source_rig_sha256=proposal.source_rig_sha256,
            seed=proposal.seed,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OfflineGenerationCertificateV1":
        _require_exact_keys(
            value,
            {
                "schema",
                "certificate_id",
                "authorization_scope",
                "proposal_sha256",
                "generator_sha256",
                "ardy_source_sha256",
                "ardy_checkpoint_sha256",
                "motionbricks_interaction_checkpoint_sha256",
                "normalization_sha256",
                "source_rig_sha256",
                "seed",
                "outcome_authority",
                "runtime_admitted",
                "certificate_sha256",
            },
            "interaction certificate",
        )
        if value["schema"] != CERTIFICATE_SCHEMA or value["authorization_scope"] != AUTHORIZATION_SCOPE:
            raise ValueError("certificate is not an offline MotionBricks authorization")
        if value["outcome_authority"] != OUTCOME_AUTHORITY or value["runtime_admitted"] is not False:
            raise ValueError("certificate violates deterministic-physics/offline-only authority")
        seed = value["seed"]
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64:
            raise ValueError("certificate.seed must be a u64")
        certificate = cls(
            certificate_id=_string(value["certificate_id"], "certificate_id"),
            proposal_sha256=_sha256(value["proposal_sha256"], "proposal_sha256"),
            generator_sha256=_sha256(value["generator_sha256"], "generator_sha256"),
            ardy_source_sha256=_sha256(value["ardy_source_sha256"], "ardy_source_sha256"),
            ardy_checkpoint_sha256=_sha256(value["ardy_checkpoint_sha256"], "ardy_checkpoint_sha256"),
            motionbricks_interaction_checkpoint_sha256=_sha256(value["motionbricks_interaction_checkpoint_sha256"], "motionbricks_interaction_checkpoint_sha256"),
            normalization_sha256=_sha256(value["normalization_sha256"], "normalization_sha256"),
            source_rig_sha256=_sha256(value["source_rig_sha256"], "source_rig_sha256"),
            seed=seed,
        )
        if _sha256(value["certificate_sha256"], "certificate_sha256") != certificate.digest:
            raise ValueError("certificate_sha256 does not bind the canonical certificate")
        return certificate

    @property
    def digest(self) -> str:
        return sha256_json(self._unsealed_dict())

    def _unsealed_dict(self) -> dict[str, object]:
        return {
            "schema": CERTIFICATE_SCHEMA,
            "certificate_id": self.certificate_id,
            "authorization_scope": AUTHORIZATION_SCOPE,
            "proposal_sha256": self.proposal_sha256,
            "generator_sha256": self.generator_sha256,
            "ardy_source_sha256": self.ardy_source_sha256,
            "ardy_checkpoint_sha256": self.ardy_checkpoint_sha256,
            "motionbricks_interaction_checkpoint_sha256": self.motionbricks_interaction_checkpoint_sha256,
            "normalization_sha256": self.normalization_sha256,
            "source_rig_sha256": self.source_rig_sha256,
            "seed": self.seed,
            "outcome_authority": OUTCOME_AUTHORITY,
            "runtime_admitted": False,
        }

    def to_dict(self) -> dict[str, object]:
        value = self._unsealed_dict()
        value["certificate_sha256"] = self.digest
        return value

    def authorizes(self, proposal: InteractionForwardProposalV1) -> None:
        expected = (
            proposal.digest,
            proposal.ardy_source_sha256,
            proposal.ardy_checkpoint_sha256,
            proposal.motionbricks_interaction_checkpoint_sha256,
            proposal.normalization_sha256,
            proposal.source_rig_sha256,
            proposal.seed,
        )
        observed = (
            self.proposal_sha256,
            self.ardy_source_sha256,
            self.ardy_checkpoint_sha256,
            self.motionbricks_interaction_checkpoint_sha256,
            self.normalization_sha256,
            self.source_rig_sha256,
            self.seed,
        )
        if observed != expected:
            raise ValueError("certificate receipts do not exactly authorize this proposal")


def parse_authorized_request(
    proposal_document: Mapping[str, Any], certificate_document: Mapping[str, Any]
) -> tuple[InteractionForwardProposalV1, OfflineGenerationCertificateV1]:
    """Parse, integrity-check, and cross-bind an offline request before model load."""
    proposal = InteractionForwardProposalV1.from_dict(proposal_document)
    certificate = OfflineGenerationCertificateV1.from_dict(certificate_document)
    certificate.authorizes(proposal)
    return proposal, certificate


def apply_fk_targets(
    target_positions: Any, target_rotations: Any, proposal: InteractionForwardProposalV1
) -> tuple[Any, Any]:
    """Apply sparse global SO(3) FK targets to an existing MotionBricks target window.

    The released base checkpoint has no interaction channel, so this is explicitly
    an offline extension adapter. It never fabricates combat truth and it refuses
    to silently truncate a certified target horizon.
    """
    if target_positions.ndim != 4 or target_rotations.ndim != 5:
        raise ValueError("MotionBricks target tensors must be [B,T,34,3] and [B,T,34,3,3]")
    if target_positions.shape[:3] != target_rotations.shape[:3] or target_positions.shape[2] != JOINT_COUNT:
        raise ValueError("MotionBricks target tensors have incompatible G1 dimensions")
    available_frames = int(target_positions.shape[1])
    if proposal.horizon_frames != available_frames:
        raise ValueError(
            f"certified horizon {proposal.horizon_frames} does not match target window {available_frames}"
        )
    positions = target_positions.clone()
    rotations = target_rotations.clone()
    for target in proposal.fk_targets:
        positions[0, target.frame_offset, target.joint_index] = positions.new_tensor(target.position_m)
        rotations[0, target.frame_offset, target.joint_index] = rotations.new_tensor(target.rotation_matrix)
    return positions, rotations
