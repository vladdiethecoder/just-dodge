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

- This is a proof-of-concept trainer on the right-hand trajectory, not a full-body
  production MotionBricks checkpoint.
- The WO §3 thresholds (hand constraint ≤ 2 mm, socket ≤ 1 mm, etc.) are NOT yet met
  by this proof-of-concept (held-out contact error is 3.5–7.2 mm, above the 2 mm
  hand-constraint gate). Closing that gap needs a larger corpus and a full-body
  model, and is forward work.
- Blinded human distinguishability trial not yet run.
- Timing variants (early/nominal/late) come from retiming to contact frames; the
  corpus currently carries target-direction diversity with timing derived downstream.

## Reproduce

```
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1   # cached model; avoids flaky hub check
python3 tools/qa/build_p3_strike_corpus.py --seeds 6
python3 tools/qa/train_p3_interaction_conditioner.py --held-out-target high_right
```
