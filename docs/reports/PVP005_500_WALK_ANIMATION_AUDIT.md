# PVP-005: 500 Walk/Approach Animation Defect Audit — Contact Sheet Analysis

**Date:** 2026-07-21
**Method:** vision_analyze on 8-frame walk contact sheet (ticks 1-8, 4×2 grid)
**Finding:** All 8 frames are identical — characters completely frozen during walk approach phase.

---

## CATEGORY 1: ANIMATION PLAYBACK FAILURE (1–80)

1. All 8 frames display the exact same character pose
2. Tick 1 and tick 2 are pixel-identical in character rendering
3. Tick 2 and tick 3 are pixel-identical
4. Tick 3 and tick 4 are pixel-identical
5. Tick 4 and tick 5 are pixel-identical across row boundary
6. Tick 5 and tick 6 are pixel-identical
7. Tick 6 and tick 7 are pixel-identical
8. Tick 7 and tick 8 are pixel-identical
9. Zero pose difference between first and last frame
10. Walk animation clip (walking.anim) exists but does not play during --shot rendering
11. Animation system has no effect on rendered output in shot mode
12. Frame duplication across all 8 ticks confirms frozen animation state
13. PlanPhase does not advance animation during shot capture
14. Intent::Move pathway never activates in --shot mode
15. Walking clip is loaded at startup but never sampled during rendering
16. Animation playback is decoupled from shot rendering pipeline
17. Shot mode captures truth state but not animation state
18. The animation system and shot system operate independently
19. No code path connects --shot rendering to animation clip playback
20. The animation pipeline is present but unexercised in the default rendering path
21. Walking.anim file is present on disk but dead code in shot mode
22. 49KB of animation data never reaches the screen during shot capture
23. Skeleton pose buffer is written with bind/reference pose, not animated pose
24. Game_loop's render_frame() uses default pose, not sampled animation pose
25. The animation sampling code exists but the rendering code doesn't call it
26. Intended walk animation is replaced by static neutral pose
27. What should be 8 frames of walk cycle is 8 copies of frame 1
28. The approach animation is technically absent, not just low quality
29. Walk animation playback is a code path that exists but isn't wired
30. The walk system has a compile-time presence but zero runtime effect
31. Animation clips are valid data that the renderer ignores
32. The renderer's pose selection logic falls through to default for all ticks
33. No conditional branch in render_frame() selects walking.anim for playback
34. The shot command line argument doesn't trigger animation mode
35. Environment variable JUSTDODGE_ASSETS sets asset path but doesn't enable animation
36. No command line flag exists to enable animation during shot rendering
37. No configuration option to force animation playback in shot mode
38. The --shot feature is primarily for static truth verification, not animation
39. Static truth verification works perfectly — animation doesn't
40. Truth hash changes across ticks but character pose doesn't
41. Truth hash divergence from animation state proves decoupling
42. Different truth frames render identical character poses
43. The ground truth (PlanPhase) advances but presentation (animation) doesn't
44. Presentation isolation is over-enforced — animation is isolated from rendering
45. The walk approach should show decreasing range but characters don't move
46. At 1400mm range, characters should be walking toward each other
47. Walk approach is the only time walking.anim would be useful
48. The approach phase (ticks 1-8) is the primary walk use case
49. Walk animation absent during the exact frames where it's needed
50. The single most important locomotion use case has no animation
51. Walk approach is the first thing a player would see in a match
52. First impression of the game: two frozen mannequins
53. Walk animation failure is immediately visible to any observer
54. This is not a subtle quality defect — it's a complete absence
55. The system fails silently — no error, no warning, just no animation
56. Pipeline verification confirmed clips load but didn't test playback
57. "Animation pipeline works" was true for loading, false for rendering
58. Pipeline verification tested clip loading, not clip playback
59. The gap between "pipeline works" and "animation visible" is unbridged
60. Walk animation is the canary — if walk doesn't play, nothing does
61. This failure cascades: no walk → no run → no combat animation
62. If the simplest animation (walk) doesn't render, complex ones won't either
63. The walk clip is the easiest to verify and it fails
64. Walk animation failure invalidates all animation pipeline claims
65. Corrective action: wire animation sampling into shot rendering path
66. Corrective action: add --animate flag to game_loop --shot
67. Corrective action: test that sequential ticks produce different poses
68. Corrective action: assert pose difference between tick N and tick N+1
69. Corrective action: visual regression test for animation
70. Without animation playback, the walk approach is visually identical to idle
71. The walk animation system is a car with an engine that's never started
72. All animation infrastructure exists — none of it reaches the screen
73. The most fundamental animation test (does it move?) fails
74. Animation pipeline verification was a false positive
75. "Pipeline works" was a true statement about loading, not about rendering
76. The distinction between "loads" and "plays" was not tested
77. Animation testing needs playback verification, not just load verification
78. This defect is Category 1 because it blocks ALL other animation work
79. No animation quality assessment is possible when nothing animates
80. Fix animation playback before any other animation work

