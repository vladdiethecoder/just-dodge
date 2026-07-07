# QA, Visual Verification, and Agentic Playtesting — Just Dodge

## Purpose

This document defines how Just Dodge is verified from prototype through finished game using deterministic tests, visual QA, replay validation, human playtesting, and bounded agentic playtesting.

The purpose is not to replace human feel judgment. The purpose is to make every build falsifiable, replayable, inspectable, and difficult to falsely declare complete.

## QA Philosophy

1. Build evidence first.
2. Runtime evidence second.
3. Replay/truth hash evidence always.
4. Visual evidence only when it verifies readability, not beauty.
5. Agentic playtesting is support evidence, not player-fun proof by itself.
6. Human playtesting remains required for “fun.”
7. No screenshots-only progress claims.
8. No debug overlays in Player mode QA captures.

## QA Surfaces

### Deterministic Test Surface

Validates truth:

- resolver outputs;
- action matrix cells;
- fixed-step simulation;
- AI choices under seed;
- injury/armor state updates;
- replay hash;
- renderer-disabled equivalence.

### Runtime Smoke Surface

Validates executable behavior:

- launch;
- window creation;
- device/backend selection;
- asset loading;
- no crash during match;
- restart path;
- packaged executable path.

### Visual Surface

Validates player readability:

- fighter identity;
- action pose;
- weapon/hand/armor attachment;
- camera framing;
- contact/consequence visibility;
- UI cleanliness;
- lighting/silhouette;
- mode correctness.

### Agentic Play Surface

Validates interaction loops:

- agent observes game state/screenshots;
- agent chooses bounded allowed inputs;
- input sequence is recorded;
- output replay is saved;
- bugs become reproducible reports.

### Human Play Surface

Validates fun/readability:

- unaided play;
- post-match explanation;
- confusion/friction notes;
- desire to rematch;
- “great exchange” moments.

## QA Mode Rules

### Player Mode

QA captures must confirm:

- no debug HUD;
- no evidence overlay;
- no placeholder panels;
- no raw internal IDs unless intentionally part of tutorial;
- readable action/consequence through final UI/audio/visual language.

### Developer Mode

Allowed for diagnosis:

- truth hash;
- FPS/frame time;
- action IDs;
- skeleton overlay;
- hitbox overlay;
- matrix cell labels;
- replay cursor;
- capture controls.

Developer mode evidence cannot substitute for Player mode evidence.

### Presentation Mode

Allowed for curated reporting:

- clean labels;
- report-safe camera path;
- selected replay/fight-film playback;
- no development clutter.

Presentation mode cannot substitute for interactive playtesting.

## Required QA Artifacts

Every milestone should produce a report under `docs/reports/` with:

```text
milestone_id
build_id / commit
platform
mode tested
commands run
replay files
truth hash before/after
agentic playtest logs
visual capture manifest
human playtest notes
performance summary
bugs found
blockers
decision
```

Suggested directory structure:

```text
artifacts/verification/<timestamp>_<unit>/
  commands.txt
  environment.txt
  build.log
  test.log
  runtime.log
  replay/
    *.replay
    hash_report.md
  captures/
    manifest.md
    *.png
  visual_audit.md
  agentic_playtest.md
  human_playtest.md
  bugs/
    BUG-*.md
  decision.md
```

## Deterministic QA

### Truth Hash Suite

Minimum golden tests:

1. Strike vs Grab: Strike wins.
2. Block vs Strike: Block wins.
3. Grab vs Block: Grab wins.
4. Same action reset.
5. AI same seed repeats same sequence.
6. Renderer on/off hash match.
7. Replay record/playback hash match.
8. Injury update deterministic.
9. Armor damage update deterministic.
10. Fight Film generation does not change hash.

### Matrix Suite

For 13 actions:

- every one of 169 action pairs resolves;
- no unknown/placeholder cells;
- each result has contact type;
- each result has next-state flags;
- each result references readable presentation requirements;
- intentional asymmetries documented.

### Replay Suite

For each milestone:

- one short match replay;
- one comeback match replay;
- one AI-heavy replay;
- one edge-case replay;
- one regression replay from prior milestone.

Replay pass condition:

