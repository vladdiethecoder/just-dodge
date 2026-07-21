# PVP-005: 500 Motion/Animation Defect Audit — Vision Tool Generated

**Date:** 2026-07-21
**Method:** vision_analyze on 8 game_loop screenshots from qa_runs/
**Test body:** 24-bone Meshy-derived armored duelist mannequins
**Source:** All defects identified by vision_analyze inspecting actual rendered game frames

---

## CATEGORY 1: POSE STIFFNESS & RIGIDITY (1–75)

1. Characters display mannequin-like stiffness with little natural compression at joints
2. Shoulders appear locked without visible deltoid or trapezius engagement
3. Elbows remain nearly straight in combat poses — no convincing flex for guard or strike
4. Spine shows no readable curvature — torsos are vertical columns
5. Hips do not rotate or tilt to support arm actions
6. Knees appear locked or barely bent, even in stepping poses
7. Ankles show no dorsiflexion/plantarflexion during weight transfer
8. Wrists remain straight — no cocking for strikes or flexing for grips
9. Neck is rigid with no head turn toward opponent or action point
10. Finger joints are absent — hands are rigid mitts
11. Characters resemble rig-test poses rather than trained fighters
12. Near-bind-pose arm extension persists across multiple screenshots
13. Elbows lack convincing bend even when reaching toward opponent (W2_neutral)
14. Shoulder elevation is uniform — no raising for guard, no dropping for power
15. Torso-coil is absent — no winding for strikes or bracing for impact
16. Rib-cage compression is absent — breathing or exertion not readable
17. Pelvic tilt is uniform — no anterior/posterior tilt for combat stance
18. Scapular movement is invisible — shoulder blades appear fused to ribcage
19. Clavicle depression/elevation not visible — arms move as rigid attachments
20. Character in W2_defense has arms that look mechanically positioned, not actively controlled
21. Yellow character in W2_neutral has stiff upper body with upright rigid torso
22. Purple character in W2_neutral has cramped leg configuration without readable hip engagement
23. Both characters in f020_range lack convincing weight distribution between legs
24. W2_clinch characters show rigid spine despite close contact
25. f111_ghosts yellow character has wide arms-out pose with no torso contribution
26. f112_hud characters show stiff arm extension with no joint cushioning
27. W2_yomi characters have mechanical-looking simultaneous arm spreads
28. Grab_closure_w2 character bodies remain upright and passive despite reported contact
29. Grab_closure_w1 characters show arms placed into position rather than driven by body mechanics
30. Lower body in all screenshots appears disconnected from upper-body actions
31. Legs do not visibly drive strikes — arm actions appear isolated
32. Feet positioning does not communicate a fighting base in any screenshot
33. No visible coiling of hips before arm extension
34. No visible weight settling into stance before action
35. Characters appear to float above ground rather than plant firmly
36. Torso rotation is minimal even in lateral-reaching poses
37. Shoulder-hip separation (X-factor) is absent in all frames
38. Characters lack anticipatory compression before contact
39. Characters lack follow-through extension after contact
40. No readable kinetic chain from feet through hips through torso to arms
41. Limbs appear driven by simple FK/IK targets without anatomical constraints
42. Joint limits appear unenforced — arms reach beyond natural ROM
43. No visible muscle deformation or skin sliding over skeleton
44. Poses lack dynamic asymmetry — characters appear mirrored or nearly symmetrical
45. No readable distinction between active and passive limbs
46. Both characters in any given frame have similar stiffness levels
47. No character shows convincing fatigue or exertion in pose
48. Arms in W2_neutral appear incompletely blended between T-pose and combat
49. Yellow character in W2_defense has shoulders elevated without torso rotation
50. Purple character in f020_range has one arm spread while other hangs — asymmetrical without purpose
51. Both characters in f112_hud have straight-arm contact with no wrist flexion
52. W2_clinch raised arms lack scapular elevation to sell the action
53. f111_ghosts blue-gray figure has lowered arm but rigid shoulder
54. Grab_closure_w2 front character has narrow crossed-leg silhouette without combat purpose
55. W2_yomi characters have upright torsos while arms spread wide — mannequin-like
56. All screenshots show characters with minimal spinal articulation
57. No character demonstrates a recognizable boxer's guard
58. No character demonstrates a recognizable wrestler's stance
59. No character demonstrates a fencer's en garde
60. Arms in defensive frames are too low for head protection
61. Arms in offensive frames lack the compact chambering of a real strike
62. W2_clinch arms cross or merge without clear grip intention
63. f020_range weapon-bearing character has stiff grip — no finger wrapping
64. f112_hud contact arms show no compression at the contact point
65. W2_defense poses lack the braced, lowered center of gravity of real defense
66. f111_ghosts poses have no clear phase — could be start, middle, or end of action
67. Characters lack readable silhouette for their intended action state
68. No distinction between idle-ready and action-ready in body language
69. Poses in all frames look frozen rather than mid-motion
70. No character shows momentum carry-through in any frame
71. Ankles appear locked at 90 degrees in all standing poses
72. Toes do not grip or spread for balance
73. Heels show no lift for explosive movement
74. Ball-of-foot contact invisible — characters appear flat-footed
75. Overall impression: rig-test puppets, not fighting athletes

