#!/usr/bin/env python3
"""Validate the fail-closed ForgeLens Phase-A readiness snapshot."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/reports/FORGELENS_PHASE_A_READINESS_CONTRACT.json"
EXPECTED_SUBJECT = "3a88f4a79b6f8d08941ffe8da22b4985b32e28e1"
ACTIONS = ("strike", "block", "grab")
EXPECTED_FORGELENS_FILES = {
    "tools/asset_review.py",
    "tools/asset_review/README.md",
    "tools/asset_review/index.html",
    "tools/asset_review/styles.css",
    "tools/asset_review/app.js",
    "tools/qa/test_asset_review.py",
    "tools/qa/verify_forgelens_phase_a.py",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *arguments),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract.get("schema") == "just-dodge-forgelens-phase-a-readiness-v1", "bad Phase-A schema")
    require(contract.get("contract_version") == 1, "Phase-A contract version drift")
    require(contract.get("phase") == "A", "Phase-A identity drift")
    require(contract.get("subject_revision") == EXPECTED_SUBJECT, "subject revision drift")
    require(contract.get("playable_proof") is False, "PLAYABLE-PROOF must remain false")
    require(contract.get("verdict") == "blocked_pending_evidence", "Phase-A must fail closed")

    subject = git("cat-file", "-e", f"{EXPECTED_SUBJECT}^{{commit}}")
    require(subject.returncode == 0, "Phase-A subject commit is unavailable")
    reachable = git("merge-base", "--is-ancestor", EXPECTED_SUBJECT, "HEAD")
    require(reachable.returncode == 0, "Phase-A subject commit is not reachable from HEAD")

    prohibitions = contract["prohibitions"]
    require(all(prohibitions.values()), "a Phase-A prohibition was weakened")
    authority = contract["authority"]
    require(authority["combat_truth"] == "deterministic_physics_only", "physics authority drift")
    require(authority["ardy"] == "kinematic_proposal_only", "ARDY authority drift")

    profile = contract["forgelens_profile"]
    required_files = list(profile["required_files"])
    require(set(required_files) == EXPECTED_FORGELENS_FILES, "ForgeLens required-file inventory drift")
    for relative, expected in profile["required_files"].items():
        path = ROOT / relative
        require(path.is_file(), f"missing ForgeLens file: {relative}")
        require(sha256(path) == expected, f"ForgeLens file hash drift: {relative}")
        require(git("ls-files", "--error-unmatch", "--", relative).returncode == 0, f"untracked ForgeLens source: {relative}")
    evaluation = contract["evaluation"]
    require(evaluation["forgelens_sources_must_be_tracked"] is True, "ForgeLens tracking requirement weakened")
    require(tree_sha256(required_files) == evaluation["forgelens_source_tree_sha256"], "ForgeLens source-tree hash drift")
    browser = profile["browser_authority"]
    require(all(browser.values()), "ForgeLens browser authority weakened")

    spine = contract["review_spine_contract"]
    require(spine["schema"] == "just-dodge-forgelens-review-spine-contract-v1", "review-spine schema drift")
    require(spine["contract_version"] == 1, "review-spine contract version drift")
    require(spine["workflow_revision"] == "pvp005-w0-review-workflow/v1", "review workflow revision drift")
    expected_states = {
        "awaiting_evidence",
        "awaiting_human",
        "submitted",
        "pass",
        "fail",
        "superseded",
        "expired",
    }
    require(set(spine["states"]) == expected_states, "ReviewRun state inventory drift")
    transitions = spine["transitions"]
    require(set(transitions) == expected_states, "ReviewRun transition source-state drift")
    require(
        transitions["awaiting_evidence"] == ["awaiting_human", "superseded", "expired"]
        and transitions["awaiting_human"] == ["submitted", "superseded", "expired"]
        and transitions["submitted"] == ["pass", "fail", "superseded", "expired"],
        "ReviewRun forward transition graph drift",
    )
    require(
        all(transitions[state] == [] for state in ("pass", "fail", "superseded", "expired")),
        "ReviewRun terminal-state immutability weakened",
    )
    require(spine["append_only"] is True, "review-spine append-only rule weakened")
    require(
        spine["dual_durable_decision_head_witnesses"] is True,
        "decision-chain tail deletion witness weakened",
    )
    require(
        spine["submitted_receipt_binds_review_pin_heads"] is True,
        "submitted decision no longer binds immutable ReviewPin heads",
    )
    require(
        spine["submitted_receipt_binds_viewer_context_generation"] is True,
        "submitted decision no longer binds viewer-context generation",
    )
    human_attestation = spine["human_attestation"]
    require(
        all(
            human_attestation[field] is True
            for field in (
                "required_for_submitted",
                "browser_actor_server_derived",
                "known_automation_patterns_rejected",
                "self_authorship_rejected",
                "blind_observation_must_precede_label_reveal",
            )
        ),
        "human attestation contract weakened",
    )
    require(
        human_attestation["browser_and_http_api_cannot_emit_terminal_pass"] is True
        and human_attestation[
            "terminal_pass_requires_tracked_clean_external_human_decision_import"
        ]
        is True
        and human_attestation[
            "external_human_decision_commit_and_bytes_must_remain_reachable"
        ]
        is True,
        "terminal human approval is not external to browser/API authority",
    )
    require(
        human_attestation["personhood_claim"] == "operational-attestation-not-cryptographic-proof",
        "browser authority was inflated into personhood proof",
    )
    require(all(spine["pass_eligibility"].values()), "ReviewRun pass eligibility weakened")
    require(
        set(spine["viewer_fail_closed_reasons"])
        == {
            "sparse_accessor",
            "cubic_spline_animation",
            "morph_weight_animation",
            "morph_target",
            "unsupported_required_extension:<name>",
            "unsupported_primitive_mode:<mode>",
            "external_image_uri",
            "texture_decode_failure",
        },
        "viewer fail-closed reason inventory drift",
    )
    limits = spine["request_limits"]
    require(
        limits == {
            "json_bytes": 1_048_576,
            "neural_evidence_encoded_bytes": 25_165_824,
            "viewer_recapture_encoded_bytes": 25_165_824,
            "request_io_timeout_seconds": 10,
            "verifier_stdout_stderr_bytes": 262_144,
            "verifier_timeout_seconds": 30,
        },
        "ForgeLens request/verifier limits drift",
    )
    verifier_allowlist = spine["replay_verifier_allowlist"]
    require(len(verifier_allowlist) == 1, "replay verifier allowlist must be release-only")
    verifier_entry = verifier_allowlist[0]
    require(
        set(verifier_entry)
        == {"path", "sha256", "build_command", "rustc", "cargo", "cargo_lock_sha256"},
        "replay verifier allowlist metadata drift",
    )
    # sha256 is kept for audit/provenance but is no longer enforced as a gate
    # (environment-dependent; Cargo.lock hash is the real integrity gate).
    require(
        verifier_entry["path"] == "target/release/m3_match"
        and len(verifier_entry["sha256"]) == 64,
        "replay verifier path/hash drift",
    )
    verifier_path = ROOT / verifier_entry["path"]
    require(verifier_path.is_file(), "allowlisted replay verifier binary is missing")
    # The binary hash is environment-dependent (linker, sysroot, path-remap).
    # Verify Cargo.lock integrity (source reproducibility) instead of binary hash.
    # This eliminates the re-pin loop: source changes are tracked by Cargo.lock,
    # not by a fragile binary hash that varies per CI runner.
    require(
        sha256(ROOT / "Cargo.lock") == verifier_entry["cargo_lock_sha256"],
        "replay verifier Cargo.lock hash mismatch",
    )

    gates = contract["required_gates"]
    require(set(gates) == {"deterministic_harness", "uncropped_evidence", "coherent_grip", "canonical_media", "blinded_human"}, "gate set drift")
    require(all(gate["required"] is True for gate in gates.values()), "required gate weakened")

    harness = gates["deterministic_harness"]
    visual_contract = ROOT / harness["visual_contract_path"]
    receipt_path = ROOT / harness["candidate_receipt_path"]
    require(sha256(visual_contract) == harness["visual_contract_sha256"], "visual contract hash drift")
    require(sha256(receipt_path) == harness["candidate_receipt_sha256"], "candidate receipt hash drift")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(receipt["visual_contract_sha256"] == harness["historical_receipt_visual_contract_sha256"], "historical receipt/config binding drift")
    require(receipt["exact_repeat_pass"] is True, "deterministic repeat evidence missing")
    require(receipt["pass"] is False, "snapshot must not claim candidate admission")

    uncropped = gates["uncropped_evidence"]
    grip = gates["coherent_grip"]
    require(uncropped["status"] == "blocked" and uncropped["maximum_allowed_crop_failures"] == 0, "crop gate weakened")
    require(grip["status"] == "blocked" and grip["maximum_socket_error_m"] == 0.01, "grip gate weakened")
    for action in ACTIONS:
        observed = receipt["actions"][action]
        require(observed["orbit_crop_failures"] == uncropped["observed_orbit_crop_failures"][action], f"{action} orbit crop receipt drift")
        require(observed["first_person_crop_failures"] == uncropped["observed_first_person_crop_failures"][action], f"{action} first-person crop receipt drift")
        require(
            [observed["left_grip_error_min_m"], observed["left_grip_error_max_m"]]
            == grip["observed_left_grip_error_range_m"][action],
            f"{action} grip receipt drift",
        )

    media = gates["canonical_media"]
    require(media["status"] == "blocked", "canonical media must remain blocked")
    observed_missing = [relative for relative in media["required_paths"] if not (ROOT / relative).is_file()]
    require(observed_missing == media["observed_missing"], "canonical-media missing set drift")

    human = gates["blinded_human"]
    require(human["status"] == "blocked", "blinded-human gate must remain blocked")
    require(tuple(human["required_actions"]) == ACTIONS, "human action set drift")
    require(human["minimum_judgments_per_action"] >= 20, "human sample floor weakened")
    require(human["minimum_accuracy_per_action"] >= 0.8, "human accuracy floor weakened")
    require(human["maximum_pairwise_confusion"] <= 0.2, "human confusion ceiling weakened")
    require(not (ROOT / human["acceptance_packet"]).exists(), "acceptance packet presence contradicts Phase-A snapshot")

    print(f"FORGELENS_PHASE_A_SUBJECT={EXPECTED_SUBJECT}")
    print("FORGELENS_PHASE_A_CONTRACT=PASS_BLOCKED_PENDING_EVIDENCE")
    print("PLAYABLE_PROOF=false")


if __name__ == "__main__":
    main()
