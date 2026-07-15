# For Honor combat/readability reference — 2026-07-15

Scope: evidence-backed patterns for Just Dodge. This is not a parity target, asset source, visual acceptance artifact, or authority change. Local binary observations come from the user's owned Steam installation; behavioral claims come from cited Ubisoft primary sources.

## Evidence boundary

The installed `forhonor.exe` (`111f205a0f6c2f40884d23818df3c633d0f1afd1d31357cc27ed48aba66e1de2`) is protected on disk: normal `.text/.rdata/.data/.pdata/.honor0` sections have zero raw bytes, the entry point falls inside a 51.65 MB `.honor2` section, and no symbols or semantic combat strings are exposed. No gameplay pseudocode was recovered. Detailed evidence is stored outside this repository at:

`/run/media/vdubrov/NVMe-Storage1/Just-Dodge-Reconstruction/for-honor/Phase_1/project_blueprint.md`

Primary behavioral sources:

- Ubisoft, “FOR HONOR: THE ART OF BATTLE,” 2015-06-15: https://www.ubisoft.com/en-us/game/for-honor/news-updates/3i9GE9e7XGWHqKQH2wUtZc/for-honor-the-art-of-battle
- Ubisoft, “How To Play: Controls & The Art of Battle,” 2017-02-02: https://www.ubisoft.com/en-us/game/for-honor/news-updates/2u0Ng5ufwteZGW2J9nIDq/how-to-play-controls-the-art-of-battle-for-honor-tips
- Ubisoft, “Patch Notes v1.22,” 2018-04-18: https://www.ubisoft.com/en-us/game/for-honor/news-updates/1jPpbDkOw2XON3K177NxBt/patch-notes-v122

## Transferable mechanisms

### 1. One intent, three mutually corroborating channels

For Honor's official design describes attack/block direction simultaneously through stance, physical weapon position, and interface indication. Just Dodge should adopt the mechanism, not the directional-guard ruleset:

- each revealed action owns a body silhouette contract;
- each action owns complete W0 pommel/tip and hand-role contracts;
- UI may label revealed intent but may not substitute for body/weapon evidence;
- disagreement among pose, weapon, and UI is a failed readability gate.

This directly reinforces W0/ARDY endpoint-first design and ForgeLens human evidence.

### 2. Input, state transition, and presentation must be distinct

Ubisoft's v1.22 notes report bugs at overlapping attack/stance branches, unlock during stance change, buffered input, recovery timing, and camera transitions. These are evidence that readable combat is a coordinated state machine, not a clip player.

For every Just Dodge action, keep separate immutable fields for:

- public committed intent;
- allowed input/buffer window;
- motion-plan proposal interval;
- physical contact window;
- deterministic outcome resolution;
- visual/audio presentation events;
- recovery and next-action eligibility.

Only deterministic physics may resolve contact/outcome/injury. Presentation timestamps cannot become truth authority.

### 3. Readability needs an executable training/evidence surface

For Honor's Training Arena can constrain an opponent to selected moves, tag executed moves, display costs/damage, expose timing windows, replay situations, and grade performance. The Just Dodge analogue should be ForgeLens/Evidence Studio over deterministic replay:

- select any subset of the 13 actions;
- run fixed seeds and exact opponent action schedules;
- overlay public commit, Reveal, contact window, physical contact packet, and recovery;
- show blinded labels only after reviewers record action identification;
- preserve immutable receipts for every timing/readability judgment;
- distinguish a correctly recognized action from a mechanically correct physical outcome.

### 4. Weapon-hand registration is a hard invariant

Ubisoft's official notes include weapon-hand offset, clipping, inversion, and stutter defects. For Just Dodge, these are contract failures rather than polish:

- active grip sockets remain inside GripCore and GripWrap;
- Strike/Block require both active hands within tolerance;
- Grab requires one weapon hand and one independent grab effector;
- complete W0 remains uncropped in fixed QA cameras;
- camera framing cannot hide failed grip registration.

### 5. Camera is presentation state, never combat authority

Official For Honor notes expose camera faults when transitions are interrupted. Just Dodge's first-person camera must therefore consume public state and deterministic root/pose output, but never affect physics truth, contact reduction, or action identity. Every lock/reveal/action/recovery transition needs a deterministic camera expectation and an uncropped evidence view independent of the shipping camera.

### 6. Timing must be measured at branch boundaries

Ubisoft's notes specify millisecond recovery, cancellation, buffer, movement, and defense-property changes. The transferable lesson is explicit timing schema and testability—not those exact balance values. Just Dodge should reject any action contract that lacks exact 60 Hz frame ranges for:

- earliest recognizable tell;
- commitment/no-return boundary;
- physical contact eligibility;
- feint/cancel policy where applicable;
- recovery and next commit;
- synchronized audio/VFX events.

## Non-transferable mechanisms

Do not import:

- authored action-label outcome tables;
- health/stamina/revenge assumptions;
- directional-guard matching as contact authority;
- hero-specific guaranteed punish chains;
- camera/HUD indicators as evidence of physical contact;
- protected code, assets, animation, audio, or proprietary archive content.

## Immediate Just Dodge gates

Before any new candidate generation:

1. W0 socket positions must remain physically inside both grip meshes with measured clearance.
2. ARDY root translation must coincide with exactly one planted support; dual-support root motion fails.
3. Reveal samples must include distinct action-specific f2/f3 whole-body and complete-weapon evidence.
4. ForgeLens must test action recognition before showing labels.
5. Candidate reports must include grip, support, crop, recognition, deterministic repeat, and provenance gates independently.
6. A failed visual/human gate cannot be repaired by changing physics truth or outcome labels.

## Next reverse-engineering target

The owned native Linux build of `Your Only Move Is HUSTLE` is unstripped and is the next static target for reconstructing deterministic action-selection, timeline preview, and consequence-inspection mechanics. Those findings must be kept separate from For Honor's opponent-facing readability evidence until independently verified.
