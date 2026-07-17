#!/usr/bin/env python3
"""Focused acceptance tests for the local Asset Review Studio server."""

from __future__ import annotations

import importlib.util
import base64
import hashlib
import http.client
import json
import multiprocessing
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "asset_review.py"


def load_module():
    spec = importlib.util.spec_from_file_location("asset_review", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_minimal_glb(path: Path) -> None:
    document = {
        "asset": {"version": "2.0", "generator": "test"},
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            }
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}],
        "buffers": [{"byteLength": 36}],
    }
    raw_json = json.dumps(document, separators=(",", ":")).encode("utf-8")
    raw_json += b" " * ((4 - len(raw_json) % 4) % 4)
    binary = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    total = 12 + 8 + len(raw_json) + 8 + len(binary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(raw_json), 0x4E4F534A)
        + raw_json
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def rgba_png(red: int, green: int, blue: int, alpha: int = 255) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes((0, red, green, blue, alpha))))
        + chunk(b"IEND", b"")
    )


class AssetReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "assets" / "source" / "meshy" / "test_asset" / "assembled_001" / "qa").mkdir(
            parents=True
        )
        self.asset = (
            self.root
            / "assets"
            / "source"
            / "meshy"
            / "test_asset"
            / "assembled_001"
            / "model.glb"
        )
        self.asset_path = "assets/source/meshy/test_asset/assembled_001/model.glb"
        write_minimal_glb(self.asset)
        (self.asset.parent / "qa" / "front.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        review_inputs = self.root / "review_inputs"
        review_inputs.mkdir(parents=True, exist_ok=True)
        self.review_verifier = review_inputs / "review_verifier.py"
        self.review_verifier.write_text(
            "#!/usr/bin/env python3\n"
            "print('verified replay=review_inputs/replay.ron frames=343 winner=Some(Player) "
            "hash=d1a3cc1bfb9c2f67d1a3cc1bfb9c2f67d1a3cc1bfb9c2f67d1a3cc1bfb9c2f67')\n",
            encoding="utf-8",
        )
        self.review_verifier.chmod(0o755)
        self._original_contract_verifiers = self.module._contract_replay_verifier_allowlist
        setattr(
            self.module,
            "_contract_replay_verifier_allowlist",
            lambda: (
                (
                    "review_inputs/review_verifier.py",
                    hashlib.sha256(self.review_verifier.read_bytes()).hexdigest(),
                ),
            ),
        )

    def tearDown(self) -> None:
        setattr(self.module, "_contract_replay_verifier_allowlist", self._original_contract_verifiers)
        self.temp.cleanup()

    def review_payload(self, **overrides):
        payload = {
            "schemaVersion": 2,
            "assetPath": self.asset_path,
            "artifact": self.module.artifact_identity(self.root, self.asset_path),
            "decision": "pending",
            "checklist": {},
            "comments": [],
        }
        payload.update(overrides)
        return payload

    def replay_config(self, *, with_capture: bool = True):
        replay = self.root / "qa_runs" / "replay_fixture" / "match_00.ron"
        verifier = self.root / "target" / "debug" / "m3_match"
        capture = self.root / "qa_runs" / "replay_fixture" / "result.png"
        replay.parent.mkdir(parents=True, exist_ok=True)
        verifier.parent.mkdir(parents=True, exist_ok=True)
        replay.write_text("(version:2,seed:77,events:[],hash_trace:[1,2,3])\n", encoding="utf-8")
        verifier.write_text(
            "#!/usr/bin/env python3\nprint('verified replay=fixture frames=343 winner=Some(Player) hash=d1a3cc1bfb9c2f67')\n",
            encoding="utf-8",
        )
        verifier.chmod(0o755)
        capture.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        )
        captures = (capture.relative_to(self.root).as_posix(),) if with_capture else ()
        return self.module.ReplayRunConfig(
            replay.relative_to(self.root).as_posix(),
            verifier.relative_to(self.root).as_posix(),
            captures,
            ((verifier.relative_to(self.root).as_posix(), hashlib.sha256(verifier.read_bytes()).hexdigest()),),
        )

    def review_run_declaration(
        self,
        *,
        cropped: bool = False,
        include_evidence: bool = True,
    ) -> dict:
        inputs = self.root / "review_inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        fixtures = {
            "build.bin": b"deterministic-build-v1",
            "replay.ron": b"(version:2,seed:77,events:[],hash_trace:[1,2,3])\n",
            "plan.json": b'{"schema":"pvp005-plan/v1","actions":["strike","block","grab"]}\n',
            "provider.json": b'{"provider":"fixture","version":"1"}\n',
            "checkpoint.bin": b"checkpoint-fixture-v1",
            "retarget.json": b'{"retarget":"fixture-v1"}\n',
            "beauty.png": base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ),
            "depth.png": base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ),
        }
        for name, payload in fixtures.items():
            (inputs / name).write_bytes(payload)
        produced = []
        if include_evidence:
            for aov, name in (("beauty", "beauty.png"), ("depth", "depth.png")):
                produced.append(
                    {
                        "path": f"review_inputs/{name}",
                        "kind": "image",
                        "cameraProfile": "duel-wide-v1",
                        "aov": aov,
                        "frame": 7,
                        "tick60Hz": 7,
                        "physicsTick120Hz": 14,
                        "physicsSubstep": 0,
                    }
                )
        camera_inventory = [
            {
                "profile": "duel-wide-v1",
                "revision": "camera-rig-v3",
                "width": 2 if cropped else 1,
                "height": 1,
            },
        ]
        aov_inventory = [
            {
                "name": "beauty",
                "cameraProfile": "duel-wide-v1",
                "geometryCompatibilityGroup": "duel-geometry-v1",
            },
            {
                "name": "depth",
                "cameraProfile": "duel-wide-v1",
                "geometryCompatibilityGroup": "duel-geometry-v1",
            },
        ]
        required_evidence = [
            {"cameraProfile": "duel-wide-v1", "aov": "beauty"},
            {"cameraProfile": "duel-wide-v1", "aov": "depth"},
        ]
        canonical_plan = {
            "schema": "forgelens.canonical-plan/v1",
            "workflowRevision": "pvp005-w0-review-workflow/v1",
            "cameraInventory": camera_inventory,
            "aovInventory": aov_inventory,
            "requiredEvidence": required_evidence,
        }
        (inputs / "plan.json").write_text(
            json.dumps(canonical_plan, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "schema": "forgelens.evidence-manifest/v1",
            "workflowRevision": "pvp005-w0-review-workflow/v1",
            "cameraInventorySha256": hashlib.sha256(
                json.dumps(camera_inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "artifacts": [
                {
                    **artifact,
                    "sha256": hashlib.sha256((self.root / artifact["path"]).read_bytes()).hexdigest(),
                    "bytes": (self.root / artifact["path"]).stat().st_size,
                    "width": 1,
                    "height": 1,
                    "captureRect": {"x": 0, "y": 0, "width": 1, "height": 1},
                }
                for artifact in produced
            ],
        }
        (inputs / "evidence_manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return {
            "schema": "forgelens.review-run-declaration/v1",
            "workflowRevision": "pvp005-w0-review-workflow/v1",
            "buildPath": "review_inputs/build.bin",
            "replayPath": "review_inputs/replay.ron",
            "verifierPath": "review_inputs/review_verifier.py",
            "truthHash": "d1a3cc1bfb9c2f67" * 4,
            "canonicalPlanPath": "review_inputs/plan.json",
            "evidenceManifestPath": "review_inputs/evidence_manifest.json",
            "providerPath": "review_inputs/provider.json",
            "checkpointPath": "review_inputs/checkpoint.bin",
            "retargetPath": "review_inputs/retarget.json",
            "geometryPath": self.asset_path,
            "sourceAuthors": ["asset-author-7"],
            "cameraInventory": camera_inventory,
            "aovInventory": aov_inventory,
            "requiredEvidence": required_evidence,
            "producedArtifacts": produced,
        }

    def review_pin(self, run: dict, *, aov: str = "beauty") -> dict:
        return {
            "schema": "forgelens.review-pin/v1",
            "pinId": "pin-combat-0001",
            "revision": run["lineage"]["code"]["revision"],
            "artifactSha256": run["lineage"]["geometry"]["sha256"],
            "workflowRevision": run["lineage"]["workflowRevision"],
            "canonicalPlanSha256": run["lineage"]["canonicalPlanPacket"]["sha256"],
            "geometryIdentitySha256": run["lineage"]["geometryIdentitySha256"],
            "frame": 7,
            "tick60Hz": 7,
            "physicsTick120Hz": 14,
            "physicsSubstep": 0,
            "cameraProfile": "duel-wide-v1",
            "aov": aov,
            "screenPoint": {"x": 0.42, "y": 0.61},
            "worldRay": {"origin": [0.0, 1.5, 3.0], "direction": [0.0, -0.2, -1.0]},
            "triangleId": "triangle-41",
            "objectId": "defender-body",
            "boneId": "hand.L",
            "socketId": "weapon-grip.L",
            "contactId": "contact-17",
            "severity": "blocker",
            "category": "gameplay",
            "text": "Weapon and hand separate during the first readable strike frame.",
            "author": "reviewer-17",
            "createdAt": "2026-07-15T12:00:00Z",
            "updatedAt": "2026-07-15T12:00:00Z",
            "status": "open",
            "resolutionRevision": None,
        }

    def human_attestation(self, run: dict, *, reviewer: str = "reviewer-17") -> dict:
        return {
            "proposedDecision": "pass",
            "reviewerId": reviewer,
            "humanAttestation": "I attest that I am a human reviewer and made this decision from direct blinded observation.",
            "authorshipExcluded": True,
            "blindObservationAt": "2026-07-15T12:00:00Z",
            "labelRevealedAt": "2026-07-15T12:01:00Z",
            "decisionAt": "2026-07-15T12:02:00Z",
            "sourceRevision": run["lineage"]["code"]["revision"],
        }

    def test_review_run_schema_binds_exact_lineage_and_fails_closed_on_missing_fields(self) -> None:
        declaration = self.review_run_declaration()
        run = self.module.build_review_run(self.root, declaration)
        self.assertEqual(run["schema"], "forgelens.review-run/v1")
        self.assertEqual(run["lineage"]["workflowRevision"], "pvp005-w0-review-workflow/v1")
        self.assertEqual(run["lineage"]["build"]["sha256"], hashlib.sha256((self.root / declaration["buildPath"]).read_bytes()).hexdigest())
        self.assertEqual(run["lineage"]["replay"]["sha256"], hashlib.sha256((self.root / declaration["replayPath"]).read_bytes()).hexdigest())
        self.assertEqual(run["lineage"]["canonicalPlanPacket"]["sha256"], hashlib.sha256((self.root / declaration["canonicalPlanPath"]).read_bytes()).hexdigest())
        self.assertEqual(run["lineage"]["truthVerification"]["replayHash"], declaration["truthHash"])
        self.assertEqual(
            run["lineage"]["evidenceManifest"]["sha256"],
            hashlib.sha256((self.root / declaration["evidenceManifestPath"]).read_bytes()).hexdigest(),
        )
        self.assertEqual(run["decisionChainHeadSha256"], None)
        self.assertEqual(len(run["lineage"]["code"]["workingTreeDiffSha256"]), 64)
        self.assertEqual(len(run["lineage"]["code"]["stagedDiffSha256"]), 64)
        self.assertEqual(len(run["lineage"]["code"]["untrackedInventorySha256"]), 64)
        for missing in (
            "buildPath",
            "replayPath",
            "verifierPath",
            "truthHash",
            "canonicalPlanPath",
            "evidenceManifestPath",
            "cameraInventory",
            "aovInventory",
            "providerPath",
            "checkpointPath",
            "retargetPath",
            "producedArtifacts",
        ):
            malformed = dict(declaration)
            malformed.pop(missing)
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, missing):
                self.module.build_review_run(self.root, malformed)
        wrong_revision = dict(declaration, sourceRevision="f" * 40)
        with self.assertRaisesRegex(ValueError, "sourceRevision"):
            self.module.build_review_run(self.root, wrong_revision)
        wrong_truth = dict(declaration, truthHash="f" * 64)
        with self.assertRaisesRegex(ValueError, "truthHash|replay truth"):
            self.module.build_review_run(self.root, wrong_truth)
        unbound_flags = self.review_run_declaration()
        unbound_flags["producedArtifacts"][0]["fullFrame"] = True
        with self.assertRaisesRegex(ValueError, "unknown|exactly match"):
            self.module.build_review_run(self.root, unbound_flags)
        forged_camera = self.review_run_declaration()
        forged_camera["cameraInventory"][0]["width"] = 2
        with self.assertRaisesRegex(ValueError, "canonical plan"):
            self.module.build_review_run(self.root, forged_camera)
        forged_png = self.review_run_declaration(cropped=True)
        beauty_path = self.root / "review_inputs" / "beauty.png"
        png = bytearray(beauty_path.read_bytes())
        png[16:20] = (2).to_bytes(4, "big")
        png[29:33] = (zlib.crc32(bytes(png[12:29])) & 0xFFFFFFFF).to_bytes(4, "big")
        beauty_path.write_bytes(png)
        forged_png_manifest_path = self.root / forged_png["evidenceManifestPath"]
        forged_png_manifest = json.loads(forged_png_manifest_path.read_text(encoding="utf-8"))
        forged_png_manifest["artifacts"][0]["sha256"] = hashlib.sha256(png).hexdigest()
        forged_png_manifest["artifacts"][0]["width"] = 2
        forged_png_manifest["artifacts"][0]["captureRect"]["width"] = 2
        forged_png_manifest_path.write_text(
            json.dumps(forged_png_manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "decoded byte count|declared dimensions"):
            self.module.build_review_run(self.root, forged_png)
        forged_manifest = self.review_run_declaration()
        manifest_path = self.root / forged_manifest["evidenceManifestPath"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "evidence manifest|sha256"):
            self.module.build_review_run(self.root, forged_manifest)
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.module.build_review_run(self.root, {**declaration, "canonicalPlanSha25": "typo"})

    def test_review_run_eligibility_rejects_cropped_missing_and_changed_evidence(self) -> None:
        cropped = self.module.build_review_run(self.root, self.review_run_declaration(cropped=True))
        cropped_eligibility = self.module.review_run_eligibility(self.root, cropped)
        self.assertIn("cropped_only_review_input", cropped_eligibility["blockers"])
        missing = self.module.build_review_run(self.root, self.review_run_declaration(include_evidence=False))
        missing_eligibility = self.module.review_run_eligibility(self.root, missing)
        self.assertIn("missing_required_evidence", missing_eligibility["blockers"])
        complete = self.module.build_review_run(self.root, self.review_run_declaration())
        (self.root / "review_inputs" / "plan.json").write_bytes(b"changed-plan")
        (self.root / "review_inputs" / "beauty.png").write_bytes(b"changed-evidence")
        changed = self.module.review_run_eligibility(self.root, complete)
        self.assertIn("canonical_plan_changed", changed["blockers"])
        self.assertIn("produced_artifact_changed", changed["blockers"])

    def test_review_run_eligibility_remeasures_every_bound_lineage_input(self) -> None:
        roles = {
            "build": "buildPath",
            "replay": "replayPath",
            "verifier": "verifierPath",
            "canonical_plan": "canonicalPlanPath",
            "evidence_manifest": "evidenceManifestPath",
            "provider": "providerPath",
            "checkpoint": "checkpointPath",
            "retarget": "retargetPath",
            "geometry": "geometryPath",
        }
        for role, declaration_field in roles.items():
            with self.subTest(role=role):
                declaration = self.review_run_declaration()
                run = self.module.build_review_run(self.root, declaration)
                path = self.root / declaration[declaration_field]
                original = path.read_bytes()
                path.write_bytes(original + b"\npost-run-mutation")
                eligibility = self.module.review_run_eligibility(self.root, run)
                self.assertIn(f"lineage_input_changed:{role}", eligibility["blockers"])
                path.write_bytes(original)

    def test_review_pin_identity_retains_compatible_aov_and_marks_geometry_or_revision_stale(self) -> None:
        run = self.module.build_review_run(self.root, self.review_run_declaration())
        pin = self.module.validate_review_pin(self.review_pin(run), run)
        retained = self.module.review_pin_status(
            pin,
            run,
            {
                "revision": pin["revision"],
                "artifactSha256": pin["artifactSha256"],
                "workflowRevision": pin["workflowRevision"],
                "canonicalPlanSha256": pin["canonicalPlanSha256"],
                "geometryIdentitySha256": pin["geometryIdentitySha256"],
                "frame": pin["frame"],
                "tick60Hz": pin["tick60Hz"],
                "physicsTick120Hz": pin["physicsTick120Hz"],
                "physicsSubstep": pin["physicsSubstep"],
                "cameraProfile": pin["cameraProfile"],
                "aov": "depth",
            },
        )
        self.assertEqual(retained["status"], "active")
        self.assertTrue(retained["aovGeometryCompatible"])
        for key, value in (("geometryIdentitySha256", "f" * 64), ("revision", "e" * 40)):
            context = dict(retained["context"])
            context[key] = value
            stale = self.module.review_pin_status(pin, run, context)
            self.assertEqual(stale["status"], "stale")
            self.assertIn(key, stale["mismatches"])
            eligibility = self.module.review_run_eligibility(self.root, run, pin_statuses=[stale])
            self.assertIn("stale_pin", eligibility["blockers"])
        invalid_timing = self.review_pin(run)
        invalid_timing["physicsTick120Hz"] = 15
        with self.assertRaisesRegex(ValueError, "120 Hz|physics"):
            self.module.validate_review_pin(invalid_timing, run)
        derived = self.module.derive_review_pin_context(self.root, run, pin, target_aov="depth")
        self.assertEqual(derived["tick60Hz"], pin["tick60Hz"])
        self.assertEqual(derived["physicsTick120Hz"], pin["physicsTick120Hz"])
        self.assertEqual(derived["physicsSubstep"], pin["physicsSubstep"])

    def test_append_only_transition_chain_rejects_terminal_edits_and_recovers_missing_head(self) -> None:
        run = self.module.build_review_run(self.root, self.review_run_declaration())
        store = self.module.ReviewRunStore(self.root)
        created = store.create(run)
        first = created["receipts"][-1]
        self.assertEqual(first["state"], "awaiting_evidence")
        awaiting_human = store.transition(
            run["runId"],
            "awaiting_human",
            expected_previous_sha256=first["receiptSha256"],
            actor_id="server-evidence-gate",
            details={},
        )
        submitted = store.transition(
            run["runId"],
            "submitted",
            expected_previous_sha256=awaiting_human["receiptSha256"],
            actor_id="browser-session-fixture",
            details=self.human_attestation(run),
        )
        external_decision_path = self.root / "docs" / "reports" / "external-human-decision.json"
        external_decision_path.parent.mkdir(parents=True, exist_ok=True)
        external_decision_path.write_text(
            json.dumps(
                {
                    "schema": "forgelens.external-human-decision/v1",
                    "runId": run["runId"],
                    "submittedReceiptSha256": submitted["receiptSha256"],
                    "reviewerPseudonym": "reviewer-human-17",
                    "finalDecision": "pass",
                    "attestation": "I independently approve this exact immutable ReviewRun for admission.",
                    "decisionAt": "2026-07-15T10:08:00Z",
                    "sourceRevision": run["lineage"]["code"]["revision"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(self.module.TransitionError, "tracked-clean|external"):
            store.import_external_human_decision(
                run["runId"],
                "docs/reports/external-human-decision.json",
            )
        terminal = store.transition(
            run["runId"],
            "fail",
            expected_previous_sha256=submitted["receiptSha256"],
            actor_id="browser-session-fixture",
            details={"reason": "readability threshold missed"},
        )
        self.assertEqual(terminal["previousReceiptSha256"], submitted["receiptSha256"])
        with self.assertRaisesRegex(self.module.TransitionError, "terminal"):
            store.transition(
                run["runId"],
                "pass",
                expected_previous_sha256=terminal["receiptSha256"],
                actor_id="browser-session-fixture",
                details={},
            )
        head_path = store._run_directory(run["runId"]) / "head.json"
        head_path.unlink()
        recovered = self.module.ReviewRunStore(self.root).load(run["runId"])
        self.assertEqual(recovered["state"], "fail")
        self.assertEqual(recovered["headReceiptSha256"], terminal["receiptSha256"])
        for receipt in recovered["receipts"]:
            content = dict(receipt)
            digest = content.pop("receiptSha256")
            self.assertEqual(hashlib.sha256(self.module._canonical_json_bytes(content)).hexdigest(), digest)
        terminal_path = next(
            (store._run_directory(run["runId"]) / "receipts").glob(f"*-{terminal['receiptSha256']}.json")
        )
        terminal_path.unlink()
        with self.assertRaisesRegex(RuntimeError, "tail is missing"):
            self.module.ReviewRunStore(self.root).load(run["runId"])

    def test_external_human_decision_import_reaches_and_reloads_terminal_pass(self) -> None:
        declaration = self.review_run_declaration()
        for arguments in (
            ("init", "--quiet"),
            ("config", "user.name", "ForgeLens Test"),
            ("config", "user.email", "forgelens-test@example.invalid"),
            ("add", "--all"),
            ("commit", "--quiet", "-m", "fixture"),
        ):
            subprocess.run(("git", *arguments), cwd=self.root, check=True)

        run = self.module.build_review_run(self.root, declaration)
        store = self.module.ReviewRunStore(self.root)
        created = store.create(run)
        store.save_pin(run["runId"], self.review_pin(run))
        awaiting_human = store.transition(
            run["runId"],
            "awaiting_human",
            expected_previous_sha256=created["receipts"][-1]["receiptSha256"],
            actor_id="server-evidence-gate",
            details={},
        )
        submitted = store.transition(
            run["runId"],
            "submitted",
            expected_previous_sha256=awaiting_human["receiptSha256"],
            actor_id="browser-session-fixture",
            details=self.human_attestation(run, reviewer="reviewer-human-17"),
        )
        decision_relative = "docs/reports/external-human-decision.json"
        decision_path = self.root / decision_relative
        decision_path.parent.mkdir(parents=True, exist_ok=True)
        decision_path.write_text(
            json.dumps(
                {
                    "schema": "forgelens.external-human-decision/v1",
                    "runId": run["runId"],
                    "submittedReceiptSha256": submitted["receiptSha256"],
                    "reviewerPseudonym": "reviewer-human-17",
                    "finalDecision": "pass",
                    "attestation": "I independently approve this exact immutable ReviewRun for admission.",
                    "decisionAt": "2026-07-15T12:08:00Z",
                    "sourceRevision": run["lineage"]["code"]["revision"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(("git", "add", "--", decision_relative), cwd=self.root, check=True)
        subprocess.run(
            ("git", "commit", "--quiet", "-m", "independent human decision"),
            cwd=self.root,
            check=True,
        )

        original_file_identity = self.module._file_identity

        def mismatched_external_identity(root, relative, field):
            identity = original_file_identity(root, relative, field)
            if field == "externalHumanDecisionPath":
                identity = {**identity, "sha256": "0" * 64}
            return identity

        setattr(self.module, "_file_identity", mismatched_external_identity)
        try:
            with self.assertRaisesRegex(self.module.TransitionError, "changed while being read"):
                store.import_external_human_decision(run["runId"], decision_relative)
        finally:
            setattr(self.module, "_file_identity", original_file_identity)

        original_git_command = self.module._git_command

        def missing_committed_decision(root, arguments):
            if arguments[:1] == ["show"]:
                return subprocess.CompletedProcess(arguments, 1, b"", b"missing")
            return original_git_command(root, arguments)

        setattr(self.module, "_git_command", missing_committed_decision)
        try:
            with self.assertRaisesRegex(self.module.TransitionError, "committed bytes are not recoverable"):
                store.import_external_human_decision(run["runId"], decision_relative)
        finally:
            setattr(self.module, "_git_command", original_git_command)

        original_pin_context = self.module.derive_review_pin_context

        def stale_pin_context(root, review_run, pin, *, target_aov=None):
            context = original_pin_context(root, review_run, pin, target_aov=target_aov)
            return {**context, "geometryIdentitySha256": "f" * 64}

        setattr(self.module, "derive_review_pin_context", stale_pin_context)
        try:
            with self.assertRaisesRegex(self.module.TransitionError, "stale_pin"):
                store.import_external_human_decision(run["runId"], decision_relative)
        finally:
            setattr(self.module, "derive_review_pin_context", original_pin_context)

        terminal = store.import_external_human_decision(run["runId"], decision_relative)
        reloaded = self.module.ReviewRunStore(self.root).load(run["runId"])

        self.assertEqual(terminal["state"], "pass")
        self.assertEqual(reloaded["state"], "pass")
        self.assertEqual(reloaded["pinStatuses"][0]["status"], "active")
        self.assertEqual(terminal["details"]["reviewerPseudonym"], "reviewer-human-17")
        self.assertEqual(
            terminal["details"]["submittedReceiptSha256"],
            submitted["receiptSha256"],
        )

    def test_review_run_transition_model_is_acyclic_terminal_and_contract_bound(self) -> None:
        contract = json.loads(
            (REPO_ROOT / "docs" / "reports" / "FORGELENS_PHASE_A_READINESS_CONTRACT.json").read_text(
                encoding="utf-8"
            )
        )["review_spine_contract"]
        graph = {state: frozenset(targets) for state, targets in contract["transitions"].items()}
        self.assertEqual(graph, self.module.REVIEW_RUN_TRANSITIONS)
        self.assertEqual(set(graph), self.module.REVIEW_RUN_STATES)
        terminal = {"pass", "fail", "superseded", "expired"}
        self.assertTrue(all(graph[state] == frozenset() for state in terminal))
        observed_paths = []

        def enumerate_paths(state: str, path: tuple[str, ...]) -> None:
            self.assertNotIn(state, path, f"cycle in ReviewRun transition graph: {path + (state,)}")
            next_path = path + (state,)
            self.assertLessEqual(len(next_path), len(graph))
            if not graph[state]:
                observed_paths.append(next_path)
                return
            for target in sorted(graph[state]):
                enumerate_paths(target, next_path)

        enumerate_paths("awaiting_evidence", ())
        self.assertIn(("awaiting_evidence", "awaiting_human", "submitted", "pass"), observed_paths)
        self.assertIn(("awaiting_evidence", "awaiting_human", "submitted", "fail"), observed_paths)
        self.assertTrue(all(path[-1] in terminal for path in observed_paths))
        self.assertTrue(
            all("submitted" not in path or "awaiting_human" in path for path in observed_paths)
        )

    def test_human_attestation_rejects_agent_self_authorship_and_blind_ordering(self) -> None:
        run = self.module.build_review_run(self.root, self.review_run_declaration())
        store = self.module.ReviewRunStore(self.root)
        created = store.create(run)
        awaiting_human = store.transition(
            run["runId"],
            "awaiting_human",
            expected_previous_sha256=created["headReceiptSha256"],
            actor_id="server-evidence-gate",
            details={},
        )
        for reviewer in ("hermes-agent", "automation-reviewer", "asset-author-7", "browser-session-fixture"):
            with self.subTest(reviewer=reviewer), self.assertRaisesRegex(ValueError, "human|author|automation"):
                store.transition(
                    run["runId"],
                    "submitted",
                    expected_previous_sha256=awaiting_human["receiptSha256"],
                    actor_id="browser-session-fixture",
                    details=self.human_attestation(run, reviewer=reviewer),
                )
        out_of_order = self.human_attestation(run)
        out_of_order["blindObservationAt"] = "2026-07-15T12:03:00Z"
        with self.assertRaisesRegex(ValueError, "blind"):
            store.transition(
                run["runId"],
                "submitted",
                expected_previous_sha256=awaiting_human["receiptSha256"],
                actor_id="browser-session-fixture",
                details=out_of_order,
            )

    def test_concurrent_transition_writers_cannot_fork_the_chain(self) -> None:
        run = self.module.build_review_run(self.root, self.review_run_declaration())
        store = self.module.ReviewRunStore(self.root)
        created = store.create(run)
        previous = created["headReceiptSha256"]
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(3)
        queue = context.Queue()

        def write_transition() -> None:
            contender = self.module.ReviewRunStore(self.root)
            barrier.wait()
            try:
                receipt = contender.transition(
                    run["runId"],
                    "awaiting_human",
                    expected_previous_sha256=previous,
                    actor_id="server-evidence-gate",
                    details={},
                )
                queue.put(("ok", receipt["receiptSha256"]))
            except Exception as exc:  # child-process result transport
                queue.put(("error", type(exc).__name__, str(exc)))

        workers = [context.Process(target=write_transition) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
        results = [queue.get(timeout=2) for _ in workers]
        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(sum(result[0] == "error" for result in results), 1)
        loaded = self.module.ReviewRunStore(self.root).load(run["runId"])
        self.assertEqual([receipt["state"] for receipt in loaded["receipts"]], ["awaiting_evidence", "awaiting_human"])

    def test_review_run_pass_requires_reachable_commit_and_tracked_clean_inputs(self) -> None:
        declaration = self.review_run_declaration()
        outside_git = self.module.build_review_run(self.root, declaration)
        self.assertIn("revision_unreachable", self.module.review_run_eligibility(self.root, outside_git)["passBlockers"])
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "ForgeLens Test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "forgelens-test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "commit.gpgsign", "false"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "--", "assets", "review_inputs"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "review inputs"], check=True)
        clean = self.module.build_review_run(self.root, declaration)
        eligibility = self.module.review_run_eligibility(self.root, clean)
        self.assertEqual(eligibility["passBlockers"], [])
        beauty_path = self.root / "review_inputs" / "beauty.png"
        beauty_path.chmod(0o755)
        dirty = self.module.build_review_run(self.root, declaration)
        self.assertIn("evidence_input_not_tracked_clean", self.module.review_run_eligibility(self.root, dirty)["passBlockers"])

    def test_review_run_store_persists_immutable_pins_and_exports_admission_packet(self) -> None:
        run = self.module.build_review_run(self.root, self.review_run_declaration())
        store = self.module.ReviewRunStore(self.root)
        created = store.create(run)
        pin = self.review_pin(run)
        saved_pin = store.save_pin(run["runId"], pin)
        self.assertEqual(saved_pin["pin"]["pinId"], pin["pinId"])
        self.assertIsNone(saved_pin["previousPinReceiptSha256"])
        loaded = store.load(run["runId"])
        self.assertEqual(loaded["pins"][0]["pinId"], pin["pinId"])
        self.assertEqual(loaded["pins"][0]["status"], "open")
        exported = store.export_admission_packet(run["runId"])
        export_path = self.root / exported["exportPath"]
        self.assertTrue(export_path.is_file())
        self.assertTrue(export_path.relative_to(self.root).as_posix().startswith("docs/reports/forgelens_review_runs/"))
        self.assertNotIn("qa_runs", export_path.relative_to(self.root).parts)
        raw = export_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), exported["exportFileSha256"])
        packet = json.loads(raw.decode("utf-8"))
        self.assertEqual(packet["reviewRun"]["decisionChainHeadSha256"], created["headReceiptSha256"])
        wrong_id = "0" * 20 if run["runId"] != "0" * 20 else "1" * 20
        wrong_directory = store._run_directory(wrong_id)
        wrong_directory.mkdir(parents=True)
        (wrong_directory / "run.json").write_bytes(
            store._run_directory(run["runId"]).joinpath("run.json").read_bytes()
        )
        with self.assertRaisesRegex(RuntimeError, "directory identity"):
            store.is_allowed_file("not/a/review/file")
        with self.assertRaisesRegex(ValueError, "pinId"):
            forged = dict(pin, pinId="../escape")
            store.save_pin(run["runId"], forged)

    def test_replay_verifier_is_path_hash_allowlisted_and_output_is_bounded(self) -> None:
        config = self.replay_config()
        self.assertEqual(self.module.build_replay_review_run(self.root, config)["verification"]["verdict"], "PASS")
        verifier = self.root / config.verifier_path
        verifier.write_text(verifier.read_text(encoding="utf-8") + "# mutation\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "allowlist"):
            self.module.build_replay_review_run(self.root, config)
        config = self.replay_config()
        verifier = self.root / config.verifier_path
        executed_replacement = self.root / "replacement-verifier-executed.txt"
        original_runner = self.module._run_bounded_process

        def replace_path_then_run(command, **kwargs):
            replacement = verifier.with_name("m3_match.replacement")
            replacement.write_text(
                "#!/usr/bin/env python3\n"
                f"open({os.fspath(executed_replacement)!r},'w').write('executed')\n"
                "print('verified replay=malicious frames=1 winner=None hash=bad')\n",
                encoding="utf-8",
            )
            replacement.chmod(0o755)
            os.replace(replacement, verifier)
            return original_runner(command, **kwargs)

        setattr(self.module, "_run_bounded_process", replace_path_then_run)
        try:
            with self.assertRaisesRegex(ValueError, "hash-to-exec|path changed"):
                self.module.build_replay_review_run(self.root, config)
        finally:
            setattr(self.module, "_run_bounded_process", original_runner)
        self.assertFalse(executed_replacement.exists(), "unallowlisted replacement verifier executed")

        replay_race_config = self.replay_config()
        replay_path = self.root / replay_race_config.replay_path

        def replace_replay_then_run(command, **kwargs):
            replacement = replay_path.with_suffix(".replacement")
            replacement.write_text("(version:2,seed:999,events:[],hash_trace:[9])\n", encoding="utf-8")
            os.replace(replacement, replay_path)
            return original_runner(command, **kwargs)

        setattr(self.module, "_run_bounded_process", replace_replay_then_run)
        try:
            with self.assertRaisesRegex(ValueError, "replay input path changed"):
                self.module.build_replay_review_run(self.root, replay_race_config)
        finally:
            setattr(self.module, "_run_bounded_process", original_runner)
        with self.assertRaisesRegex(ValueError, "timeout"):
            self.module._run_bounded_process(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                cwd=self.root,
                timeout_seconds=0.05,
                max_output_bytes=1_024,
            )
        orphan_marker = self.root / "verifier-child-survived.txt"
        child_code = f"import time; time.sleep(.25); open({os.fspath(orphan_marker)!r},'w').write('survived')"
        parent_code = (
            "import subprocess,sys,time;"
            f"subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
            "time.sleep(2)"
        )
        with self.assertRaisesRegex(ValueError, "timeout"):
            self.module._run_bounded_process(
                [sys.executable, "-c", parent_code],
                cwd=self.root,
                timeout_seconds=0.05,
                max_output_bytes=1_024,
            )
        time.sleep(0.35)
        self.assertFalse(orphan_marker.exists(), "verifier timeout left a child process alive")
        with self.assertRaisesRegex(ValueError, "output"):
            self.module._run_bounded_process(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100000); sys.stdout.flush()"],
                cwd=self.root,
                timeout_seconds=2,
                max_output_bytes=1_024,
            )

    def test_viewer_eligibility_reports_unsupported_without_silent_approximation(self) -> None:
        supported = self.module.viewer_eligibility(
            {"accessors": [], "animations": [], "extensionsRequired": [], "meshes": []}
        )
        self.assertEqual(supported, {"status": "viewer_supported", "reasons": []})
        unsupported = self.module.viewer_eligibility(
            {
                "accessors": [{"sparse": {"count": 1}}],
                "animations": [
                    {
                        "samplers": [{"interpolation": "CUBICSPLINE"}],
                        "channels": [{"target": {"path": "weights"}}],
                    }
                ],
                "extensionsRequired": ["KHR_draco_mesh_compression"],
                "meshes": [{"primitives": [{"targets": [{"POSITION": 1}]}]}],
            }
        )
        self.assertEqual(unsupported["status"], "viewer_unsupported")
        self.assertEqual(
            set(unsupported["reasons"]),
            {
                "sparse_accessor",
                "cubic_spline_animation",
                "morph_weight_animation",
                "morph_target",
                "unsupported_required_extension:KHR_draco_mesh_compression",
            },
        )
        external = self.module.viewer_eligibility(
            {
                "images": [{"uri": "texture.png"}],
                "meshes": [{"primitives": [{"mode": 1}]}],
            }
        )
        self.assertEqual(
            set(external["reasons"]),
            {"external_image_uri", "unsupported_primitive_mode:1"},
        )
        undecodable = self.module.viewer_eligibility(
            {
                "images": [{"bufferView": 0, "mimeType": "image/png"}],
                "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 4}],
                "meshes": [],
                "accessors": [],
                "animations": [],
                "extensionsRequired": [],
            }
        )
        self.assertIn("texture_decode_failure", undecodable["reasons"])
        run = self.module.build_review_run(self.root, self.review_run_declaration())
        original_read = getattr(self.module, "_read_glb_json")
        setattr(self.module, "_read_glb_json", lambda _path: {
            "accessors": [{"sparse": {"count": 1}}],
            "animations": [],
            "extensionsRequired": [],
            "meshes": [],
        })
        try:
            self.assertIn(
                "viewer_unsupported:sparse_accessor",
                self.module.review_run_eligibility(self.root, run)["blockers"],
            )
        finally:
            setattr(self.module, "_read_glb_json", original_read)
        app_source = (REPO_ROOT / "tools" / "asset_review" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"viewer_unsupported"', app_source)
        self.assertIn('"webglcontextlost"', app_source)
        self.assertIn('"webglcontextrestored"', app_source)
        self.assertIn('"recapture_required"', app_source)
        self.assertIn("texture_decode_failure", app_source)

    def test_file_route_uses_immutable_allowlist_and_rejects_symlinks(self) -> None:
        (self.root / "secret.txt").write_text("not review evidence", encoding="utf-8")
        outside = Path(self.temp.name).parent / f"outside-{os.getpid()}-{time.time_ns()}.txt"
        outside.write_text("outside", encoding="utf-8")
        symlink = self.root / "assets" / "source" / "escape.txt"
        symlink.symlink_to(outside)
        authority = self.module.BrowserAuthority("file-route-bootstrap")
        session_token, _ = authority.exchange("file-route-bootstrap")
        catalog = self.module.build_catalog(self.root)
        file_identities = self.module._catalog_file_identities(self.root, catalog)
        file_identities["assets/source/escape.txt"] = (
            {"path": "assets/source/escape.txt", "sha256": "0" * 64, "bytes": 7},
        )
        context = self.module.ServerContext(
            root=self.root,
            initial_asset=None,
            catalog=catalog,
            reviews=self.module.ReviewStore(self.root),
            authority=authority,
            review_runs=self.module.ReviewRunStore(self.root),
            file_identities=file_identities,
        )
        handler = type("AllowlistHandler", (self.module.AssetReviewHandler,), {"context": context})
        server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        cookie = f"{authority.cookie_name}={session_token}"
        try:
            for relative, expected in (
                (self.asset_path, 200),
                ("secret.txt", 403),
                ("assets/source/escape.txt", 400),
                ("../outside.txt", 403),
            ):
                with self.subTest(relative=relative):
                    connection.request(
                        "GET",
                        "/file/" + urllib.parse.quote(relative, safe=""),
                        headers={"Cookie": cookie},
                    )
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
            original_asset = self.asset.read_bytes()
            self.asset.write_bytes(original_asset + b"post-catalog-mutation")
            connection.request(
                "GET",
                "/file/" + urllib.parse.quote(self.asset_path, safe=""),
                headers={"Cookie": cookie},
            )
            stale = connection.getresponse()
            self.assertEqual(stale.status, 409)
            self.assertIn("identity", stale.read().decode("utf-8"))
            self.asset.write_bytes(original_asset)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            outside.unlink(missing_ok=True)

    def test_store_single_instance_lock_and_http_json_contract_fail_closed(self) -> None:
        lock = self.module.StoreInstanceLock(self.root)
        lock.acquire()
        context = multiprocessing.get_context("fork")
        queue = context.Queue()

        def contend() -> None:
            contender = self.module.StoreInstanceLock(self.root)
            try:
                contender.acquire()
                queue.put("acquired")
                contender.close()
            except Exception as exc:  # child-process result transport
                queue.put(f"{type(exc).__name__}:{exc}")

        worker = context.Process(target=contend)
        worker.start()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertIn("already", queue.get(timeout=2))
        lock.close()

        authority = self.module.BrowserAuthority("json-contract-bootstrap")
        session_token, session = authority.exchange("json-contract-bootstrap")
        context_value = self.module.ServerContext(
            root=self.root,
            initial_asset=None,
            catalog=self.module.build_catalog(self.root),
            reviews=self.module.ReviewStore(self.root),
            authority=authority,
        )
        handler = type("JsonContractHandler", (self.module.AssetReviewHandler,), {"context": context_value})
        server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        origin = f"http://127.0.0.1:{server.server_port}"
        headers = {
            "Cookie": f"{authority.cookie_name}={session_token}",
            "Origin": origin,
            "X-ForgeLens-CSRF": session["csrfToken"],
        }
        try:
            connection.request("POST", "/api/review", body=b"{}", headers={**headers, "Content-Type": "text/plain"})
            wrong_type = connection.getresponse()
            self.assertEqual(wrong_type.status, 415)
            wrong_type.read()
            connection.request(
                "POST",
                "/api/review",
                body=b"{bad-json",
                headers={**headers, "Content-Type": "application/json"},
            )
            malformed = connection.getresponse()
            self.assertEqual(malformed.status, 400)
            malformed.read()
            for invalid_body, expected_fragment in (
                (b'{"schemaVersion":2,"schemaVersion":2}', "duplicate"),
                (b'{"value":NaN}', "non-finite"),
            ):
                connection.request(
                    "POST",
                    "/api/review",
                    body=invalid_body,
                    headers={**headers, "Content-Type": "application/json"},
                )
                invalid = connection.getresponse()
                self.assertEqual(invalid.status, 400)
                self.assertIn(expected_fragment, invalid.read().decode("utf-8"))
            with self.assertRaisesRegex(ValueError, "compliant|range"):
                self.module._canonical_json_bytes({"value": float("nan")})
            connection.putrequest("POST", "/api/review")
            for name, value in {**headers, "Content-Type": "application/json", "Content-Length": str(self.module.MAX_REQUEST_BYTES + 1)}.items():
                connection.putheader(name, value)
            connection.endheaders()
            oversized = connection.getresponse()
            self.assertEqual(oversized.status, 413)
            oversized.read()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_review_run_http_lifecycle_persists_browser_actor_and_rejects_stale_or_expired_submission(self) -> None:
        clock = [10.0]
        authority = self.module.BrowserAuthority(
            "review-run-bootstrap",
            ttl_seconds=5,
            monotonic=lambda: clock[0],
        )
        session_token, session = authority.exchange("review-run-bootstrap")
        store = self.module.ReviewRunStore(self.root)
        catalog = self.module.build_catalog(self.root)
        context_value = self.module.ServerContext(
            root=self.root,
            initial_asset=None,
            catalog=catalog,
            reviews=self.module.ReviewStore(self.root),
            authority=authority,
            review_runs=store,
        )
        handler = type("ReviewRunApiHandler", (self.module.AssetReviewHandler,), {"context": context_value})
        server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        origin = f"http://127.0.0.1:{server.server_port}"
        mutation_headers = {
            "Content-Type": "application/json",
            "Cookie": f"{authority.cookie_name}={session_token}",
            "Origin": origin,
            "X-ForgeLens-CSRF": session["csrfToken"],
        }

        def request_json(method: str, route: str, payload: dict | None = None):
            body = None if payload is None else json.dumps(payload, separators=(",", ":"))
            headers = (
                {"Cookie": f"{authority.cookie_name}={session_token}"}
                if method == "GET"
                else mutation_headers
            )
            connection.request(method, route, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8"))

        try:
            status, created = request_json("POST", "/api/review-run", self.review_run_declaration())
            self.assertEqual(status, 201)
            run = created["reviewRun"]
            run_id = created["runId"]
            status, loaded = request_json("GET", f"/api/review-run?runId={run_id}")
            self.assertEqual(status, 200)
            self.assertEqual(loaded["headReceiptSha256"], created["headReceiptSha256"])
            pin = self.review_pin({**run, "decisionChainHeadSha256": None})
            status, pin_receipt = request_json(
                "POST", "/api/review-pin", {"runId": run_id, "pin": pin}
            )
            self.assertEqual(status, 200)
            self.assertEqual(pin_receipt["pin"]["pinId"], pin["pinId"])
            status, awaiting_human = request_json(
                "POST",
                "/api/review-run-transition",
                {
                    "runId": run_id,
                    "targetState": "awaiting_human",
                    "expectedPreviousSha256": created["headReceiptSha256"],
                    "details": {},
                },
            )
            self.assertEqual(status, 200)
            submitted_payload = {
                "runId": run_id,
                "targetState": "submitted",
                "expectedPreviousSha256": awaiting_human["receiptSha256"],
                "details": self.human_attestation({**run, "decisionChainHeadSha256": None}),
                "targetAov": "depth",
            }
            status, rejected_context = request_json(
                "POST",
                "/api/review-run-transition",
                {**submitted_payload, "pinContext": {"geometryIdentitySha256": "f" * 64}},
            )
            self.assertEqual(status, 400)
            self.assertIn("unknown", rejected_context["error"])
            viewer_head = created["viewerContext"]["headReceiptSha256"]
            status, lost = request_json(
                "POST",
                "/api/viewer-context",
                {
                    "runId": run_id,
                    "event": "context_lost",
                    "expectedPreviousSha256": viewer_head,
                },
            )
            self.assertEqual(status, 200)
            status, context_blocked = request_json("POST", "/api/review-run-transition", submitted_payload)
            self.assertEqual(status, 409)
            self.assertIn("visual_context", context_blocked["error"])
            status, restored = request_json(
                "POST",
                "/api/viewer-context",
                {
                    "runId": run_id,
                    "event": "context_restored",
                    "expectedPreviousSha256": lost["viewerReceiptSha256"],
                },
            )
            self.assertEqual(status, 200)
            status, restore_blocked = request_json("POST", "/api/review-run-transition", submitted_payload)
            self.assertEqual(status, 409)
            self.assertIn("recapture", restore_blocked["error"])
            status, missing_capture = request_json(
                "POST",
                "/api/viewer-context",
                {
                    "runId": run_id,
                    "event": "recaptured",
                    "expectedPreviousSha256": restored["viewerReceiptSha256"],
                },
            )
            self.assertEqual(status, 400)
            self.assertIn("capture", missing_capture["error"])
            status, unrelated_capture = request_json(
                "POST",
                "/api/viewer-context",
                {
                    "runId": run_id,
                    "event": "recaptured",
                    "expectedPreviousSha256": restored["viewerReceiptSha256"],
                    "capturePngBase64": base64.b64encode(rgba_png(255, 0, 0)).decode("ascii"),
                },
            )
            self.assertEqual(status, 400)
            self.assertIn("bound produced artifact", unrelated_capture["error"])
            status, recaptured = request_json(
                "POST",
                "/api/viewer-context",
                {
                    "runId": run_id,
                    "event": "recaptured",
                    "expectedPreviousSha256": restored["viewerReceiptSha256"],
                    "capturePngBase64": base64.b64encode(
                        (self.root / "review_inputs" / "beauty.png").read_bytes()
                    ).decode("ascii"),
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(recaptured["capture"]["sha256"], hashlib.sha256(
                (self.root / "review_inputs" / "beauty.png").read_bytes()
            ).hexdigest())
            original_geometry = self.asset.read_bytes()
            self.asset.write_bytes(original_geometry + b"post-run-geometry-mutation")
            status, stale_snapshot = request_json("GET", f"/api/review-run?runId={run_id}")
            self.assertEqual(status, 200)
            self.assertEqual(stale_snapshot["pinStatuses"][0]["status"], "stale")
            status, stale = request_json("POST", "/api/review-run-transition", submitted_payload)
            self.assertEqual(status, 409)
            self.assertIn("geometry", stale["error"])
            self.assertIn("stale_pin", stale["error"])
            self.asset.write_bytes(original_geometry)
            status, submitted = request_json("POST", "/api/review-run-transition", submitted_payload)
            self.assertEqual(status, 200)
            self.assertEqual(submitted["details"]["browserActorId"], session["actorId"])
            self.assertEqual(
                submitted["details"]["humanAttestationAuthority"],
                "operational-attestation-not-cryptographic-proof",
            )
            self.assertEqual(submitted["details"]["reviewPinHeads"][0]["pinId"], pin["pinId"])
            self.assertEqual(len(submitted["details"]["reviewPinSetSha256"]), 64)
            self.assertEqual(
                submitted["details"]["viewerContextReceiptSha256"],
                recaptured["viewerReceiptSha256"],
            )
            status, browser_pass = request_json(
                "POST",
                "/api/review-run-transition",
                {
                    "runId": run_id,
                    "targetState": "pass",
                    "expectedPreviousSha256": submitted["receiptSha256"],
                    "details": {},
                },
            )
            self.assertEqual(status, 409)
            self.assertIn("external human decision import", browser_pass["error"])
            status, exported = request_json(
                "POST", "/api/review-run-export", {"runId": run_id}
            )
            self.assertEqual(status, 200)
            self.assertTrue((self.root / exported["exportPath"]).is_file())
            clock[0] = 20.0
            status, expired = request_json(
                "POST",
                "/api/review-run-transition",
                {
                    "runId": run_id,
                    "targetState": "fail",
                    "expectedPreviousSha256": submitted["receiptSha256"],
                    "details": {"reason": "expired authority must not decide"},
                },
            )
            self.assertEqual(status, 401)
            self.assertIn("expired", expired["error"])
            pin_directory = store._run_directory(run_id) / "pins" / pin["pinId"]
            for receipt_path in pin_directory.glob("*.json"):
                receipt_path.unlink()
            pin_directory.rmdir()
            with self.assertRaisesRegex(RuntimeError, "ReviewPin set"):
                store.load(run_id)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_active_review_run_endpoint_and_ui_expose_blockers_without_claiming_human_proof(self) -> None:
        authority = self.module.BrowserAuthority("active-run-bootstrap")
        session_token, _ = authority.exchange("active-run-bootstrap")
        store = self.module.ReviewRunStore(self.root)
        run = self.module.build_review_run(self.root, self.review_run_declaration())
        store.create(run)
        catalog = self.module.build_catalog(self.root)
        context_value = self.module.ServerContext(
            root=self.root,
            initial_asset=None,
            catalog=catalog,
            reviews=self.module.ReviewStore(self.root),
            authority=authority,
            review_runs=store,
            active_review_run_id=run["runId"],
        )
        handler = type("ActiveReviewRunHandler", (self.module.AssetReviewHandler,), {"context": context_value})
        server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request(
                "GET",
                "/api/active-review-run",
                headers={"Cookie": f"{authority.cookie_name}={session_token}"},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["runId"], run["runId"])
            self.assertIn("revision_unreachable", payload["eligibility"]["passBlockers"])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        html = (REPO_ROOT / "tools" / "asset_review" / "index.html").read_text(encoding="utf-8")
        app_source = (REPO_ROOT / "tools" / "asset_review" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="reviewRunGate"', html)
        self.assertIn('id="reviewRunBlockers"', html)
        self.assertIn("Final approval requires an external human attestation", html)
        self.assertIn('apiFetch("/api/active-review-run")', app_source)
        self.assertIn("eligibleForPass", app_source)
        self.assertIn("operational attestation, not cryptographic proof", app_source)

    def test_safe_repo_path_rejects_traversal_and_absolute_paths(self) -> None:
        self.assertEqual(
            self.module.safe_repo_path(self.root, "assets/source/meshy/test_asset/assembled_001/model.glb"),
            self.asset,
        )
        for unsafe in ("../outside.glb", "/etc/passwd", "assets/../../outside"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                self.module.safe_repo_path(self.root, unsafe)

    def test_browser_authority_is_one_use_csrf_bound_and_expiring(self) -> None:
        now = [100.0]
        authority = self.module.BrowserAuthority(
            "one-use-bootstrap", ttl_seconds=10, monotonic=lambda: now[0]
        )
        session_token, session = authority.exchange("one-use-bootstrap")
        cookie = f"{authority.cookie_name}={session_token}"
        self.assertEqual(authority.authorize(cookie, session["csrfToken"])["actorId"], session["actorId"])
        with self.assertRaisesRegex(self.module.AuthorityError, "already used"):
            authority.exchange("one-use-bootstrap")
        with self.assertRaisesRegex(self.module.AuthorityError, "CSRF"):
            authority.authorize(cookie, "wrong-csrf")
        now[0] = 110.0
        with self.assertRaisesRegex(self.module.AuthorityError, "expired"):
            authority.authorize(cookie)

    def test_replay_review_run_binds_replay_verifier_capture_and_rejects_stale_receipts(self) -> None:
        config = self.replay_config()
        first = self.module.build_replay_review_run(self.root, config)
        second = self.module.build_replay_review_run(self.root, config)
        self.assertEqual(first, second)
        self.assertEqual(first["verification"]["truthHash"], "d1a3cc1bfb9c2f67")
        self.assertEqual(first["visualStatus"], "capture-backed")
        submitted = self.module.submit_replay_review(
            self.root,
            config,
            {
                "reviewRunFingerprint": first["fingerprintSha256"],
                "decision": "approved",
                "summary": "Bound replay and capture reviewed.",
            },
            submitted_by="human-browser-test",
        )
        self.assertEqual(submitted["submittedBy"], "human-browser-test")
        repeated = self.module.submit_replay_review(
            self.root,
            config,
            {
                "reviewRunFingerprint": first["fingerprintSha256"],
                "decision": "approved",
                "summary": "Bound replay and capture reviewed.",
            },
            submitted_by="human-browser-test",
        )
        self.assertEqual(repeated, submitted)
        replay = self.root / config.replay_path
        replay.write_text(replay.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        with self.assertRaisesRegex(self.module.StaleArtifactError, "ReviewRun changed"):
            self.module.submit_replay_review(
                self.root,
                config,
                {
                    "reviewRunFingerprint": first["fingerprintSha256"],
                    "decision": "changes-requested",
                    "summary": "stale",
                },
                submitted_by="human-browser-test",
            )
        truth_only = self.replay_config(with_capture=False)
        truth_run = self.module.build_replay_review_run(self.root, truth_only)
        with self.assertRaisesRegex(ValueError, "visual capture"):
            self.module.submit_replay_review(
                self.root,
                truth_only,
                {
                    "reviewRunFingerprint": truth_run["fingerprintSha256"],
                    "decision": "approved",
                    "summary": "cannot approve presentation",
                },
                submitted_by="human-browser-test",
            )

    def test_bootstrap_route_sets_http_only_cookie_and_rejects_replay(self) -> None:
        authority = self.module.BrowserAuthority("route-bootstrap")
        context = self.module.ServerContext(
            root=self.root,
            initial_asset=self.asset_path,
            catalog=self.module.build_catalog(self.root),
            reviews=self.module.ReviewStore(self.root),
            authority=authority,
            replay_config=self.replay_config(),
        )
        handler = type("BootstrapHandler", (self.module.AssetReviewHandler,), {"context": context})
        server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", "/auth/bootstrap?token=route-bootstrap")
            response = connection.getresponse()
            self.assertEqual(response.status, 303)
            cookie = response.getheader("Set-Cookie") or ""
            location = response.getheader("Location") or ""
            response.read()
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            self.assertNotIn("route-bootstrap", location)
            connection.request("GET", "/auth/bootstrap?token=route-bootstrap")
            replay = connection.getresponse()
            self.assertEqual(replay.status, 403)
            replay.read()
            cookie_header = cookie.split(";", 1)[0]
            connection.request("GET", "/api/session", headers={"Cookie": cookie_header})
            session_response = connection.getresponse()
            self.assertEqual(session_response.status, 200)
            session = json.loads(session_response.read().decode("utf-8"))
            forged = self.review_payload(
                decision="changes-requested",
                comments=[{"id": "authority-comment", "text": "Bound", "author": "forged-author"}]
            )
            forged["submission"] = {"submittedBy": "forged-human"}
            body = json.dumps(forged)
            connection.request(
                "POST",
                "/api/review",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            unauthenticated = connection.getresponse()
            self.assertEqual(unauthenticated.status, 403)
            unauthenticated.read()
            origin = f"http://127.0.0.1:{server.server_port}"
            connection.request(
                "POST",
                "/api/review",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Cookie": cookie_header,
                    "Origin": origin,
                    "X-ForgeLens-CSRF": session["csrfToken"],
                },
            )
            authorized = connection.getresponse()
            self.assertEqual(authorized.status, 200)
            saved = json.loads(authorized.read().decode("utf-8"))
            self.assertEqual(saved["comments"][0]["author"], session["actorId"])
            self.assertIsNone(saved["submission"])
            connection.request(
                "POST",
                "/api/report",
                body=json.dumps(saved),
                headers={
                    "Content-Type": "application/json",
                    "Cookie": cookie_header,
                    "Origin": origin,
                    "X-ForgeLens-CSRF": session["csrfToken"],
                },
            )
            report_response = connection.getresponse()
            self.assertEqual(report_response.status, 200)
            submitted = json.loads(report_response.read().decode("utf-8"))
            self.assertEqual(submitted["submission"]["submittedBy"], session["actorId"])
            connection.request("GET", "/api/replay-run", headers={"Cookie": cookie_header})
            run_response = connection.getresponse()
            self.assertEqual(run_response.status, 200)
            review_run = json.loads(run_response.read().decode("utf-8"))
            connection.request(
                "POST",
                "/api/replay-report",
                body=json.dumps(
                    {
                        "reviewRunFingerprint": review_run["fingerprintSha256"],
                        "decision": "changes-requested",
                        "summary": "Authenticated replay review.",
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                    "Cookie": cookie_header,
                    "Origin": origin,
                    "X-ForgeLens-CSRF": session["csrfToken"],
                },
            )
            replay_response = connection.getresponse()
            self.assertEqual(replay_response.status, 200)
            replay_receipt = json.loads(replay_response.read().decode("utf-8"))
            self.assertEqual(replay_receipt["submittedBy"], session["actorId"])
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_artifact_identity_rejects_path_aliases_and_normalizes_parent_hashes(self) -> None:
        alias = "assets/source/meshy/test_asset/assembled_001/../assembled_001/model.glb"
        with self.assertRaisesRegex(ValueError, "canonical repository-relative spelling"):
            self.module.artifact_identity(self.root, alias)
        parent_a = "a" * 64
        parent_b = "b" * 64
        normalized = self.module.artifact_identity(
            self.root,
            self.asset_path,
            parent_evidence_sha256=[parent_b, parent_a, parent_b],
        )
        repeated = self.module.artifact_identity(
            self.root,
            self.asset_path,
            parent_evidence_sha256=[parent_a, parent_b],
        )
        self.assertEqual(normalized["parentEvidenceSha256"], [parent_a, parent_b])
        self.assertEqual(normalized, repeated)

    def test_catalog_groups_pipeline_asset_and_reports_measured_glb_metadata(self) -> None:
        catalog = self.module.build_catalog(self.root)
        self.assertEqual(catalog["schemaVersion"], 2)
        self.assertEqual(len(catalog["assets"]), 1)
        record = catalog["assets"][0]
        self.assertEqual(record["path"], "assets/source/meshy/test_asset/assembled_001/model.glb")
        self.assertEqual(record["family"], "test_asset")
        self.assertEqual(record["stage"], "DCC / assembled")
        self.assertEqual(record["metrics"]["triangles"], 1)
        self.assertEqual(record["metrics"]["vertices"], 3)
        self.assertEqual(record["metrics"]["meshes"], 1)
        self.assertEqual(record["id"], record["artifact"]["versionId"])
        self.assertEqual(record["logicalId"], record["artifact"]["logicalId"])
        self.assertEqual(record["artifact"]["contentSha256"], self.module._sha256_file(self.asset))
        self.assertEqual(len(record["artifact"]["toolProfileSha256"]), 64)
        self.assertEqual(record["artifact"]["captureProfile"], "repository-glb/catalog-v2")
        self.assertIn("assets/source/meshy/test_asset/assembled_001/qa/front.png", record["evidenceImages"])

    def test_same_path_changed_bytes_get_a_new_artifact_version(self) -> None:
        first = self.module.build_catalog(self.root)["assets"][0]
        repeated = self.module.build_catalog(self.root)["assets"][0]
        self.assertEqual(first["id"], repeated["id"])
        self.assertEqual(first["artifact"], repeated["artifact"])

        changed = bytearray(self.asset.read_bytes())
        changed[-1] ^= 1
        self.asset.write_bytes(changed)
        second = self.module.build_catalog(self.root)["assets"][0]
        self.assertEqual(first["logicalId"], second["logicalId"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["artifact"]["contentSha256"], second["artifact"]["contentSha256"])

    def test_same_bytes_keep_their_version_across_reachable_heads_and_staged_diff_is_measured(self) -> None:
        def git(*arguments: str) -> None:
            subprocess.run(
                ["git", "-C", str(self.root), *arguments],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        git("init", "-q")
        git("config", "user.name", "ForgeLens Test")
        git("config", "user.email", "forgelens-test@example.invalid")
        git("config", "commit.gpgsign", "false")
        git("add", "--", self.asset_path)
        git("commit", "-qm", "asset baseline")
        first = self.module.artifact_identity(self.root, self.asset_path)
        self.assertEqual(first["repository"]["state"], "tracked-clean")

        (self.root / "unrelated.txt").write_text("new reachable head\n", encoding="utf-8")
        git("add", "--", "unrelated.txt")
        git("commit", "-qm", "unrelated revision")
        second = self.module.artifact_identity(self.root, self.asset_path)
        self.assertNotEqual(first["repository"]["head"], second["repository"]["head"])
        self.assertEqual(first["versionId"], second["versionId"])
        self.assertNotEqual(first["fingerprintSha256"], second["fingerprintSha256"])

        changed = bytearray(self.asset.read_bytes())
        changed[-1] ^= 1
        self.asset.write_bytes(changed)
        git("add", "--", self.asset_path)
        staged = self.module.artifact_identity(self.root, self.asset_path)
        self.assertEqual(staged["repository"]["state"], "tracked-modified")
        self.assertEqual(len(staged["repository"]["relevantDiffSha256"]), 64)
        self.assertNotEqual(staged["versionId"], second["versionId"])

    def test_review_validation_requires_asset_identity_and_bounded_surface_points(self) -> None:
        valid = {
            "schemaVersion": 2,
            "assetPath": self.asset_path,
            "artifact": self.module.artifact_identity(self.root, self.asset_path),
            "decision": "changes-requested",
            "checklist": {"silhouette": "pass", "topology": "needs-work"},
            "comments": [
                {
                    "id": "pin-1",
                    "text": "Guard silhouette collapses from this angle.",
                    "category": "silhouette",
                    "severity": "major",
                    "status": "open",
                    "author": "human",
                    "createdAt": "2026-07-14T12:00:00Z",
                    "point": {"world": [0.1, 0.2, 0.3], "normal": [0.0, 1.0, 0.0]},
                }
            ],
        }
        normalized = self.module.validate_review(valid)
        self.assertEqual(normalized["comments"][0]["point"]["world"], [0.1, 0.2, 0.3])

        invalid = json.loads(json.dumps(valid))
        invalid["comments"][0]["point"]["world"] = [float("inf"), 0.0, 0.0]
        with self.assertRaises(ValueError):
            self.module.validate_review(invalid)
        invalid = json.loads(json.dumps(valid))
        invalid["schemaVersion"] = 1
        with self.assertRaisesRegex(ValueError, "schemaVersion must be 2"):
            self.module.validate_review(invalid)

    def test_review_store_writes_atomically_outside_asset_tree(self) -> None:
        store = self.module.ReviewStore(self.root)
        payload = {
            "schemaVersion": 2,
            "assetPath": self.asset_path,
            "artifact": self.module.artifact_identity(self.root, self.asset_path),
            "decision": "pending",
            "checklist": {},
            "comments": [],
        }
        saved = store.save(payload)
        self.assertEqual(saved["assetPath"], payload["assetPath"])
        self.assertEqual(store.load(payload["assetPath"]), saved)
        review_files = list((self.root / "qa_runs" / "asset_reviews").glob("*.json"))
        self.assertEqual(len(review_files), 1)
        self.assertFalse(any(self.asset.parent.glob("*.review.json")))

    def test_neural_animation_gate_and_evidence_are_persisted_with_measured_identity(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"deterministic-test-payload"
        receipt = self.module.save_neural_evidence(
            self.root,
            {
                "assetPath": self.asset_path,
                "artifact": self.module.artifact_identity(self.root, self.asset_path),
                "clip": "Strike",
                "pngDataUrl": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            },
        )
        evidence = self.root / receipt["evidencePath"]
        self.assertEqual(evidence.read_bytes(), png)
        self.assertEqual(len(receipt["evidenceSha256"]), 64)
        normalized = self.module.validate_review(
            {
                "schemaVersion": 2,
                "assetPath": self.asset_path,
                "artifact": self.module.artifact_identity(self.root, self.asset_path),
                "decision": "changes-requested",
                "checklist": {},
                "comments": [],
                "neuralMotion": {
                    "status": "fail",
                    "clip": "Strike",
                    "model": "vision-model",
                    "summary": "Foot sliding and grip separation observed.",
                    "evidencePath": receipt["evidencePath"],
                    "evidenceSha256": receipt["evidenceSha256"],
                    "criteria": {
                        "footContacts": {"verdict": "fail", "score": 0.2, "finding": "Left foot slides."},
                        "weaponGrip": {"verdict": "fail", "score": 0.1, "finding": "Hand separates."},
                    },
                },
            }
        )
        self.assertEqual(normalized["neuralMotion"]["status"], "fail")
        self.assertEqual(normalized["neuralMotion"]["criteria"]["footContacts"]["score"], 0.2)

    def test_neural_evidence_rejects_a_stale_artifact_claim(self) -> None:
        claimed = self.module.artifact_identity(self.root, self.asset_path)
        changed = bytearray(self.asset.read_bytes())
        changed[-1] ^= 1
        self.asset.write_bytes(changed)
        png = b"\x89PNG\r\n\x1a\n" + b"stale-evidence"
        with self.assertRaisesRegex(self.module.StaleArtifactError, "artifact changed"):
            self.module.save_neural_evidence(
                self.root,
                {
                    "assetPath": self.asset_path,
                    "artifact": claimed,
                    "clip": "Strike",
                    "pngDataUrl": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                },
            )

    def test_human_report_submission_is_content_bound_and_later_edits_invalidate_receipt(self) -> None:
        store = self.module.ReviewStore(self.root)
        payload = {
            "schemaVersion": 2,
            "assetPath": self.asset_path,
            "artifact": self.module.artifact_identity(self.root, self.asset_path),
            "decision": "changes-requested",
            "checklist": {"silhouette": "needs-work"},
            "comments": [],
            "reportSummary": "Scale and silhouette require another pass.",
        }
        submitted = store.submit(payload)
        receipt = submitted["submission"]
        self.assertEqual(len(receipt["receiptId"]), 20)
        self.assertEqual(len(receipt["contentSha256"]), 64)
        self.assertEqual(receipt["receiptId"], receipt["contentSha256"][:20])
        self.assertEqual(store.load(payload["assetPath"]), submitted)

        unchanged = store.save(submitted)
        self.assertEqual(unchanged["submission"]["receiptId"], receipt["receiptId"])
        unchanged["reportSummary"] = "A different final report."
        changed = store.save(unchanged)
        self.assertIsNone(changed["submission"])

    def test_client_supplied_receipt_id_must_match_the_content_digest_prefix(self) -> None:
        store = self.module.ReviewStore(self.root)
        submitted = store.submit(
            self.review_payload(decision="changes-requested", reportSummary="Bound report")
        )
        forged = json.loads(json.dumps(submitted))
        forged["submission"]["receiptId"] = "0" * 20
        if forged["submission"]["receiptId"] == forged["submission"]["contentSha256"][:20]:
            forged["submission"]["receiptId"] = "1" * 20
        with self.assertRaisesRegex(ValueError, "content digest"):
            store.save(forged)

    def test_changed_artifact_rejects_stale_write_and_archives_prior_receipt(self) -> None:
        store = self.module.ReviewStore(self.root)
        submitted = store.submit(
            self.review_payload(
                decision="changes-requested",
                checklist={"silhouette": "needs-work"},
                reportSummary="Exact source requires another pass.",
            )
        )
        prior_receipt = submitted["submission"]["receiptId"]
        changed = bytearray(self.asset.read_bytes())
        changed[-1] ^= 1
        self.asset.write_bytes(changed)

        with self.assertRaisesRegex(self.module.StaleArtifactError, "artifact changed"):
            store.save(submitted)
        forged_current = self.review_payload(
            decision="approved",
            reportSummary="Direct current-version payload must not replace prior evidence.",
        )
        with self.assertRaisesRegex(self.module.StaleArtifactError, "superseded artifact"):
            store.save(forged_current)
        current = store.load(self.asset_path)
        self.assertEqual(current["decision"], "pending")
        self.assertIsNone(current["submission"])
        self.assertNotEqual(current["artifact"]["versionId"], submitted["artifact"]["versionId"])
        archives = list((store.directory / "superseded" / store._path(self.asset_path).stem).glob("*.json"))
        self.assertEqual(len(archives), 1)
        archive = archives[0]
        self.assertTrue(archive.is_file())
        self.assertEqual(json.loads(archive.read_text(encoding="utf-8"))["submission"]["receiptId"], prior_receipt)
        with self.assertRaisesRegex(self.module.StaleArtifactError, "receipt is stale"):
            store.submit_task_plan({"assetPath": self.asset_path, "reportReceiptId": prior_receipt})

    def test_archive_guard_cannot_move_a_newer_concurrent_review_slot(self) -> None:
        store = self.module.ReviewStore(self.root)
        saved = store.save(self.review_payload())
        path = store._path(self.asset_path)
        expected_raw = path.read_bytes()
        newer_raw = expected_raw.replace(b'"decision": "pending"', b'"decision": "approved"')
        path.write_bytes(newer_raw)
        with self.assertRaisesRegex(self.module.StaleArtifactError, "changed concurrently"):
            store._archive_stale(path, expected_raw, saved, "test-race")
        self.assertEqual(path.read_bytes(), newer_raw)

    def test_post_check_asset_replacement_cannot_leave_a_stale_review_slot(self) -> None:
        store = self.module.ReviewStore(self.root)
        payload = self.review_payload(decision="changes-requested", reportSummary="Race probe")
        original_require = store._require_current_artifact
        calls = 0

        def mutate_after_final_check(review):
            nonlocal calls
            calls += 1
            original_require(review)
            if calls == 2:
                changed = bytearray(self.asset.read_bytes())
                changed[-1] ^= 1
                self.asset.write_bytes(changed)

        store._require_current_artifact = mutate_after_final_check
        with self.assertRaisesRegex(self.module.StaleArtifactError, "artifact changed"):
            store.submit(payload)
        self.assertFalse(store._path(self.asset_path).exists())

    def test_schema_v1_snapshot_is_preserved_but_cannot_approve_current_bytes(self) -> None:
        store = self.module.ReviewStore(self.root)
        store.directory.mkdir(parents=True)
        legacy = {
            "schemaVersion": 1,
            "assetPath": self.asset_path,
            "artifact": self.module.artifact_identity(self.root, self.asset_path),
            "decision": "approved",
            "checklist": {},
            "comments": [],
            "submission": {"submittedBy": "human"},
        }
        store._path(self.asset_path).write_text(json.dumps(legacy), encoding="utf-8")
        current = store.load(self.asset_path)
        self.assertEqual(current["schemaVersion"], 2)
        self.assertEqual(current["decision"], "pending")
        self.assertIsNone(current["submission"])
        archive = self.root / current["supersededSnapshot"]["archivedPath"]
        self.assertEqual(json.loads(archive.read_text(encoding="utf-8")), legacy)

    def test_nominal_schema_v2_human_receipt_is_archived_and_requires_resubmission(self) -> None:
        store = self.module.ReviewStore(self.root)
        nominal = store.submit(
            self.review_payload(decision="changes-requested", reportSummary="Legacy nominal receipt"),
            submitted_by="human",
        )
        current = store.load(self.asset_path)
        self.assertIsNone(current["submission"])
        self.assertEqual(current["decision"], nominal["decision"])
        self.assertEqual(
            current["supersededSnapshot"]["reason"], "nominal-human-authority-replaced"
        )
        archived = self.root / current["supersededSnapshot"]["archivedPath"]
        self.assertEqual(
            json.loads(archived.read_text(encoding="utf-8"))["submission"]["receiptId"],
            nominal["submission"]["receiptId"],
        )

    def test_stale_http_writes_reports_and_report_plans_return_conflict(self) -> None:
        authority = self.module.BrowserAuthority("stale-http-bootstrap")
        session_token, session = authority.exchange("stale-http-bootstrap")
        context = self.module.ServerContext(
            root=self.root,
            initial_asset=None,
            catalog=self.module.build_catalog(self.root),
            reviews=self.module.ReviewStore(self.root),
            authority=authority,
        )
        handler = type("TestAssetReviewHandler", (self.module.AssetReviewHandler,), {"context": context})
        server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            submitted = context.reviews.submit(
                self.review_payload(decision="changes-requested", reportSummary="Bound review")
            )
            plan = {
                "assetPath": self.asset_path,
                "reportReceiptId": submitted["submission"]["receiptId"],
            }
            changed = bytearray(self.asset.read_bytes())
            changed[-1] ^= 1
            self.asset.write_bytes(changed)
            cookie = f"{authority.cookie_name}={session_token}"
            origin = f"http://127.0.0.1:{server.server_port}"
            catalog_request = urllib.request.Request(
                f"{origin}/api/catalog", headers={"Cookie": cookie}
            )
            with urllib.request.urlopen(catalog_request, timeout=5) as response:
                current_catalog = json.loads(response.read().decode("utf-8"))
            self.assertNotEqual(current_catalog["assets"][0]["id"], submitted["artifact"]["versionId"])
            forged_current = self.review_payload(decision="pending")
            requests = (
                ("review", forged_current),
                ("review", submitted),
                ("report", submitted),
                ("report-plan", plan),
            )
            for route, payload in requests:
                with self.subTest(route=route):
                    request = urllib.request.Request(
                        f"{origin}/api/{route}",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Cookie": cookie,
                            "Origin": origin,
                            "X-ForgeLens-CSRF": session["csrfToken"],
                        },
                        method="POST",
                    )
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(request, timeout=5)
                    self.assertEqual(caught.exception.code, 409)
                    response = json.loads(caught.exception.read().decode("utf-8"))
                    caught.exception.close()
                    self.assertEqual(response["status"], 409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_human_report_requires_decision_and_animated_approval_requires_neural_pass(self) -> None:
        store = self.module.ReviewStore(self.root)
        payload = {
            "schemaVersion": 2,
            "assetPath": self.asset_path,
            "artifact": self.module.artifact_identity(self.root, self.asset_path),
            "decision": "pending",
            "checklist": {},
            "comments": [],
            "reportSummary": "Inspection complete.",
        }
        with self.assertRaisesRegex(ValueError, "choose Approve"):
            store.submit(payload)
        payload["decision"] = "approved"
        with self.assertRaisesRegex(ValueError, "passing neural"):
            store.submit(payload, animated=True)
        payload["neuralMotion"] = {
            "status": "pass",
            "clip": "Idle",
            "model": "vision-model",
            "summary": "No blocking defects.",
            "criteria": {},
        }
        with self.assertRaisesRegex(ValueError, "neural evidence"):
            store.submit(payload, animated=True)
        png = b"\x89PNG\r\n\x1a\n" + b"approval-evidence"
        evidence = self.module.save_neural_evidence(
            self.root,
            {
                "assetPath": self.asset_path,
                "artifact": self.module.artifact_identity(self.root, self.asset_path),
                "clip": "Idle",
                "pngDataUrl": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            },
        )
        payload["neuralMotion"].update(evidence)
        receipt_path = (self.root / evidence["evidencePath"]).with_suffix(".json")
        forged_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        forged_receipt["assetPath"] = "assets/forged.glb"
        receipt_path.write_text(json.dumps(forged_receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not bound"):
            store.submit(payload, animated=True)
        self.module.save_neural_evidence(
            self.root,
            {
                "assetPath": self.asset_path,
                "artifact": self.module.artifact_identity(self.root, self.asset_path),
                "clip": "Idle",
                "pngDataUrl": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            },
        )
        self.assertIsNotNone(store.submit(payload, animated=True)["submission"])

    def test_task_plan_requires_matching_report_and_passing_adversarial_review(self) -> None:
        store = self.module.ReviewStore(self.root)
        submitted = store.submit(
            {
                "schemaVersion": 2,
                "assetPath": self.asset_path,
                "artifact": self.module.artifact_identity(self.root, self.asset_path),
                "decision": "changes-requested",
                "checklist": {},
                "comments": [{"id": "pin-1", "text": "Fused fingers", "severity": "blocker"}],
                "reportSummary": "Repair hand topology.",
            }
        )
        payload = {
            "assetPath": submitted["assetPath"],
            "reportReceiptId": submitted["submission"]["receiptId"],
            "planner": "specialized-asset-planner",
            "tasks": [
                {
                    "id": "HAND-001",
                    "title": "Separate finger topology",
                    "description": "Rebuild the fused hand geometry without changing scale.",
                    "priority": "critical",
                    "acceptanceCriteria": ["Five distinct finger silhouettes are visible."],
                    "sourceCommentIds": ["pin-1"],
                    "dependencies": [],
                }
            ],
            "adversarialReview": {
                "verdict": "fail",
                "reviewer": "adversarial-plan-auditor",
                "reviewedAt": "2026-07-14T19:00:00Z",
                "findings": ["Missing close-up evidence requirement."],
            },
        }
        with self.assertRaisesRegex(ValueError, "adversarial verification passes"):
            store.submit_task_plan(payload)
        payload["adversarialReview"]["verdict"] = "pass"
        payload["adversarialReview"]["findings"] = []
        planned = store.submit_task_plan(payload)
        self.assertEqual(planned["taskPlan"]["reportReceiptId"], submitted["submission"]["receiptId"])
        self.assertEqual(planned["taskPlan"]["tasks"][0]["sourceCommentIds"], ["pin-1"])
        self.assertEqual(planned["taskPlan"]["adversarialReview"]["verdict"], "pass")

        payload["reportReceiptId"] = "0" * 20
        with self.assertRaisesRegex(ValueError, "does not match"):
            store.submit_task_plan(payload)
        payload["reportReceiptId"] = submitted["submission"]["receiptId"]

        persisted_before = store._path(self.asset_path).read_bytes()
        original_artifact_identity = self.module.artifact_identity
        calls = 0

        def mutate_before_final_write(*arguments, **keywords):
            nonlocal calls
            calls += 1
            if calls == 2:
                changed = bytearray(self.asset.read_bytes())
                changed[-1] ^= 1
                self.asset.write_bytes(changed)
            return original_artifact_identity(*arguments, **keywords)

        setattr(self.module, "artifact_identity", mutate_before_final_write)
        try:
            with self.assertRaisesRegex(self.module.StaleArtifactError, "artifact changed"):
                store.submit_task_plan(payload)
        finally:
            setattr(self.module, "artifact_identity", original_artifact_identity)
        self.assertEqual(store._path(self.asset_path).read_bytes(), persisted_before)


    def test_motion_lab_is_repository_bound_append_only_and_api_reviewers_cannot_approve(self) -> None:
        payload = {
            "schema": "forgelens.motion-lab/v1",
            "motionLabId": "r6k-strike-motion-lab",
            "revision": "b1f704003b7a76ff300fbff76d0583183041848d",
            "fps": 60,
            "frameCount": 4,
            "tracks": {
                "text": [{"frame": 0, "label": "windup"}],
                "fullBody": [{"frame": 0, "label": "Kimodo full body"}],
                "root": [{"frame": 0, "position": [0, 0, 0]}],
                "endEffectors": [{"frame": 0, "jointId": "right_hand", "position": [0.1, 1.0, 0.2]}],
                "contacts": [{"frame": 0, "objectId": "left_foot", "state": "planted"}],
            },
            "views": [
                {"id": "kimodo-teacher", "label": "Kimodo teacher", "frames": [{"frame": 0, "root": [0, 0, 0]}]},
                {"id": "ardy-proposal", "label": "ARDY proposal", "frames": [{"frame": 0, "root": [0.01, 0, 0]}]},
                {"id": "motionbricks-target", "label": "MotionBricks target", "frames": [{"frame": 0, "root": [0, 0, 0.01]}]},
                {"id": "physics-execution", "label": "Physics execution", "frames": [{"frame": 0, "root": [0, 0, 0]}]},
            ],
            "candidates": [
                {"id": "teacher", "label": "Teacher", "viewId": "kimodo-teacher"},
                {"id": "proposal", "label": "Proposal", "viewId": "ardy-proposal"},
            ],
            "metrics": {
                "fkResidual": {"unit": "m", "series": [0.01, 0.02, 0.01, 0.01]},
                "footDrift": {"unit": "m", "series": [0, 0.001, 0.002, 0.001]},
                "com": {"unit": "m", "series": [0.9, 0.91, 0.9, 0.89]},
                "grip": {"unit": "m", "series": [0.16, 0.16, 0.161, 0.16]},
                "weaponPath": {"unit": "m", "series": [0.1, 0.2, 0.3, 0.4]},
            },
        }
        motion_path = self.root / "tools" / "qa" / "motion_lab_fixture.json"
        motion_path.parent.mkdir(parents=True, exist_ok=True)
        motion_path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = self.module.load_motion_lab(self.root, "tools/qa/motion_lab_fixture.json")
        self.assertEqual(loaded["motionLabId"], payload["motionLabId"])
        store = self.module.MotionLabStore(self.root, "tools/qa/motion_lab_fixture.json")
        snapshot = store.load()
        self.assertEqual(snapshot["source"]["sha256"], hashlib.sha256(motion_path.read_bytes()).hexdigest())
        annotation = store.append_annotation(
            {
                "motionLabId": payload["motionLabId"],
                "sourceSha256": snapshot["source"]["sha256"],
                "reviewerKind": "api",
                "text": "Foot plant slides after impact.",
                "revision": payload["revision"],
                "frame": 2,
                "jointId": "left_ankle",
                "objectId": "left_foot",
                "worldPoint": [0.0, 0.0, 0.1],
            },
            actor_id="api-reviewer-fixture",
        )
        self.assertEqual(annotation["eventType"], "annotation")
        self.assertEqual(store.load()["events"][0]["previousEventSha256"], None)
        with self.assertRaisesRegex(ValueError, "annotation"):
            store.append_annotation(
                {**annotation, "eventType": "approved"}, actor_id="api-reviewer-fixture"
            )
        human_event_path = self.root / "tools" / "qa" / "motion_lab_human_event.json"
        human_event_path.write_text(
            json.dumps(
                {
                    "schema": "forgelens.motion-lab-human-event/v1",
                    "motionLabId": payload["motionLabId"],
                    "revision": payload["revision"],
                    "sourceSha256": snapshot["source"]["sha256"],
                    "reviewerPseudonym": "independent-reviewer",
                    "action": "changes-requested",
                    "comment": "Hold admission; foot drift requires correction.",
                    "decidedAt": "2026-07-16T12:00:00Z",
                    "attestation": "I independently reviewed this exact Motion Lab payload; this outcome does not approve a ReviewRun.",
                }
            ),
            encoding="utf-8",
        )
        human_event = store.import_human_event("tools/qa/motion_lab_human_event.json")
        self.assertEqual(human_event["eventType"], "human-outcome")
        self.assertEqual(human_event["action"], "changes-requested")
        authority = self.module.BrowserAuthority("motion-lab-http")
        session_token, session = authority.exchange("motion-lab-http")
        context = self.module.ServerContext(
            root=self.root,
            initial_asset=None,
            catalog=self.module.build_catalog(self.root),
            reviews=self.module.ReviewStore(self.root),
            authority=authority,
            motion_lab=store,
        )
        handler = type("MotionLabHandler", (self.module.AssetReviewHandler,), {"context": context})
        server = self.module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        origin = f"http://127.0.0.1:{server.server_port}"
        headers = {"Cookie": f"{authority.cookie_name}={session_token}", "Origin": origin, "X-ForgeLens-CSRF": session["csrfToken"], "Content-Type": "application/json"}
        try:
            connection.request("GET", "/api/motion-lab", headers={"Cookie": headers["Cookie"]})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read().decode("utf-8"))["motionLab"]["motionLabId"], payload["motionLabId"])
            forbidden = {"motionLabId": payload["motionLabId"], "sourceSha256": snapshot["source"]["sha256"], "reviewerKind": "api", "text": "forged approve", "revision": payload["revision"], "frame": 2, "jointId": "left_ankle", "objectId": "left_foot", "worldPoint": [0, 0, 0], "action": "approved"}
            connection.request("POST", "/api/motion-lab-annotation", body=json.dumps(forbidden), headers=headers)
            blocked = connection.getresponse()
            self.assertEqual(blocked.status, 400)
            self.assertIn("unknown", blocked.read().decode("utf-8"))
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        with self.assertRaisesRegex(ValueError, "canonical repository-relative"):
            self.module.load_motion_lab(self.root, "../motion_lab_fixture.json")


if __name__ == "__main__":
    unittest.main()
