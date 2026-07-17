#!/usr/bin/env python3
"""Focused contract tests for the offline ARDY -> MotionBricks forward path."""
from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from motionbricks_service import generate_interaction_clip  # noqa: E402
from motionbricks_service.interaction_forward import (  # noqa: E402
    InteractionForwardProposalV1,
    OfflineGenerationCertificateV1,
    apply_fk_targets,
    canonical_json,
    parse_authorized_request,
    sha256_json,
    strict_json_load,
)

CERTIFICATE_TOOL = ROOT / "tools/qa/generate_motionbricks_interaction_certificate.py"
CORPUS_TOOL = ROOT / "tools/qa/build_interaction_corpus.py"
PARTITIONS_TOOL = ROOT / "tools/qa/build_motionbricks_interaction_partitions.py"


def proposal_document() -> dict[str, object]:
    identity3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    document: dict[str, object] = {
        "schema": "just-dodge.motionbricks.interaction-forward/v1",
        "proposal_id": "ardy-offline-strike-0001",
        "ardy_source_sha256": "a" * 64,
        "ardy_checkpoint_sha256": "b" * 64,
        "motionbricks_interaction_checkpoint_sha256": "c" * 64,
        "normalization_sha256": "d" * 64,
        "source_rig_sha256": "e" * 64,
        "seed": 7,
        "action": "Strike",
        "weapon": "Longsword",
        "stance": "Top",
        "horizon_frames": 4,
        "context_frame": None,
        "fk_targets": [
            {"frame_offset": 0, "joint_index": 0, "position_m": [0.0, 1.0, 0.0], "rotation_matrix": identity3},
            {"frame_offset": 3, "joint_index": 25, "position_m": [0.2, 1.4, 0.5], "rotation_matrix": identity3},
        ],
        "outcome_authority": "deterministic_physics_only",
        "runtime_admitted": False,
    }
    document["proposal_sha256"] = sha256_json(document)
    return document