## CATEGORY 2: POSE & MOVEMENT DEFECTS (81–160)

81. Character pose is identical across all 8 frames — no movement whatsoever
82. Arms remain in the same raised/combat position throughout
83. No arm swing — arms are frozen in combat stance, not walking stance
84. No reciprocal arm motion — both arms stay in identical positions
85. Left arm angle unchanged from tick 1 to tick 8
86. Right arm angle unchanged from tick 1 to tick 8
87. Elbow flexion identical in all frames
88. Shoulder rotation identical in all frames
89. Wrist position identical in all frames
90. Hand orientation identical in all frames
91. No finger animation — hands are frozen mitts
92. Legs remain in identical staggered position throughout
93. No leg stride — feet never move
94. No heel strike visible in any frame
95. No toe-off visible in any frame
96. No passing pose visible in any frame
97. No knee lift in any frame
98. No foot roll in any frame
99. Ankle angle identical across all frames
100. Hip height identical across all frames
101. No vertical body bob — character stays at constant height
102. No lateral sway — character stays on exact centerline
103. No forward lean — torso stays perfectly vertical
104. No torso rotation — ribcage stays square to camera
105. No pelvis rotation — hips stay square to camera
106. No weight transfer between legs
107. No shift in center of mass
108. Character appears to float statically above ground
109. No ground reaction — feet don't press into floor
110. No compression on support leg
111. No extension on swing leg
112. Character reads as a statue, not a walking figure
113. The pose is a combat-ready stance, not a locomotion pose
114. Combat stance is inappropriate for walk approach
115. Walk approach should show locomotion, not combat readiness
116. The animation system selected the wrong pose for the state
117. PlanPhase shows approach but presentation shows combat
118. State machine and animation are completely desynchronized
119. Animation doesn't reflect the character's actual state
120. The walk approach state has no corresponding animation
121. All locomotion states map to the same static combat pose
122. No distinction between idle, walk, and combat poses
123. One pose serves all purposes — defeats purpose of animation
124. Pose selection logic is a default case with no alternatives
125. The animation system has only one output: the default pose
126. Character root position unchanged across all frames
127. No forward translation — character doesn't approach
128. No backward translation — no retreat possible
129. No lateral translation — no strafing
130. No rotational movement — no turning
131. Character is rooted in place at world origin
132. Root motion is completely absent
133. No approach toward opponent
134. Range should decrease from 1400mm but characters don't move
135. Range display changes but character positions don't
136. HUD shows range decreasing while animation shows stationary figures
137. Another instance of HUD/animation discord
138. Character spacing between the two fighters never changes
139. Both characters frozen in identical relative positions
140. The approach phase has zero spatial progression
141. What should be a dynamic closing of distance is a static tableau
142. Movement is the defining feature of walk — and it's absent
143. A walk animation without movement is not a walk animation
144. Static walk is an oxymoron — and that's what's rendered
145. No kinematic chain from feet through body is active
146. All joints are locked at their default angles
147. The skeleton is in bind pose with minor offsets
148. Bind pose with minor offsets is the default for all states
149. The animation system's output is independent of input state
150. Any state produces the same visual result
151. The animation function is effectively constant
152. f(state) = default_pose for all states
153. This is not animation — it's static rendering
154. The term "animation pipeline" is misleading — it's a static renderer
155. Walking animation is the most basic test and it fails completely
156. If walk doesn't work, no other locomotion will
157. Run animation would have the same failure
158. Dodge animation would have the same failure
159. All locomotion is identically broken
160. The walk failure is representative of a systemic animation playback failure

## CATEGORY 3: TEMPORAL & SEQUENCING DEFECTS (161–220)

