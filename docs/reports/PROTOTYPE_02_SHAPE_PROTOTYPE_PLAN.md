# Prototype Plan: Shape Prototype (Custom Engine)

**Question:** Does the digital 3-action simultaneous-reveal feel good in a minimal custom engine?
**Duration:** 2–3 weeks.
**Method:** Rust + wgpu, two colored triangles, 3 actions, simple AI, text UI.
**Success Criterion:** A first-time player plays 5 consecutive matches without asking how to play.

## Scope

- Window via `winit`.
- Rendering via `wgpu`: two triangles and text.
- Input: 3 keys for Strike, Block, Grab.
- AI: random or counters last player action.
- Simultaneous reveal with 1-second countdown.
- Color change: red = Strike, blue = Block, green = Grab.
- Health bar, win/loss, restart key.
- No 3D models, no physics engine, no sounds (optional beeps), no particles, no menus.

## Engine Stack

- Rust 1.79+
- `winit` for window and input
- `wgpu` for rendering
- `glam` for math
- `glyphon` or custom bitmap font for text
- `pollster` for sync runtime

## Build Steps

1. `cargo init` in project root.
2. Add dependencies: `winit`, `wgpu`, `glam`, `pollster`.
3. Open a 1280×720 window with event loop.
4. Render two triangles (player blue, opponent red).
5. Add text rendering for health and state labels.
6. Add keyboard input: Z=Strike, X=Block, C=Grab, R=Restart.
7. Add combat state machine: Observe → Commit → Reveal → Resolve → Consequence → loop.
8. Implement 3×3 matchup resolver.
9. Implement AI: random or last-player-action counter.
10. Add health bars and win/loss detection.
11. Add restart on R.
12. Play 50 matches and log.

## Data Sheet

```
Match | Player Action | AI Action | Winner | Feeling | Confusion?
------|---------------|-----------|--------|---------|------------
1     |               |           |        |         |
...   |               |           |        |         |
```

## Report

After playtest, rename this file to `PROTOTYPE_02_SHAPE_PROTOTYPE_REPORT.md` and fill in:

- Result: PASS / FAIL / INCONCLUSIVE
- Decision: KILL / PIVOT / CONTINUE
- What we learned
- Surprises
- Recommendation