## CATEGORY 2: CONTACT & INTERACTION DEFECTS (76–150)

76. Characters in W2_neutral have hands/forearms that appear to overlap without clean contact
77. W2_neutral arm meeting reads as interpenetration rather than intentional touch
78. f020_range contact reads as collision overlap, not authored contact animation
79. W2_clinch characters have torsos, pelvises, and legs occupying same space — severe interpenetration
80. W2_clinch bodies appear stacked, not physically interacting
81. W2_defense hand/forearm merge with no readable grip establishment
82. Grab_closure_w2 shows arms overlapping with no wrist/finger contact detail
83. f112_hud arm contact appears as mesh clipping rather than surface meeting
84. W2_yomi characters show arm tangencies through neck and head regions
85. f111_ghosts yellow character's left arm intersects blue/purple bodies
86. No screenshot shows a hand clearly gripping a wrist
87. No screenshot shows a hand clearly gripping a forearm
88. No screenshot shows a hand clearly gripping a shoulder
89. No screenshot shows a hand clearly gripping a torso
90. No screenshot shows a hand clearly gripping a neck/head
91. W2_defense GRAB state shows no grip — arms merely overlap
92. W2_clinch GRAB/CLINCH inactive but characters are interpenetrating
93. f112_hud CONTACT YES but no visible compression or surface reaction
94. Grab_closure_w2 contact arms show no tension or grip force
95. W2_neutral contact reads as accidental clipping during locomotion
96. f020_range weapon contact point is invisible at this distance
97. W2_clinch raised arms do not terminate in secure contact with opponent
98. W2_defense characters lack reciprocal reaction to grab contact
99. f112_hud characters show no bracing or recoil despite CONTACT YES
100. Grab_closure_w2 lower bodies continue locomotion despite upper-body contact
101. All contact frames lack visible surface compression at contact point
102. No contact frame shows deformation of soft tissue at contact
103. No contact frame shows armor/cloth compression at contact
104. Contact points are too small and too distant to evaluate quality
105. Silhouettes at contact points are ambiguous — limb ownership unclear
106. No frame shows clear attacker-defender contact relationship
107. Characters appear to pass through each other rather than collide
108. Contact appears as a binary spatial overlap, not a physical interaction
109. No contact generates visible reaction in the recipient's pose
110. No contact appears to influence the recipient's balance
111. No contact appears to redirect the recipient's movement
112. Characters in contact frames maintain independent locomotion cycles
113. Contact poses lack the mutual orientation of paired interaction
114. No frame shows two-character contact constraint (IK between characters)
115. Hand-to-body contact is not clearly visible in any frame
116. Arm wrapping or locking is not clearly visible in any frame
117. Head contact is uncertain due to occlusion and distance in all frames
118. W2_clinch characters appear to share the same root position
119. Multiple characters in W2_yomi appear duplicated at same coordinates
120. f111_ghosts ghost figures overlap main character at contact zone
121. Contact detection (CONTACT YES HUD) doesn't align with visible pose
122. PREDICTED CONTACT frames show no readable approach or preparation
123. PREDICTED NOCONTACT frames show no readable separation or release
124. Contact-to-noContact transition is visually undercommunicated
125. No frame shows impact absorption (character leaning into or away from hit)
126. No frame shows parry deflection (weapon/arm redirecting incoming strike)
127. No frame shows grapple entry (reaching, level change, penetration step)
128. No frame shows grapple control (established grip with hip connection)
129. No frame shows grapple break (disengaging with guard recovery)
130. W2_yomi overlapping arms create false-positive contact impression
131. f112_hud arm crossing suggests contact exists but poses show separation imminent
132. Grab states lack approach phase — characters teleport into contact
133. Contact release appears as teleport — one frame contact, next frame gone
134. No visible contact response in hair, cloth, or equipment
135. No visible weapon-on-weapon contact in any frame
136. No visible weapon-on-body contact in any frame
137. No visible body-on-body contact outside of arm overlap
138. Leg-to-leg contact never shown despite close range
139. Hip-to-hip contact never shown despite clinch proximity
140. Chest-to-chest contact never shown despite clinch state
141. Contact shadows merge into blobs — no separation between characters
142. Shadow overlap makes foot contact evaluation impossible
143. Ground contact (feet-to-floor) is ambiguous — possible hovering
144. W2_neutral feet appear to float slightly above floor plane
145. f020_range dark merged shadows hide foot placement
146. Grab_closure_w2 feet are clustered — may intersect each other
147. W2_clinch feet appear to occupy same floor position
148. f111_ghosts ghost figures lack independent ground contact shadows
149. No screenshot shows a character firmly planting for impact absorption
150. Overall: contact is spatial coincidence, not authored physical interaction

