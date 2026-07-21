# Atomic Task Ledger

**Amended:** 2026-07-21 — post-exhaustive-interview reset

## Global Context

**Global Goal:** Ship Just Dodge as a playable, deterministic, condition-driven intent-combat game with generative MotionBricks motion and deterministic physics. The old SG01→SG10 sequential infrastructure gating is retired; replaced by visual-first pipeline where every gate is a screenshot/GIF + owner decision.

**Key amendment:** SG01-SG10 sequential gating consumed 95% of development on evidence infrastructure with 5% on gameplay across three projects (OATHYARD, Hustle & Honor, Just Dodge). The new pipeline delivers visual evidence at every step and gates on owner acceptance, not infrastructure completeness.

**Active Phase:** PHASE-1 — Asset & Motion Proof

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

**Unit ID:** PH1-FIGHTER-001
**Mode:** Meshy web → Blender validation → engine cook → visual gate
**Goal:** One properly proportioned fighter with clean topology, no fused fingers, no clipping, anatomically correct T-pose, rendered in-engine.
**Pipeline:**
1. Generate multi-view reference images (GPT Image) — front, side, back, 3/4 — deep-sim readability pillars
2. Generate fighter in Meshy web (multi-view image-to-3D, custom T-pose, Smart Topology for separated parts)
3. Download candidate GLB, inspect in Blender headless (geometry, rig, materials)
4. Cook for engine (SKM1 + ANM1 format)
5. Load in game_loop, capture native screenshot + GIF
6. Show owner: visual checklist → Accept/Reject/Needs Changes
**Baseline:** One completed but uninspected Meshy task (`019f85a5-b944-7d64-8e54-6dcbdf5619d7`) exists. Inspect it first; if acceptable, use it; if not, generate fresh.
**Current Status:** IN PROGRESS — Two API-generated Meshy candidates (019f85a5, 019f85f0) REJECTED after 500-defect audit. 60 credits spent, zero usable output. Hard numeric gates established (≤25K verts, ≤50K tris, watertight, ≥24 bones). Next: owner must review reference images BEFORE any Meshy credit spend. Meshy web interface mandatory for next attempt; API/MCP locked to repeatable batches only. Full audit: `docs/reports/PH1_FIGHTER_001_500_DEFECT_AUDIT.json` (SHA-256: `2e731dcb`). game-asset-pipeline skill hardened with API-vs-Web Gate and Reference Image Quality Gates.

## Pending Units

- PH1-STRIKE-001: MotionBricks strike generation (blocked by PH1-FIGHTER-001)
- PH1-BLOCK-GRAB-001: Block and grab motions (blocked by PH1-STRIKE-001)
- PH2-VERTICAL-SLICE-001: Full playable match loop (blocked by PHASE-1)

## Retired Infrastructure Gates

The following SG01-SG10 units are retired/archived. Their evidence and receipts are preserved for provenance but no longer gate gameplay progress:

- SG01-EVIDENCE-CANON-RESET-002 (PASS, commit `f821c98`)
- SG02-MATCH-LIFECYCLE (machine PASS, visual REJECTED at `c982c88`)
- SG02-CROSS-PLATFORM-PARITY-001 (Linux only; Windows/Deck blocked)
- SG02-VISUAL-CARRIER-REPLACEMENT-003 (IN PROGRESS — superseded by PH1-FIGHTER-001)
- SG03-SG10 (not started; replaced by PHASE-2/PHASE-3)
