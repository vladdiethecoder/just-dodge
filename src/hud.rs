//! Stroke-font HUD for the forecast planning freeze (F-110/F-112).
//!
//! Design authority: docs/design/FORECAST_HUD_DESIGN.md (canvas-c602d5588727
//! r4). Zero dependencies: glyphs are hand-authored 4x6 stroke grids rendered
//! as NDC line segments through the HUD line pipeline (identity MVP,
//! depth-always). Every numeric readout comes from `PlanSnapshot` / the
//! forecast outcome — presentation never recomputes truth.

use glam::{Vec3, vec3};

use crate::intent::{ClinchIntent, ForecastOutcome, Intent, PlanSnapshot, predicted_outcome};

/// NDC line segment with RGB color.
pub type HudSegments = Vec<(Vec3, Vec3, [f32; 3])>;

const CYAN: [f32; 3] = [0.22, 0.78, 1.0];
const RED: [f32; 3] = [1.0, 0.3, 0.37];
const AMBER: [f32; 3] = [1.0, 0.7, 0.28];
const TEXT: [f32; 3] = [0.91, 0.93, 0.96];
const DIM: [f32; 3] = [0.42, 0.47, 0.55];
const GREEN: [f32; 3] = [0.22, 1.0, 0.62];

// ---------------------------------------------------------------------------
// Stroke font: 4 wide x 6 tall grid, y down. Each glyph is line pairs.
// ---------------------------------------------------------------------------

type G = &'static [((i8, i8), (i8, i8))];

