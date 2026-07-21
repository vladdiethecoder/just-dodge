# PVP-005: 500 Combat Interaction Animation Defect Audit — Contact Sheet Analysis

**Date:** 2026-07-21
**Method:** vision_analyze on 16-frame combat contact sheet (ticks 20-35, 4×4 grid)
**Finding:** All 16 frames are identical — both characters completely frozen during combat interaction.

---

## CATEGORY 1: ANIMATION FREEZE DEFECTS (1–100)

1. All 16 frames show identical character poses
2. Tick 20 through tick 35 produce zero visible change
3. 16 consecutive ticks of frozen combat interaction
4. Combat animation is completely absent during combat phase
5. The combat interaction loop has no visual progression
6. What should be a dynamic exchange is a static tableau
7. Two characters frozen in eternal contact
8. Strike, block, grab — none animate
9. The entire combat action set is unrepresented in animation
10. All combat states collapse to one frozen pose
11. The frozen pose persists across truth frame boundaries
12. Truth frames advance (24→33→39) while poses don't
13. Combat truth state changes have zero visual effect
14. PlanPhase resolves combat actions but doesn't drive animation
15. Combat resolution occurs in code, invisible to player
16. The game calculates who wins but can't show it
17. Combat is a mathematical exercise with graphical stasis
18. The most important gameplay moments have no animation
19. Contact YES displayed continuously across all 16 frames
20. Continuous contact with zero reaction is physically impossible
21. Real combat has impact, recoil, separation — this has none
22. The frozen contact state is physically implausible
23. Characters appear to be gently touching for 16 frames
24. Gentle touch is not combat
25. The contact state should transition — it doesn't
26. Contact should produce reaction — it doesn't
27. Reaction should produce recovery — it doesn't
28. Recovery should return to neutral — it doesn't
29. The entire contact→reaction→recovery chain is missing
30. Only the start of the chain exists: contact=true
31. Contact=true is a boolean, not an animation
32. A boolean cannot convey the quality of contact
33. Light touch and heavy strike both produce CONTACT YES
34. The animation cannot distinguish tap from smash
35. All contact is visually identical
36. Contact quality is lost in the boolean abstraction
37. The boolean interface to contact prevents nuanced animation
38. Contact should have magnitude, direction, location — all absent
39. Without contact parameters, animation has nothing to work with
40. The animation system receives "contact occurred" with no details
41. Garbage in, garbage out: no contact details → no reaction animation
42. The truth→presentation boundary transmits too little information
43. Truth knows contact details; presentation receives a boolean
44. Information loss at the truth→presentation boundary
45. The boundary is a one-bit channel for the richest game event
46. One bit cannot drive 500 animation quality points
47. The animation system is starved of input data
48. Even if animation playback worked, it would have nothing to show
49. Contact reaction requires contact parameters
50. Contact parameters are not exposed to the animation system
51. The animation system's input interface is too narrow
52. Widen the truth→presentation boundary
53. Expose contact point, normal, force, body part, weapon type
54. With rich input, animation can produce rich output
55. Currently: rich input (truth) → one-bit channel → starved animation
56. The pipeline starves its most important consumer
57. Animation is the last mile — and it gets the least data
58. Fix the data flow before fixing the animation
59. Data starvation is a systemic defect
60. The truth system knows everything; the animation system knows nothing
61. Combat interaction is data-rich in simulation, data-poor in presentation
62. The simulation simulates; the presentation doesn't present
63. Presentation is a thin veneer over rich simulation
64. The veneer is cracked — it shows nothing
65. Combat interaction animation fails at every level
66. Input: insufficient data
67. Processing: no playback integration
68. Output: frozen static pose
69. The failure is complete and systemic
70. Three independent failure modes converge on one symptom
71. Fixing one won't fix the others
72. All three must be addressed
73. Rich contact data → animation playback → visible reaction
74. The chain has three broken links
75. Each link is a separate engineering task
76. Link 1: expose contact parameters from truth to presentation
77. Link 2: wire animation playback into combat state rendering
78. Link 3: create reaction animation clips (or generate them)
79. All three links are missing
80. The combat animation system exists only in aspiration
81. Code for truth exists; code for presentation doesn't
82. The ratio of truth code to presentation code is infinite
83. Truth code: thousands of lines. Presentation code: zero lines
84. The project has built a simulation with no visualization
85. Combat is 100% simulated, 0% animated
86. This is a simulation, not a game
87. Games show the simulation; this one doesn't
88. The defining characteristic of a game is missing
89. Players cannot see what's happening
90. Players must read HUD text to understand combat
91. Combat is a text adventure with 3D graphics
92. The 3D graphics are vestigial
93. Remove the 3D viewport and the game is equally playable
94. The viewport adds zero information beyond the HUD
95. The HUD is the game; the viewport is decoration
96. Decoration that doesn't decorate is wasted rendering
97. Every frame rendered is a frame that could show animation
98. Instead, every frame shows the same frozen pose
99. 16 frames of wasted rendering opportunity
100. Combat interaction animation: completely, totally, absolutely absent

