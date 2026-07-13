# Current State Audit — M3 Packet Truth and Armored Duelist

- Audit revision: `0e5a29a0cc99b7e29e259a4192ef6be3e8c8eb60`
- Audit UTC: 2026-07-13
- Branch: `milestone3-first-playable-terra`

## Observed current path

1. `src/main.rs` owns an `m3::Session` and consumes its immutable snapshot for UI and rendering.
2. `src/m3_cleanbox.rs` advances `M3CleanboxWorld` shared cleanbox geometry at 120 Hz and submits one `PhysicalContactBatch` for the active 60 Hz Resolve truth frame.
3. `src/milestone3.rs` accepts only the exact pending Resolve packet, rejects missing/stale/duplicate packets, applies contact-role outcome/injury, serializes replay v2, and verifies canonical hashes during replay.
4. `src/bin/m3_match.rs` exercises the same session/cleanbox route headlessly. Fresh autoplay ended at frame 342 with hash `d1a3cc1bfb9c2f67`; fresh replay verification reproduced it.
5. `src/motion_request.rs`, `src/motion_runtime.rs`, and `src/motion_retarget.rs` define deterministic public requests, fail-closed source-cache loading, and numeric G1→24-bone conversion. `src/bin/shot.rs` produced standard action-QA frames, but `src/main.rs` retains static reference skin matrices because the current source fails the visual tell gate.

## Evidence classification

| Subsystem | Status | Reason |
|---|---|---|
| M3 intent/phase/replay truth | Verified | Warning-clean all-target compile and repeated full test pass |
| 120 Hz → 60 Hz contact packet path | Verified for current cleanbox targets | Exact two-substep test and headless replay |
| Outcome authority | Verified packet-driven | Missing packet holds resolve; body/guard/whiff tests pass |
| Armored character import | Verified static asset integrity | Valid SKM1, 24-bone load, front/first-person frame inspection |
| Motion-readable combat | Blocked | Four-frame source candidates are not semantic tells; neural Kimodo source generation is blocked on gated Hugging Face authorization. |
| Pose-derived contact | Unproven | Current cleanbox target geometry is not produced from MotionBricks/retargeted sockets |
| Player loop | Unproven | No five-match human packaged evidence |
| Runtime materials | Partial | Light bronze supports silhouette; PBR import/shading is pending |
| Distribution | Blocked | Rights/provenance closure is incomplete |

## Replaced baseline assumptions

- The active M3 resolver is not the former 3×3 action lookup. Action intent selects planned behavior; `PhysicalContactBatch` is outcome evidence.
- The active runtime opponent is not the old nude 163-bone carrier. It is the new 24-bone armored duelist in `assets/source/meshy/c0_armored_duelist_001/`.
- A passing static bind frame proves import/skinning integrity only. It cannot prove action motion, combat tells, visible weapon alignment, or contact parity.

## Current critical path

`B.1.4a neural semantic source admission` → `B.1.4 motion tell gate` → runtime promotion → `B.2 pose-derived contact` → `B.3 camera` → `B.5 player loop` → `E.2 human matches` → `E.3 canonical media`.

Parallel non-truth work: PBR/material contract, asset cooker reproducibility, rights closure, and CI flake stabilization.
