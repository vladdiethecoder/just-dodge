# M3 Motion Gate — 2026-07-13

## Decision

**Do not wire retargeted action frames into `App::current_pose()`.**

The G1→armored-duelist transport is numerically valid, but the available action source does not meet the semantic/readability gate. Retaining the existing bind-pose runtime path is deliberate; it is not an action-motion fallback.

## Implemented transport boundary

| Unit | Commit | Result |
|---|---|---|
| M3 motion request contract | `4d6a015` | Public snapshot → deterministic request; hidden Plan/Commit intent produces no request. |
| Fail-closed source cache | `0b971fa` | ONNX/NPY artifacts plus measured G1 source clips validated; unsupported actions reject rather than bind-fallback. The motion-service integration suite is serialized and passed 10 consecutive runs. |
| Armored 24-bone retarget | `0e5a29a` | `Hips`-rooted armored hierarchy accepts 24 finite, positive-determinant skin matrices and deterministic pose receipts for all source frames. |

`RUSTFLAGS='-Dwarnings' cargo test --locked --all-targets` passed at `0e5a29a`:

- 85 library tests
- 93 game-binary tests
- 1 official MotionBricks integration test
- 1 serialized motion-service integration test

Retarget output is exercised only by `src/bin/shot.rs` QA through `JUSTDODGE_QA_ACTION={strike,block,grab}`. It is not part of normal gameplay yet.

## Source-readability failure

The source library defines four-frame primitive windows (`assets/data/primitives.ron`). The three action-QA runs selected source frame 2/4:

| Label | Pose receipt | Front-frame SHA-256 | Observed result |
|---|---:|---|---|
| Strike | `f208733e7abcd092` | `2d7bce1e7a8a258d324698b4dc44a9b38404bd4f02a6f3fbe3d8ad7e66b6d165` | Mesh remains coherent, but this is an unarmed raised-arm gesture; no sword arc or clear strike tell. |
| Block | `1bfee7695a6579f7` | `94a4a9dacc0e9c514231fafa236c3338d828b347a5338cf000241f40e3f85d81` | Mesh remains coherent, but both arms form a near-T pose; not a defensive guard. |
| Grab | `5d9671e7ff7f050d` | `0e0894d9fc551519b3e359ac594ad9f06435791c0c98c338986a6a5e4ff5895b` | Mesh remains coherent, but both arms are laterally spread; no torso-directed grab tell. |

Logs: `qa_runs/m3_contact_truth_001/b13_retarget/shot_{strike,block,grab}.log`.

This falsifies the current primitive source as a player-visible three-action source. No mesh collapse, limb inversion, or armor separation was observed; semantic failure is the blocker.

## Primary replacement path and reproduced blocker

The repository already contains a provenance-preserving neural authoring path:

1. `tools/kimodo_generate.py` produces G1 action candidates from `tools/data/kimodo_prompts.json`.
2. `tools/encode_primitives.py` transforms an admitted G1 candidate into a normalized four-frame MotionBricks primitive.
3. MotionBricks remains the runtime source-cache and retarget substrate.

Discovery passed:

- `kimodo_gen` exists at `/home/vdubrov/.local/bin/kimodo_gen` and detects `cuda:0`.
- `python3 tools/kimodo_generate.py --dry-run --out-dir /tmp/kimodo_probe` expands exact Strike/Block/Grab candidates.
- The official MotionBricks README and project page confirm the released preview’s public interface focuses on navigation/smart-object controls and custom-data authoring; the repository’s `generate_official_navigation_clip` explicitly has no combat-action conditioning.

Actual source generation stopped before producing a candidate:

```text
kimodo_gen 'two handed overhead longsword strike downward, planted feet' \
  --model Kimodo-G1-SEED-v1 --duration 1.2 --num_samples 1 \
  --seed 20260709 --output qa_runs/m3_contact_truth_001/b14_readability/kimodo_candidates/strike_00
```

Observed failure in `qa_runs/m3_contact_truth_001/b14_readability/kimodo_candidates/strike_00.log`:

1. configured remote text-encoder service: connection refused;
2. fallback local LLM2Vec encoder attempted `meta-llama/Meta-Llama-3-8B-Instruct`;
3. Hugging Face returned `401 GatedRepoError` because the local account lacks authorization.

No neural candidate was admitted, encoded, committed, or promoted.

## Exact owner action

Approve access to `meta-llama/Meta-Llama-3-8B-Instruct` for the local Hugging Face account, then authenticate locally with `huggingface-cli login`. Do not send a token in chat and do not commit it.

After local authorization, the next run is the same deterministic Kimodo command above for Strike, Block, and Grab. Each candidate must then pass G1 topology/continuity, 24-bone retarget, eight-frame visual tell, weapon-socket, and replay-receipt gates before runtime promotion.