#[allow(clippy::too_many_lines)]
fn glyph(c: char) -> G {
    match c {
        'A' => &[((0, 6), (2, 0)), ((2, 0), (4, 6)), ((1, 4), (3, 4))],
        'B' => &[
            ((0, 0), (0, 6)),
            ((0, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 2)),
            ((4, 2), (3, 3)),
            ((3, 3), (0, 3)),
            ((3, 3), (4, 4)),
            ((4, 4), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (0, 6)),
        ],
        'C' => &[
            ((4, 0), (1, 0)),
            ((1, 0), (0, 1)),
            ((0, 1), (0, 5)),
            ((0, 5), (1, 6)),
            ((1, 6), (4, 6)),
        ],
        'D' => &[
            ((0, 0), (0, 6)),
            ((0, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (0, 6)),
        ],
        'E' => &[
            ((4, 0), (0, 0)),
            ((0, 0), (0, 6)),
            ((0, 6), (4, 6)),
            ((0, 3), (3, 3)),
        ],
        'F' => &[((0, 6), (0, 0)), ((0, 0), (4, 0)), ((0, 3), (3, 3))],
        'G' => &[
            ((4, 1), (3, 0)),
            ((3, 0), (1, 0)),
            ((1, 0), (0, 1)),
            ((0, 1), (0, 5)),
            ((0, 5), (1, 6)),
            ((1, 6), (4, 6)),
            ((4, 6), (4, 3)),
            ((4, 3), (2, 3)),
        ],
        'H' => &[((0, 0), (0, 6)), ((4, 0), (4, 6)), ((0, 3), (4, 3))],
        'I' => &[((1, 0), (3, 0)), ((2, 0), (2, 6)), ((1, 6), (3, 6))],
        'J' => &[
            ((4, 0), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (1, 6)),
            ((1, 6), (0, 5)),
        ],
        'K' => &[((0, 0), (0, 6)), ((4, 0), (0, 3)), ((0, 3), (4, 6))],
        'L' => &[((0, 0), (0, 6)), ((0, 6), (4, 6))],
        'M' => &[
            ((0, 6), (0, 0)),
            ((0, 0), (2, 3)),
            ((2, 3), (4, 0)),
            ((4, 0), (4, 6)),
        ],
        'N' => &[((0, 6), (0, 0)), ((0, 0), (4, 6)), ((4, 6), (4, 0))],
        'O' => &[
            ((1, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (1, 6)),
            ((1, 6), (0, 5)),
            ((0, 5), (0, 1)),
            ((0, 1), (1, 0)),
        ],
        'P' => &[
            ((0, 6), (0, 0)),
            ((0, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 2)),
            ((4, 2), (3, 3)),
            ((3, 3), (0, 3)),
        ],
        'Q' => &[
            ((1, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (1, 6)),
            ((1, 6), (0, 5)),
            ((0, 5), (0, 1)),
            ((0, 1), (1, 0)),
            ((2, 4), (4, 6)),
        ],
        'R' => &[
            ((0, 6), (0, 0)),
            ((0, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 2)),
            ((4, 2), (3, 3)),
            ((3, 3), (0, 3)),
            ((2, 3), (4, 6)),
        ],
        'S' => &[
            ((4, 1), (3, 0)),
            ((3, 0), (1, 0)),
            ((1, 0), (0, 1)),
            ((0, 1), (0, 2)),
            ((0, 2), (1, 3)),
            ((1, 3), (3, 3)),
            ((3, 3), (4, 4)),
            ((4, 4), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (1, 6)),
            ((1, 6), (0, 5)),
        ],
        'T' => &[((0, 0), (4, 0)), ((2, 0), (2, 6))],
        'U' => &[
            ((0, 0), (0, 5)),
            ((0, 5), (1, 6)),
            ((1, 6), (3, 6)),
            ((3, 6), (4, 5)),
            ((4, 5), (4, 0)),
        ],
        'V' => &[((0, 0), (2, 6)), ((2, 6), (4, 0))],
        'W' => &[
            ((0, 0), (1, 6)),
            ((1, 6), (2, 3)),
            ((2, 3), (3, 6)),
            ((3, 6), (4, 0)),
        ],
        'X' => &[((0, 0), (4, 6)), ((4, 0), (0, 6))],
        'Y' => &[((0, 0), (2, 3)), ((4, 0), (2, 3)), ((2, 3), (2, 6))],
        'Z' => &[((0, 0), (4, 0)), ((4, 0), (0, 6)), ((0, 6), (4, 6))],
        '0' => &[
            ((1, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (1, 6)),
            ((1, 6), (0, 5)),
            ((0, 5), (0, 1)),
            ((0, 1), (1, 0)),
        ],
        '1' => &[((1, 1), (2, 0)), ((2, 0), (2, 6)), ((1, 6), (3, 6))],
        '2' => &[
            ((0, 1), (1, 0)),
            ((1, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 2)),
            ((4, 2), (0, 6)),
            ((0, 6), (4, 6)),
        ],
        '3' => &[
            ((0, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 2)),
            ((4, 2), (3, 3)),
            ((3, 3), (1, 3)),
            ((3, 3), (4, 4)),
            ((4, 4), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (0, 6)),
        ],
        '4' => &[((0, 0), (0, 3)), ((0, 3), (4, 3)), ((3, 0), (3, 6))],
        '5' => &[
            ((4, 0), (0, 0)),
            ((0, 0), (0, 3)),
            ((0, 3), (3, 3)),
            ((3, 3), (4, 4)),
            ((4, 4), (4, 5)),
            ((4, 5), (3, 6)),
            ((3, 6), (0, 6)),
        ],
        '6' => &[
            ((3, 0), (1, 0)),
            ((1, 0), (0, 1)),
            ((0, 1), (0, 5)),
            ((0, 5), (1, 6)),
            ((1, 6), (3, 6)),
            ((3, 6), (4, 5)),
            ((4, 5), (4, 4)),
            ((4, 4), (3, 3)),
            ((3, 3), (0, 3)),
        ],
        '7' => &[((0, 0), (4, 0)), ((4, 0), (2, 6))],
        '8' => &[
            ((1, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 2)),
            ((4, 2), (3, 3)),
            ((3, 3), (1, 3)),
            ((1, 3), (0, 2)),
            ((0, 2), (0, 1)),
            ((0, 1), (1, 0)),
            ((1, 3), (0, 4)),
            ((0, 4), (0, 5)),
            ((0, 5), (1, 6)),
            ((1, 6), (3, 6)),
            ((3, 6), (4, 5)),
            ((4, 5), (4, 4)),
            ((4, 4), (3, 3)),
        ],
        '9' => &[
            ((1, 6), (3, 6)),
            ((3, 6), (4, 5)),
            ((4, 5), (4, 1)),
            ((4, 1), (3, 0)),
            ((3, 0), (1, 0)),
            ((1, 0), (0, 1)),
            ((0, 1), (0, 2)),
            ((0, 2), (1, 3)),
            ((1, 3), (4, 3)),
        ],
        '.' => &[((2, 5), (2, 6))],
        ',' => &[((2, 4), (1, 6))],
        ':' => &[((2, 1), (2, 2)), ((2, 4), (2, 5))],
        ';' => &[((2, 1), (2, 2)), ((2, 4), (1, 6))],
        '-' => &[((1, 3), (3, 3))],
        '+' => &[((1, 3), (3, 3)), ((2, 2), (2, 4))],
        '/' => &[((0, 6), (4, 0))],
        '(' => &[((2, 0), (1, 1)), ((1, 1), (1, 5)), ((1, 5), (2, 6))],
        ')' => &[((1, 0), (2, 1)), ((2, 1), (2, 5)), ((2, 5), (1, 6))],
        '[' => &[((2, 0), (1, 0)), ((1, 0), (1, 6)), ((1, 6), (2, 6))],
        ']' => &[((1, 0), (2, 0)), ((2, 0), (2, 6)), ((2, 6), (1, 6))],
        '<' => &[((3, 0), (1, 3)), ((1, 3), (3, 6))],
        '>' => &[((1, 0), (3, 3)), ((3, 3), (1, 6))],
        '!' => &[((2, 0), (2, 4)), ((2, 5), (2, 6))],
        '?' => &[
            ((1, 1), (2, 0)),
            ((2, 0), (3, 0)),
            ((3, 0), (4, 1)),
            ((4, 1), (4, 2)),
            ((4, 2), (2, 4)),
            ((2, 5), (2, 6)),
        ],
        '\'' => &[((2, 0), (2, 1))],
        '=' => &[((1, 2), (3, 2)), ((1, 4), (3, 4))],
        '_' => &[((0, 6), (4, 6))],
        '*' => &[((2, 1), (2, 5)), ((0, 2), (4, 4)), ((4, 2), (0, 4))],
        '%' => &[
            ((0, 6), (4, 0)),
            ((0, 0), (1, 0)),
            ((1, 0), (1, 1)),
            ((1, 1), (0, 1)),
            ((0, 1), (0, 0)),
            ((3, 5), (4, 5)),
            ((4, 5), (4, 6)),
            ((4, 6), (3, 6)),
            ((3, 6), (3, 5)),
        ],
        // Diamond pip (feint charge etc.).
        '\u{25CF}' => &[
            ((2, 1), (3, 3)),
            ((3, 3), (2, 5)),
            ((2, 5), (1, 3)),
            ((1, 3), (2, 1)),
        ],
        _ => &[],
    }
}

/// Draw text at layout position (x, y) with character height `size`. Layout
/// coordinates are top-down (y = -1 top, +1 bottom); NDC y is negated at
/// emission (NDC grows upward). Lowercase renders as uppercase.
pub fn text_lines(
    out: &mut HudSegments,
    s: &str,
    x: f32,
    y: f32,
    size: f32,
    aspect: f32,
    color: [f32; 3],
) {
    let unit = size / 6.0;
    let xu = unit / aspect;
    let mut cx = x;
    for c in s.chars() {
        let c = c.to_ascii_uppercase();
        for &((ax, ay), (bx, by)) in glyph(c) {
            out.push((
                vec3(cx + ax as f32 * xu, -(y + ay as f32 * unit), 0.5),
                vec3(cx + bx as f32 * xu, -(y + by as f32 * unit), 0.5),
                color,
            ));
        }
        cx += 5.0 * xu;
    }
}

/// Outline rectangle (layout coordinates, top-down y; negated at emission).
pub fn rect_lines(out: &mut HudSegments, x: f32, y: f32, w: f32, h: f32, color: [f32; 3]) {
    let (x2, y2) = (x + w, y + h);
    for (a, b) in [
        (vec3(x, -y, 0.5), vec3(x2, -y, 0.5)),
        (vec3(x2, -y, 0.5), vec3(x2, -y2, 0.5)),
        (vec3(x2, -y2, 0.5), vec3(x, -y2, 0.5)),
        (vec3(x, -y2, 0.5), vec3(x, -y, 0.5)),
    ] {
        out.push((a, b, color));
    }
}

/// Hatched fill bar: track outline + vertical hatch lines across `frac`.
#[allow(clippy::too_many_arguments)]
pub fn bar_lines(
    out: &mut HudSegments,
    x: f32,
    y: f32,
    w: f32,
    h: f32,
    frac: f32,
    color: [f32; 3],
    track: [f32; 3],
) {
    rect_lines(out, x, y, w, h, track);
    let fill = w * frac.clamp(0.0, 1.0);
    let steps = 24;
    for i in 0..steps {
        let fx = x + fill * (i as f32 + 0.5) / steps as f32;
        if fx > x + fill {
            break;
        }
        out.push((vec3(fx, -y, 0.5), vec3(fx, -(y + h), 0.5), color));
    }
}

// ---------------------------------------------------------------------------
// HUD content (design receipt panels, NDC coordinates)
// ---------------------------------------------------------------------------

fn intent_label(intent: Intent) -> String {
    match intent {
        Intent::Strike { variant } => format!("STRIKE {variant:?}").to_uppercase(),
        Intent::Block => "BLOCK".into(),
        Intent::Grab => "GRAB".into(),
        Intent::Dodge { .. } => "DODGE".into(),
        Intent::Move { dir, .. } => format!("MOVE {dir:?}").to_uppercase(),
        Intent::Feint => "FEINT".into(),
        Intent::Cancel => "CANCEL".into(),
        Intent::Idle => "IDLE".into(),
        Intent::Clinch { sub } => format!("CLINCH {sub:?}").to_uppercase(),
    }
}

/// The selectable intent rows (matches game_loop's what-if cycle).
pub const SELECTABLE: &[Intent] = &[
    Intent::Strike {
        variant: crate::intent::StrikeVariant::Slash,
    },
    Intent::Strike {
        variant: crate::intent::StrikeVariant::Thrust,
    },
    Intent::Block,
    Intent::Grab,
    Intent::Dodge {
        dir: crate::intent::MoveDirection::LateralLeft,
    },
    Intent::Feint,
    Intent::Cancel,
    Intent::Idle,
];

const CLINCH_ROWS: &[ClinchIntent] = &[
    ClinchIntent::Hold,
    ClinchIntent::Knee,
    ClinchIntent::Throw,
    ClinchIntent::Tech,
    ClinchIntent::Break,
];

/// Build the full HUD for a planning freeze. `availability[i]` is the
/// feasibility of SELECTABLE[i] for the player; `opp_availability` the same
/// for the opponent (what-if picker dimming).
#[allow(clippy::too_many_arguments)]
pub fn build_hud(
    snapshot: &PlanSnapshot,
    forecast: Option<&ForecastOutcome>,
    availability: &[bool],
    opp_availability: &[bool],
    aspect: f32,
) -> HudSegments {
    let mut out = Vec::new();
    let ch = 0.028_f32; // character height in NDC
    let line = 0.038_f32; // line advance

    // --- Yomi resources (top-left; receipt 24,24,360,140) ---
    let x = -0.965;
    let mut y = -0.95;
    text_lines(&mut out, "BURST", x, y, ch, aspect, DIM);
    y += line;
    bar_lines(
        &mut out,
        x,
        y,
        0.30,
        0.016,
        f32::from(snapshot.burst[0]) / 100.0,
        CYAN,
        DIM,
    );
    // 75% whiff-cancel threshold tick.
    let tick_x = x + 0.30 * 0.75;
    out.push((
        vec3(tick_x, -(y - 0.004), 0.5),
        vec3(tick_x, -(y + 0.02), 0.5),
        AMBER,
    ));
    y += line;
    let pips: String = (0..2)
        .map(|i| {
            if (i as u8) < snapshot.feint_charges[0] {
                '\u{25CF}'
            } else {
                '.'
            }
        })
        .collect();
    text_lines(&mut out, &format!("FEINT {pips}"), x, y, ch, aspect, AMBER);
    y += line;
    if snapshot.whiffed[0] {
        text_lines(
            &mut out,
            "WHIFF WINDOW - CANCEL READY",
            x,
            y,
            ch,
            aspect,
            GREEN,
        );
    }

    // --- Truth readout (top-right; receipt injury panel position). Injury is
    // NOT wired into PlanPhase — this panel shows only real snapshot state.
    let x = 0.62;
    let mut y = -0.95;
    text_lines(&mut out, "STATE", x, y, ch, aspect, DIM);
    y += line;
    let grab_text = snapshot.grab.map_or("GRAB -".to_string(), |g| {
        format!("GRAB {g:?}").to_uppercase()
    });
    text_lines(&mut out, &grab_text, x, y, ch, aspect, TEXT);
    y += line;
    let clinch_text = snapshot.clinch.map_or("CLINCH -".to_string(), |c| {
        format!("CLINCH {c:?}").to_uppercase()
    });
    text_lines(&mut out, &clinch_text, x, y, ch, aspect, TEXT);
    y += line;
    text_lines(
        &mut out,
        &format!(
            "CONTACT {}",
            if snapshot.last_contact_observed {
                "YES"
            } else {
                "NO"
            }
        ),
        x,
        y,
        ch,
        aspect,
        TEXT,
    );

    // --- Intent list (bottom-left; receipt 24,560 → layout y ≈ +0.04) ---
    let x = -0.965;
    let mut y = 0.04;
    text_lines(&mut out, "INTENT", x, y, ch, aspect, DIM);
    y += line;
    if snapshot.clinch.is_some() {
        for sub in CLINCH_ROWS {
            text_lines(
                &mut out,
                &format!("{sub:?} {}F", sub.frame_cost()).to_uppercase(),
                x,
                y,
                ch,
                aspect,
                RED,
            );
            y += line;
        }
    } else {
        for (i, intent) in SELECTABLE.iter().enumerate() {
            let ok = availability.get(i).copied().unwrap_or(false);
            let color = if ok { TEXT } else { DIM };
            let frames = intent.state().anim_length;
            text_lines(
                &mut out,
                &format!("{} {frames}F", intent_label(*intent)),
                x,
                y,
                ch,
                aspect,
                color,
            );
            y += line;
        }
    }

    // --- Opponent what-if picker (bottom-right; receipt 1596,560) ---
    let x = 0.66;
    let mut y = 0.04;
    text_lines(&mut out, "OPPONENT WHAT-IF", x, y, ch, aspect, DIM);
    y += line;
    for (i, intent) in SELECTABLE.iter().enumerate() {
        let ok = opp_availability.get(i).copied().unwrap_or(false);
        let color = if ok { RED } else { DIM };
        let frames = intent.state().anim_length;
        text_lines(
            &mut out,
            &format!("{} {frames}F", intent_label(*intent)),
            x,
            y,
            ch,
            aspect,
            color,
        );
        y += line;
    }

    // --- Forecast strip (bottom-center; receipt 344,820 → layout y ≈ +0.52) ---
    let x = -0.64;
    let mut y = 0.52;
    text_lines(
        &mut out,
        "FORECAST - LIVE SIM TO FIRST ACTIONABILITY",
        x,
        y,
        ch * 0.8,
        aspect,
        DIM,
    );
    y += line;
    if let Some(outcome) = forecast {
        // Lane blocks: length proportional to the window, capped at 0.55 NDC.
        let w = (outcome.ticks as f32 * 0.02).clamp(0.05, 0.55);
        let lane_h = 0.03;
        rect_lines(&mut out, x, y, w, lane_h, CYAN);
        text_lines(&mut out, "P1", x - 0.05, y + 0.004, ch * 0.8, aspect, CYAN);
        y += lane_h + 0.012;
        rect_lines(&mut out, x, y, w, lane_h, RED);
        text_lines(&mut out, "P2", x - 0.05, y + 0.004, ch * 0.8, aspect, RED);
        y += lane_h + 0.02;
        text_lines(
            &mut out,
            &format!(
                "PREDICTED {:?} IN {}F",
                predicted_outcome(outcome),
                outcome.ticks
            ),
            x,
            y,
            ch,
            aspect,
            AMBER,
        );
        y += line;
    } else {
        text_lines(
            &mut out,
            "FORECAST UNAVAILABLE (BUSY)",
            x,
            y,
            ch,
            aspect,
            DIM,
        );
        y += line;
    }
    text_lines(&mut out, "SPACE LOCK INTENT", x, y, ch * 0.8, aspect, DIM);
    out
}
