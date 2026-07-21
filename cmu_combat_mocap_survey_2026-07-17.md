# CMU combat-motion survey — 2026-07-17

## Bottom line

**CMU does not contain a named wrestling/grappling session, judo, clinching, takedown, collar-tie, body-lock, pummeling, underhook, or combat-throw clip.** The only `wrestl*` index hits are the paired `rush up, arm wrestle` recordings (22_17/23_17), not wrestling. The full B. Hahne text index was searched for those terms and for `fight`, `boxing`, `martial`, `sword`, `knife`, `throw`, `punch`, and `kick`.

The only usable *two-person physical-resistance* material is the paired subject sets **18/19** and **22/23**. These are valuable contact/constraint references, but must **not** be mislabeled as wrestling or MMA. The closest is arm wrestling; no take-down, clinch, throw, or ground-control motion is present.

**How durations were measured:** number of numeric frames in the official `.amc`, divided by the per-trial rate listed by CMU. CMU's BVH conversion adds a T-pose frame, so BVH durations may differ by one frame. `~` denotes this estimate.

**Sources:**
- Official subject index: `http://mocap.cs.cmu.edu/search.php?subjectnumber=<N>`
- Original files: `http://mocap.cs.cmu.edu/subjects/<NN>/<NN>_<TT>.amc`
- Consolidated full index: `https://raw.githubusercontent.com/una-dinosauria/cmu-mocap/master/cmu-mocap-index-text.txt`
- CMU FAQ: `http://mocap.cs.cmu.edu/faqs.php`

CMU says the data may be “copied, modified, or redistributed without permission.” Its homepage also says it is free for all uses / commercial products, but says not to resell the data directly. This is **not an explicit CC0/public-domain dedication** on the official site; retain the CMU provenance/license note.

## A. Priority: real paired physical contact / grappling proxies

For each row, download **both synchronized subject recordings**. The same action is captured separately as role A and role B; treating either file as a solo clip loses the partner relationship.

| Subject/trial pair | CMU index description | Duration | Combat use / actual content | Grappling? |
|---|---|---:|---|---|
| 18_03 + 19_03 | `A pulls B; B resists` | ~4.93 s each | Standing hand/arm pull against resistance; closest available off-balance / grip-resistance material. | **Yes—contact proxy**, not a named clinch or takedown. |
| 18_04 + 19_04 | `A pulls B; B resists` | ~3.38 s each | Second pull/resist take. | **Yes—contact proxy**, not wrestling. |
| 18_05 + 19_05 | `A pulls B by the elbow; B resists` | ~3.65 s each | Elbow control, resistance and posture reaction; useful for arm-control conditioning. | **Yes—limited arm-control proxy**; no collar tie/underhook. |
| 18_06 + 19_06 | `A pulls B by the elbow; B resists` | ~3.39 s each | Second elbow-pull/resist take. | **Yes—limited arm-control proxy**. |
| 18_07 + 19_07 | `navigate busy sidewalk; A leads the way, takes B by the arm` | ~2.42 s each | Arm-guiding contact while walking; weak but real connected-body contact. | Contact only; **not combat grappling**. |
| 22_01 + 23_01 | `B sits; A pulls up B` | ~6.52 s each | Assisted rise / lift; can support pull-to-stand mechanics, not a throw. | **Yes—contact proxy**, not combat grappling. |
| 22_02 + 23_02 | `A sits; B pulls up A` | ~3.93 s each | Same assisted-rise action with reversed narrative role. | **Yes—contact proxy**, not combat grappling. |
| 22_17 + 23_17 | `rush up, arm wrestle` | ~6.93 s each | The strongest available coupled upper-body resistance/hand-contact sequence. | **Yes—real physical contest**, but seated arm wrestling; no clinch, body lock, shot, throw, or ground work. |

### Direct answer to the requested grappling inventory

