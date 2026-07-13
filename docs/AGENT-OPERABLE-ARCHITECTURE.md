# Agent-Operable Application Architecture — Just Dodge

This document collects research-backed schemas, tradeoffs, failure modes, and verification procedures for making a game (or similar interactive application) operable by software agents. It is focused on the patterns needed for headless execution, JSON/NDJSON control, deterministic simulation, replay, input synthesis, RL-style interfaces, fast-forward evaluation, and benchmarking.

## 1. Summary of What We Need

The parent task describes a video-presenter-like runtime that:
- Runs the full game headlessly.
- Speaks a JSON/NDJSON control protocol.
- Sends mouse/events and records outputs.
- Replays interactions.
- Executes ~40k fixed-dt frames/s so agents can play 1,000 games.

This is not a single protocol; it is a stack of tightly coupled guarantees:
1. **Control protocol** — how an agent talks to the runtime.
2. **Headless execution** — no window/GPU required for simulation.
3. **Event sourcing / replay log** — reproducible state reconstruction.
4. **Deterministic simulation** — same input, same state, same hash.
5. **Input synthesis** — agents inject inputs exactly like human inputs.
6. **RL interface** — Gymnasium/PettingZoo-style `reset/step/render/close`.
7. **Fast-forward** — thousands of steps per second, possibly many envs in parallel.
8. **Benchmarking** — repeatable metrics, regression detection, golden replays.

---

## 2. Control Protocol: JSON/NDJSON

### 2.1 Why NDJSON

The NDJSON spec (github.com/ndjson/ndjson-spec) is the simplest framing for a stream protocol:
- One JSON object per line, terminated by `\n`.
- UTF-8 only.
- Lines MUST NOT contain newlines or carriage returns inside the JSON text.
- MIME type `application/x-ndjson`, extension `.ndjson`.

NDJSON is ideal for stdin/stdout or TCP streaming because:
- No length prefix needed; newline is the delimiter.
- Parser can stream line-by-line.
- Easy to append to a log file.
- One corrupted line does not invalidate the whole stream.

### 2.2 Recommended Protocol Shape

Use a JSON-RPC 2.0–like request/response envelope (jsonrpc.org/specification) but constrained to NDJSON:

```json
{"jsonrpc":"2.0","id":1,"method":"env.reset","params":{"seed":123,"headless":true}}
```

Response:
```json
{"jsonrpc":"2.0","id":1,"result":{"obs":{"frame":0,"phase":"Observe"},"info":{"ruleset_hash":"abc..."}}}
```

Methods to expose:

| Method | Params | Returns |
|--------|--------|---------|
| `env.reset` | `seed`, `options` | `obs`, `info` |
| `env.step` | `action` | `obs`, `reward`, `terminated`, `truncated`, `info` |
| `env.render` | `mode` (rgb_array, state, none) | `frame` or `bytes` |
| `env.close` | — | ok |
| `replay.load` | `path` | ok |
| `replay.save` | `path` | ok |
| `sim.fast_forward` | `frames` or `target_frame` | obs at target |
| `sim.hash` | — | `truth_hash` |
| `input.inject` | `events[]` | ok |

Notifications (`id` omitted) can be used for streaming observations or logs without requiring a response.

### 2.3 Command/Event Log

For replay, store the **input commands** the agent sent, not just the resulting observations. This is command sourcing (gist.github.com/eulerfx/11227933). Command sourcing is a specialization of event sourcing where the persisted facts are the user's/intent inputs; replay re-runs the deterministic apply function:

```text
State = fold(apply, initial_state, command_log)
```

The `apply` function must be deterministic. The log entry should contain:

```json
{"frame":120,"source":"agent","player_id":0,"command":"select_action","args":{"action":"Strike"}}
```

---

## 3. Headless Execution

### 3.1 Definition

Headless means the simulation produces correct state without:
- Creating a window.
- Creating a GPU surface/swapchain.
- Loading visual-only assets (optional but useful).
- Playing audio.
- Running presentation-only systems.

