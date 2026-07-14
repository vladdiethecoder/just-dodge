# Just Dodge

A deterministic, simulation-backed, YOMI-style melee combat game.

This project takes the lessons learned from OATHYARD — simultaneous-reveal intent combat, MotionBricks procedural animation, truth-isolated presentation, and AAA asset integration — and expands them into a complete, shippable, in-depth combat simulation game.

## Project Status

- Stage: PLAYABLE-PROOF construction on clean `main`; the requested packaged vertical-slice gate has not passed.
- Selected runtime path: `main::App` → `milestone3::Session/Match` → `m3_cleanbox` → `cleanbox/duel_world/duel_physics` → `PhysicalContactBatch` → immutable `milestone3::Snapshot` → renderer/UI/replay.
- Verified baseline: deterministic three-action M3 truth, 120 Hz cleanbox reduction, 100 replay reconstructions, frame-342 truth hash `d1a3cc1bfb9c2f67`, fmt/warning-denying clippy/check, 233 all-target tests in a hydrated clean mirror, release binary launch, and static integrity of the 24-bone armored duelist.
- Isolated foundations, not live gameplay: post-Reveal ARDY proposals, quantized motion-plan packets, MotionBricks receipts, official G1 articulation data, integer hinge projection, and independent-joint active-ragdoll tracking.
- Open PLAYABLE-PROOF path: complete player flow and input proof; reproducible package/repo verification; admitted Strike/Block/Grab motion; coupled articulated physics; pose-derived contact and sword sockets; camera/readability; truth-driven presentation; five human packaged matches; canonical media and machine-readable evidence.
- Distribution boundary: runtime asset source identity is recorded, but complete redistribution-rights records are not; this does not halt technical development and does block redistribution claims.

## Quick Links

- [Game Design Document](docs/GDD.md)
- [Full Roadmap](docs/ROADMAP.md)
- [Combat System Design](docs/COMBAT-SYSTEM.md)
- [Technical Stack](docs/TECH-STACK.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Systems Design](docs/SYSTEMS-DESIGN.md)
- [Phased Production Plan](docs/PHASED-PRODUCTION-PLAN.md)
- [QA, Visual Verification, and Agentic Playtesting](docs/QA-AGENTIC-PLAYTESTING.md)
- [File Inventory Audit](docs/FILE-INVENTORY-AUDIT.md)
- [Verifiable Milestones](docs/MILESTONES.md)
- [Prototype Plans](docs/PROTOTYPES.md)
- [Master Checklist](docs/CHECKLIST.md)
- [Risk Register](docs/RISK-REGISTER.md)
- [Lessons from OATHYARD](docs/LESSONS-FROM-OATHYARD.md)
- [Milestone 3 Build Record](docs/reports/TERRA_AGENTIC_BUILD.md)
- [Milestone 3 First Playable Report](docs/reports/MILESTONE_03_FIRST_PLAYABLE_REPORT.md)
- [Milestone 3 Asset Provenance Audit](docs/reports/ASSET_PROVENANCE_M3.md)
- [Development Task List](docs/reports/DEVELOPMENT_TASKLIST.md)
- [Changelog](CHANGELOG.md)

## One-Line Pitch

A first-person duel game where you and your opponent each commit to one hidden action, reveal simultaneously, and live or die by the physics, timing, and reading of that single exchange.

## Core Pillars

1. **Mind-Game First** — every exchange is a YOMI read, not a reaction test.
2. **Physical Truth** — hitboxes, timing, and consequences are deterministic and simulation-backed.
3. **Motion That Reads** — every action is readable through pose, weapon motion, and audio before contact.
4. **Emergent Depth** — simple rules, complex outcomes through matchup matrices, capability injury, and state adaptation.
5. **Presentation Isolated** — renderer, animation, camera, and audio never mutate combat truth.

## How to Use This Repo

This repo is documentation-gated and evidence-gated. Code and assets exist, but no feature should be accepted until the corresponding playable prototype, replay/truth-hash test, visual QA pass, and playtest evidence pass.

Do not advance production scope until the corresponding prototype report says CONTINUE and the evidence gate in `docs/PHASED-PRODUCTION-PLAN.md` passes.

## Setup

```bash
# Rust/wgpu game code
cargo build

# Hydrate the pinned large-model bundle from a trusted cache when live motion
# tests or the game runtime are needed. Compilation does not embed these files.
tools/hydrate_motionbricks_runtime.sh /path/to/trusted/motionbricks-assets

# Python motion service dependencies
python3 -m pip install -r motionbricks_service/requirements.txt
```

Note: `kimodo` is installed from the upstream GitHub repository. Kimodo's wheel builds a small C++ extension, so `cmake` must be available. On this machine the install succeeded with `--no-build-isolation` because the isolated build environment could not see the `cmake` Python package.

Running Kimodo generation requires:
- A writable Hugging Face cache directory. The environment default may point to a non-writable path; override it if needed: `HF_HOME=/tmp/hf_cache`.
- Access to the gated `meta-llama/Meta-Llama-3-8B-Instruct` model used by Kimodo's local text encoder. Set a Hugging Face token with Llama access: `HF_TOKEN=...`.