| Requested class | CMU result |
|---|---|
| Wrestling / grappling | No explicitly labeled clips. Use 18/19 pull-resist and 22/23 arm-wrestle only as weak proxies. |
| Judo / throws | No judo or person-throw clip. Index `throw` hits are ball/object throws and are excluded. |
| Single-/double-leg takedown | None found. |
| Clinching / collar ties / body locks / pummeling / underhooks | None found. |
| Ground fighting / submissions | None found. |

## B. Explicit solo combat, striking, weapon, and martial-arts clips

All rows below are **not grappling**. They are included because their official index descriptions explicitly name striking, boxing, swordplay, martial art, blocking, or kicking. Mixed vignettes should be segmented before training.

| Subject | Trial(s): CMU index description; duration | What it covers | Grappling? |
|---|---|---|---|
| 2 — various expressions/human behaviors | `02_05` `punch/strike` ~15.45 s; `02_07` `swordplay` ~18.76 s; `02_08` `swordplay` ~12.50 s; `02_09` `swordplay` ~8.61 s | Direct punch plus three weapon/swordplay takes. `02_07` is already on disk. | No |
| 12 — tai chi, walk | `12_04` `tai chi` ~148.32 s | Long solo Tai Chi form; martial-art-adjacent, not sparring. | No |
| 13 — everyday behaviors | `13_17` `boxing` ~40.33 s; `13_18` `boxing` ~25.00 s | Solo boxing. | No |
| 14 — everyday behaviors | `14_01` `boxing` ~46.62 s; `14_02` `boxing` ~45.19 s; `14_03` `boxing` ~46.13 s | Solo boxing. All are already represented locally; `14_02` is on disk. | No |
| 15 — everyday/dance | `15_04` mixed `wash windows, paint; hand signals; dance …; boxing` ~187.91 s; `15_05` same mixed label ~191.23 s; `15_13` `boxing` ~77.75 s | Long mixed motion vignettes; only the boxing portions are candidates. | No |
| 17 — walking styles | `17_10` `boxing` ~23.19 s | Solo boxing. | No |
| 56 — transition vignettes | `56_02` `fists up … angrily grab, smash against wall` ~28.48 s; `56_03` same plus `throw punches` ~51.83 s; `56_04` includes `throw punches` ~56.39 s; `56_05` includes `throw punches` ~61.33 s; `56_06` `throw punches, grab …` ~56.53 s | Mixed solo action-transition source. “Grab” is object/wall handling, not a partner clinch. | No |
| 74 — kicks/walking on slopes | `74_03` `kick` ~6.60 s; `74_04` `kick` ~5.25 s; `74_05` `kick` ~5.38 s; `74_06` `kick` ~5.42 s | Short isolated kicks. | No |
| 75 — jumps/hopscotch/sits | `75_16` `jump kick` ~5.72 s | Short jump-kick. | No |
| 76 — avoidance | `76_01` `walk backwards then attack with a punch` ~7.75 s; `76_02` `walk backwards, feign a few attacks, then attack` ~9.70 s; `76_03` `avoid attacker` ~9.02 s; `76_04` `defensive guard pose` ~3.48 s | Useful approach/retreat, feint, avoidance and guard references. The attacker is implied; this is not paired capture. | No |
| 79 — actor activities | `79_08` `boxing` ~7.37 s | Solo boxing; source rate is 60 fps. | No |
| 80 — assorted motions | `80_10` `boxing` ~12.88 s | Solo boxing; source rate is 60 fps. | No |
| 86 — sports/activities | `86_01` `jumps kicks and punches` ~38.16 s; `86_02` mixed `… jumps, punches …` ~88.47 s; `86_04` mixed `… punching …` ~83.98 s; `86_05` mixed `… punching …` ~69.50 s; `86_06` mixed `… kicking, punching, knee kicking …` ~82.83 s; `86_08` mixed `… kicking and punching` ~76.72 s | Long mixed solo exercise sequences; segment individual strikes/kicks before admission. | No |
| 87 — acrobatics | `87_01` `Jump with kick and spin` ~10.27 s | Acrobatic/spinning kick, 60 fps. | No |
| 88 — acrobatics | `88_04` mixed `… spin kicks, spins, and fall` ~20.67 s; `88_06` `jump and spin kick` ~3.83 s | Acrobatic kick/fall source, 60 fps. | No |
| 90 — acrobatics/dance | `90_05` `jump kick` ~4.28 s; `90_06` `jump kick` ~5.20 s; `90_07` `jump kick` ~7.46 s | Short jump-kick alternatives. | No |
| 111 — pregnant woman | `111_19` `Punch Kick` ~8.53 s | Solo punch/kick. | No |
| 113 — post-pregnant woman | `113_13` `Punch and kick` ~11.19 s | Solo punch/kick. The project has subject 113 material, but not this trial under `data/cmu`. | No |
| 135 — Martial Arts Walks | `135_01` `Bassai` ~50.97 s; `135_02` `Empi` ~43.35 s; `135_03` `Empi` ~22.91 s; `135_04` `Front Kick` ~10.97 s; `135_05` `Gedanbarai` ~20.50 s; `135_06` `Heiansyodan` ~27.18 s; `135_07` `Mawashigeri` ~12.27 s; `135_09` `Oiduki` ~17.92 s; `135_10` `Syutouuke` ~16.68 s; `135_11` `Yokogeri` ~20.38 s | Best broad solo traditional martial-art source: kata/forms, front/roundhouse/side kicks, punch/block techniques. Excludes `135_08` motorcycle pose. | No |
| 141 — general capture | `141_14` `Punch and Kick` ~4.81 s | Short solo punch/kick take. | No |
| 143 — general capture | `143_23` `Punching` ~6.78 s; `143_24` `Kicking` ~8.38 s | Separate solo punch and kick takes. | No |
| 144 — punching female | `144_05` `Front_Kicking` ~23.22 s; `144_06` `Front_Kicking001` ~30.27 s; `144_07` `Left_Blocks` ~20.40 s; `144_08` `Left_Blocks001` ~25.01 s; `144_09` `Left_Front_Kicking` ~28.18 s; `144_10` `Left_Front_Kicking001` ~29.15 s; `144_11` `Left_Lunges` ~28.57 s; `144_12` `Left_Lunges001` ~27.66 s; `144_13` `Left_Punch_Sequence001` ~16.22 s; `144_14` `Left_Punch_Sequence002` ~17.12 s; `144_17` `Lunges` ~23.50 s; `144_18` `Lunges001` ~25.80 s; `144_20` `Punch_Sequence` ~18.92 s; `144_21` `Punch_Sequence001` ~16.08 s; `144_26` `Right_Blocks` ~27.89 s; `144_27` `Right_Blocks001` ~22.12 s | Strong, explicitly named solo block/kick/lunge/punch coverage. Excludes reaches/spin-reaches and sun salutations. | No |

## Candidate download priorities

1. **Contact proxies first:** synchronized `18_03/19_03`, `18_05/19_05`, `22_17/23_17`; inspect native CMU preview video before claiming any usable interaction label.
2. **Best solo martial expansion:** complete `135` list (except 08), then `144` explicit punch/block/kick/lunge list.
3. **Combat timing / approach-defense:** `76_01–04`, then 2 swordplay and boxing sets.
4. **Do not use CMU alone for a grappling generator.** It has no labeled takedown/clinch/throw corpus. Source dedicated paired-contact/wrestling/judo motion elsewhere for that data class.

## Exclusions

- Object/ball throws (`15_12`, `33/34`, `111_33`, `113_24`, `141_10/11`, `143_20/22`, etc.) are not person throws; excluded.
- Angry arguments/quarrels, handshakes, stool threats, generic pulls, falls, ducking, or obstacle courses are not counted as combat grappling.
- Subject 18/19 and 22/23 non-contact social/comfort actions were also excluded; only the physically constrained actions are listed above.