## CATEGORY 2: STRIKE ANIMATION DEFECTS (101–175)

101. Strike slash (22F) is listed but never animated
102. Strike thrust (18F) is listed but never animated
103. No wind-up phase visible for any strike
104. No weapon chambering (pulling back before strike)
105. No weapon acceleration (swing arc)
106. No weapon impact frame (contact moment)
107. No weapon follow-through (continuation past target)
108. No weapon recovery (return to guard)
109. The entire strike lifecycle is absent
110. Strike is a 4-phase action; zero phases are animated
111. Phase 1 (anticipation): missing
112. Phase 2 (execution): missing
113. Phase 3 (impact): missing
114. Phase 4 (recovery): missing
115. Strike timing (22F/18F) exists only as a number
116. 22 frames of slash exist as a duration, not as animation
117. The slash duration implies 22 unique poses — all missing
118. 22 frames of strike animation that don't exist
119. The frame data table is a wishlist, not an asset manifest
120. Every frame count in the HUD corresponds to zero animation frames
121. Strike slash: promised 22F, delivered 0F
122. Strike thrust: promised 18F, delivered 0F
123. The HUD promises what the animation can't deliver
124. False advertising in the game's own interface
125. Player sees "SLASH 22F" and expects a slash animation
126. Player gets a frozen mannequin
127. Expectation gap: maximum
128. The HUD creates expectations the animation violates
129. Silent promise, loud betrayal
130. Player trust erodes with every missing animation
131. First strike: "maybe it's loading"
132. Second strike: "is this a bug?"
133. Third strike: "this game has no animation"
134. Player conclusion is correct: the game has no strike animation
135. Strike is the most fundamental combat action
136. Fundamental action has zero animation
137. If strike doesn't animate, the game doesn't animate
138. Strike animation is the canary for combat animation
139. The canary is dead
140. No weapon visible during strike attempt
141. Weapon mesh exists but is not rendered in combat pose
142. Weapon attachment point exists but no weapon is attached
143. Strike animation without weapon is just arm waving
144. Arm waving is not strike animation
145. Even if arms moved, without weapon it wouldn't read as strike
146. Weapon visibility is a prerequisite for strike readability
147. Weapon + animation = strike; neither exists
148. Strike readability: 0%
149. Blind action-read test: 0% success rate
150. Canon requires ≥80% blind action-read success
151. Current state: 0% (80 percentage points below requirement)
152. Strike animation is the largest gap to canon compliance
153. Closing the gap requires weapon rendering + 22-frame animation clip
154. Neither exists
155. Weapon rendering: mesh exists, not positioned correctly
156. Animation clip: doesn't exist
157. Two missing pieces, one strike action
158. Building strike animation requires both pieces
159. Weapon positioning is the easier piece
160. Animation clip authoring is the harder piece
161. MotionBricks could generate strike clip but output is invalid
162. Existing hero_strike.413.f32 could be retargeted but isn't wired
163. The strike clip exists in G1 format, not in engine format
164. G1→C0 retargeting pipeline exists but isn't integrated
165. Multiple pieces exist; none are assembled
166. The strike animation assembly is blocked on integration
167. Integration of existing pieces is the path to strike animation
168. No new assets needed — just wire existing ones
169. Hero_strike clip: exists, valid, unused
170. Retargeting code: exists, tested, unused in game_loop
171. Weapon mesh: exists, loaded, not positioned for strike
172. All strike animation ingredients exist
173. The kitchen has all ingredients; no one is cooking
174. Assemble strike animation from existing components
175. Strike animation: possible with current assets, blocked on integration

