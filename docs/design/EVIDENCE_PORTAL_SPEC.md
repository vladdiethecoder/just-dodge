# Evidence Portal Spec — ADHD-Style Visual Review

**Date:** 2026-07-21
**Based on:** `ayghri/i-have-adhd` (6.5K stars, GitHub trending #4, 2026-07-21)
**Replaces:** verbose multi-check evidence reports with log dumps

## Rules

1. **Lead with the visual.** Screenshot, GIF, or video is the first thing the owner sees. No text preamble.
2. **One decision at a time.** One ticket per screen. Never a multi-page report.
3. **Multiple choice only.** Accept / Reject / Needs Changes. No text fields, no comments required.
4. **No verbose explanations.** If a check needs context, show it in the image itself (annotation, overlay, side-by-side).
5. **Show concrete next step.** After each decision: "Next: generate strike motion" or "Next: fix finger webbing and resubmit."
6. **Cap lists at 5 items.** If there are more than 5 checks, paginate. Never show a wall of text.
7. **Make wins visible.** "3/5 accepted, 1 rejected, 1 pending" at the top.
8. **No "hope this helps," no recaps, no closers.** The decision is the output.

## Visual Deliverables Per Gate

| Gate | Deliverable | Format |
|---|---|---|
| Fighter T-pose | Front/side/back renders in-engine | Screenshot (PNG) |
| Fighter topology | Wireframe close-up of hands, feet, joints | Screenshot (PNG) |
| Strike motion | Full strike sequence from anticipation to recovery | GIF (looping) |
| Block motion | Guard raise → contact → recovery | GIF (looping) |
| Grab motion | Reach → grasp → clinch entry | GIF (looping) |
| Match flow | Full Boot→Result sequence | Video (MP4, 30-60s) |
| Combat readability | Two exchanges with visible contact | Video (MP4) |

## Implementation

The existing evidence review server at tools/evidence_review/ should be refactored to:
- Single-check view (not multi-check reports)
- Image/GIF embed as primary content
- Three buttons: Accept / Reject / Needs Changes
- Progress bar: "N/M decided"
- After all decisions: summary with next action

The `i-have-adhd` SKILL.md from `ayghri/i-have-adhd` (MIT license) should be adapted as a Hermes skill for evidence presentation.
