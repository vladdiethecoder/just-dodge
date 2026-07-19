# Forecast HUD design authority (F-109..F-114)

Status: DESIGN GATE PASSED (visual QA on rendered mock). Implementation against
this receipt is authorized. Owner: just-dodge-ui.

## Canvas receipt

- Document: `canvas-c602d5588727` ("Just Dodge — Forecast HUD (F-109..F-114)")
- Revision: 4
- Semantic SHA-256: `119336a9b0db028547385d883e8519f779747eb1d058395288bf6e9ea7b7dca4`
- Artboard: 1920x1080, local-only, hash-chained history
- Visual QA: Chrome headless screenshot at 1920x1080 reviewed (rows one-per-line,
  both forecast lanes visible, no overlap, panels clear of center view)

## Layout (artboard coordinates)

| Panel | Node | x,y,w,h |
|---|---|---|
| Yomi resources (burst/feint/whiff) | `yomi-resources` | 24,24,360,140 |
| Injury readout | `injury-readout` | 1536,24,360,150 |
| Player intent list | `intent-list` | 24,560,300,496 |
| Forecast panel | `forecast-panel` | 344,820,1232,236 |
| Opponent what-if picker | `opponent-whatif-picker` | 1596,560,300,496 |
| Dev overlay anchor (F3) | `dev-overlay-anchor` | 24,1040,400,18 |

Center screen (344..1596 x 174..820) stays clear: the opponent's body/tell is
never covered during first-person or observer play.

## Control map (Canvas node → Rust anchor)

| Canvas node | Rust anchor | Binding |
|---|---|---|
| `burst-meter` / `burst-meter-fill` | `src/intent/plan_phase.rs` `PlanSnapshot.burst` | fill width = burst/100; tick mark at 75 (WHIFF_CANCEL_BURST_COST) |
| `feint-charges` | `PlanSnapshot.feint_charges` | one pip per charge |
| `whiff-indicator` | `PlanSnapshot.whiffed[side]` | visible only while the window is open |
| `intent-rows` | `PlanPhase::is_feasible` + `Intent::state().anim_length` | dim rows that are infeasible (range/charges/whiff-gate); frame-cost chip per row |
| `clinch-submenu` | `PlanSnapshot.clinch.is_some()` | replaces intent rows while clinched (HOLD/KNEE/THROW/TECH/BREAK with `ClinchIntent::frame_cost`) |
| `forecast-timeline-strip` (`lane-p1`, `lane-p2`) | `PlanPhase::simulate_to_boundary` (forecast copy) + `PlanEvent` stream | intent blocks per lane, event markers (IASA/interrupt/hit-cancel/contact/GrabSecure), window-end cursor |
| `contact-outcome-indicator` | forecast `PlanEvent`s + `PhysicalContactBatch` | predicted hit/block/whiff/grab/injury delta; NEVER fabricated — "no contact predicted" is a valid readout |
| `ready-interrupt-status` | `ActionabilityReason` per side at freeze | per-side ready/interrupt/IOOT/negative-on-hit/grab-hold |
| `lock-intent-button` | `PlanPhase::submit_intent` | locks both sides' chosen intents |
| `opponent-whatif-picker` (`whatif-rows`) | forecast with hypothetical opponent intent | full-information tactics preview (game-first spec: legal) |
| `injury-regions` | injury truth `available_intents` | capability-gated readout, not debug numbers |
| `dev-overlay-anchor` | `show_dev` flag (existing) | F3 toggles frame data/contact boxes/truth hash |

## Behavior rules (binding on implementation)

1. Forecast is a COPY simulation (never mutates live truth); it runs the same
   `step_truth_tick` path so predicted events are real engine events.
2. The timeline strip ends at the first actionability event (IASA / interrupt /
   hit-cancel / contact / grab resolution) — never a fixed window.
3. In-world ghosts (F-112) render the forecast root track for both fighters in
   wireframe cyan/red; they are presentation-only and may not feed truth.
4. Intent list and what-if picker reflect state-conditioned availability:
   burst, feint charges, whiff gate, grab range, clinch state.
5. All numeric readouts come from `PlanSnapshot` (replay-hashed state), never
   from presentation-side recomputation.

## Evidence gates (per backlog Part D)

- G4/G5: ForgeLens visual review of the implemented HUD in the live game loop.
- H1/H2: headless forecast test — scripted lock → forecast event stream matches
  an independently stepped copy (determinism), plus golden hash continuity.
- E2: Steam Deck profile with HUD active ≥60 FPS.