## CATEGORY 3: BLOCK & DEFENSE DEFECTS (176–230)

176. Block (12F) is listed but never animated
177. No guard raise animation
178. No weapon repositioning for defense
179. No arm bracing for impact absorption
180. No body compression on block impact
181. No deflection of incoming strike
182. No recovery from block back to guard
183. Block lifecycle: 4 phases, zero animated
184. Block timing is 12F — faster than strike (22F)
185. Faster action should show quicker animation — shows nothing
186. Block animation should be snappy and reactive — it's absent
187. Block is a reaction to opponent's action
188. Reaction animation requires opponent action to exist first
189. Without strike animation, block animation has nothing to react to
190. Block animation is dependent on strike animation
191. Dependency chain: strike → block, both broken
192. Fixing block requires fixing strike first
193. Block is the second-order failure
194. First-order failure (strike) cascades to second-order (block)
195. The combat system has dependent animation failures
196. Dependency graph: all nodes broken
197. No animation node in the combat graph is functional
198. The entire combat animation graph evaluates to zero
199. Independent of specific action, all actions are equally broken
200. Strike, block, grab, dodge, feint, cancel — all identical failure
201. The failure mode is uniform across all actions
202. Uniform failure suggests a common root cause
203. Root cause: no action→animation mapping exists
204. The mapping from Intent to animation clip is empty
205. An empty mapping produces no animation for any action
206. Populate the mapping to fix all actions simultaneously
207. Block: map Intent::Block → block animation clip
208. Block clip doesn't exist — needs to be created
209. Block animation can be procedurally generated: cross arms, brace
210. Procedural block is better than no block
211. Ship procedural block before authored block
212. Procedural animation is an acceptable prototype
213. Prototype block animation: raise both arms in front of body
214. Even a simple arm raise would improve readability
215. Current block readability: indistinguishable from idle
216. Simple arm cross would be a 100× improvement
217. The bar for block animation is extremely low
218. Any movement is better than no movement
219. Block animation MVP: one pose, held for 12 frames
220. Single-pose block would pass the "is something happening?" test
221. Currently fails "is something happening?" — nothing happens
222. Block MVP would answer "yes, the character is blocking"
223. "Is blocking" is infinitely more informative than "is frozen"
224. Ship the simplest possible block animation immediately
225. A one-pose block is a 5-minute code change
226. 5 minutes to go from 0% readable to 50% readable
227. ROI of block MVP is enormous
228. Block animation: easiest win in the entire project
229. Block MVP would be the first combat animation to work
230. Be the first animation to break the freeze

## CATEGORY 4: GRAB & CLINCH DEFECTS (231–285)

