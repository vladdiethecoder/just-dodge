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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
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
    for relative, expected in profile["required_files"].items():
        path = ROOT / relative
        require(path.is_file(), f"missing ForgeLens file: {relative}")
        require(sha256(path) == expected, f"ForgeLens file hash drift: {relative}")
    browser = profile["browser_authority"]
    require(all(browser.values()), "ForgeLens browser authority weakened")

    gates = contract["required_gates"]
    require(set(gates) == {"deterministic_harness", "uncropped_evidence", "coherent_grip", "canonical_media", "blinded_human"}, "gate set drift")
    require(all(gate["required"] is True for gate in gates.values()), "required gate weakened")

    harness = gates["deterministic_harness"]
    visual_contract = ROOT / harness["visual_contract_path"]
    receipt_path = ROOT / harness["candidate_receipt_path"]
    require(sha256(visual_contract) == harness["visual_contract_sha256"], "visual contract hash drift")
    require(sha256(receipt_path) == harness["candidate_receipt_sha256"], "candidate receipt hash drift")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
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