### 3.2 Architecture Split

From Just Dodge's own architecture docs, the platform shell must be split from combat truth:

```text
┌────────────────────────────────────────┐
│ Platform Shell (window/GPU/audio)      │
├────────────────────────────────────────┤
│ Input normalization                    │
├────────────────────────────────────────┤
│ Combat Truth (fixed-step, deterministic)│
├────────────────────────────────────────┤
│ Presentation bridge (optional)         │
├────────────────────────────────────────┤
│ Renderer (optional)                    │
└────────────────────────────────────────┘
```

Headless mode bypasses the bottom two layers entirely. The same `fixed_tick(dt)` path is used; only rendering is skipped.

### 3.3 Headless Tradeoffs

| Pros | Cons |
|------|------|
| Runs on CI/servers without GPU | Cannot verify visual readability |
| 10-1000× faster for bulk rollouts | Bugs in renderer-only code not caught |
| Determinism easier without GPU timing | Agent training on pixels requires render path |
| Enables exact replay validation | Input latency/frame pacing differ from interactive mode |

### 3.4 Failure Modes

- **Silent desync**: headless and headed runs diverge because RNG branch depends on render state. Fix: never branch on render state in truth code.
- **Missing validation**: headless replay passes but game crashes in windowed mode. Fix: run a small headed smoke test for every build.
- **Asset format mismatch**: headless skips loading visual assets and misses corrupt meshes. Fix: keep a lightweight asset validation path.

---

## 4. Event Sourcing / Replay Logs

### 4.1 Event-Sourcing Pattern

Per Microsoft Learn and Martin Fowler, event sourcing persists state changes as an append-only log of events. The current state is derived by replaying events. Key properties:
- Events are immutable.
- Append-only writes avoid lock contention.
- Full audit trail.
- State can be rebuilt to any point in time.
- Snapshots are an optimization, not the source of truth.

For games, the canonical source of truth is the **command/input log + initial seed + ruleset version**.

### 4.2 Replay Log Schema

```json
{
  "header": {
    "version": 1,
    "build_id": "git:abc123",
    "ruleset_hash": "sha256:...",
    "asset_manifest_hash": "sha256:...",
    "initial_seed": 123456,
    "dt": 0.0166667,
    "fps": 60
  },
  "inputs": [
    {"frame": 0, "player_id": 0, "kind": "SelectAction", "action": "Strike"},
    {"frame": 0, "player_id": 0, "kind": "SelectStance", "stance": "Top"},
    {"frame": 1, "player_id": 0, "kind": "Commit"}
  ],
  "events": [
    {"frame": 60, "kind": "PhaseChange", "from": "Reveal", "to": "Resolve"},
    {"frame": 60, "kind": "Contact", "point": [0.1, 1.2, 0.3]}
  ]
}
```

Just Dodge already has a binary replay format in `src/replay.rs` (`JDRP` magic + postcard payload). This is good for compactness; an NDJSON mirror is better for human inspection and agent tooling.

### 4.3 Replay Verification Procedure

1. Record a replay from a human/agent run.
2. Replay the command log in a fresh headless instance with the same seed.
3. Compare `truth_hash` at every recorded frame.
4. Require bit-exact equality for the hash sequence.
5. Golden replays are checked into `tests/golden_replays/` and fail CI on mismatch.

---

## 5. Deterministic Simulation

### 5.1 Requirements

Determinism means the same sequence of inputs and seed always produces the same sequence of states. Requirements:
- Fixed timestep (Glenn Fiedler, "Fix Your Timestep!").
- Seeded RNG, stable algorithm (e.g., `rand_xoshiro::Xoshiro256PlusPlus`).
- No `HashMap` iteration order in serialized output; use `BTreeMap` or sort.
- No `f32` branching on near-equal values unless carefully controlled.
- No dependency on wall-clock time inside truth code.
- Same compiler/version for reproducibility (document toolchain).

### 5.2 Just Dodge Current State

