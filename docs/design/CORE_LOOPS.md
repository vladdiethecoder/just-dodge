# Just Dodge — Core Loops

## Loop Overview

| Loop | Question | Time Scale | Viral Goal |
|---|---|---|---|
| Core | What does the player do every exchange? | 5–15 seconds | Simple, expressive, repeatable |
| Skill | Why do they improve? | Match to match | Clear mastery, surprising depth |
| Social | Why do friends matter? | Session to session | Local duels, shared replays, fight films |
| Content | What changes over time? | Hours to days | Loadouts, weapons, arenas, AI personalities |
| Creator | Why would someone stream/post it? | Every match | Clip-worthy reads and consequences |

---

## 1. Core Loop — The Exchange

**Question:** What does the player do every 5–15 seconds?

### Actions
1. **Observe** — read opponent stance, loadout, injury, tempo, distance.
2. **Plan** — choose a hidden action and stance.
3. **Commit** — lock the choice; cannot change.
4. **Reveal** — both actions become visible through pose/audio/UI.
5. **Resolve** — deterministic resolver computes contact, injury, armor, tempo.
6. **Consequence** — outcome is displayed; loop returns to Observe unless match ends.

### Feedback
- Stance pose changes during Observe/Plan.
- Commit confirmation sound/UI pulse.
- Reveal animation and wind-up audio.
- Contact sound, camera shake, injury/armor visual state change.
- Tempo bar changes.
- Match result and replay prompt.

### Progression Within Loop
- Each exchange changes injury state, tempo, and AI prediction.
- No exchange exists in isolation; the next exchange is flavored by the last.

### Shareability
- A single exchange is short enough to clip.
- The reveal-to-consequence sequence is visually legible to spectators.

---

## 2. Skill Loop — Mastery

**Question:** Why do they improve?

### Actions
- Learn the 3-action triangle.
- Expand to the 13-action matrix.
- Recognize stance tells and audio cues.
- Predict AI personalities and human patterns.
- Adapt tactics to injury and armor state.

### Feedback
- Win/loss trends.
- Replay review showing missed reads.
- Fight Film highlights correct predictions.
- AI difficulty scaling and personality variety.

### Progression
- Beginner: knows Strike/Block/Grab.
- Intermediate: uses Dodge/Feint/Thrust/Parry.
- Advanced: manipulates stance/tempo, targets injury, switches loadouts.

### Shareability
- Players share fight films of outplays.
- Ranked leaderboard and direct-IP rivalries.

---

## 3. Social Loop — Friends and Rivals

**Question:** Why do friends matter?

### Actions
- Local 2P duel with hidden input method.
- Share replay files and fight films.
- Discuss reads and counter-strategies.
- Compare loadout choices.

### Feedback
- Replay theater supports frame-by-frame review.
- Fight Film auto-generates cinematic highlights.
- Local duel results persist per session.

### Progression
- Friendly rivalries develop through repeated local matches.
- Online ranked/direct-IP adds persistent competition after launch.

### Shareability
- Fight films and replay clips are natively shareable.
- Spectators can follow a match without playing.

---

## 4. Content Loop — Variety

**Question:** What changes over time?

### Actions
- Unlock or select fighters, weapons, armor loadouts, arenas.
- Encounter AI personalities.
- Experience tutorial challenges.
- Try daily seeds or challenge modifiers (post-launch).

### Feedback
- Visual identity changes: silhouette, weapon, armor class.
- Gameplay changes: timing, ROM, noise, protection.
- Arena lighting and readability variations.

### Progression
- Tutorial → AI duel → local duel → ranked.
- Loadout knowledge becomes part of the YOMI read.

### Shareability
- Distinct loadouts and arenas make clips visually varied.
- Challenge modifiers create shareable scenarios.

---

## 5. Creator Loop — Streaming and Clips

**Question:** Why would someone stream/post it?

### Actions
- Every match produces at least one decisive read.
- Fight Film auto-edits the best exchange.
- Replay viewer lets creators analyze and narrate.

### Feedback
- Clear moments of triumph and surprise.
- Visible loadout and injury consequences.
- Deterministic replays enable exact reproduction for tutorials.

### Progression
- Creators build meta-knowledge and teach the matrix.
- Community develops terminology for reads and counters.

### Shareability
- Short exchange clips are ideal for TikTok/Shorts.
- Full fight films work for YouTube/Twitch.
- Replay files let viewers load the exact match.