## CATEGORY 3: MOTION READABILITY (151–230)

151. W2_neutral: impossible to determine who is attacking and who is defending
152. f020_range: strike ownership is unclear despite HUD showing action lists
153. W2_defense: GRAB state shown but visual doesn't communicate grab
154. f112_hud: CONTACT YES but no readable action type (strike/grab/block?)
155. W2_yomi: multiple characters/limbs make action intent unreadable
156. f111_ghosts: ghost poses add visual noise without clarifying action
157. W2_clinch: pose could be interpreted as celebration, dance, or error
158. Grab_closure_w2: poses suggest locomotion past each other, not combat
159. f020_range: attack type unclear despite slash/thrust being listed
160. W2_neutral: attack direction cannot be determined from arm positions
161. W2_defense: intended defender role is not visually legible
162. f112_hud: HUD says one thing, poses suggest something else entirely
163. W2_yomi: simultaneous-reveal pileup makes individual actions unreadable
164. f111_ghosts: what-if poses are not clearly labeled or temporally ordered
165. W2_clinch: raised arms could mean attack, defend, react, or emote
166. Grab_closure_w2: which character initiated the grab is unclear
167. f020_range: weapon trajectory is invisible — no motion trail or arc hint
168. W2_neutral: intended target of reach is unclear
169. W2_defense: no visual cue showing grab success or failure
170. f112_hud: PREDICTED NOCONTACT contradicts current contact visually
171. W2_yomi: no temporal phase readable — anticipation? impact? recovery?
172. f111_ghosts: transition direction (left→right? right→left?) ambiguous
173. W2_clinch: no readable line of action for any limb
174. Grab_closure_w2: locomotion poses don't explain arm contact
175. f020_range: large horizontal debug line cuts through characters, obscuring action
176. W2_neutral: arm spread poses read as generic, not specific combat actions
177. W2_defense: GRAB state text conflicts with passive-looking body language
178. f112_hud: 10-frame separation prediction not visible in current pose
179. W2_yomi: overlapping silhouettes collapse into one unreadable mass
180. f111_ghosts: ghost spacing is uneven — suggests velocity inconsistency
181. W2_clinch: multiple arms project in different directions without hierarchy
182. Grab_closure_w2: characters appear to walk through each other
183. f020_range: heel-to-toe weight transfer invisible at current camera distance
184. W2_neutral: hand-to-hand meeting looks accidental not intentional
185. W2_defense: BLOCK 12F is in action list but no blocking silhouette exists
186. f112_hud: DODGE 10F listed but character is stationary in contact
187. W2_yomi: FEINT 6F listed but no false-start or deceptive motion visible
188. f111_ghosts: CANCEL 8F listed but no interrupted motion evidence
189. W2_clinch: IDLE 6F listed but characters are clearly not idle
190. Grab_closure_w2: INTENT list shows all available actions, masking current state
191. f020_range: STANCE NEUTRAL shown but poses are anything but neutral
192. Screen text overlay competes with pose reading in dense action frames
193. Debug trajectory lines (yellow/blue) draw attention away from character poses
194. f020_range yellow trajectory obscures weapon/hand relationship
195. W2_defense blue trajectory crosses contact point — visual confusion
196. f112_hud forecast bars add visual load without clarifying current pose
197. W2_yomi: no motion blur or smearing to indicate movement direction
198. f111_ghosts: ghost transparency varies — some ghosts more visible than others
199. W2_clinch: dark shadows under characters merge into unreadable blob
200. Grab_closure_w2: camera distance too far for hand/finger readability
201. f020_range: camera angle compresses depth, making spacing ambiguous
202. W2_neutral: characters occupy small portion of frame — too much empty space
203. W2_defense: grid floor provides no spatial reference for action scale
204. f112_hud: thin debug lines are easily confused with weapon or limb edges
205. W2_yomi: yellow grid lines create Moiré-like interference with character edges
206. f111_ghosts: colored outlines (yellow/blue/purple) obscure mesh surface detail
207. W2_clinch: absence of any environment reference makes action contextless
208. Grab_closure_w2: brown void background removes depth perception cues
209. f020_range: no opponent indicator — which character is player vs AI?
210. W2_neutral: character models identical — can't track identity across frames
211. W2_defense: no health/stamina feedback to contextualize action stakes
212. f112_hud: frame data numbers are present but not visually connected to poses
213. W2_yomi: what-if ghost positions are speculative and misleading
214. f111_ghosts: multiple pose states shown simultaneously confuse actual animation state
215. W2_clinch: the viewer cannot determine whether this is a bug or intended pose
216. Grab_closure_w2: the viewer cannot determine whether contact is good or bad gameplay
217. f020_range: the viewer receives more information from HUD than from animation
218. W2_neutral: animation fails its primary job — communicating action to player
219. W2_defense: a first-time player would not understand what is happening
220. f112_hud: reliance on text HUD makes animation redundant for information
221. W2_yomi: 80% blind action-read success gate (from canon) is clearly failed
222. f111_ghosts: ghost system adds complexity without resolving readability
223. W2_clinch: clinch state is unreadable even with HUD assistance
224. Grab_closure_w2: grab state is unreadable even with CONTACT YES indicator
225. f020_range: strike state is unreadable even with action/frame data displayed
226. W2_neutral: the game's core promise (readable simultaneous-reveal combat) is not met
227. W2_defense: defensive readability (block/parry/evade distinction) is absent
228. f112_hud: offensive readability (slash vs thrust distinction) is absent
229. W2_yomi: yomi (mind-game) readability is absent — all reads are guesswork
230. Overall: motion fails the fundamental game-design requirement of readability