- `src/truth.rs` already has `fixed_tick(dt)` and `truth_hash()`.
- `src/ai.rs` uses `Xoshiro256PlusPlus` and is seeded.
- `src/replay.rs` stores per-frame truth hash.
- Binary replay has versioned header.

Gaps:
- `fixed_tick(dt)` uses `dt * 60.0` rounded to frames; wall-clock dt can cause frame count variation. Headless protocol should specify exact frame counts, not real dt.
- `f32` health/stamina equality compares `to_bits()`, which is correct but must be maintained across all float fields.
- Need a canonical state hash that excludes presentation-only data.

### 5.3 Verification Procedure

1. Run identical command log twice.
2. Assert `truth_hash` sequence is identical.
3. Run once headed, once headless; assert hashes match.
4. Run on two different machines with same build; assert hashes match.
5. Golden test: a known input log must produce a known final hash.

---

## 6. Input Synthesis

### 6.1 Principle

Agent inputs must be indistinguishable from human inputs at the combat-truth boundary. The agent does not "press" a key; it emits a frame-stamped command:

```json
{"frame":42,"player_id":0,"command":"SelectAction","args":{"action":"Block"}}
```

This is the same object that would be produced by a human input mapper after collecting key events.

### 6.2 Input Sources

All sources should normalize to the same `InputEvent` type:
- HumanLocal
- AI
- Replay
- NetworkRemote
- TestAgent

### 6.3 Synthesis Failure Modes

- **Frame drift**: agent sends input for frame N but it is applied at N+1. Fix: protocol confirms the frame the input was applied to.
- **Impossible inputs**: agent selects an action while in Resolve phase. Fix: server rejects invalid inputs and returns an error; agent must observe phase before acting.
- **Hidden-state cheating**: agent reads internal state it shouldn't see. Fix: observations only expose allowed fields.

---

## 7. RL Interface (Gymnasium / PettingZoo)

### 7.1 Gymnasium Single-Agent API

The standard API (gymnasium.farama.org/api/env):

```python
obs, info = env.reset(seed=123)
obs, reward, terminated, truncated, info = env.step(action)
env.close()
```

Attributes:
- `action_space: Space[ActType]`
- `observation_space: Space[ObsType]`
- `metadata`, `render_mode`

For Just Dodge, a single-agent wrapper would treat the opponent as part of the environment:

```python
obs = {"phase": "Plan", "my_health": 100.0, "opponent_health": 100.0}
action = 0  # discrete action index
obs, reward, terminated, truncated, info = env.step(action)
```

### 7.2 PettingZoo Multi-Agent APIs

PettingZoo (pettingzoo.farama.org) provides two APIs:
- **AEC (Agent Environment Cycle)**: agents step sequentially; natural for turn-based games.
- **Parallel**: all agents step simultaneously; returns dicts keyed by agent ID.

For a simultaneous-reveal duel, the **Parallel API** is the natural fit:

```python
from pettingzoo import ParallelEnv
observations, infos = env.reset(seed=42)
while env.agents:
    actions = {agent: policy(observations[agent]) for agent in env.agents}
    observations, rewards, terminations, truncations, infos = env.step(actions)
```

Just Dodge is two-player, so either:
- Wrap as a single-agent Gymnasium env with the opponent as internal AI, or
- Expose both players as a PettingZoo ParallelEnv.

### 7.3 Vectorized Environments

Gymnasium `VectorEnv` (gymnasium.farama.org/api/vector) runs N independent copies in parallel and batches observations/rewards. Required for training at scale:

```python
envs = gym.make_vec("JustDodge-v0", num_envs=64, vectorization_mode="sync")
obs, infos = envs.reset(seed=123)
actions = envs.action_space.sample()
obs, rewards, terminations, truncations, infos = envs.step(actions)
```

For ~40k frames/s with 1,000 games, vectorization or native batching is essential. The Rust runtime can expose a batch step method over NDJSON:

```json
{"jsonrpc":"2.0","id":7,"method":"env.step_batch","params":{"actions":[0,1,2,...]}}
```

### 7.4 Observation / Action Space Schema

