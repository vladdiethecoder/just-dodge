# YOMI Hustle deterministic preview/replay reference — 2026-07-15

Scope: architecture evidence for Just Dodge from the user's owned Steam build of *Your Only Move Is HUSTLE* (App ID 2212330, build 23959498). No recovered code or assets are included here.

Local reconstruction evidence:

`/run/media/vdubrov/NVMe-Storage1/Just-Dodge-Reconstruction/yomi-hustle/Phase_2/project_blueprint.md`

## Verified reconstruction

- Godot PCK SHA-256: `9466f7e4fefb3232ce99847df2d096e28dc14dcaf963ea9b111b935516bbf566`
- Native Rust deterministic library SHA-256: `edd2e7e91d70a0c52c182d0f68f46a6cde9953607603e4decdb60dcd95fe957e`
- PCK format 1, Godot 3.5.1, 5,452 entries.
- A selective parser extracted 858 script/text resources with per-entry MD5 verification.
- GDRETools v2.6.0-beta.4 recovered 502/502 GDScript bytecode files with zero failures and zero lossy conversions.
- `tbfg.so` contains Rust debug information and 2,247 defined symbols. Its registered native APIs expose fixed-point vector math plus position, velocity, facing, grounded state, friction, gravity, speed limits, pushback, relative forces, snap-to-ground, and state copying.

## Transferable architecture

### Provisional choice → preview → explicit commit

The recovered action UI derives currently legal actions from the fighter's cancel/state graph. Selecting an action updates a provisional packet and consequence preview. Execution does not begin until an explicit submit/lock-in step. The packet separates the action identifier from action-specific parameters and modifiers.

Just Dodge application:

1. Build the selectable set only from public deterministic state and the 13-action rules.
2. Keep hover/selection provisional and side-effect-free.
3. Preview by cloning an immutable truth snapshot and executing the normal deterministic simulation path.
4. Commit an exact action packet at an exact truth tick.
5. Never let preview state, camera, UI, or motion-plan inference mutate live truth.

### One simulation path for live, preview, replay, and undo

The recovered game ticks until either player reaches an interruptible decision boundary. A separate ghost game executes predictions through the same tick path. Replay stores per-player action packets keyed by simulation tick; undo removes the latest paired choice and resimulates from an earlier tick. Presentation events are suppressed during fast resimulation.

Just Dodge application:

- `TruthSnapshot + ActionPacket[] → TruthSnapshot'` must be the single deterministic core used by live play, ForgeLens preview, replay verification, and rollback.
- Store committed inputs/events, not rendered frames.
- At every decision boundary, persist the truth hash, selected packet hashes, next-action eligibility, and physical contact receipts.
- Resimulation must regenerate identical hashes without audio, particles, camera impulses, or UI callbacks affecting truth.

### Decision boundaries are first-class state

The reference pauses when a fighter becomes interruptible, not at arbitrary wall-clock intervals. Network peers synchronize on the exact simulation tick at that boundary.

Just Dodge application:

- define exact 60 Hz commit, Reveal, physical-contact eligibility, resolution, and recovery/next-commit boundaries;
- expose those boundaries in ForgeLens;
- distinguish “recognizable action,” “mechanically committed action,” “physical contact,” and “next legal decision” as separate events;
- reject plans whose event ordering is ambiguous.

### Simulation and presentation clocks are separate

Recovered action states independently encode simulation length, physics, hit/hurt intervals, and presentation timestamps. Sprite-frame mapping derives from simulation ticks. Sprite/audio work is skipped during replay resimulation.

Just Dodge application:

- keep body/weapon targets, audio, VFX, camera, and UI as tick-addressed consumers;
- allow presentation compression/interpolation without changing fixed-step truth;
- verify that skipped presentation during headless replay does not change truth hashes;
- record synchronized presentation events in evidence receipts without making them outcome authority.

## Explicit rejection boundary

YOMI Hustle's deterministic tick order includes authored hitboxes and action-metadata priority heuristics. Those mechanisms do not transfer.

Just Dodge must not use:

- action labels, damage, health, or authored hitbox metadata to decide physical contact/outcome;
- category or exact-action prediction leakage in adversarial live play;
- character-specific guaranteed chains;
- recovered source/assets as implementation substrate.

Deterministic articulated physics remains the only authority for contact, outcome, and injury. The valid transfer is the commit/preview/replay architecture and evidence UX.

## Implementation gates

Before exposing a Just Dodge consequence preview:

1. Clone live truth into isolated storage; prove live hashes unchanged after preview.
2. Execute preview with the production fixed-step physics reducer.
3. Store exact action packets and per-tick truth hashes.
4. Replay headlessly with presentation disabled and compare every hash.
5. Render preview from replayed truth, not a separate heuristic trajectory.
6. Hide private opponent choice; show only information allowed by the public commit/reveal protocol.
7. ForgeLens must label previews as hypothetical until both committed packets and deterministic resolution exist.