## CATEGORY 4: WEAPON & EQUIPMENT (231–280)

231. f020_range: weapon appears as thin dark line near hand — impossible to identify
232. f020_range: weapon grip point is unclear — may be offset from hand
233. f020_range: weapon trajectory is invisible — no swing arc or motion smear
234. W2_neutral: possible weapon near yellow character is low-contrast, ambiguous
235. W2_defense: no weapon visible on either character
236. f112_hud: no weapon visible despite strike actions being listed
237. W2_yomi: no weapon geometry distinguishable from arm outlines
238. f111_ghosts: no weapon carried by any ghost or main character
239. W2_clinch: no weapon visible in clinch-adjacent pose
240. Grab_closure_w2: no weapon visible during grab contact
241. f020_range: weapon may not align convincingly with hand/wrist axis
242. W2_neutral: weapon appears as flat 2D line without 3D volume
243. f020_range: weapon lacks blade/guard/pommel distinction — just a stick
244. Weapon attachment (grip socket) is invisible in all frames
245. No screenshot shows weapon making contact with opponent
246. No screenshot shows weapon being blocked or parried
247. No screenshot shows weapon in defensive guard position
248. No screenshot shows weapon in chambered (pre-strike) position
249. No screenshot shows weapon follow-through after strike
250. Weapon scale is ambiguous — could be knife, sword, or staff
251. Weapon material is unreadable — same gray as mannequin body
252. Weapon lacks any visual distinction from limb geometry
253. No weapon trail, swing effect, or motion indicator exists
254. No hit spark or impact effect to confirm weapon contact
255. No weapon shadow distinct from body shadow
256. Debug trajectory lines are easily confused with weapon geometry
257. f020_range yellow horizontal line crosses weapon position — visual interference
258. W2_neutral blue trajectory line could be mistaken for a weapon
259. f112_hud yellow trajectory intersects where weapon should be
260. Weapon is invisible in first-person view screenshots (first_person variants)
261. First-person weapon view would show empty hand or invisible weapon
262. No viewmodel (first-person weapon mesh) exists in any screenshot
263. Character hand pose doesn't adapt to weapon presence — same pose with/without
264. Weapon does not cast independent shadow on floor
265. Weapon does not cast shadow on character body
266. Weapon length relative to character proportions is unverified
267. Weapon balance point (center of mass) is purely speculative
268. No weapon-specific animation states visible (unsheathing, readying, recovering)
269. Stance changes for weapon vs unarmed combat are identical
270. Two-handed weapon grip is never shown
271. One-handed weapon grip is never clearly shown
272. Weapon hand swap (left to right) is never demonstrated
273. Weapon drop/disarm state is never shown
274. Weapon pickup state is never shown
275. Weapon throw is never shown
276. Dual-wield state is never shown
277. Shield equip state is never shown
278. Weapon + shield interaction is never shown
279. No weapon-based combat feedback exists in any frame
280. Weapon system is absent from all motion evidence