Observation (JSON):
```json
{
  "frame": 120,
  "phase": "Plan",
  "phase_frame": 15,
  "my": {"health": 0.85, "stamina": 0.72, "committed": false, "stance": "Top"},
  "opponent": {"health": 0.90, "stamina": 0.80, "committed": false, "stance": "Top"},
  "last_result": null,
  "legal_actions": [0,1,2,3,4]
}
```

Action (JSON):
```json
{"action": 0, "stance": 1}
```

or for raw input events:
```json
{"events":[{"frame":120,"command":"SelectAction","args":{"action":"Strike"}}]}
```

---

## 8. Fast-Forward Simulation

### 8.1 Goal

Run many games quickly without rendering, without waiting for real time. The 40k frames/s target means each frame must take ≤25 µs on average.

### 8.2 Techniques

- **Headless, no GPU**: avoid surface present entirely.
- **Fixed dt with integer frame counts**: simulate N frames per batch step.
- **Skip intermediate observations**: return only the final state after N frames unless requested.
- **Parallel envs**: use `SyncVectorEnv` or async subprocess workers; or native batching inside the Rust runtime.
- **No allocation hot path**: pre-allocate observation buffers, reuse RNG state.
- **State snapshots**: allow fast reset by loading a snapshot instead of reinitializing from scratch.

### 8.3 Fast-Forward Protocol

```json
{"jsonrpc":"2.0","id":8,"method":"sim.fast_forward","params":{"frames":180,"inputs":[...]}}
```

Response:
```json
{"jsonrpc":"2.0","id":8,"result":{"final_frame":180,"obs":{...},"truth_hash":"0x..."}}
```

### 8.4 Failure Modes

- **Non-deterministic frame counts**: using real dt can make fast-forward produce different states than interactive play. Fix: simulate by exact frame counts.
- **Memory blow-up**: creating a new env per rollout. Fix: reset-in-place and snapshot reset.
- **Observation skipping hides bugs**: agent only sees final state. Fix: keep a truth-hash trace for replay validation.

---

## 9. Game Agent Benchmarking

### 9.1 Benchmark Requirements

A benchmark must be:
- **Repeatable**: same agent, same seed, same result.
- **Comparable**: scalar metrics that summarize performance.
- **Inspectable**: replays and logs for failed runs.
- **Regression-resistant**: golden replays detect when the environment changes.

### 9.2 Metrics

| Metric | How |
|--------|-----|
| Win rate | games won / total games |
| Average reward per episode | sum rewards / episodes |
| Action distribution | histogram over actions |
| Match length | mean/median frames to termination |
| Determinism score | hash match across replay reruns |
| Coverage | % of action matrix cells exercised |
| Strategy adaptation | win rate vs different AI personalities |

### 9.3 Benchmark Protocol

1. Define a ruleset version and asset manifest hash.
2. Fix seeds for environment and agent.
3. Run N episodes headless.
4. Record command logs and truth hashes.
5. Compute metrics.
6. Compare against a baseline (random agent, heuristic agent, previous agent).
7. Re-run golden replays to confirm environment stability.

### 9.4 Arcade Learning Environment (ALE) as Reference

ALE (ale.farama.org) is the canonical game-agent benchmark. Its C++ interface is simple:

```cpp
ale::ALEInterface ale;
ale.setInt("random_seed", 123);
ale.loadROM("asterix.bin");
while (!ale.game_over()) {
    float reward = ale.act(action);
}
```

Key ideas to borrow:
- ROM/ruleset versioning.
- Minimal action set vs. legal action set.
- Standardized evaluation protocols (e.g., sticky actions, frame skipping).
- Deterministic seeds for reproducibility.

For Just Dodge, the equivalent is:
- A "ruleset ROM" (the action matrix + timing RON).
- `env.reset(seed)`, `env.step(action)`, `env.match_over()`.
- A minimal action set and a legal action set.

---

## 10. Recommended Just Dodge Implementation Path

