# Just Dodge — Concept Canvas

## One-Sentence Promise

"Just Dodge is a game where players commit to one hidden melee action and reveal it simultaneously against an opponent, so they can feel like a duelist who wins by reading intent before steel meets steel, and they will want to share it because every match generates at least one 'I knew you would do that' moment worth clipping."

## Player Fantasy & Motivation

### Aesthetics (MDA)
- **Tension:** both duelists hide intent until the last possible moment.
- **Mastery:** learning matchup timing, stance tells, and opponent patterns.
- **Catharsis:** a correct read pays off instantly and visibly.
- **Expression:** loadout and pacing choices reflect personal dueling style.

### Mechanics
- Hidden action selection during the Plan phase.
- Simultaneous Reveal with readable animation/audio tells.
- Deterministic resolver using a 13×13 matchup matrix.
- Localized injury and armor that changes capability, not just a HP bar.

### Dynamics
- Predictability is punished; adaptability is rewarded.
- Heavy armor trades mobility for survival; light armor rewards precision.
- Stance hints at intent without revealing it.
- Tempo gates aggression and creates pacing rhythm.

### Self-Determination
- **Competence:** clear skill ceiling through timing reads, matrix knowledge, and adaptation.
- **Autonomy:** meaningful choice of action, stance, loadout, weapon, and pacing.
- **Relatedness:** local duels, shared replays, fight films, and eventually ranked matches.

## Audience & Platform

- **Primary audience:** PC players who enjoy fighting games, deck builders, tactical shooters, and dueling games like YOMI Hustle, For Honor, or OATHYARD.
- **Primary platform:** Steam on Linux and Windows.
- **Discovery channel:** Steam tags (Fighting, Indie, Strategy, Action), short gameplay clips, YouTube creators, Twitch streamers, Discord communities.
- **Session length target:** 1–5 minutes per duel; 15–30 minutes per session.

## Emotional Pillars

1. **Tension** — the moment before reveal.
2. **Triumph** — landing a read and seeing the consequence.
3. **Respect** — recognizing a better read from the opponent.
4. **Ownership** — loadout and injury state tell the story of the duel.
5. **Curiosity** — wanting to see the replay or fight film to understand what happened.

## Comparable Games

**This game is like:**
- **YOMI Hustle** — simultaneous reveal and mind-game loop.
- **For Honor** — stance, weapon weight, and readable animations.
- **OATHYARD** — truth isolation, MotionBricks, replay evidence, 13-action matrix.

See `docs/design/RESEARCH_SYNTHESIS.md` for the comparative analysis of YOMI Hustle and For Honor that grounds these choices.

**This game is deliberately NOT copying:**
- **Reaction brawlers** (e.g., Street Fighter, Tekken) — no twitch reactions after reveal.
- **RPG loot treadmills** — armor is readable counterplay, not hidden stat power.
- **Open-world action games** — no exploration; pure focused duel.

## Monetization Model

Premium one-time purchase on Steam. No in-game purchases, no loot boxes, no battle pass. Post-launch content updates are free or small paid expansions only if they expand the duel meaningfully.

## Content Rating Risks

- **Violence:** melee combat with injury and armor damage; no gore required, but blood and persistent wounds may affect rating.
- **Fear:** dark medieval atmosphere; no horror jumps.
- **Gambling:** none.
- **Online interaction:** planned 1v1 PvP with rollback; requires moderation plan for launch.

## First 30-Second Video Concept

A first-person view shows the opponent across a dim arena. Both fighters enter the Plan phase. The player selects Strike. The opponent's stance shifts. Reveal: both actions snap into readable poses. The opponent's Grab closes the distance, but the player's Strike already has initiative. Contact. Armor dents. The opponent staggers. Cut to a slow-motion consequence with the fight-film camera. End card: "Read. Reveal. Resolve."

## First Playable Prototype Goal

A Strike/Block/Grab duel against a simple AI in the existing Rust/wgpu executable. The player can complete a match unaided, understand why they won or lost, and want to play again. The build records a replay and produces a stable truth hash.
