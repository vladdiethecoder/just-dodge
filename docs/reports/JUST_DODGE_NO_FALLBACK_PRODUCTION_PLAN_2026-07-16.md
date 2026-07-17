# Just Dodge — No-Fallback Production Plan Update

Date: 2026-07-16
Status: active planning update, not a release claim

## User corrections now governing the plan

- Fallback clips and pre-baked animations are strictly forbidden.
- The point of the game is not baked action playback; production motion must come from the MotionBricks interaction stack and deterministic physics.
- Kimodo and ARDY do not have to remain offline-only teachers; they should be integrated where they make sense in the game architecture, while still never becoming baked runtime clip sources.
- The end-of-duel Fight Film must be as intense and cinematic as anime combat, while staying readable and YOMI-first.
- Anime combat clips/images/videos may be gathered and converted into offline teachers, constraints, or training corpora, never runtime presentation assets.
- Current Strike and current motions are not accepted as passing production quality.

## Prior Hermes-session synthesis

Recurring constraints recovered from prior Just Dodge sessions:

1. MotionBricks is the sole production motion engine.
2. ARDY/Kimodo were previously treated as offline planners/teachers; the current correction allows them to be integrated into the game architecture where useful, but never as baked runtime clip sources.
3. No bind-pose fallback, no prebaked action clips, no hidden action bank.
4. Player mode must fail closed instead of silently degrading.
5. The current released MotionBricks checkpoint is not enough by itself; it needs a trained interaction-conditioning extension.
6. R6K hero Strike is only the first proof path, not the final game.
7. The end-of-duel replay is supposed to become a cinematic fight film, not a stop-motion first-person replay.
8. New combat media must enter through provenance-gated offline corpus intake, constraint compilation, and interaction-conditioned training, never through runtime clip wiring.

## Updated production rule

Production combat motion must be synthesized live from:

- intent,
- opponent geometry,
- timing,
- physical state,
- and deterministic 120 Hz physics feedback,

then executed by articulated physics and resolved by deterministic truth.

Kimodo/ARDY may be integrated as planner/proposal systems where they are useful, but their outputs must enter the runtime only through validated, hash-bound plan/packet contracts, never as animation playback.

Offline media may only become:

- teacher trajectories,
- sparse/dense constraints,
- training corpora,
- evaluation fixtures,
- proposal references.

Offline media may never become:

- runtime animation files,
- fallback clips,
- pre-baked action clips,
- runtime pose banks.

## Immediate plan

### P0 — stop treating current Strike/motion as accepted
- Current Strike/motion stack is development evidence, not accepted production motion.
- Motion Frontier Lab remains a falsification surface, not a beauty pass.
- ForgeLens/Motion Lab remains evidence infrastructure, not promotion proof.

### P1 — build an aggressive combat-media intake pipeline
- Gather all high-quality combat clip/image/video sources that can benefit the game, without self-limiting research intake.
- Prefer sources that can support offline analysis of strikes, blocks, dodges, parries, grabs, footwork, guards, counters, and recovery.
- Candidate source classes:
  - anime/film combat clips, images, and videos,
  - sakuga and production reference material,
  - mocap and movement datasets,
  - user-owned media,
  - any other high-quality combat source that can improve MotionBricks conditioning, evaluation, or proposal quality.
- Subagent shortlist now available:
  - Blender Studio `Charge` and `Sintel` are the strongest clear-license combat sources.
  - OpenGameArt CC0/CC-BY assets and the public-domain `Namakura Gatana` are suitable tiny harness sources.
  - Morevna and CC-BY-only Anita rows are conditional candidates.
  - Sakuga-42M and Sakugabooru are research/reference only, not corpus input.

### P2 — convert media into MotionBricks-usable training/constraint data
Primary technical candidates:
- GEM-X / SOMA-X for monocular video pose estimation into SOMA-style 77-joint motion.
- SOMA-X conversion utilities for SMPL/MHR/AMASS to SOMA.
- Kimodo for offline text/constraint-to-motion teacher generation.
- ARDY for offline semantic plan proposals and possible integrated planner/proposal roles where they fit the game architecture.
- MotionBricks interaction extension as the only runtime production path.
- Blender/DCC only for repair, retarget, validation, and evidence.

Integration boundary from repo audit:
- Use provenance-gated corpus intake and constraint compilation, not clip wiring.
- Feed interaction-conditioning training/evaluation, not `assets/motion/*` runtime assets.
- Any future runtime entrance must be packet-only through `NeuralPlanPacketV1` / `MotionPlanPacketV1`.
- Legacy clip/player paths such as baked HeroStrike/Move playback must be removed or gated out of normal Player mode before any no-fallback compliance claim.

### P3 — expand beyond one strike
- R6K Strike remains the first bridge proof, not the endpoint.
- Use gathered media to train/evaluate additional combat arts and moves as intent classes, not animation IDs.
- Required output form: interaction conditioning data, plan references, and evaluation fixtures.
- Forbidden output form: runtime clips or baked libraries.

### P4 — rebuild Fight Film as anime-intense replay
- Keep replay deterministic and truth-isolated.
- Replace stop-motion feel with continuous, directed, chained fight-film presentation.
- Visual target: clear, high-impact anime combat readability, not generic cinematic blur or clutter.
- Must remain presentation-only.

## Current blockers

1. Current motion quality is not accepted by the owner.
2. Released MotionBricks checkpoint still lacks the required interaction-conditioning semantics.
3. No production-cleared broad combat media corpus is assembled yet.
4. No validated media-to-motion pipeline is installed as a repo workflow yet.
5. No anime-intense Fight Film quality pass exists yet.
6. Packaging/media/human evidence gates remain open.

## Next atomic units

1. `ANIME-COMBAT-MEDIA-INTAKE-001`
   - gather source inventory, rights matrix, and toolchain matrix.

2. `MEDIA-CORPUS-ABI-V1`
   - define and validate a strict per-sequence manifest for licensed media intake.

3. `MEDIA-TO-CONSTRAINT-COMPILER-V1`
   - convert admitted fitted sequences into canonical semantic constraints, not frame arrays.

4. `INTERACTION-DATASET-V1`
   - join compiled constraints with physical-state snapshots into interaction-conditioning training/evaluation data.

5. `INTERACTION-EXTENSION-CONFORMANCE`
   - prove a root+pose MotionBricks extension actually consumes interaction channels.

6. `PACKET-ONLY-RUNTIME-ADAPTER`
   - only after the model gate passes, connect output through validated plan/packet contracts.

7. `REMOVE-LEGACY-CLIP-PLAYER-PATH`
   - remove or gate baked HeroStrike/Move playback out of normal Player mode.

8. `FIGHT-FILM-ANIME-READABILITY-001`
   - define and test the first anime-clear replay presentation pass.

## Hard rule

If a candidate path ends in baked runtime animation, it is the wrong path.