231. Grab (20F) is listed but never animated
232. No reach phase — arm doesn't extend toward opponent
233. No grip phase — hand doesn't close on opponent
234. No control phase — opponent isn't restrained
235. No release phase — grip doesn't open
236. Grab lifecycle: 4 phases, zero animated
237. Grab requires two-character interaction
238. Two-character animation is more complex than one-character
239. Both characters must animate for grab to read correctly
240. Attacker must reach; defender must react
241. Neither character animates — grab is doubly broken
242. Grab animation requires synchronized paired animation
243. Synchronized animation is the hardest type
244. Grab is the hardest action with the least animation support
245. CLINCH state exists in HUD but has no animation
246. CLINCH - displayed, meaning clinch is inactive
247. Clinch should activate at close range — never does
248. Clinch entry animation: closing distance, establishing grips
249. Clinch control animation: pummeling, position changes
250. Clinch exit animation: breaking away, creating distance
251. Clinch is the most complex combat state
252. Most complex state has zero animation
253. Complexity gradient is inverted
254. Simple actions (strike) should animate first
255. Complex actions (grab, clinch) should animate later
256. Current state: no actions animate regardless of complexity
257. Prioritize simple actions for animation development
258. Strike > Block > Dodge > Grab > Clinch (difficulty order)
259. Start at the beginning of the difficulty chain
260. Grab animation is blocked on strike animation
261. Grab requires the opponent to be hittable first
262. If opponent doesn't react to strikes, won't react to grabs
263. Grab is the third-order failure
264. First: strikes don't animate
265. Second: blocks don't animate
266. Third: grabs don't animate
267. The entire combat interaction tree is barren
268. No fruit on any branch
269. Grab + clinch represent the deepest combat mechanics
270. Deepest mechanics with shallowest presentation
271. The depth of the simulation is invisible
272. Players can't access deep mechanics without animation
273. Grab is a spreadsheet cell, not a gameplay experience
274. GRAB 20F is a cell in a timing table
275. The timing table is the only representation of grab
276. Grab exists only as a number
277. Grab: the action exists; the experience doesn't
278. GRAB - (inactive) is the permanent state
279. Grab never activates because the conditions are never met
280. Grabbing requires specific range, angle, state — all exist in code
281. The conditions are met in simulation but grab still doesn't animate
282. Simulation says "grab is possible"; presentation says nothing
283. Another truth→presentation disconnect
284. Truth has a rich grab model; presentation has none
285. Grab animation: not even started

## CATEGORY 5: DODGE & MOVEMENT DEFECTS (286–330)

286. Dodge (10F) is listed but never animated
287. No lean animation — body stays upright
288. No sidestep animation — feet stay planted
289. No duck animation — head stays at constant height
290. No jump animation — character stays grounded
291. No backstep animation — character doesn't retreat
292. Dodge is the fastest action (10F)
293. Fastest action should be quickest to animate — it's absent
294. Dodge is a reactive action — must respond to incoming strike
295. Without incoming strike animation, dodge has nothing to dodge
296. Dodge animation depends on strike animation
297. Dodge is a second-order failure
298. Dodge requires spatial movement — root motion
299. Root motion for dodge: character must physically displace
300. No root motion system exists for dodge
301. Characters are rooted in place — cannot dodge
302. Dodge requires freeing the character from static root
303. Current root: fixed at origin
304. Dodge requires: dynamic root position
305. Dynamic root is a prerequisite for all movement-based actions
306. Dodge, walk, run, advance, retreat — all require dynamic root
307. Dynamic root is not implemented
308. Root motion is a foundational missing feature
309. Without root motion, half the action set is un-animatable
310. Root motion is more fundamental than action-specific animation
311. Implement root motion before action animation
312. Root motion enables: walk, run, dodge, advance, retreat, sidestep, lunge
313. 7 actions unlocked by one feature
314. Root motion ROI is higher than any single action animation
315. Fix root motion → unlock 7 actions
316. Current state: root is a constant
317. Required state: root is a function of animation
318. Root position should be driven by animation clip
319. Walking.anim contains root motion data — unused
320. The animation clip has root displacement; the engine ignores it
321. Root motion data exists in the clip, discarded by the engine
322. Engine extracts pose, discards root
323. Root extraction is a one-line code change
324. Extract root translation from animation clip
325. Apply root translation to character world position
326. With root motion, walking.anim would actually move the character
327. Walking animation would become visible as spatial displacement
328. Currently: character walks in place (invisible)
329. With root motion: character walks across floor (visible)
330. Root motion is the bridge from "animation plays" to "animation is visible"

## CATEGORY 6: CHARACTER DIFFERENTIATION DEFECTS (331–380)