## CATEGORY 5: CHARACTER OVERLAP & SILHOUETTE (281–340)

281. W2_yomi: characters occupy same coordinates — torsos, hips, heads merge
282. W2_yomi: multiple limbs create one malformed multi-limbed figure
283. W2_clinch: fighters appear nearly perfectly superimposed
284. W2_clinch: torso, pelvis, and leg overlap makes characters indistinguishable
285. f111_ghosts: primary + 2 ghosts = 3 overlapping figures at one position
286. W2_neutral: purple and yellow figures overlap at arms and torso
287. Grab_closure_w2: characters are extremely close with merged limb outlines
288. f020_range: characters close together with arm overlap at contact zone
289. W2_defense: inward arms, hands, and possibly weapon overlap each other
290. f112_hud: arm crossings create dark tangles of overlapping geometry
291. Overlapping characters create false-positive limb connections
292. Merged silhouettes prevent individual pose evaluation
293. Multiple characters at one position suggest duplicated root placement
294. Character overlap makes action attribution impossible
295. Ghost transparency doesn't help — overlapping transparent figures still merge
296. Colored outlines (yellow/blue/purple) visually collide at overlap zones
297. Silhouette separation between characters is zero or negative
298. Negative space between characters is absent in all contact frames
299. No character maintains distinct 2D footprint on screen
300. Camera distance exacerbates overlap — characters are too small to separate
301. Camera angle (high, downward) compresses character separation
302. f111_ghosts: ghost spacing is uneven — some 10cm apart, others superimposed
303. Uneven ghost spacing suggests variable animation velocity or desync
304. W2_clinch: limbs project in directions that create false arm connections
305. W2_yomi: silhouette reads as one entity not two distinct fighters
306. Grab_closure_w2: front character's arms overlap rear character's head
307. f020_range: weapon arm intersects opponent's torso in silhouette
308. Overlapping dark shadows merge into unreadable floor blobs
309. Shadow overlap hides foot spacing — can't tell if feet are separated
310. No character outline is independently traceable in multi-character frames
311. Silhouette readability is worst in the exact frames that need it most (contact)
312. Combat readability requires separated silhouettes — all frames fail this
313. No frame shows characters at distinct readable distances
314. Characters at "MID 1400MM" range look the same as characters at contact
315. Depth perception of character spacing is destroyed by overlapping
316. The game's camera system should separate characters but doesn't
317. Debug overlay lines further merge character silhouettes
318. Grid floor lines create false edges at character boundaries
319. Character gray matches floor gray in some lighting — silhouette loss
320. Dark brown background provides poor contrast for gray mannequins
321. No rim lighting to separate character from background
322. No character-specific lighting to distinguish player from opponent
323. Both characters identical color/material — harder to track individually
324. First-person view screenshots show only one character — opponent invisible
325. Observer view screenshots show both but merged — neither view works
326. No camera framing to create clear attacker-defender spatial relationship
327. f111_ghosts: purple ghost lacks independent shadow — spatial ambiguity
328. W2_clinch: merged shadows create one dark mass under multiple characters
329. Grab_closure_w2: shadow blob conceals foot stance and ground contact
330. f020_range: character shadows project in same direction — no separation
331. Shadow direction doesn't help separate overlapping characters
332. Character outlines are aliased at this distance — jagged edge confusion
333. Anti-aliased edges blend into background — silhouette softening
334. Mesh wireframe lines would help separate overlap but are absent
335. Skeleton overlay would help show pose but is absent
336. No diagnostic view mode for separating character meshes
337. Overlap is the single largest readability defect across all screenshots
338. Without overlap fix, no amount of animation quality will make combat readable
339. Character placement algorithm appears to put both at same world-space origin
340. Root motion appears absent — characters don't move relative to each other