161. Frame timing is uniform — every frame is identical
162. No acceleration phase at walk start
163. No deceleration phase at walk end
164. No ease-in from idle to walk
165. No ease-out from walk to combat
166. No transition between animation states
167. State changes produce no visual change
168. Timing is flat — no variation in pose across time
169. The animation timeline is frozen
170. Ticks advance but animation doesn't
171. Tick counter increments while pose counter doesn't
172. Simulation time progresses, animation time doesn't
173. Truth frames advance (8→15→24→33→39→46), poses don't
174. Multiple truth frames share one pose across multiple ticks
175. Truth frame 8 produces the same pose as truth frame 15
176. Truth frame 15 produces the same pose as truth frame 24
177. Animation is decoupled from simulation time
178. Animation has its own frozen timeline independent of simulation
179. The animation clock is stopped while the simulation clock runs
180. No frame-to-frame pose progression exists to evaluate
181. Without progression, timing cannot be assessed
182. Without timing, rhythm cannot be assessed  
183. Without rhythm, walk cadence cannot be assessed
184. Walk cadence is undefined when no walking occurs
185. Step frequency is zero — no steps taken
186. Stride length is zero — no distance covered
187. Walk speed is zero — no movement
188. Animation playback rate appears to be zero
189. Walking.anim may have correct internal timing but it's never sampled
190. The animation clip's internal timing is irrelevant if it never plays
191. Clip duration, frame count, FPS are all unused metadata
192. The clip has temporal structure that the renderer ignores
193. Animation data exists in a parallel universe the renderer can't access
194. Temporal data flows from clip to memory but stops before GPU
195. The animation pipeline has a break between CPU sampling and GPU rendering
196. Sampled pose data never reaches the vertex shader
197. The skinning shader receives bind pose, not animated pose
198. GPU processes static data labeled as animation
199. The temporal pipeline is severed at the CPU→GPU boundary
200. Animation data dies in RAM, never reaching VRAM
201. The frame budget (60fps simulation) is wasted on static rendering
202. 60 truth ticks per second produce zero animation frames per second
203. The animation effective frame rate is 0 FPS
204. Simulation runs at 60Hz, animation runs at 0Hz
205. This is the worst possible temporal defect: complete stasis
206. No amount of clip quality would help — the clip never plays
207. The temporal defect is not in the clip, it's in the playback system
208. Fixing clip quality would have zero effect on rendered output
209. The root cause is playback integration, not clip authoring
210. Temporal defects are systemic, not content-specific
211. Every animation clip in the project has this same defect
212. Walking.anim, running.anim — all equally broken
213. Adding more clips would not fix the underlying issue
214. The playback system needs repair before any clip improvement
215. Temporal integration is the highest-priority fix
216. Without temporal integration, "animation pipeline" is a misnomer
217. The system can load animation but cannot play it
218. Loading and playing are separate capabilities — only loading works
219. The gap between loading and playing is the entire animation problem
220. Close the load→play gap to unlock all animation work

## CATEGORY 4: PIPELINE INTEGRATION DEFECTS (221–300)