class MotionBricksInteractionForwardTest(unittest.TestCase):
    def test_certificate_binds_proposal_and_fk_targets(self) -> None:
        document = proposal_document()
        proposal = InteractionForwardProposalV1.from_dict(document)
        certificate = OfflineGenerationCertificateV1.issue(proposal, "certificate-0001", "f" * 64)
        parsed_proposal, parsed_certificate = parse_authorized_request(document, certificate.to_dict())
        self.assertEqual(parsed_proposal.digest, proposal.digest)
        self.assertEqual(parsed_certificate.proposal_sha256, proposal.digest)

        positions = torch.zeros((1, 4, 34, 3), dtype=torch.float32)
        rotations = torch.eye(3, dtype=torch.float32).reshape(1, 1, 1, 3, 3).repeat(1, 4, 34, 1, 1)
        result_positions, result_rotations = apply_fk_targets(positions, rotations, proposal)
        self.assertEqual(result_positions[0, 0, 0].tolist(), [0.0, 1.0, 0.0])
        self.assertEqual(result_positions[0, 3, 25].tolist(), [0.20000000298023224, 1.399999976158142, 0.5])
        self.assertTrue(torch.equal(result_rotations[0, 3, 25], torch.eye(3)))
        self.assertTrue(callable(generate_interaction_clip))

    def test_bridge_accepts_only_authorized_fk_request_before_model_load(self) -> None:
        proposal = InteractionForwardProposalV1.from_dict(proposal_document())
        certificate = OfflineGenerationCertificateV1.issue(proposal, "certificate-bridge", "f" * 64)
        bridge = importlib.import_module("motionbricks_service.generate")

        class FakeMotionRep:
            def inverse(self, _features: torch.Tensor, **_kwargs: object) -> dict[str, torch.Tensor]:
                positions = torch.zeros((1, 4, 34, 3), dtype=torch.float32)
                rotations = torch.eye(3, dtype=torch.float32).reshape(1, 1, 1, 3, 3).repeat(1, 4, 34, 1, 1)
                return {"posed_joints": positions, "global_joint_rots": rotations}

        fake_service = {"ready": True, "device": "cpu", "motion_rep": FakeMotionRep()}
        expected_frames = np.zeros((2, 413), dtype=np.float32)
        with (
            mock.patch.object(bridge, "init_service", return_value=fake_service) as init_service,
            mock.patch.object(bridge, "_load_primitive", return_value=np.zeros((4, 414), dtype=np.float32)),
            mock.patch.object(bridge, "_context_to_transforms", return_value=("context-pos", "context-rot")),
            mock.patch.object(bridge, "_run_inference", return_value="prediction") as run_inference,
            mock.patch.object(bridge, "_to_413_frames", return_value=expected_frames),
        ):
            payload = bridge.generate_interaction_clip(proposal.to_dict(), certificate.to_dict())
        self.assertEqual(payload, expected_frames.tobytes())
        init_service.assert_called_once_with()
        run_inference.assert_called_once()

        invalid_certificate = certificate.to_dict()
        invalid_certificate["proposal_sha256"] = "0" * 64
        invalid_certificate["certificate_sha256"] = sha256_json(
            {key: value for key, value in invalid_certificate.items() if key != "certificate_sha256"}
        )
        with mock.patch.object(bridge, "init_service") as forbidden_load:
            with self.assertRaisesRegex(ValueError, "do not exactly authorize"):
                bridge.generate_interaction_clip(proposal.to_dict(), invalid_certificate)
        forbidden_load.assert_not_called()

    def test_rejects_invalid_so3_and_receipt_drift(self) -> None:
        invalid = proposal_document()
        invalid["fk_targets"][0]["rotation_matrix"][0][0] = 2.0  # type: ignore[index]
        invalid["proposal_sha256"] = sha256_json({key: value for key, value in invalid.items() if key != "proposal_sha256"})
        with self.assertRaisesRegex(ValueError, "orthonormal"):
            InteractionForwardProposalV1.from_dict(invalid)

        proposal = InteractionForwardProposalV1.from_dict(proposal_document())
        certificate = OfflineGenerationCertificateV1.issue(proposal, "certificate-0002", "f" * 64).to_dict()
        certificate["seed"] = 8
        certificate["certificate_sha256"] = sha256_json(
            {key: value for key, value in certificate.items() if key != "certificate_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "do not exactly authorize"):
            parse_authorized_request(proposal.to_dict(), certificate)

    def test_generator_and_partitions_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="motionbricks-interaction-") as temporary:
            temp = Path(temporary)
            proposal_path = temp / "proposal.json"
            proposal_path.write_bytes(canonical_json(proposal_document()) + b"\n")
            certificates = [temp / "certificate-a.json", temp / "certificate-b.json"]
            for output in certificates:
                subprocess.run(
                    [sys.executable, str(CERTIFICATE_TOOL), "--proposal", str(proposal_path), "--output", str(output), "--certificate-id", "certificate-0003"],
                    cwd=ROOT,
                    check=True,
                )
            self.assertEqual(certificates[0].read_bytes(), certificates[1].read_bytes())
            certificate = strict_json_load(certificates[0].read_text("utf-8"))
            parse_authorized_request(proposal_document(), certificate)

            corpus_dir = temp / "corpus"
            subprocess.run([sys.executable, str(CORPUS_TOOL), "--out", str(corpus_dir)], cwd=ROOT, check=True)
            partition_outputs = [temp / "partitions-a.json", temp / "partitions-b.json"]
            for output in partition_outputs:
                subprocess.run(
                    [sys.executable, str(PARTITIONS_TOOL), "--corpus", str(corpus_dir / "interaction_corpus.json"), "--output", str(output)],
                    cwd=ROOT,
                    check=True,
                )
            self.assertEqual(partition_outputs[0].read_bytes(), partition_outputs[1].read_bytes())
            manifest = strict_json_load(partition_outputs[0].read_text("utf-8"))
            # Check the self-hash correctly, without treating the self field as input.
            unsealed = dict(manifest)
            supplied = unsealed.pop("manifest_sha256")
            self.assertEqual(supplied, sha256_json(unsealed))
            self.assertEqual({name: manifest["splits"][name]["count"] for name in ("train", "validation", "test")}, {"train": 54, "validation": 54, "test": 54})
            groups = [set(manifest["splits"][name]["partition_groups"]) for name in ("train", "validation", "test")]
            self.assertFalse(groups[0] & groups[1])
            self.assertFalse(groups[0] & groups[2])
            self.assertFalse(groups[1] & groups[2])


if __name__ == "__main__":
    unittest.main()