```text
initial_seed + input_stream + ruleset_version + asset_manifest_hash
  → same final truth hash
```

## Visual QA Protocol

### Capture Requirements

For each action or tested state, capture:

1. Observe.
2. Commit locked.
3. Reveal first frame.
4. Startup tell.
5. Active/contact frame.
6. Consequence.
7. Recovery/return to observe.

For each content combination selected for QA, capture:

- player/opponent identity;
- weapon visible and attached;
- armor/loadout visible;
- action readable;
- contact readable;
- injury/armor consequence readable;
- UI not clipped;
- camera not hiding state.

### Visual Audit Questions

For every capture, answer:

1. Are both fighters visible?
2. Can the player and opponent be distinguished without UI labels?
3. Is the current phase visually understandable?
4. Is the action pose identifiable?
5. Is the weapon held, attached, and aimed plausibly?
6. Is armor worn rather than floating?
7. Is contact visible at impact/block/grab?
8. Is consequence visible after resolution?
9. Does the camera frame the duel or hide the read?
10. Is UI clean for the selected mode?
11. Are debug overlays absent in Player mode?
12. Does lighting support silhouettes?
13. Are objects grounded?
14. Does any visual element contradict truth state?
15. What specific issue would cause a player to misread the exchange?

### Visual Issue Tiers

Tier 1 — Fighter Identity:

- same color/silhouette;
- no positional/shape/equipment distinction;
- player/opponent cannot be separated.

Tier 2 — Attachment:

- floating weapon;
- detached armor;
- wrong socket;
- skinning collapse.

Tier 3 — Pose/Action:

- static/T-pose look;
- pose offsets too subtle;
- action tells identical;
- no recovery/consequence pose.

Tier 4 — Contact:

- hit/block/grab not visible;
- weapon misses but truth says hit;
- truth says block but pose says idle.

Tier 5 — Camera/Framing:

- too far;
- too close;
- opponent offscreen;
- weapon arc hidden;
- UI dominates screen.

Tier 6 — Material/Lighting:

- low contrast;
- flat lighting;
- texture noise hides silhouette;
- armor class unreadable.

Tier 7 — UI/Mode:

- placeholder UI in Player mode;
- debug overlay in gameplay;
- clipped panels;
- labels contradict scene.

## Agentic Playtesting Protocol

### Agent Inputs

Agent may receive:

- current objective;
- allowed inputs;
- screenshot/capture;
- optional JSON state snapshot if exposed by QA mode;
- last N input/output events;
- remaining budget.

Agent returns:

```json
{
  "input": "Z|X|C|R|...",
  "reason": "short reason",
  "risk": "what might fail or be ambiguous"
}
```

### Agent Constraints

- Max tick count.
- Max retries.
- Fixed seed.
- Input stream recorded.
- No hidden-state cheating unless the test explicitly targets debug mode.
- Every failure becomes a reproducible bug or known limitation.
- Every success becomes a replay regression candidate.

### Agent Roles

#### Smoke Agent

Objective: launch, start match, press legal inputs, verify no crash.

Pass:

- reaches gameplay;
- completes at least one exchange;
- exits cleanly or restarts.

#### Triangle Agent

Objective: play 10 Strike/Block/Grab matches.

Pass:

- completes 10 matches;
- logs all inputs;
- produces replay(s);
- reports action confusion.

#### Matrix Explorer Agent

Objective: exercise all 13 actions.

Pass:

- each action selected at least once;
- no unresolved action state;
- replay saved.

#### Win-Seeking Agent

Objective: win against AI.

Pass:

- adapts action choices based on observed outcomes;
- does not use hidden debug truth;
- reports strategy.

#### Confusion Agent

Objective: identify unclear player-facing feedback.

Pass:

- records moments where action/phase/outcome is unclear;
- marks required capture frame;
- produces bug reports.

#### Visual Readability Agent

Objective: inspect captures exhaustively.

Pass:

- audits every required capture;
- categorizes issues by tier;
- distinguishes scene evidence from UI labels;
- proposes specific fixes.

#### Regression Agent

Objective: replay golden inputs and compare hashes.

Pass:

- all golden replays match expected hash;
- differences produce minimized repro.

