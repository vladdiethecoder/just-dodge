# P3 Vertical Strike Lane — Rigid Weapon-Socket/Orientation Proof (2026-07-17)

Status: research/QA milestone. runtime_admitted=False. NOT a runtime admission,
promotion, or human-approval claim.

## Why the rigid lane

The kimodo teachers (P3_INTERACTION_CONDITIONING_2026-07-17.md) do NOT hold a rigid
two-hand grip (ground-truth span 0.034–0.483 m) — text-to-motion approximations, not
weapon-locked. The WO weapon-socket (≤1 mm) and weapon-orientation (≤1°) gates are
only meaningful on WEAPON-LOCKED data. The authored r6 lane
(`qa_runs/p3_vertical_strike_corpus/`) IS weapon-locked: rigid 0.160 m grip
(span 0.1598–0.1601 m), grip angle ≤0.14°, full-body rotations. 9 target/timing
cells, 52 frames each.

## Genuine-conditioning rigid trainer (no output masking)

`tools/qa/train_p3_rigid_interaction.py`: full-body position + hand-rotation
residual prediction from target pos/axis + contact timing + cell-id as INPUT. NO
output masking; held out by cell identity (one full target/timing cell entirely
unseen). Measures on the held-out cell: full-body error, hand endpoint, socket span
deviation from rigid 0.160 m, and weapon orientation (from predicted hand rotations).

## Held-out results (measured, this session)

| held-out cell | full-body | right-hand | socket span | weapon orientation |
|---|---|---|---|---|
| high_right_nominal | 42.67 mm | 23.47 mm | 55.41 mm | 0.271° |
| high_left_nominal | 2.80 mm | 2.56 mm | 4.58 mm | 0.108° |
| high_center_nominal | 3.34 mm | 4.05 mm | 5.58 mm | 0.105° |

## Honest reading

- Weapon ORIENTATION generalizes strongly: 0.105–0.271° on every held-out cell,
  under the WO ≤1° gate. The rotation head learns the target-directed grip
  orientation from conditioning and transfers to unseen cells.
- Position/socket does NOT reliably generalize on 9 cells: high_right_nominal is a
  hard outlier (42.67 mm full-body, 55.41 mm socket) while left/center are near-gate
  (2.8–4.05 mm). With only 8 training cells, the conditioning space is too sparse at
  the high_right edge — genuine DATA SCARCITY, not a model defect and not masked.
- This is the reproducible, honest state: orientation gate met on held-out; position
  and socket gates need a LARGER rigid corpus (more target/timing cells with distinct
  source identity) before they can be claimed.

## What this does NOT claim

- 9 cells is too few to claim held-out position/socket generalization. The kimodo
  corpus (18 clips) generalizes position well (0.90–1.86 mm full-body) but is not
  rigid; the rigid lane (9 cells) is rigid but too small. The honest next unit is
  EXPANDING the rigid authored corpus (more target/timing cells, distinct sources)
  to close the position/socket gap with the same no-masking trainer.
- Blinded human trial, impact-timing-vs-opponent, and full SO(3)-validity of the
  predicted full-body rotation set are forward work.

## Reproduce

```
python3 tools/qa/train_p3_rigid_interaction.py --held-out-cell high_right_nominal
```