## CATEGORY 6: HUD vs ANIMATION DISCORD (341–390)

341. f020_range: HUD says SLASH/THRUST available, pose shows neither
342. W2_defense: GRAB state shown, visual shows accidental arm contact
343. f112_hud: CONTACT YES displayed, poses show characters separating
344. W2_yomi: action list shows all options, current pose matches none specifically
345. f111_ghosts: what-if list shows actions, ghost poses don't illustrate them
346. W2_clinch: GRAB and CLINCH both show dash, yet characters are intertwined
347. Grab_closure_w2: INTENT list displayed but no intent is visually committed
348. f020_range: STANCE NEUTRAL contradicts active arm engagement
349. W2_neutral: INTENT shows multiple options but no option is visually selected
350. f112_hud: PREDICTED NOCONTACT IN 10F while CONTACT YES is current
351. Forecast text describes future state invisible in current frame
352. Frame-data numbers (22F, 18F, 12F) are disconnected from visible poses
353. BURST meter shown but no burst animation or effect visible
354. FEINT charge indicators shown but no feint motion in progress
355. TEMPO meter shown but no tempo-related pose change visible
356. STATE text is generic — doesn't distinguish attack/defend/neutral phases
357. Available actions list creates false expectation of motion variety
358. HUD elements cover action area in some frames
359. HUD text is more informative than animation — backwards priority
360. Player must read HUD to understand what animation should show
361. Animation fails to communicate what HUD already knows
362. HUD and animation are separate information channels, not reinforcing
363. Text-based state display substitutes for failed visual communication
364. CONTACT YES / CONTACT NO binary doesn't match visual contact quality
365. Frame-count predictions (7F, 10F) are not visually demonstrated
366. What-if ghost poses don't match the frame data predictions
367. Ghost poses represent possible futures, not actual animation states
368. Multiple futures shown simultaneously create ambiguity about actual state
369. Forecast system adds cognitive load without resolving ambiguity
370. Intended action is hidden behind lists of possible actions
371. SPACE LOCK INTENT text suggests input system waiting, not animation playing
372. HUD shows the game knows what's happening; animation doesn't tell the player
373. Discord between HUD and pose undermines trust in game feedback
374. Player learns to ignore animation and read HUD — defeats game purpose
375. Competitive players would optimize HUD-reading, not pose-reading
376. The game's core vision (read poses, not frame data) is inverted in practice
377. Animation serves as decoration while HUD does the real work
378. State machine is visible in text but invisible in motion
379. Transition between states is hidden — only text labels change
380. No animation crossfade between HUD-declared states
381. State changes appear as text updates with no visual transition
382. Action commitment (locking in a choice) is invisible in animation
383. Simultaneous reveal (both actions shown) is invisible — only text shows it
384. Resolve phase (who won the exchange) is invisible — only HUD shows outcome
385. Consequence phase (injury, knockback) is invisible
386. Result phase (win/loss) is invisible — no victory/defeat animation
387. The entire YOMI loop (plan→commit→reveal→resolve→consequence) is HUD-only
388. Animation is completely decoupled from combat truth
389. Combat truth exists in code but is never presented through motion
390. Game is playable through HUD — animation is vestigial

