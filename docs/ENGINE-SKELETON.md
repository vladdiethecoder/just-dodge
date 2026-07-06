# Minimal Custom Engine Skeleton — Just Dodge

## Purpose

This document defines the smallest custom engine needed for the Shape Prototype. It intentionally omits every system not required to prove the YOMI loop.

## What the Shape Prototype Engine Needs

1. **Window** — open a 1280×720 window via `winit`.
2. **Render loop** — clear screen, draw two colored triangles, draw text.
3. **Input** — read 3 keys (e.g., Z/X/C) for Strike/Block/Grab.
4. **Fixed-step simulation** — 60 Hz combat state machine.
5. **Matchup resolver** — 3×3 table, deterministic.
6. **State machine** — Observe → Plan → Commit → Reveal → Resolve → Consequence → loop.
7. **Health tracking** — simple numeric health per fighter.
8. **Win/loss detection** — first to deplete health loses.
9. **Restart** — press R to reset.
10. **AI opponent** — random or last-action counter.

## What It Does NOT Need

- Physics engine.
- 3D camera.
- Models, textures, animations.
- Sound beyond optional beeps.
- Menus, settings, save/load.
- Networking.
- Asset pipeline.

## Suggested Crate Stack

| Concern | Crate |
|---|---|
| Window + input | `winit` |
| Rendering | `wgpu` |
| Math | `glam` |
| Text | `glyphon` or simple raster text |
| Async | `pollster` |

## Module Layout (Shape Prototype)

```
just-dodge/
├── Cargo.toml
├── src/
│   ├── main.rs              # window loop, platform glue
│   ├── renderer.rs          # wgpu triangle + text
│   ├── input.rs             # keyboard state events
│   ├── simulation.rs        # fixed-step update
│   ├── combat_state.rs      # state machine
│   ├── resolver.rs          # 3×3 matchup table
│   ├── ai.rs                # opponent decision
│   └── app.rs               # top-level app state
```

## State Machine Pseudocode

```rust
enum CombatState {
    Observe,     // waiting for player input
    Commit,      // both inputs locked
    Reveal,      // show chosen actions for N frames
    Resolve,     // apply matchup result
    Consequence, // show outcome, apply damage
    MatchResult, // someone won
}
```

On `Consequence`, if no one has won, transition back to `Observe`. If someone has won, transition to `MatchResult`, then to `Observe` on restart.

## Rendering Pseudocode

```rust
fn render(&mut self) {
    clear_screen();
    draw_triangle(PLAYER_POS, player_color_for_action());
    draw_triangle(OPPONENT_POS, opponent_color_for_action());
    draw_text(&format!("P1: {}", self.player_health), PLAYER_POS.x, 32.0);
    draw_text(&format!("AI: {}", self.opponent_health), OPPONENT_POS.x, 32.0);
    draw_text(state_label(), center_x, 64.0);
}
```

## Truth Isolation Even at This Scale

- `simulation.rs` never imports `renderer.rs`.
- `renderer.rs` reads `app.combat_state` and `app.fighters` but never writes.
- Match result is identical whether renderer is enabled or disabled.

## First Compile Target

A window with a blue and red triangle. Nothing else. Once that runs, add input. Once input works, add the state machine. Build one verified layer at a time.

## Verification Checklist

- [ ] Window opens and renders two triangles.
- [ ] Input keys are detected.
- [ ] State machine transitions correctly.
- [ ] 3×3 resolver produces expected results for all pairs.
- [ ] Health decrements correctly.
- [ ] Match resets on R.
- [ ] AI commits before reveal every exchange.
