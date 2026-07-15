# ForgeLens

ForgeLens is Just Dodge's local browser gate for reviewing 3D assets, environment/world models, and animated GLB artifacts. It does not mutate source assets and adds no project dependency.

## Launch

From the repository root:

```bash
python3 tools/asset_review.py
python3 tools/asset_review.py --asset assets/source/meshy/w0_sword/assembled_001/model.glb
python3 tools/asset_review.py --asset assets/source/meshy/c0_armored_duelist_001/model.glb --port 4177 --no-open
```

The server binds only to `127.0.0.1`. On startup it prints `ASSET_REVIEW_URL`, `ASSET_REVIEW_ROOT`, and the indexed asset count. The default launch opens the system's regular human browser. `--no-open` is automation-only: never use it when a human decision or visual acceptance is required. In that case ForgeLens must be opened in the user's normal browser, not an agent-automation browser.

## Review mechanics

- Repository catalog grouped into asset families and pipeline stages.
- Pure WebGL2 GLB 2.0 rendering; no CDN, package, or external runtime.
- Smooth damped orbit, shift-pan, wheel dolly, reset framing, grid, material, clay, normals, wireframe, and screenshot modes.
- Stage/version comparison using a cyan ghost overlay and metric deltas.
- Triangle, vertex, material, texture, node, skin, and animation metadata.
- Surface-space comment pins with persisted world point, normal, camera, discipline, severity, author, and status.
- Review decisions, a design acceptance matrix, adjacent QA evidence, JSON/Markdown export, drag-and-drop local GLB inspection, and keyboard command palette.
- CPU skin evaluation for dependency-free animation playback, clip selection, timeline scrubbing, speed, and looping.

Review JSON is atomically persisted under `qa_runs/asset_reviews/reviews/`. Source assets remain read-only.

## Human report handoff

The top-level **Submit report** action sends the current decision, summary, checklist, comments, spatial pins, and neural-gate context to `POST /api/report`. The server persists a content-bound receipt, emits `FORGELENS_REPORT_SUBMITTED=...`, and the review window requests closure after a successful response. Any later human edit invalidates the stale receipt.

Hermes watches `FORGELENS_REPORT_SUBMITTED=`. A specialized planning agent converts that exact submitted report into ordered implementation tasks. An independent adversarial agent then challenges coverage, dependencies, acceptance criteria, and fidelity to the human observations. Only a plan with an adversarial `pass` verdict may be persisted through `POST /api/report-plan`; accepted plans emit `FORGELENS_TASK_PLAN_VERIFIED=...` and remain bound to the exact human report receipt.

## Mandatory neural animation gate

Animated assets cannot be approved until their persisted `neuralMotion.status` is `pass`.

1. Open an animated GLB.
2. Choose the clip and camera.
3. Select **Prepare neural gate**. ForgeLens deterministically evaluates eight evenly spaced clip times, renders a 1600×900 contact sheet, hashes it, and stores it under `qa_runs/asset_reviews/evidence/<asset-id>/`.
4. Hermes loads that exact PNG with a neural vision model and scores:
   - semantic intent,
   - temporal coherence,
   - foot contacts,
   - balance/support,
   - deformation integrity,
   - weapon/hand grip,
   - transition continuity,
   - physical plausibility.
5. Hermes updates the persisted review through `POST /api/review`, including model identity, evidence path/hash, criterion verdicts/scores/findings, and summary.
6. ForgeLens displays the audit. `Approve` remains mechanically blocked for animated assets unless the neural verdict is `pass`.

A stable/static sequence is not motion acceptance. Criteria that are not visible must remain `not-evaluated`; they may not be inferred as passes.

## HTTP surface

- `GET /api/catalog` — measured repository GLB catalog and initial asset.
- `GET /api/review?asset=<repo-relative-path>` — normalized persisted review.
- `POST /api/review` — validate and atomically replace a review.
- `POST /api/report` — submit a content-bound human report and issue a receipt.
- `POST /api/report-plan` — persist a receipt-bound task plan only after adversarial verification passes.
- `POST /api/neural-evidence` — validate a PNG data URL, hash it, and persist a contact sheet.
- `GET /file/<percent-encoded-repo-relative-path>` — read-only asset/evidence access.

Path traversal, absolute paths, oversized request bodies, malformed review states, invalid decisions, invalid comment points, unknown neural criteria, and non-PNG neural evidence are rejected.

## Verification

```bash
python3 -m py_compile tools/asset_review.py tools/qa/test_asset_review.py
python3 tools/qa/test_asset_review.py -v
node --check tools/asset_review/app.js
git diff --check -- tools/asset_review.py tools/asset_review tools/qa/test_asset_review.py
```

For live verification, launch with `--no-open`, open the emitted URL, load at least one static and one skinned/animated GLB, exercise camera and pin controls, persist a note, capture neural evidence, and verify the reloaded review.