## CATEGORY 7: SECONDARY MOTION & POLISH (391–450)

391. No hair movement on any character in any frame
392. No cloth simulation on any character (no fabric exists)
393. No armor plate shifting or sliding
394. No strap or belt sway during movement
395. No weapon sheath/scabbard movement
396. No breathing animation — chest is static in all frames
397. No idle animation — characters freeze between actions
398. No blink or eye movement on mannequins
399. No facial animation at all (no face geometry exists)
400. No finger animation — hands are static mitts
401. No foot roll during stepping — feet are flat blocks
402. No wrist flexion/extension
403. No ankle pronation/supination
404. No toe spread or grip
405. No heel lift
406. No weight shift visible through hip sway
407. No shoulder shrug or drop
408. No head turn or nod
409. No spine undulation
410. No balance recovery animation (stumbling, rebalancing)
411. No impact reaction (flinching, recoiling, staggering)
412. No pain reaction (grabbing injured area, limping)
413. No exhaustion animation (slumping, heavy breathing)
414. No victory celebration animation
415. No defeat collapse animation
416. No taunt or gesture animation
417. No weapon flourish or ready animation
418. No stance transition animation (neutral→combat, combat→neutral)
419. No dodge animation (lean, sidestep, duck, jump)
420. No block animation (raise guard, brace, parry)
421. No strike wind-up animation (chamber, coil)
422. No strike follow-through animation (extension, recovery)
423. No grab entry animation (reach, penetrate, grip)
424. No grab struggle animation (resist, counter, break)
425. No clinch animation (tie-up, pummel, control)
426. No throw animation (lift, rotate, release)
427. No ground transition animation (fall, getup, roll)
428. No walk cycle variation (direction change, speed change)
429. No run cycle
430. No jump animation
431. No crouch animation
432. No slide animation
433. No vault or climb animation
434. No interact animation (pickup, drop, open)
435. No death animation
436. No respawn animation
437. No match start animation (walk-in, ready)
438. No match end animation (victory pose, handshake)
439. No replay-compatible deterministic animation system
440. No motion blur or trail effect for fast movements
441. No hit-stop or impact freeze frame
442. No screen shake on heavy impact
443. No camera animation (zoom, shake, tilt during action)
444. No sound-synchronized animation (no audio exists)
445. No particle effects (blood, sparks, dust, sweat)
446. No environmental interaction (footprints, floor scuffs)
447. No shadow animation (shadows are static blobs)
448. No dynamic lighting response to character movement
449. No post-processing effects (motion blur, depth of field)
450. Polish level: raw debug visualization, not game-ready presentation

