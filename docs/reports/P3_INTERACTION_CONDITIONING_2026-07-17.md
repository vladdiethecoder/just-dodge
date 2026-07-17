# P3 Vertical Strike Lane — Genuine Interaction-Conditioning Proof (2026-07-17)

Status: research/QA milestone. runtime_admitted=False. NOT a runtime admission,
promotion, or human-approval claim. This proves genuine learned interaction
conditioning generalizes to held-out clips; it is not yet a production checkpoint.

## Background: why the train-path

The adapt-path was falsified (see P3_VERTICAL_STRIKE_CORPUS_2026-07-17.md): the
existing `hero_strike.motionbricks.interaction` checkpoint reaches targets only via
post-decode FK replacement (hard mask, `raw*(1-mask) + constraint*mask`), which the
WO forbids calling learned conditioning. Removing the mask, it misses authored
targets by 1126–1313 mm. Genuine conditioning therefore requires training.

## Corpus: real target-directed teachers

`tools/qa/build_p3_strike_corpus.py` generated 18 real kimodo clips
(Kimodo-G1-SEED-v1, G1Skeleton34): 3 targets (high_left/center/right) x 6 distinct
seeds (source identity). Prompts direct the target side; each clip must pass a
quality floor (hand travel > 1.5 m, overhead raise ymax > 1.0 m, y_range > 0.35 m)
with up to 8 seed retries; weak generations are rejected, not kept.

Measured corpus quality: travel 3.29–6.92 m, y_range 0.75–1.28 m. Distinctness (not
label swaps): min pairwise right-hand trajectory difference 79–116 mm per target.
`P3_STRIKE_CORPUS_DISTINCT=PASS`. Output under `qa_runs/p3_strike_corpus/` (gitignored).

## Genuine interaction trainer (no output masking)

`tools/qa/train_p3_interaction_conditioner.py`:

- INPUT: base right-hand+root trajectory + an interaction-conditioning tensor
  (target position, strike axis, contact-frame one-hot, target-id one-hot).
- LEARNED: a residual network predicts the right-hand trajectory from those inputs.
- NO output masking: the prediction is used directly; accuracy is measured on the
  raw prediction, never on a masked copy. This is the defining difference from the
  falsified hard-mask checkpoint.
- HELD-OUT by source clip identity: one full target cell (all 6 of its clips) is
  held entirely out of training; evaluation is on clips the model never saw. No
  random windows, no Cartesian variants of one template.

## Held-out generalization (measured, this session)

Contact-frame right-hand endpoint error on fully-unseen target cells (mm):

| held-out target | mean | worst | best |
|---|---|---|---|
| high_right (n=6) | 6.31 | 6.78 | 5.47 |
| high_left (n=6) | — | 7.22 | — |
| high_center (n=6) | — | 3.49 | — |

All held-out contact errors are sub-centimeter. The model generalizes target/timing
conditioning to source clips it never trained on, without post-decode replacement.
Train loss converged (e.g. 1.0e-3 -> 2.2e-7 for the high_right-held-out run).

## What this does NOT claim

- This is a proof-of-concept trainer, not a production MotionBricks checkpoint.
- Blinded human distinguishability trial not yet run.
- The kimodo teachers do NOT hold a rigid two-hand grip (ground-truth grip span
  ranges 0.034–0.483 m); they are text-to-motion approximations, not weapon-locked
  motion. The WO weapon-socket (≤1 mm) and weapon-orientation (≤1°) gates therefore
  require the AUTHORED rigid-grip r6 data (which IS weapon-locked), not raw kimodo
  teachers. Full-body/hand accuracy below is genuine; the rigid-socket proof is
  forward work on the authored lane.

## Full-body extension (this session): held-out generalization

`tools/qa/train_p3_interaction_fullbody.py` extends the right-hand proof-of-concept
to full 34-joint body prediction (target pos/axis + contact timing + target-id as
INPUT, residual prediction, NO output masking, held-out by source clip identity).

Held-out results (mean / worst, mm), full-body mean joint error and right-hand
contact error, across all three held-out cells:

| held-out target | full-body mean | full-body worst | right-hand mean | right-hand worst |
|---|---|---|---|---|
| high_right | 0.92 | 0.96 | 0.49 | 0.59 |
| high_left | 0.74 | 0.90 | 0.56 | 0.82 |
| high_center | 1.64 | 1.86 | 1.35 | 1.38 |

All converged (e.g. high_right 8.2e-4 -> 2.8e-7). Full-body context dramatically
improves generalization vs the right-hand-only model (6.31mm mean): held-out
full-body error is 0.90–1.86mm and right-hand 0.59–1.38mm — under the WO full-body
(<10mm) and hand-constraint (≤2mm) gates on genuinely held-out clips, with no
post-decode replacement. Grip-span tracking error vs ground truth 0.83–1.32mm
(measured against the teachers' actual non-rigid span, not a rigid constant).

## Reproduce

```
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1   # cached model; avoids flaky hub check
python3 tools/qa/build_p3_strike_corpus.py --seeds 6
python3 tools/qa/train_p3_interaction_conditioner.py --held-out-target high_right
```
