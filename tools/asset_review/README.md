# ForgeLens

ForgeLens is Just Dodge's local browser gate for reviewing 3D assets, environment/world models, and animated GLB artifacts. It does not mutate source assets and adds no project dependency.

## Launch

From the repository root:

```bash
python3 tools/asset_review.py
python3 tools/asset_review.py --asset assets/source/meshy/w0_sword/assembled_001/model.glb
python3 tools/asset_review.py --asset assets/source/meshy/c0_armored_duelist_001/model.glb --port 4177 --no-open
python3 tools/asset_review.py --review-run-declaration docs/reports/my_review_run.json
python3 tools/asset_review.py --import-human-decision <run-id> docs/reports/human_decisions/<decision>.json
python3 tools/asset_review.py --motion-lab tools/qa/forgelens_motion_lab_example.json --no-open
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

## Motion Lab (fail closed)

`--motion-lab <repository-relative-json>` enables the diagnostic Motion Lab. If it is omitted, `GET /api/motion-lab` returns 404; ForgeLens never invents a Kimodo, ARDY, MotionBricks, or physics payload. The configured file must be a regular, non-symlink repository file under 1 MiB with strict duplicate-key/non-finite JSON rejection. Its exact source SHA-256 and bytes are returned with every snapshot; a changed source or an event chain bound to old bytes fails closed.

The `forgelens.motion-lab/v1` payload contains a fixed 1–240 Hz, bounded-frame timeline with five tracks (`text`, `fullBody`, `root`, `endEffectors`, `contacts`), exactly four synchronized ordered views (`kimodo-teacher`, `ardy-proposal`, `motionbricks-target`, `physics-execution`), two or more candidates, and same-length finite series for `fkResidual`, `footDrift`, `com`, `grip`, and `weaponPath`. The included `tools/qa/forgelens_motion_lab_example.json` is a schema/example payload, not provider evidence.

The UI renders draggable timeline pins, synchronized view cards, side-by-side candidate selection with a root-difference overlay, five compact plots, and append-only annotations bound to payload revision, source SHA, frame, joint, object, and world-space point. `POST /api/motion-lab-annotation` accepts only `annotation` receipts; `reviewerKind` may be `human`, `api`, or `inkling`, but it cannot carry approve/reject/request-change. API and Inkling reviewers therefore can annotate only.

Human outcomes are intentionally unavailable over HTTP. An external operator may append a `forgelens.motion-lab-human-event/v1` record with:

```bash
python3 tools/asset_review.py \
  --motion-lab tools/qa/forgelens_motion_lab_example.json \
  --import-motion-lab-human-event docs/reports/my_motion_lab_human_event.json \
  --no-open