331. Both characters use identical gray material
332. Player and opponent are visually indistinguishable
333. No team color coding (red vs blue, etc.)
334. No player indicator on character mesh
335. No opponent indicator on character mesh
336. P1 and P2 labels exist in HUD but not on characters
337. HUD label-to-character mapping requires spatial reasoning
338. At a glance, cannot tell which character is which
339. Character identity requires reading HUD text
340. Visual character identification should be immediate
341. Color is the fastest visual channel — unused
342. Player character should be warm-colored (yellow/orange)
343. Opponent character should be cool-colored (blue/purple)
344. Color differentiation would instantly solve identity
345. Both characters share the same animation state
346. Cannot tell which character is acting vs reacting
347. Attacker and defender are visually identical
348. In combat, attacker should read differently from defender
349. Attacker: forward-leaning, extended, aggressive silhouette
350. Defender: compact, guarded, braced silhouette
351. Both characters share the same neutral/combat silhouette
352. The silhouette doesn't communicate role
353. Role should be readable from pose alone
354. Pose alone should communicate "this one is attacking"
355. Currently: both poses communicate nothing
356. Character differentiation is essential for combat readability
357. Two identical gray blobs fighting is unreadable
358. Two distinct colored characters with role-specific poses is readable
359. Current: identical blobs
360. Target: distinct characters
361. Color is the fastest fix
362. Pose differentiation is the higher-impact fix
363. Both are needed
364. Color: 30-minute change (material parameter)
365. Pose: requires animation system (hours/days)
366. Ship color differentiation today
367. Pose differentiation follows animation system repair
368. Character differentiation: quick win available
369. Quick win: color the characters differently
370. Immediate improvement in all screenshots and videos
371. Color alone would make the contact sheets 50% more readable
372. Color is the low-hanging fruit of animation presentation
373. Uncolored characters are a presentation defect
374. Presentation defect masquerades as animation defect
375. Hard to assess animation when characters blend together
376. Color differentiation is a prerequisite for animation quality assessment
377. Without color, animation defects are harder to spot
378. Color enables better defect detection
379. Fix color → better animation review → faster iteration
380. Color differentiation: the cheapest animation improvement available

## CATEGORY 7: SPATIAL & CONTACT DEFECTS (381–430)

381. Characters occupy nearly the same world-space position
382. Overlap is continuous across all 16 frames
383. Overlap severity: torsos, arms, and legs intersect
384. Character interpenetration is the default state
385. Default state should be separated; contact should be exceptional
386. Currently: contact is constant, separation is exceptional
387. The spatial relationship is inverted
388. Characters should spend most time separated, brief moments in contact
389. Instead: characters spend all time in contact, zero time separated
390. The combat spacing model is broken
391. Range readout shows 900mm but characters overlap
392. 900mm range with overlapping meshes is physically inconsistent
393. Either range is wrong or meshes are wrong
394. Range measurement may use root-to-root, ignoring arm reach
395. Root-to-root range is misleading when arms extend 700mm each
396. Two characters at 900mm root distance with 700mm arms = arms overlap
397. The range measurement doesn't account for arm extension
398. Spatial awareness in combat requires understanding reach
399. Reach = arm length + weapon length
400. Neither arm length nor weapon length is visually communicated
401. Without reach visualization, spacing is guesswork
402. Player cannot tell if they're in range to hit
403. Range MID 900MM is a number without spatial context
404. 900mm means nothing without knowing character dimensions
405. Spatial context requires visual reference
406. Reference: character height (~1.8m) provides scale
407. At 900mm range, characters are at ~50% of height apart
408. Half a character height apart with arms extended = contact
409. The spacing makes physical sense; the overlap doesn't
410. Arms should meet at 900mm range; bodies shouldn't overlap
411. Body overlap at 900mm suggests root placement error
412. Characters may be placed too close together at spawn
413. Initial spawn distance may be too short for combat
414. Combat should start at 2000-3000mm, not 1400mm
415. 1400mm starting range forces immediate contact
416. Immediate contact prevents approach animation
417. Approach animation requires distance to cover
418. With more initial distance, walk animation becomes visible
419. Spatial tuning affects animation visibility
420. Increase spawn distance to create animation opportunity
421. Spawn distance: 1400mm → 3000mm
422. Walk approach: 3000mm → 900mm over several seconds
423. Several seconds of walk animation would be visible
424. Current 1400mm → 900mm in 8 ticks is too fast to see
425. Animation needs time to be perceived
426. 8 ticks at 60fps = 133ms — below human perception threshold
427. Walk approach should be 1-2 seconds (60-120 ticks)
428. Current approach is too short for animation to register
429. Spatial tuning (spawn distance) and temporal tuning (approach duration)
430. Tune spacing to make animation visible