## CATEGORY 8: PIPELINE & SYSTEMIC DEFECTS (451–500)

451. MotionBricks has zero visual evidence of producing acceptable output
452. No generative motion pipeline demonstrated working end-to-end
453. No .g1 motion clip files exist in the repository
454. No .anim animation files exist in the repository
455. No .413 float32 frame files exist in the repository  
456. No .bvh motion capture files exist in the repository
457. Game_loop renders bind-pose matrices, not live motion
458. The cooked mesh verifier passed but animation loading is broken
459. Asset pipeline produces static meshes, not animated characters
460. SKM1 format supports skinning data but ANM1 animation format is unused
461. Renderer pose buffer is written with identical data for both characters
462. Both characters display the same pose (lack of independent animation)
463. No animation controller or state machine exists in game_loop
464. PlanPhase/intent system is disconnected from animation playback
465. Combat truth (PlanPhase) has no presentation (animation) output
466. The truth→presentation boundary exists in code but produces no motion
467. Deterministic replay works for truth but has no motion to replay
468. Golden replay determinism (100-run) proven for static frames only
469. Motion service (async) exists in code but never produces usable output
470. MotionBricks Python bridge exists but generates invalid/contorted source skeletons
471. MotionBricks ONNX VQVAE decoder cannot generate — only reconstructs
472. Full PyTorch pipeline generates contorted G1 skeletons — source invalid
473. Source skeleton validation catches invalid motion but provides no fallback
474. G1→24-bone retargeting pipeline exists but has no valid source to retarget
475. World-frame calibration retargeting was proven in research but not integrated
476. Bones-seed source validation admitted clips but none were combat-usable
477. Unity/ARDY G1 checkpoint is navigation-only — cannot generate combat motion
478. No combat-conditioned MotionBricks checkpoint exists
479. No action-conditioning tensor in any available model
480. Smart-primitive keyframes exist in research but not in runtime
481. Combat-motion teacher corpus exists as research but produces no runtime clips
482. Depth-video and Seedance are offline teacher channels — no pipeline to convert to G1
483. Procedural IK fallback was falsified but no replacement exists
484. Blender-to-engine animation export pipeline exists but has no animation to export
485. FBX extraction script can convert animations but source animations don't exist
486. Rigify grip canary produced finger articulation evidence but no combat motion
487. MPFB base mesh has 163 bones — retargeting gap from G1's 34 joints
488. Retargeting bone-count mismatch (34→163 or 34→24) is unresolved for production
489. Presentation isolation (renderer can't mutate truth) is proven but moot
490. Cross-platform replay parity (Linux/Windows) is proven for truth only
491. All motion work is research-phase — nothing graduated to runtime
492. Motion pipeline is a collection of disconnected research modules
493. No single end-to-end path from "generate motion" to "see on screen"
494. 135 Meshy credits spent on static meshes — zero on motion
495. The project has spent orders of magnitude more on static assets than motion
496. Motion is the game's selling point but receives zero production investment
497. The "deep combat simulation" vision requires motion that doesn't exist
498. The "condition-driven generative motion" promise is unmet after months of development
499. Without motion, Just Dodge is a static model viewer with a HUD
500. The single largest defect: the game has no animation