## Human Playtesting Protocol

### First-Time Player Test

Prompt:

```text
Play one match. No explanation beyond controls shown in-game. Say aloud when you understand what happened and when you are confused.
```

Record:

- time to first valid action;
- time to first completed exchange;
- whether player understood outcome;
- whether player wanted rematch;
- confusion points;
- “read” moments.

Pass:

- completes match unaided;
- explains core triangle;
- identifies at least one outcome reason.

### Returning Player Test

Prompt:

```text
Play 10 matches. Try to win. Explain why you change strategies.
```

Pass:

- uses multiple actions intentionally;
- adapts to AI/loadout/injury;
- reports at least one great exchange.

### Advanced Systems Test

Prompt:

```text
Play against three loadouts and two AI personalities. Explain what changed.
```

Pass:

- player recognizes loadout differences;
- player changes decisions for readable reasons;
- AI personalities feel distinct and fair.

## Milestone QA Matrices

### First Playable QA

| Category | Required Evidence |
|---|---|
| Build | successful build output |
| Runtime | executable launches |
| Play | 5 full matches completed |
| Replay | one replay saved and reproduced |
| Truth | hash stable with same input |
| Visual | observe/reveal/resolve/consequence captures readable |
| Human | first-time player unaided match |
| Agent | Triangle Agent 10-match log |

### Vertical Slice QA

| Category | Required Evidence |
|---|---|
| Matrix | 169 cells tested |
| Motion | 80%+ blind action-read score |
| AI | 3+ personalities distinct |
| Injury | tactics change due to injury |
| Armor | tactics change due to loadout |
| Replay | replay/fight-film verified |
| Visual | exhaustive capture audit |
| Human | 10 playtests, each with a great exchange |
| Agent | Explorer, Win-Seeking, Visual, Regression agents pass |

### Content Complete QA

| Category | Required Evidence |
|---|---|
| Fighters | 3+ verified |
| Weapons | 6+ verified |
| Arenas | 3+ verified |
| Tutorial | first-time completion |
| Modes | local duel and AI duel |
| UI | no placeholder UI in Player mode |
| Visual | representative content matrix audited |
| Performance | frame/load budgets pass |
| Agent | content matrix smoke pass |

### Multiplayer QA

| Category | Required Evidence |
|---|---|
| Determinism | local replay suite pass |
| Network | remote input injection works |
| Rollback | rollback tests pass |
| Desync | 100+ matches no unresolved desync |
| Latency | perceived latency budget met |
| Agent | network regression scenarios pass |

## Bug Report Format

```markdown
# BUG-[id]: [title]

## Build
- commit/build:
- platform:
- mode:

## Repro
1.
2.
3.

## Input Stream
```text
frame,input
```

## Expected

## Actual

## Evidence
- replay:
- capture(s):
- log:
- truth hash expected/actual:

## Severity
P0/P1/P2/P3

## Suspected System
combat / replay / renderer / motion / asset / UI / input / audio / network
```

## QA Stop Gates

Stop and fix before advancing if:

- truth hash unstable;
- replay cannot reproduce;
- executable cannot launch;
- Player mode requires debug overlay to understand;
- action readability below threshold;
- agent cannot complete basic legal input path;
- human cannot complete target match unaided;
- visual capture contradicts truth event;
- performance makes input feel delayed;
- code/package requires repo-only paths for runtime.

## QA Anti-Patterns

Forbidden:

- claiming fun from screenshots;
- accepting debug-mode-only evidence;
- using visual scoring to inflate progress;
- letting agentic replay replace interactive play;
- hiding known bugs in report language;
- skipping failed captures;
- inspecting only representative captures when exhaustive audit is required;
- changing tests to pass instead of fixing the system;
- adding more tooling instead of fixing player experience.

## Minimum Done Definition by Build

A build is not accepted unless:

1. It runs.
2. It can be played for the target scenario.
3. It records replay/input evidence.
4. Its deterministic checks pass.
5. Its Player mode visual state is audited where relevant.
6. Agentic playtest either passes or produces concrete bugs.
7. Human playtest evidence exists for fun/readability gates.
8. Blockers are concrete and reproducible.