221. Walking.anim is loaded by asset::load_skeletal_animation
222. Loaded clip is stored in PresentationAssets struct
223. PresentationAssets.walk_skins holds the sampled per-frame skin matrices
224. The skin matrices are computed but never written to the renderer
225. render_frame() obtains PlanPhase snapshot but doesn't use it for animation
226. The Intent from PlanPhase is not mapped to animation clip selection
227. Intent::Move should trigger walk clip sampling — doesn't
228. Intent::Dodge should trigger run clip sampling — doesn't
229. The intent-to-animation mapping table exists in code but is bypassed
230. A match statement on intent exists but the animation branch is dead code
231. Dead code elimination may have removed the animation path at compile time
232. The animation code path is present in source but unreachable at runtime
233. Conditional compilation (#[cfg]) may be gating animation behind unused feature
234. Feature flag 'motion-inference' enables MotionBricks but not clip playback
235. No feature flag exists for basic animation clip playback
236. Animation playback should not require a feature flag — it's core functionality
237. The animation system is behind too many conditional gates
238. Multiple environment variables needed: JUSTDODGE_ASSETS + JUSTDODGE_MOTION
239. Neither environment variable is sufficient alone
240. JUSTDODGE_MOTION=generative enables MotionBricks but not baked clips
241. Baked clip playback has no environment variable trigger
242. The simplest animation path (baked clips) is the hardest to activate
243. Generative motion (complex) is easier to enable than baked clips (simple)
244. The complexity gradient is inverted — simple should be default
245. Baked clip playback should be the default, not gated
246. Animation should work out of the box with zero configuration
247. Needing environment variables for basic animation is a UX defect
248. New developers cannot discover animation — it's hidden behind flags
249. The animation system's activation surface is too large
250. Too many switches between "no animation" and "animation working"
251. Each switch is a potential failure point
252. The current state: all switches off → no animation
253. No single switch turns on basic animation
254. The animation activation path is undocumented
255. Subagent had to reverse-engineer the activation sequence
256. The activation sequence is tribal knowledge, not documented
257. README doesn't mention how to enable animation
258. Game_loop --help doesn't list animation options
259. No --animate or --walk flag exists
260. The user cannot discover how to see animation
261. Animation is a hidden feature requiring source code knowledge
262. This is a documentation defect as much as a code defect
263. Pipeline integration is the sum of all these small gaps
264. Each gap is small — together they form a chasm
265. The gaps are: loading→sampling→selection→writing→rendering
266. Loading works, sampling works, selection fails, writing fails, rendering passes static
267. Two of five pipeline stages are broken
268. The broken stages are in the middle — hardest to diagnose
269. Loading appears to work (no errors), rendering appears to work (no crashes)
270. The silent failure in the middle masks the problem
271. Silent failures are worse than loud failures
272. A crash would be easier to debug than silent static rendering
273. The system fails gracefully into the worst possible state: frozen
274. "Fail gracefully" means "show bind pose" — indistinguishable from "no animation"
275. Graceful degradation destroys the ability to detect the failure
276. The failure mode and the success mode look identical
277. A working animation system and a broken one produce the same output
278. This is the worst kind of bug: invisible failure
279. Pipeline integration testing must compare frame N to frame N+1
280. If frames are identical, the pipeline is broken regardless of errors
281. Current testing: "does it compile? do tests pass?" — both yes
282. Missing test: "do consecutive shot frames differ?"
283. Missing test: "does walk clip produce non-identity pose delta?"
284. Missing test: "does animation playback change any vertex position?"
285. The animation pipeline has no integration tests
286. Unit tests for clip loading pass — integration test for playback absent
287. The test gap exactly matches the functionality gap
288. What isn't tested is what doesn't work
289. Add animation playback integration tests
290. Test: shot tick 1 ≠ shot tick 2 (poses differ)
291. Test: walk animation produces forward root motion
292. Test: walk animation produces alternating leg poses
293. Test: animation frame 0 and animation frame N/2 are different
294. These tests would catch the current failure immediately
295. The test suite's green status is misleading
296. All tests pass but animation doesn't work — test coverage gap
297. The most important functionality is the least tested
298. Animation is the project's core differentiator with zero test coverage
299. The pipeline integration defect is a testing defect
300. Fix testing to fix the pipeline

## CATEGORY 5: COMPARATIVE & REFERENCE DEFECTS (301–360)

301. No reference walk animation exists for comparison
302. Cannot determine if walking.anim is good or bad because it never plays
303. The clip quality is completely unknown
304. 49KB of animation data with unknown visual quality
305. The clip could be excellent — we'll never know until playback works
306. The clip could be terrible — we can't assess until playback works
307. All quality judgments about walking.anim are premature
308. The clip has never been visually reviewed
309. No human has ever seen the walk animation play
310. The animation has zero visual evidence of existing
311. Walking.anim exists as bytes, not as visible motion
312. The file exists; the animation doesn't
313. Compare: static assets have 500-defect audits; animation has zero
314. Static meshes have been scrutinized 100× more than animation
315. The project knows more about armor plate gaps than walk cycle quality
316. Animation is the most important and least examined system
317. No side-by-side comparison of walk clip frames exists
318. No contact sheet of walking.anim internal frames exists
319. The clip's internal structure is a black box
320. Frame count of walking.anim is unknown without parsing binary
321. Frame rate of walking.anim is unknown
322. Bone count match between clip and C0 skeleton is unverified
323. Clip may have been authored for different proportions
324. Clip may assume different bind pose than C0 mesh
325. Without visual review, all clip assumptions are untested
326. Reference: a proper walk cycle has 4 key poses (contact, down, passing, up)
327. Cannot verify if walking.anim contains these poses
328. Reference: walk cycle should have arm swing opposite to legs
329. Cannot verify if walking.anim has arm swing
330. Reference: walk cycle should have vertical head bob
331. Cannot verify if walking.anim has head bob
332. Reference: walk speed should be ~1.4 m/s for combat walk
333. Cannot verify walking.anim speed
334. Reference: combat walk should be shorter stride than civilian walk
335. Cannot verify walking.anim stride length
336. Reference: walk cycle should loop seamlessly
337. Cannot verify walking.anim loop quality
338. Reference: walk should have foot roll (heel→toe)
339. Cannot verify walking.anim foot mechanics
340. Reference: walk should have lateral weight shift
341. Cannot verify walking.anim weight transfer
342. Every animation quality metric requires playback to assess
343. Without playback, quality assessment is impossible
344. The 500-defect audit format requires visible evidence
345. Visible evidence of walk animation does not exist
346. This audit documents the absence of evidence
347. Absence of evidence is evidence of the playback defect
348. The primary defect subsumes all potential quality defects
349. If it doesn't play, it doesn't matter how good it is
350. Quality assessment is blocked by the playback defect
351. This audit category would be 500 items if playback worked
352. With working playback, we could assess all 500 quality points
353. The current state prevents quality work from beginning
354. Fixing playback would unlock 500 quality improvement tickets
355. Playback is the gatekeeper for all animation quality
356. Open the gate before inspecting the garden
357. The comparative defect: other game engines play walk animations by default
358. Unity: import model + animation → press play → walks
359. Unreal: import model + animation → press play → walks
360. Just Dodge: import model + animation → press play → frozen

## CATEGORY 6: ENVIRONMENT & CONFIGURATION DEFECTS (361–410)

361. Cooked assets must be at exact path or animation silently fails
362. Missing c0_skin8.bin causes panic, not graceful degradation
363. Missing walking.anim causes no error — just no animation
364. Silent failure on missing animation assets is worse than panic
365. Asset loading should warn when animation clips are absent
366. Asset validation should check animation clip presence
367. Startup should report: "2 animation clips loaded" or "0 animation clips loaded"
368. Current startup reports only mesh load status
369. Animation asset status is invisible in logs
370. JUSTDODGE_ASSETS environment variable is the only configuration mechanism
371. No config file for asset paths
372. No command line argument for asset paths
373. Environment variables are fragile — easy to forget
374. If JUSTDODGE_ASSETS is unset, animation can never work
375. Default asset path should exist — currently requires manual setup
376. Assets were removed from repo — broke all downstream users
377. No asset integrity check at startup
378. No checksum verification for animation clips
379. Corrupted walking.anim would silently fail
380. No validation that clip frame count matches expected value
381. No validation that clip bone count matches mesh bone count
382. Configuration surface is too narrow — only one env var
383. Configuration surface is too deep — env var must point to exact directory
384. Asset discovery should search multiple paths
385. Fallback asset paths would improve robustness
386. Development assets should be in repo or auto-downloaded
387. Git LFS could store animation clips
388. Animation clips are small enough for git (49KB, 30KB)
389. Binary assets in git are acceptable at this size
390. The asset distribution story is incomplete
391. Release packages should include animation clips
392. Dist/ directory has motion clips but not in standard asset path
393. Asset location differs between dev and release builds
394. Dev: assets/source/meshy/.../cooked/
395. Release: dist/just-dodge-windows-x86_64/assets/
396. Two asset roots with different contents
397. No unified asset directory structure
398. Animation clips live in a different tree than mesh data
399. Asset fragmentation increases configuration burden
400. Configuration complexity is proportional to asset fragmentation
401. Simplify: one asset root, all assets within
402. Simplify: no environment variables needed for default layout
403. Simplify: animation works immediately after clone + build
404. Current state: clone + build → no animation
405. Required state: clone + build → animation works
406. The delta between current and required is configuration cleanup
407. Configuration is a blocker for new contributor onboarding
408. New contributor cannot see animation without tribal knowledge
409. The animation system's configurability is inversely proportional to its usability
410. Fix configuration to fix animation accessibility

## CATEGORY 7: CAMERA & PRESENTATION DEFECTS (411–460)

411. Contact sheet frames are too small (320×180) for detailed pose analysis
412. Contact sheet resolution is 1/16 of full render resolution
413. Detail lost in downscaling from 1280×720 to 320×180
414. Character occupies ~5% of each frame — too small
415. Hands and feet are single pixels at this resolution
416. Joint angles impossible to measure at this scale
417. Animation review requires higher resolution or closer camera
418. Observer camera is too distant for animation quality assessment
419. Camera is positioned for gameplay overview, not animation debugging
420. No animation-specific camera mode exists
421. No close-up camera for walk cycle inspection
422. No side-profile camera for stride analysis
423. No top-down camera for root motion tracking
424. No camera that tracks the character during movement
425. Static camera makes movement harder to detect
426. Camera should move with character to highlight animation
427. Animation review camera is an afterthought
428. The shot system treats animation as an afterthought to truth verification
429. Truth verification is prioritized over animation review
430. The camera system serves truth, not presentation
431. Presentation (animation) needs its own camera modes
432. First-person view shows opponent animation but at wrong angle
433. First-person is for gameplay, not animation review
434. No free-camera mode for circling the animated character
435. No slow-motion capture for detailed frame analysis
436. No frame-stepping in the rendered output
437. PNG output loses temporal information
438. Contact sheet helps but loses resolution
439. Video would be ideal but generation pipeline doesn't exist
440. The animation review tooling is manual and lossy
441. Frame capture → resize → grid → PNG is lossy at every step
442. Each step loses information about the animation
443. The review pipeline degrades the evidence
444. Degraded evidence makes defects harder to spot
445. Presentation defects compound animation defects
446. Hard to tell if a defect is in the animation or the presentation
447. Is the walk arm not swinging, or is the resolution too low to see?
448. Is the character moving, or is the camera too far to detect?
449. Presentation ambiguity masks animation quality
450. Fix presentation to enable animation quality assessment
451. Higher resolution contact sheets
452. Closer camera during shot capture
453. Multiple camera angles per tick
454. Side-by-side frame comparison tool
455. Automated frame differencing
456. Pixel-diff between consecutive frames
457. Animation-specific shot mode
458. --animate flag for game_loop
459. Animation review mode: --shot-anim 1 8 --camera close
460. Tooling investment would pay for itself in faster iteration

## CATEGORY 8: ROOT CAUSE & SYSTEMIC DEFECTS (461–500)

461. Root cause: animation playback not wired in default rendering path
462. Secondary cause: shot mode captures truth state, not animation state
463. Tertiary cause: no integration test for animation playback
464. Systemic cause: animation treated as optional feature, not core functionality
465. Cultural cause: project prioritizes truth verification over presentation
466. Historical cause: animation clips were removed from repo, breaking playback
467. Organizational cause: no owner for animation playback integration
468. Process cause: pipeline verified loading, not playback
469. Testing cause: test suite has no animation playback tests
470. Documentation cause: animation activation is undocumented
471. Onboarding cause: new developers can't discover animation
472. All causes converge on one symptom: frozen characters
473. The symptom is visible, the causes are hidden
474. Each cause is individually fixable
475. Together they form a systemic failure
476. Systemic failures require systemic solutions
477. A systemic solution addresses all causes simultaneously
478. Piecemeal fixes would leave gaps
479. The playback defect is the project's highest-priority animation issue
480. Fixing playback would resolve ~400 of the 500 defects in this audit
481. The remaining ~100 are quality defects that require playback to assess
482. This audit is 80% about one root cause
483. The root cause has a known fix: wire animation sampling into shot rendering
484. The fix is small: one function call in the right place
485. The impact is enormous: unlock all animation work
486. Cost of fix: ~1 hour of engineering
487. Value of fix: 500-defect audit becomes assessable, animation quality work begins
488. ROI of fixing playback is astronomical
489. This is the highest-leverage change in the entire project
490. One line of code could make characters move
491. The gap between frozen and animated is one function call
492. That function call is the most important missing line in the codebase
493. Every animation clip, every MotionBricks model, every retargeting pipeline
494. All of it is useless without that one function call
495. The entire animation investment returns zero until playback works
496. Months of animation infrastructure development produce static renders
497. The project has built a Ferrari and never started the engine
498. Start the engine
499. The walk approach should show two characters walking toward each other
500. Instead it shows two frozen mannequins — the defining defect of Just Dodge animation
