# Game Design Document — Just Dodge

## 1. Identity

**Working Title:** Just Dodge
**Genre:** First-person deterministic melee duel
**Target Platforms:** Linux, Windows (Steam), macOS if feasible
**Players:** 1v1 (local first, networked later)
**Session Length:** 1–5 minutes per duel
**Core Fantasy:** "I feel like a duelist who wins by reading my opponent's intent a split second before steel meets steel."

## 2. Core Loop (One Sentence)

Both duelists secretly select one action, reveal simultaneously, resolve the contact through a deterministic physical matchup matrix, suffer consequences, and immediately loop back for the next exchange until one duelist can no longer fight.

## 3. The YOMI Triangle (and Extensions)

Base triangle:
- **Strike** — fast attack, loses to Block, beats nothing on defense
- **Block** — defensive counter, beats Strike, loses to Grab/Break
- **Grab / Break** — beats Block, slow, loses to Strike and Dodge

Extension actions (research-backed expansions):
- **Dodge** — evades Strike/Grab, creates whiff opening, loses to Feint/Thrust
- **Feint** — cancels into a punish on Dodge/Block, loses to fast Strike
- **Thrust** — committed forward attack, beats Dodge/Feint, loses to Block/Parry
- **Parry** — high-skill defensive option, beats Thrust/Strike, narrow timing window
- **Riposte** — follow-up after successful Block/Parry
- **Disengage** — reset to neutral, costs stamina/position
- **Kick / Shield Bash** — break defensive shells, slow recovery
- **Low Attack** — must be blocked low, beats high Block
- **High Attack** — must be blocked high, beats low Block
- **Spin / Dodge-Attack** — high risk, punishes predictable reads

Total action count target: **13 actions**, matching OATHYARD's proven cardinality.

## 4. Win/Loss Conditions

- **Health/Injury Model:** localized body-part injury instead of a single HP bar.
- Incapacitation when:
  - head injury threshold reached,
  - torso injury threshold reached,
  - both arms or both legs injured,
  - total cumulative injury exceeds duelist limit.
- **Match End:** one fighter incapacitated, or time limit reached (rare).
- **Replay & Fight Film:** post-match playback of every resolved contact from cinematic angles.

## 5. Differentiation from Reference Games

| Source | What We Take | What We Change |
|---|---|---|
| YOMI | Simultaneous reveal, matchup triangle, mind-game loop | First-person 3D presentation, local injury simulation |
| For Honor | Stance/zone system, weapon weight feel, readable animations | No guard mode UI triangle; intent is hidden until reveal |
| OATHYARD | Truth isolation, 13-action matrix, MotionBricks, replay | Expand to first-person feel, networking, persistent progression |
| MotionBricks | Procedural pose interpolation | Drive interpolation from physical state, not authored clips |

## 6. Player Experience Goals

- A first-time player understands the triangle in under 3 minutes.
- A returning player discovers depth in feinting, timing, and matchup knowledge.
- An expert player expresses personality through stance, pacing, and prediction.
- Every match has at least one "I knew you would do that" moment.

## 7. Non-Goals (Explicitly Out)

- Open world or exploration.
- Crafting, loot, or procedural gear stats.
- Large-scale multiplayer or MMO systems.
- Complex narrative or dialogue trees.
- Physics-driven emergent comedy (this is a serious combat sim).

## 8. Aesthetics

- Dark, grounded, late-medieval/early-renaissance dueling culture.
- Arena lighting is functional: silhouettes and weapon arcs must read clearly.
- UI is diegetic or minimally invasive. No debug overlays in player mode.
- Sound design is information-bearing: every action has a distinct wind-up and contact signature.

## 9. Modes

1. **Tutorial Duel** — scripted opponent teaches one action at a time.
2. **Local Duel** — two players on one machine, hidden input method.
3. **AI Duel** — adaptive deterministic AI with difficulty personalities.
4. **Ranked / Casual Matchmaking** — rollback netcode, added after local game is great.
5. **Replay Theater** — browse, share, and analyze match replays.
6. **Fight Film** — auto-generated cinematic highlight reel.

## 10. Success Metrics

- A first-time player completes a full match without asking what to do.
- 10 consecutive internal playtests produce at least one "great exchange" per match.
- Truth hash remains stable across all presentation changes.
- Packaged executable runs the full loop on a clean machine without repo access.
