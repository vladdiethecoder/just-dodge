# Atomic Task Ledger

**Amended:** 2026-07-21 — post-exhaustive-interview reset

## Global Context

**Global Goal:** Ship Just Dodge as a playable, deterministic, condition-driven intent-combat game with generative MotionBricks motion and deterministic physics. The old SG01→SG10 sequential infrastructure gating is retired; replaced by visual-first pipeline where every gate is a screenshot/GIF + owner decision.

**Key amendment:** SG01-SG10 sequential gating consumed 95% of development on evidence infrastructure with 5% on gameplay across three projects (OATHYARD, Hustle & Honor, Just Dodge). The new pipeline delivers visual evidence at every step and gates on owner acceptance, not infrastructure completeness.

**Active Phase:** PVP-005 — readable simultaneous-commit combat. Meshy asset generation demoted to candidate source. Existing 24-bone armored duelist frozen as canonical test body. Motion/readability is the active blocker, not character generation.

## Visual-First Pipeline

### PHASE-1: Asset & Motion Proof (active)

**Unit ID:** PH1-FIGHTER-001
**Goal:** Generate a properly proportioned, anatomically correct fighter in Meshy web → validate in Blender → cook for engine → show owner screenshot + GIF of T-pose in-engine.
**Acceptance:** Owner sees screenshot/GIF, picks Accept/Reject/Needs Changes. 30-second decision.

**Unit ID:** PH1-STRIKE-001 (blocked by PH1-FIGHTER-001)
**Goal:** Generate one clean strike motion via MotionBricks → retarget to fighter skeleton → skinned render → show owner GIF of the strike.
**Acceptance:** Owner sees GIF, picks Accept/Reject/Needs Changes.

**Unit ID:** PH1-BLOCK-GRAB-001 (blocked by PH1-STRIKE-001)
**Goal:** Generate clean block and grab motions → show owner GIFs → iterate until accepted.

### PHASE-2: Playable Vertical Slice (blocked by PHASE-1)

**Goal:** Wire accepted fighter + motion into game_loop. Implement full match flow: Boot → Observe → Plan Intent → Commit → Reveal → Resolve → Consequence → Result → Rematch. Add AI opponent, injury, camera, basic UI.
**Acceptance:** Owner sees video of complete match → Accept/Reject.

### PHASE-3: Full Game (blocked by PHASE-2)

**Goal:** Expand to 13 actions, multiple fighters/weapons/arenas. Add replay theater, fight film, audio, tutorial. Steam packaging.

## Active Unit

**Unit ID:** PH1-STRIKE-002
**Mode:** Implementation
**Goal:** Wire the admitted `hero_strike` MotionBricks clip into `game_loop` as presentation-only Strike animation.
**Expected Behavior:** `Intent::Strike` samples retargeted 24-bone hero-strike poses over the action timeline; idle and non-Strike presentation remain unchanged, and truth/combat resolution is untouched.
**Expected Files Changed:** `src/bin/game_loop.rs`, `.hermes/atomic_ledger.md` (only if needed for evidence)
**Exact Validation Command:** `cargo check --locked --bin game_loop` followed by `cargo run --locked --bin game_loop -- --shot <ticks> <out_dir>` with artifact inspection.
**Baseline Result:** Pending fresh baseline check.
**Strike Count:** 0
**Rollback Plan:** Revert only the `game_loop.rs` integration hunk; keep the existing clip and retargeting modules unchanged.
**Current Status:** In Progress

## Pending Units

- PH1-STRIKE-001: MotionBricks strike generation (blocked by PH1-FIGHTER-001)
- PH1-BLOCK-GRAB-001: Block and grab motion generation (blocked by PH1-STRIKE-001)
- PH2-VERTICAL-SLICE-001: Full playable match loop (blocked by PHASE-1)

## Retired Infrastructure Gates

The following SG01-SG10 units are retired/archived. Their evidence and receipts are preserved for provenance but no longer gate gameplay progress:

- SG01-EVIDENCE-CANON-RESET-002 (PASS, commit `f821c98`)
- SG02-MATCH-LIFECYCLE (machine PASS, visual REJECTED at `c982c88`)
- SG02-CROSS-PLATFORM-PARITY-001 (Linux only; Windows/Deck blocked)
- SG02-VISUAL-CARRIER-REPLACEMENT-003 (IN PROGRESS — superseded by PH1-FIGHTER-001)
- SG03-SG10 (not started; replaced by PHASE-2/PHASE-3)