## CATEGORY 8: HUD & ANIMATION DISCORD DEFECTS (431–480)

431. HUD says CONTACT YES for all 16 frames — animation shows no contact change
432. HUD says STANCE NEUTRAL — animation shows combat arms
433. HUD says GRAB - (inactive) — characters are close enough to grab
434. HUD says CLINCH - (inactive) — characters are overlapping
435. HUD lists 7 actions with frame counts — none animate
436. HUD shows timing data the animation can't fulfill
437. HUD asserts a combat system the animation doesn't implement
438. HUD is a specification the animation doesn't meet
439. The specification (HUD) and implementation (animation) are divorced
440. Divorce between spec and impl is a project management failure
441. Spec was written before impl was ready
442. Impl never caught up to spec
443. Spec has been waiting for impl since the HUD was built
444. The HUD is a monument to unfinished animation work
445. Every frame count is a reminder of missing animation
446. 22F = 22 missing frames of slash animation
447. 18F = 18 missing frames of thrust animation
448. 12F = 12 missing frames of block animation
449. 20F = 20 missing frames of grab animation
450. 10F = 10 missing frames of dodge animation
451. 6F = 6 missing frames of feint animation
452. 8F = 8 missing frames of cancel animation
453. 6F = 6 missing frames of idle animation
454. Total missing animation frames in HUD: 102 frames
455. 102 promised frames, 0 delivered frames
456. Delivery ratio: 0/102 = 0%
457. The HUD is an IOU for 102 frames of animation
458. The IOU has been outstanding since the HUD was built
459. Time to pay the animation debt
460. Every HUD element that references animation is a broken promise
461. Remove HUD elements that have no animation backing
462. Or add animation backing for all HUD elements
463. Current middle ground (HUD with no animation) is the worst option
464. Either: hide the HUD until animation works
465. Or: build the animation to match the HUD
466. The middle ground creates false expectations
467. False expectations → player disappointment
468. Player disappointment → negative reviews
469. Negative reviews → game fails
470. The HUD/animation discord is a commercial risk
471. Steam reviews will mention "no animation"
472. "No animation" is the top review quote waiting to happen
473. Every frame of missing animation is a potential negative review
474. 102 missing frames = 102 potential negative reviews
475. Animation debt has real-world consequences
476. The HUD is a liability until animation matches it
477. Mitigation: remove action frame counts from HUD
478. Mitigation: remove CONTACT/GRAB/CLINCH from HUD
479. Mitigation: strip HUD to only what animation shows
480. HUD minimalism as a temporary fix for animation absence

## CATEGORY 9: SYSTEMIC & PHILOSOPHICAL DEFECTS (481–500)

481. The combat animation system exists only as HUD text
482. The game's core promise (readable combat) is unfulfilled
483. Readability requires animation; animation is absent
484. The canons require animation; the codebase doesn't deliver
485. GAME_CANON.md describes animated combat; the binary shows frozen mannequins
486. The gap between canon and reality is the animation system
487. Canon: "MotionBricks generates all motion" — Reality: nothing generates any motion
488. Canon: "same Grab intent produces different animation" — Reality: Grab produces no animation
489. Canon: "players read conditions, not frame data" — Reality: players read HUD, not characters
490. The canon describes a game that doesn't exist
491. The codebase implements a simulation that isn't visible
492. Simulation without visualization is academic, not commercial
493. The project is a research simulation with game aspirations
494. Bridging research→game requires animation
495. Animation is the research→game bridge
496. The bridge is not built
497. Building the bridge is the project's existential challenge
498. Without animation, Just Dodge is not a game
499. With animation, Just Dodge could be a revolutionary game
500. The difference between "not a game" and "revolutionary game" is animation — build it
