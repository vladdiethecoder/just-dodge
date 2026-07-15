#!/usr/bin/env python3
"""Focused acceptance tests for the local Asset Review Studio server."""

from __future__ import annotations

import importlib.util
import base64
import http.client
import json
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
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

    def tearDown(self) -> None:
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
        )

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


if __name__ == "__main__":
    unittest.main()
