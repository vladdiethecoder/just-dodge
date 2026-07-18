# PVP005-GRAB07-650MM-VISUAL-TRUTH-002 — Closure Ledger

Owner decision: OPTION 3. Preserve GRAB_REACH_MM=650. Close the ~150mm
motion-reach gap via physically plausible approach/root displacement + stepped
footwork + action-specific target/contact keypose conditioning. Never lower
GRAB_REACH, never accept 220.9mm, no bone-length/scale/teleport/threshold
weakening, no relabeling near-miss as contact.

## Baseline (verify.A) — reconciled 2026-07-17
- HEAD: d9d0c6d (grab07-650mm-closure). origin/main: 97cf06f. Local is authoritative.
- NOTE: ledger previously recorded HEAD 71e18ca; d9d0c6d landed the T4 receipt/
  determinism/gates tooling, T5 ForgeLens surface, M4 baked provider, hand_probe,
  and this ledger. main is at 71e18ca.
- Retarget presentation baseline committed at 71e18ca (grab07_capture retargets
  grab_07 to C0 mannequin; --skip-render; pose_and_detect --no-render).
- Test baseline RE-VERIFIED this session: 328 passed, 0 failed, 3 ignored
  (cargo test --locked --all-targets = 165+158+2+3). Matches reported 328/0.
- Truth hash (capture): 7f7e22fbbab15a98. Motion hash: df134b66 (original grab_07).
- Secure grab window: ticks 32..47. Measured clearance (retargeted original): 220.9mm.
- Uncommitted preserved: /tmp/grab07_closure_preserve/uncommitted_tracked.patch
  (sha256 652c86e0...) + inventory.txt. Untracked: build_grab07_interaction_corpus.py,
  train_grab07_interaction_fullbody.py (in-flight UNIT-2 Approach A corpus+trainer).

## UNIT-2 blocker resolution (2026-07-17)
- Corpus build FAILED at reach_nominal clip2 ("no strong grab after retries").
  Root causes: (1) orphaned kimodo_gen seed 20260720 held 15.6 GiB GPU after the
  background harness SIGKILLed its parent -> all new gens OOM; (2) online HF auth
  broken ("OAuth token signature verification failed" on gated LLM2Vec llama repo).
- FIX: killed orphan PID 1308753 (26 GiB free); run corpus with HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1 to load cached Kimodo+LLM2Vec weights and skip dead auth.
  Offline single-gen verified working (60x34x3, zmax 0.40 m passes floor).

## Installed-skill reconciliation (routing rule 4)
- INSTALLED: gated-agent-engineering, game-vertical-slice-triage,
  motionbricks-runtime-parity-audit, skeletal-retargeting, game-visual-qa-readiness,
  hermes-cua-game-testing, game-milestone-readiness-audit, game-testing-qa.
- NOT INSTALLED (kept in default profile): renderer-visual-validation,
  strict-visual-gate-loop (covered by game-testing-qa refs), game-build-packaging.

## Strike ledger
- strike_count per root cause tracked here. Two failed approaches to the same
  root cause => stop patching, replan from measurements.
- PRIOR SESSION strike: hand-authored grab_07 keyframe clip (grab07_author.rs)
  was FORBIDDEN by owner ("hand-authored is strictly forbidden"). Reverted.
  Root cause class: authored-not-generated motion. CLOSED, will not retry.

## Active unit
UNIT-0: reconcile + preserve + baseline. STATUS: DONE (this ledger + patch).
UNIT-1: capability verdict. STATUS: DONE — existing interaction path is a hard
  mask (apply_fk_targets, interaction_forward.py:422-424). Hard-mask (B) and
  hand-authored (C) forbidden. Option 1/2 NOT silently chosen.
UNIT-2: APPROACH A (owner-approved) — genuine trained GRAB interaction
  conditioner. Build a real target-directed GRAB teacher corpus (kimodo/CC0,
  NOT hand-authored) + full-body grab conditioner, no output masking, held-out
  by source identity. Target: held-out hand contact error ≤15mm (the G5 gate)
  at the 650mm acquisition. Truth stays authoritative (clinch at 650mm intact).

## UNIT-2 outcome (2026-07-17, commit 4a6ad53)
- VERDICT: FAIL (evidence-gated, reproducible). Held-out <=15mm at GRAB_REACH_MM=650 NOT met.
- Best trained conditioner: 77.71mm hand-surface error; condition-ablation INSENSITIVE
  (model does not use target geometry). Corpus: 16 kimodo teacher clips (offline,
  runtime_admitted=False). No hand-authored/prebaked runtime motion introduced.
- Truth/clinch at 650mm PRESERVED. Baseline 220.9mm unchanged. G4/G5 PENDING_HUMAN.
- Receipt: qa_runs/grab07_interaction_train/UNIT2_RECEIPT.json (sha256 b9b3bce5...).
- Next falsifiable experiment: reach-calibrated teacher corpus (hand terminating in
  [620,680]mm); current corpus overshoots (790-1120mm), making the 650mm gate
  inconsistent with its own teachers.

## Capability question to answer mechanically (gate B)
Is MotionBricks target-conditioned grappling GENUINE (learned) or HARD-MASKED
(post-decode apply_fk_targets overwrite)? Test: remove post-decode patch and
measure held-out reach error. Exactly 0.0mm at contact = masking red flag.
