# Just Dodge

A deterministic, simulation-backed, YOMI-style melee combat game.

This project takes the lessons learned from OATHYARD — simultaneous-reveal intent combat, MotionBricks procedural animation, truth-isolated presentation, and AAA asset integration — and expands them into a complete, shippable, in-depth combat simulation game.

## Project Status

- Stage: Custom Rust/wgpu prototype architecture + planning lock
- Current baseline: textured arena renderer, orbital camera, static/skinned mannequin asset paths, MotionBricks ONNX integration work, and documentation-driven combat/armor/motion design
- Next playable target: verified 3-action Strike/Block/Grab match loop with replay/truth-hash evidence

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
