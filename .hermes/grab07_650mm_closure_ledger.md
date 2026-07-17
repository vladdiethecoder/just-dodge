# PVP005-GRAB07-650MM-VISUAL-TRUTH-002 — Closure Ledger

Owner decision: OPTION 3. Preserve GRAB_REACH_MM=650. Close the ~150mm
motion-reach gap via physically plausible approach/root displacement + stepped
footwork + action-specific target/contact keypose conditioning. Never lower
GRAB_REACH, never accept 220.9mm, no bone-length/scale/teleport/threshold
weakening, no relabeling near-miss as contact.

## Baseline (verify.A) — reconciled 2026-07-17
- HEAD: 71e18ca (main, ahead 22). origin/main: 97cf06f. Local is authoritative.
- Retarget presentation baseline committed at 71e18ca (grab07_capture retargets
  grab_07 to C0 mannequin; --skip-render; pose_and_detect --no-render).
- Test baseline: 328 passed, 0 failed, 3 ignored (cargo test --locked --all-targets).
  Matches reported 328/0. Baseline consistent.
- Truth hash (capture): 7f7e22fbbab15a98. Motion hash: df134b66 (original grab_07).
- Secure grab window: ticks 32..47. Measured clearance (retargeted original): 220.9mm.
- Uncommitted preserved: /tmp/grab07_closure_preserve/uncommitted_tracked.patch (451 lines)
  + inventory.txt. Untracked: ForgeLens T5, m4_baked, m4 test, hand_probe, T4 receipt tools.

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

## Capability question to answer mechanically (gate B)
Is MotionBricks target-conditioned grappling GENUINE (learned) or HARD-MASKED
(post-decode apply_fk_targets overwrite)? Test: remove post-decode patch and
measure held-out reach error. Exactly 0.0mm at contact = masking red flag.