### Phase A: Headless Runtime
1. Add `--headless` CLI flag.
2. Skip window, surface, renderer, audio initialization.
3. Keep `fixed_tick` path intact.
4. Add NDJSON stdin/stdout control loop.
5. Expose `env.reset`, `env.step`, `env.render(state)`, `env.close`, `sim.hash`, `replay.load`, `replay.save`.

### Phase B: Determinism Hardening
1. Replace `fixed_tick(dt)` with `step_frames(n)` for headless protocol.
2. Audit all float fields for `to_bits()` equality.
3. Use deterministic `BTreeMap`/`Vec` ordering everywhere state is hashed.
4. Add golden replay tests in CI.

### Phase C: RL Wrappers
1. Implement a Gymnasium `Env` wrapper in Python that speaks NDJSON to the Rust process.
2. Implement PettingZoo `ParallelEnv` wrapper.
3. Implement `VectorEnv` wrapper (sync or async).

### Phase D: Fast-Forward / Batch
1. Add `env.step_batch` to the Rust protocol.
2. Add `sim.fast_forward`.
3. Benchmark frames/s on 1, 8, 64 parallel envs.

### Phase E: Benchmark Harness
1. Define baseline agents: random, heuristic, AI personality mirror.
2. Run 1,000-game benchmark with fixed seeds.
3. Output metrics JSON and golden replay set.
4. Add CI check that golden replays still hash-match.

---

## 11. Failure Modes and Mitigations

| Failure | Cause | Mitigation |
|---------|-------|------------|
| Replay hash mismatch | RNG branch on render state | Split truth/presentation |
| Headless faster but different | Frame count from real dt | Use integer frame steps |
| Agent crashes env | Invalid action sent | Validate and reject with error |
| NDJSON parser loses sync | Embedded newline in JSON | Reject inputs containing `\n` |
| Golden replay breaks after code change | Intentional rule change | Version ruleset, update golden files |
| Floating-point divergence across CPUs | f32 math order | Use fixed-point or stable ordering; hash only gameplay-relevant bits |
| Observation too large | Full world state exposed | Provide structured, bounded observation |
| Agent overfits to deterministic AI | No stochasticity option | Support resampling seeds per episode |
| Benchmark noise | OS scheduling | Run multiple seeds, report mean/std |
| Visual bugs not caught headless | Missing render path | Run visual QA subset with renderer enabled |

---

## 12. Verification Checklist

- [ ] Headless binary starts and accepts NDJSON commands.
- [ ] `env.reset(seed)` returns the same initial `truth_hash` every time.
- [ ] `env.step` returns `obs, reward, terminated, truncated, info` matching Gymnasium shape.
- [ ] A recorded command log replayed headless produces identical `truth_hash` sequence.
- [ ] Headless and headed runs with the same inputs produce identical `truth_hash` sequence.
- [ ] 1,000 episodes complete without crash.
- [ ] Frames/s target measured and reported.
- [ ] Golden replay files pass on CI.
- [ ] Random, heuristic, and trained agents produce distinguishable metrics.
- [ ] Visual QA subset passes with renderer enabled.

---

## 13. References

- NDJSON spec: https://github.com/ndjson/ndjson-spec
- JSON-RPC 2.0: https://www.jsonrpc.org/specification
- Gymnasium Env API: https://gymnasium.farama.org/api/env/
- Gymnasium Vector API: https://gymnasium.farama.org/api/vector/
- PettingZoo AEC API: https://pettingzoo.farama.org/api/aec/
- PettingZoo Parallel API: https://pettingzoo.farama.org/api/parallel/
- PettingZoo paper: https://arxiv.org/abs/2009.14471
- ALE C++ interface: https://ale.farama.org/main/cpp-interface/
- Event Sourcing (Fowler): https://martinfowler.com/eaaDev/EventSourcing.html
- Event Sourcing (Azure): https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
- Command Sourcing vs Event Sourcing: https://gist.github.com/eulerfx/11227933
- "Fix Your Timestep!" (Gaffer on Games): industry-standard fixed-timestep reference