```

The imported record binds `motionLabId`, revision, source SHA-256, reviewer pseudonym, action (`approved`, `rejected`, or `changes-requested`), comment, timestamp, and the exact statement: `I independently reviewed this exact Motion Lab payload; this outcome does not approve a ReviewRun.` Automation/API/Inkling/Hermes identities are rejected for this import. These receipts are append-only under `qa_runs/asset_reviews/motion_lab/<id>/events/` and are explicitly **not** ReviewRun transitions, terminal passes, or substitutes for the existing tracked-clean external-human ReviewRun decision path.

## Immutable ReviewRun admission spine

The versioned spine is independent from the legacy editable review JSON. Its schemas are defined by `docs/reports/FORGELENS_PHASE_A_READINESS_CONTRACT.json` under `review_spine_contract`:

- `forgelens.review-run-declaration/v1` declares `workflowRevision`, build/replay/verifier/canonical-plan/evidence-manifest/provider/checkpoint/retarget/geometry paths, measured truth hash, camera/AOV inventories, produced artifacts, required evidence, and source-author pseudonyms.
- `forgelens.review-run/v1` measures every declared file into exact path/SHA-256/byte/repository-state lineage, executes the contract-allowlisted verifier against the bound replay, stores its bounded truth receipt, validates camera/AOV/evidence inventories against `forgelens.canonical-plan/v1`, and carries a content-derived run fingerprint.
- `forgelens.evidence-manifest/v1` binds each PNG SHA-256/byte count, measured dimensions, camera/AOV/timing identity, and capture rectangle. `fullFrame`/`uncropped` are server-derived only when the PNG and capture rectangle exactly equal the canonical-plan camera dimensions; client booleans are rejected.
- `forgelens.decision-receipt/v1` is an append-only, SHA-256-linked transition receipt. Allowed states are `awaiting_evidence -> awaiting_human -> submitted -> pass|fail`; `superseded` and `expired` are terminal exits. Terminal receipts cannot be edited or extended. A `submitted` receipt binds both the sorted current ReviewPin heads and the server-side viewer-context generation.
- `forgelens.review-pin/v1` binds revision, artifact, workflow, canonical plan, geometry, frame/tick/substep, camera/AOV, screen point, world ray or point/normal, semantic IDs, severity/category/author, timestamps, status, and resolution revision. A pin survives an AOV change only when the camera and declared geometry-compatibility group match; otherwise it is `stale` and blocks submission/pass.
- `forgelens.admission-packet/v1` exports the run manifest, complete decision chain, current pins and pin history, and fail-closed eligibility result under `docs/reports/forgelens_review_runs/<run-id>/exports/`.

Canonical objects are UTF-8 JSON with sorted keys and compact separators. A decision receipt hash is SHA-256 over the canonical receipt with `receiptSha256` omitted; pin receipts use the same rule with `pinReceiptSha256` omitted. Immutable files are fsynced and linked without replacement. The decision tip is duplicated into fsynced `head.json` and `head.witness.json`: a missing/stale witness is repaired forward from the receipt chain, while a witness ahead of a missing tail fails closed. A store-wide `flock` serializes writers and a process-lifetime lock rejects a second ForgeLens server on the same store.

`pass` eligibility remeasures every bound lineage file, reruns the measured verifier executable through its already-open file descriptor, and fails closed unless the recorded revision is a full reachable commit, code and every declared input are tracked-clean, all required camera/AOV evidence is canonically full-frame, viewer support is exact, the server-side viewer context is stable, and no pin is stale. Draft runs may bind dirty or outside-git inputs, but they cannot pass.

Submitting a blind human attestation requires the exact text, a reviewer pseudonym that is neither a known automation identity nor a source author, explicit authorship exclusion, and timestamps proving blind observation preceded label reveal and decision. The server persists the browser-session actor separately. Browser/HTTP authority can never emit terminal `pass`; final approval requires a separate tracked-clean `forgelens.external-human-decision/v1` file imported by an external operator with `--import-human-decision RUN_ID PATH`. The pass receipt binds that file, its SHA-256, and its commit; every later load requires those committed bytes and commit ancestry to remain recoverable. This remains operational attestation, not cryptographic proof of personhood.

When a ReviewRun is active, the **ReviewRun gate** presents the immutable chain head and only the browser-authorized exits: `Fail ReviewRun` from `submitted`, and `Supersede ReviewRun` before a terminal state. Both require a human-entered reason, compare against the displayed receipt head, append a hash-bound receipt, and reload the server snapshot. The UI intentionally has no browser `pass` control; pass remains the external tracked-clean human-decision import described above.

## Viewer eligibility and invalidation

ForgeLens reports `viewer_unsupported` and refuses visual approximation for sparse accessors, CUBICSPLINE animation, morph targets/weight animation, non-triangle primitive modes, external image URIs, texture decode/upload failure, or any `extensionsRequired` entry. The dependency-free server validates embedded/data-URI PNG bytes; image formats it cannot validate independently remain fail-closed. Unsupported artifacts remain available as lineage records but their visual evidence is not pass-eligible and the UI disables approval/submission.

`webglcontextlost` immediately appends a server-side viewer-context receipt and invalidates current viewport evidence. Restoration appends `recapture_required`; only a subsequent PNG that passes bounded CRC/decompression/dimension validation is stored content-addressed and permits `recaptured` for the same incremented generation. Submission binds that immutable viewer-context head and capture identity. The UI displays ReviewRun state, lineage, pins, and every mechanical blocker when launched with `--review-run-declaration`.

## Human report handoff

The top-level **Submit report** action sends the current decision, summary, checklist, comments, spatial pins, and neural-gate context to `POST /api/report`. The server persists a content-bound receipt, emits `FORGELENS_REPORT_SUBMITTED=...`, and the review window requests closure after a successful response. Any later human edit invalidates the stale receipt.

This legacy editable report is planning input, not a ReviewRun admission decision and never constitutes terminal `pass`.

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

- `GET /api/session` — server-derived loopback browser actor, CSRF token, and expiry.
- `GET /api/catalog` — measured repository GLB catalog and initial asset.
- `GET /api/motion-lab` — configured immutable-source Motion Lab snapshot; 404 fail-closed when `--motion-lab` was omitted.
- `GET /api/active-review-run` — active immutable ReviewRun snapshot or `null`.
- `GET /api/review-run?runId=<id>` — exact manifest, receipt chain, pins, and eligibility.
- `GET /api/review?asset=<repo-relative-path>` — normalized persisted review.
- `POST /api/review` — validate and atomically replace a review.
- `POST /api/report` — submit a content-bound human report and issue a receipt.
- `POST /api/report-plan` — persist a receipt-bound task plan only after adversarial verification passes.
- `POST /api/motion-lab-annotation` — append an annotation receipt only; no action/approval field is accepted.
- `POST /api/neural-evidence` — validate a PNG data URL, hash it, and persist a contact sheet.
- `POST /api/review-run` — measure a declaration and create its immutable manifest/initial receipt.
- `POST /api/review-pin` — append a content-bound pin version before submission.
- `POST /api/viewer-context` — append `context_lost`, `context_restored`, or `recaptured` to the server-side visual-evidence generation.
- `POST /api/review-run-transition` — compare-and-append one allowed non-pass transition using `expectedPreviousSha256`; the server derives pin revision/artifact/plan/geometry/frame/60-Hz/120-Hz/camera/AOV context and rejects client-supplied pin identity.
- `POST /api/review-run-export` — write a content-addressed admission packet.
- `GET /file/<percent-encoded-repo-relative-path>` — read only non-symlink bytes whose SHA-256 and byte count still match one non-conflicting immutable catalog/ReviewRun identity.

Every mutation requires the loopback Host and Origin, HttpOnly SameSite session cookie, CSRF token, `Content-Type: application/json`, unsigned `Content-Length`, strict UTF-8 JSON without duplicate keys, and a bounded body. JSON is limited to 1 MiB; encoded neural evidence to 24 MiB; socket I/O times out after 10 seconds. Oversize is HTTP 413, wrong media type 415, malformed/schema/path input 400, stale identity or transition conflicts 409, expired authority 401, and unauthorized file access 403. Replay verification opens the non-symlink verifier and replay, hashes/allowlists the verifier and measures the replay, executes both through `/proc/self/fd/<fd>`, and rechecks inode/stat identity after execution; it has a 30-second timeout and combined 256 KiB output cap, and timeout/output-cap termination kills the process group.

## Verification

```bash
cargo build --release --bin m3_match
python3 -m py_compile tools/asset_review.py tools/qa/test_asset_review.py tools/qa/validate_forgelens_review_run.py tools/qa/test_forgelens_review_run_schema.py tools/qa/verify_forgelens_phase_a.py
python3 tools/qa/test_asset_review.py -v
python3 tools/qa/test_forgelens_review_run_schema.py
python3 tools/qa/verify_forgelens_phase_a.py
node --check tools/asset_review/app.js
git diff --check -- tools/asset_review.py tools/asset_review tools/qa/test_asset_review.py tools/qa/forgelens_review_run_v1.schema.json tools/qa/validate_forgelens_review_run.py tools/qa/test_forgelens_review_run_schema.py tools/qa/verify_forgelens_phase_a.py docs/reports/FORGELENS_PHASE_A_READINESS_CONTRACT.json
```

For live verification, launch with `--no-open`, open the emitted URL, load at least one static and one skinned/animated GLB, exercise camera and pin controls, persist a note, capture neural evidence, and verify the reloaded review.