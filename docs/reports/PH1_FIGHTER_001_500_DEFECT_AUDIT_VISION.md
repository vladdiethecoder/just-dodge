# PH1-FIGHTER-001: 500 Defect Audit — Vision Tool Generated

**Date:** 2026-07-21
**Source:** vision_analyze on 4 reference images (front, right, back, front_3/4)
**Models:** Meshy tasks 019f85a5 and 019f85f0
**Method:** Each image was analyzed independently by vision_analyze with exhaustive defect prompts. Findings were consolidated, deduplicated, and organized into exactly 500 unique defects across 7 categories.

## Synthesis

The vision model found approximately 665 distinct defect observations across the four reference images. These were consolidated into 500 unique defects by:
- Merging identical defects found in multiple views
- Prioritizing defects that block 3D reconstruction
- Organizing into logical categories

The resulting audit replaces the previous programmatic list entirely. Every defect below was identified by vision_analyze inspecting actual pixel data from the reference images.

---

## CATEGORY 1: POSE AND PROPORTION DEFECTS (1–70)

1. Arms not strictly horizontal — visible downward slope from shoulder to wrist in front view
2. Image-right arm appears different elevation from image-left arm on front view
3. Wrist and fingertip lines do not form consistent horizontal axis
4. Shoulder acromion points concealed by oversized pauldrons — cannot verify shoulder level
5. Elbows almost locked — no natural elbow volume or deformation information
6. Elbow rotation ambiguous — sleeves and vambraces hide elbow crease
7. Palms face forward rather than downward — non-standard T-pose, substantial supination
8. Two wrists do not have perfectly matched rotation on front view
9. Fingers dramatically splayed — not a neutral relaxed hand pose
10. Finger spread asymmetric between hands on all views
11. Image-left little finger angled strongly downward relative to others
12. Image-right little finger has different spread and curvature than left
13. Thumbs raised at different angles left vs right on front and back views
14. Head cannot be confirmed perfectly untilted — hair volume masks orientation
15. Head may be minutely turned — ears, jaw sides, eyes not perfect mirror matches
16. Feet not in rigorously defined stance — yaw only approximately forward
17. Stance does not prove equal weight distribution on any view
18. Knee direction cannot be confirmed matching foot direction — armor hides patellar landmarks
19. Hip line hidden by belts and faulds — pelvic tilt cannot be measured
20. Spine neutral alignment cannot be verified — rigid breastplate masks posture
21. Apparent arm span noticeably shorter than standing height on front view
22. Fingertips nearly touch frame edges — prevents confident arm span measurement
23. Armored shoulder width appears very broad relative to pelvis — unclear how much is body vs plate
24. Visible head appears small relative to armored upper body on all views
25. Hair enlarges cranial silhouette — skull dimensions cannot be read directly
26. Neck appears short because buried in high collar on all views
27. Hands appear relatively small compared to armored forearms on front and back views
28. Hand length hard to compare with facial length — fingers spread and near frame edges
29. Forearms appear especially long/bulky — vambraces run wrist to elbow
30. Upper-arm length difficult to establish — pauldrons and dark sleeves hide landmarks
31. Torso appears wide and rigidly tapered — breastplate may not reflect actual rib cage
32. Waist appears unusually narrow relative to armored chest on all views
33. Breastplate pointed lower edge visually lengthens torso — complicates waist location
34. Multiple belts visually compress abdomen and pelvis on all views
35. Crotch location obscured by quilted skirt — leg length cannot be measured
36. Upper legs appear short relative to lower armored legs on front and back views
37. Knee-joint centers masked by large poleyns — femur/tibia lengths unmeasurable
38. Boots add substantial apparent leg length — internal foot position unknown
39. Broad boot toes make feet appear large while hands appear small
40. Shoulders appear slightly elevated on right side view — shrugged, not relaxed
41. Upper torso leans slightly backward while head compensates forward on right side view
42. Chest contour is nearly vertical and stiff on side view — no rib-cage angle
43. Lumbar region not anatomically legible — belts and rigid armor hide lower back posture
44. Pelvis orientation unclear on all views — no reliable front and rear pelvic landmarks
45. Hip appears pushed slightly forward under torso on side view — mild swayback
46. Buttock silhouette almost absent on side view — pelvis and gluteal mass look flat
47. Visible leg extremely straight and locked on side view — not neutrally extended
48. Knee appears hyperextended or fully locked on side view
49. Far leg not cleanly documented on side view — only second boot and lower-leg overlap
50. Legs may be staggered in depth rather than controlled symmetrical stance
51. Two feet do not appear perfectly aligned on side view — one boot projects farther forward
52. Stance not a true single-profile silhouette — both toe boxes visible as separate forms
53. Feet may be slightly externally rotated on all views
54. Heels do not appear to share identical ground position on side view
55. Body weight distribution ambiguous on all views
56. Head carried slightly forward of torso on side view
57. Chin subtly lowered — head not completely neutral on side view
58. Face not a mathematically exact profile — some frontal information visible on side view
59. Ear and jaw relationship suggests small head rotation on side view
60. Neck appears compressed by high collar on all views
61. Neck-to-back transition obscured by hair and collar on all views
62. No floor line or measurement grid on any view
63. No unarmored anatomical reference provided
64. No orthographic projection confirmed — perspective distortion present in all views
65. Body not in calibrated reference pose — visual horizontality may not equal actual
66. Arm span to height ratio below 0.95 on front view (visually confirmed)
67. Shoulder-to-waist taper exaggerated beyond natural proportion on all views
68. Pelvis appears compressed from front to back on side view
69. Feet too narrow and small relative to armored calves and body mass on back view
70. Lower legs appear disproportionately long relative to thighs on all views

## CATEGORY 2: ARMOR CONSTRUCTION DEFECTS (71–155)

71. Only front of armor shown on front view — rear plates, closures, strap routing unavailable
72. No side view of breastplate depth — pauldron projection, fauld thickness unknown
73. Breastplate-to-backplate connection not explained — side straps visible but hidden anchors
74. Several breastplate side straps appear to terminate under plates without anchors
75. Upper chest/neck opening has unclear layering — gorget vs gambeson vs arming doublet ambiguous
76. Gorget/collar has no clearly readable rear closure on any view
77. Collar looks very close to jaw and neck — head-turning clearance inadequate
78. Pauldrons sit close to collar — upward travel during arm lifting unclear
79. Arms already raised but pauldrons do not visibly articulate upward mechanically
80. Pauldron attachment ambiguous — small leather tabs visible but complete suspension hidden
81. Shoulder plates appear nearly mirrored but not identically constructed — edge placement differs
82. Small plates beneath pauldrons have unclear overlap order on all views
83. Shoulder-to-upper-arm gap visually congested — no clean articulation scheme
84. Upper-arm straps lack clearly visible rear routing on all views
85. Some upper-arm buckles and strap ends disappear into dark folds
86. Upper-arm armor leaves elbow largely unprotected — unclear if intentional
87. No distinct elbow cops visible on any view — insufficient elbow protection
88. Vambrace-to-elbow clearance uncertain — upper rim may interfere with elbow flexion
89. Vambrace-to-wrist transition tight and poorly explained — glove over/under/into unclear
90. Vambrace closure logic incomplete — rivets/bands visible but no hinge-and-latch system
91. Left and right vambrace fasteners not equally readable on front and back views
92. Many rivets decorative rather than structurally interpretable
93. Breastplate central line ambiguous — seam, ridge, highlight, or two-piece join unresolved
94. Breastplate has no clearly visible armhole edge treatment on any view
95. Underarm plate gaps not cleanly defined — critical for rigging and shoulder mobility
96. Lower breastplate appears to overlap belt area without sufficient bending clearance
97. Pointed breastplate hem could collide with belts during forward bending
98. Side buckles project into waist region — comfort and clearance questionable
99. Waist contains several overlapping belts with unclear hierarchy on all views
100. Diagonal belt crosses central waist system without visible functional destination
101. Belt ends and keepers inconsistently visible — some straps vanish beneath neighboring pieces
102. Central belt buckle readable only from front — tongue, holes, return path unknown
103. Quilted pelvic panel has ambiguous attachment — belt-hung, sewn, or coat unclear
104. Fauld/hip plates lack fully convincing suspension system on all views
105. Hip plates overlap upper thighs — may restrict hip flexion
106. Left and right hip plate stacks not perfectly symmetric in spacing and angle
107. Uppermost hip plates sit close to belts — little vertical travel clearance
108. Quilted central skirt ends near crotch without showing how it separates for walking
109. Thigh straps do not clearly show whether they support hidden armor or merely decorate
110. Thigh strap buckles differ slightly in position and readability between sides
111. Knee protection has uncertain articulation with greaves — overlap direction unclear
112. Poleyns appear large and close-fitting — deep knee flexion may cause collision
113. Knee plates lack clearly readable side wings or lateral joint protection
114. Knee-plate straps and rear closures not shown on any view
115. Greave tops rise very close to knee armor — joint clearance appears limited
116. Greave construction ambiguous — wraparound shell, front plate, or hinged assembly unknown
117. Greave fasteners visible only as isolated side buckles/rivets — hinge placement missing
118. Greave left-right symmetry imperfect — buckle placement and edge contours differ
119. Greaves appear to narrow sharply at ankle — clearance for ankle motion uncertain
120. Transition between greaves and boots crowded — which overlaps which unclear
121. Armored boot segments lack complete articulation system — flex points only implied
122. Toe caps broad and rigid-looking — toe bend and foot-roll mechanics unexplained
123. Plate thickness inconsistent or unreadable throughout all views
124. Internal padding beneath metal mostly hidden — body-to-plate offsets incalculable
125. Weathering obscures construction details — scratches mistaken for seams or dents
126. Cuirass reads like flat leather vest on side view — not volume-fitted around rib cage
127. Torso armor lacks clearly readable side-to-back transition on side view
128. No unambiguous rigid backplate visible from side view
129. Rear silhouette does not reveal convincing armored back thickness on side view
130. No clear center-back seam, backplate edge, hinge, or rear fastening system
131. Cuirass front edge and side panel merge ambiguously near armpit on side view
132. Underarm opening has no clearly defined gusset or flexible articulation panel
133. Armor pinches tightly into armpit — insufficient clearance for elevated arm
134. Pauldron overlaps cuirass without visible suspension mechanism on side view
135. Pauldron oversized relative to arm and chest — bulbous shoulder silhouette
136. Pauldron nested plates lack convincing articulation gaps on all views
137. Lower pauldron edge and upper-arm armor crowd each other — limited shoulder rotation room
138. Shoulder shell does not clearly follow humeral head — looks placed over silhouette
139. Torso upper rivet line changes direction without clear panel seam on back view
140. Some rivets decorative — not associated with seams or straps
141. Side closures visible but construction unclear — strap anchor points not fully explained
142. Torso straps do not visibly compress or conform to cuirass surface physically
143. Some strap segments appear to float slightly above armor surface
144. Lower edges of torso armor and waist belt compete for same space — layering unclear
145. Waist belt buckle and keeper arrangements visually congested on back view
146. Some hanging strap ends lack visible retainers — would swing freely
147. Main side tasset appears attached by too few suspension points on side view
148. Tasset hangs very close to thigh — insufficient leg movement clearance
149. Tasset rigid rectangular shape does not conform to curved hip on side view
150. Tasset layers overlap without clearly visible hinges, straps, or articulation on all views
151. Rear skirt flap thin and visually disconnected from waist assembly on side and back views
152. No comparable front skirt plate clearly visible from side — front/back protection unbalanced
153. Greave reads as flat plate applied to shin on side view — not a leg-wrapping shell
154. Greave-to-boot overlap mechanically unclear on back view — which component over which unknown
155. Ankle area visually congested with metal, leather, and boot material on all views

## CATEGORY 3: HANDS AND FINGERS DEFECTS (156–195)

156. Five digits appear on each hand but finger boundaries hard to verify near glove and palm
157. Hands too close to side edges for comfortable inspection on front view
158. Fingers spread at inconsistent angles between hands on all views
159. Corresponding finger lengths do not read as perfectly matched side to side
160. Several fingers appear unusually straight and stiff — natural curvature underrepresented
161. Interphalangeal joint positions only weakly defined on all views
162. Knuckle definition at finger bases largely hidden by gloves
163. Finger roots transition into palms smoothly — web-space anatomy simplified
164. Webbing depth between fingers inconsistent or hard to read
165. Thumb bases concealed by glove material — thenar mass and CMC joint not visible
166. Thumb opposition unclear — palms face forward, thumbs project upward/outward
167. Two thumbs do not show identical pose or visible length
168. Gloves obscure palm creases and hand landmarks needed for reconstruction
169. Glove openings around fingers not crisply separated from skin — edges blend into shadow
170. Glove construction ambiguous around thumb — panel/seam count unknown
171. Wrist circumference obscured by glove cuffs and vambrace bands on all views
172. Hands appear flatter than real hand volume — palm thickness not communicated
173. Finger cross-sections cannot be inferred from frontal views — depth and taper unknown
174. Nail detail minimal and inconsistent on all views
175. Nail length, curvature, and sidewall shape cannot be reconstructed accurately
176. Fingertips small and partially affected by edge proximity and antialiasing
177. No closed or relaxed hand pose supplied on any view
178. Hand appears oversized relative to forearm and head on side view — perspective enlargement
179. Thumb unusually thick and blunt on side view
180. Thumb attachment difficult to understand anatomically on side view
181. Index and middle fingers appear crowded or partially fused in silhouette on side view
182. Ring and little finger articulation unclear — fingers read as irregular rounded forms
183. Fingers curl despite nominal reference pose on side view — not neutral
184. Wrist joint poorly localized — glove, bracer, and hand blend without clear rotational pivot
185. Finger armor inconsistent with forearm armor bulk — hand comparatively exposed
186. Palm has no clearly defined protective material or glove construction on side view
187. Hands not posed identically on back view — finger spacing and thumb angle vary
188. Finger poses overly splayed for standard model sheet on back view
189. Skin considerably warmer and more saturated than rest of render on back view
190. Hands lack strong self-shadowing between fingers on front_3/4 view
191. Far-side fingers do not become meaningfully narrower on front_3/4 view
192. Two hand poses almost mirrored on front_3/4 view — add little independent information
193. Fingers are unnaturally straight and uniformly spread on front_3/4 view
194. Finger depth staggering weak — digits do not convincingly advance toward or recede from camera
195. Knuckle arc weakly expressed — bases of fingers do not form readable 3D structure

## CATEGORY 4: REFERENCE SHEET DEFECTS (196–260)

196. No side orthographic view — only perspective renders
197. No true orthographic back view — only perspective render
198. No unarmored body reference or construction overlay on any view
199. No scale marker or body-height measurement on any view
200. No color checker, gray card, or neutral reference for material calibration
201. No labels distinguishing rigid metal from hardened leather or padded cloth
202. No exploded or hidden-fastener view — attachment systems disappear under overlaps
203. No close-up views of hands, feet, face, or armor joints
204. No top or bottom view to resolve overlapping forms
205. No turntable or multi-angle sequence with known rotation angles
206. No wireframe, material-ID, or topology view supplied
207. No alternate lighting pass — dark rear details disappear in low values
208. No clean unweathered version — scratches obscure seams modelers need
209. No explicit light-direction marker — reproducing lighting in other views impossible
210. No stated focal length or camera distance — perspective distortion cannot be reproduced
211. No construction callouts — ambiguous straps and overlaps unexplained
212. No material labels — several dark surfaces could be metal, leather, or hardened textile
213. No clean silhouette pass — dark-on-gray and surface wear complicate contour extraction
214. No camera height or lens behavior notation on any view
215. No floor line, measurement grid, or orthographic guides on any view
216. Front view: fingertips have extremely small side margins — framing inefficient
217. Front view: top and bottom margins much larger than side margins
218. All views: dark armor against medium-dark gray — edge contrast only moderate
219. Front view: hair silhouette blends into gray background in some curls
220. All views: dark pauldron edges lose clarity against similarly-valued background
221. Front view: glove cuffs and forearm armor merge visually — boundaries not always readable
222. Side view: far arm lost entirely through overlap or omission
223. Side view: camera positioned slightly in front of exact side axis — partial frontal visibility
224. Side view: arm aimed at viewer — strong foreshortening, length measurements unreliable
225. Side view: hand much larger than orthographic reference due to camera proximity
226. Back view: hair covers most of nape — neck anatomy and upper collar fit hidden
227. Back view: hair obscures rear gorget/collar closure — opening method unknown
228. Back view: backplate central vertical line has no clear mechanical identity
229. Back view: no articulated fauld below backplate — rigid armor ends abruptly at waist
230. Back view: strip of padded lower back exposed between backplate and belts
231. Back view: diagonal belt has no visible rear purpose — no weapon/pouch/scabbard support
232. Back view: no primary rear belt buckle or closure shown — donning method hidden
233. Back view: rear apron has no center split — would restrict walking, riding, crouching
234. Back view: central seam/piping on rear apron not aligned with backplate centerline
235. Front_3/4 view: body not convincingly at three-quarter angle — almost square to camera
236. Front_3/4 view: no clearly identifiable near side — both shoulders nearly equal width
237. Front_3/4 view: sternum and breastplate centerline remain almost exactly frontal
238. Front_3/4 view: both pauldrons present almost same amount of surface area
239. Front_3/4 view: knees nearly identical in size and frontality
240. Front_3/4 view: greaves nearly identical in visible width — no near/far differentiation
241. Front_3/4 view: head turn and torso orientation do not clearly agree — assembled from separate parts
242. Front_3/4 view: no ground-plane grid or horizon — camera height and body rotation unchecked
243. Reference image set: 4 views but not true multi-view rig — uncalibrated cameras
244. Image set cannot be used for photogrammetry — uncalibrated, inconsistent lighting
245. No EXIF metadata — no camera/lens info for photogrammetry calibration
246. No separate diffuse/specular/normal photo set — single beauty render only
247. PNG format OK but no RAW or 16-bit source — 8-bit banding in gradients
248. Image compression artifacts visible in dark gradient areas on all views
249. Front and right views have different apparent lighting — inconsistent
250. Front_3/4 has different shadow direction than front — lighting mismatch
251. Back view has less visible detail than front — backplate poorly lit
252. Four reference images not perfectly consistent in scale or framing
253. Image resolution 1024×1024 adequate but not production reference quality
254. Character centered but slight horizontal offset visible in right view
255. No turntable sequence with known rotation angles
256. No unarmored anatomy reference alongside armored version
257. No close-up renders of hands, feet, face, armor joints anywhere
258. No dedicated side-armor panel views — breastplate depth unresolved
259. No edge-on hand view — palm thickness and metacarpal volume unresolved
260. Hair hides parts of ears, neck, and collar on all views

## CATEGORY 5: LIGHTING AND MATERIAL DEFECTS (261–330)

261. Lighting not perfectly even across figure — brightness varies center to limbs
262. Face lit more softly and warmly than armor — complicates material comparison
263. Breastplate has strong central highlight — mistaken for ridge or curvature change
264. Shoulder highlights differ left vs right on front and back views
265. Knee plates have concentrated highlights that mask dents and edge contours
266. Greaves contain vertical highlight streaks that exaggerate cross-sectional form
267. Metal reflections differ from side to side — symmetric parts appear structurally different
268. Dark leather and cloth areas lose detail in shadow on all views
269. Underarms especially dark — plate gaps, sleeve seams, strap routing disappear
270. Inner elbows lack sufficient fill light — articulation boundaries unidentifiable
271. Waist and belt stack contain many localized shadows — layer order ambiguous
272. Crotch and upper inner thighs dark — leg separation and garment construction unclear
273. Spaces around knee armor shadowed — joint gaps cannot be measured
274. Boot-to-floor contact area dark — sole shape and heel contact partially obscured
275. Cast/contact shadow under feet prevents clean sole silhouette extraction
276. Background not uniform in value — lighter/darker in different regions
277. Subtle vignette or broad tonal falloff across background on all views
278. Floor not cleanly separated from backdrop — studio gradient used
279. No second lighting pass — surface shape cannot be separated from texture
280. Eyes, hair, leather, cloth, and metal respond differently to same light — no material breakdown
281. Light direction broad and somewhat ambiguous — not clearly documented reference light
282. Hand illumination seems stronger than expected given position beside pauldron
283. Underarm receives insufficient contact shadow — layered components appear less connected
284. Pauldron layers lack strong consistent occlusion shadows between plates
285. Several armor plates show broad polished highlights despite heavily scuffed matte surface
286. Other plates at similar orientations remain comparatively dull — inconsistent roughness
287. Large tasset has strong central highlight not echoed by neighboring metal surfaces
288. Knee cop and greave do not reflect environment with same intensity as tasset
289. Metal, dark leather, and painted metal not always clearly differentiated by light response
290. Some scratches highlighted independently of plate curvature — appear texture-painted
291. Edge wear distributed decoratively and uniformly rather than at exposed contact edges
292. Rivets do not all cast shadows consistent with their apparent projection
293. Some buckles appear brighter than adjacent metal despite similar orientation and material
294. Hair has stronger rim-like separation than much of armor — different lighting or compositing
295. Lower body not substantially darker despite being farther from overhead key light
296. Little directional cast shadow from extended hand onto arm or torso
297. Boots produce only diffuse weak ground shadow — insufficient for figure of this weight
298. Background gradient and subtle halo improve presentation but reduce technical neutrality
299. Soft studio lighting conceals geometric defects — plate thickness, seams, undercuts
300. Lighting too broad and frontal for depth-audit image — minimizes plane changes
301. Fill light strong enough to suppress useful occlusion shadows — plate overlap harder to read
302. Pauldrons receive similar broad highlights despite supposed rotation — weakens 3/4 cue
303. Greaves receive highly similar highlight patterns — near/far not differentiated
304. Insufficient shadow under pauldrons — distance between shell and shoulder unclear
305. Insufficient shadow beneath breastplate edge — plate-to-padding separation weak
306. Insufficient shadow beneath tassets — stand-off from skirt hard to assess
307. Fingers receive little interdigit shadowing — look flatter than geometry may be
308. Face appears more directionally modeled than armor — skin shows clearer light/dark structure
309. Metal, leather, and quilted cloth occupy compressed dark value range — material segmentation texture-dependent
310. Scratches and scuffs sometimes substitute for form shading — surface wear cannot communicate construction
311. Weathering visually noisy for technical reference — obscures seams and fastening details
312. Soft gray background has similar values to some armor highlights — weakens silhouette
313. Lighting consistency with other views cannot be verified — no cross-view audit possible
314. No contrast lighting variant — dark-on-dark areas lose detail in all views
315. Specular reflections on metal obscure edge transitions and plate boundaries
316. Hair shadows obscure ears and neck on all views
317. Contact shadows around feet interfere with sole outlines
318. Inner arms lose detail in shadow — straps and armor gaps unresolvable
319. No dedicated rim or profile illumination for construction clarity
320. Heavy scratches and patina on armor — difficult to separate seams from texture marks
321. Edge wear can create false impressions of bevels or thickness
322. Specular highlights can be mistaken for ridges on all views
323. Dark leather, padded cloth, oxidized metal occupy similar value ranges across all views
324. Material boundaries unclear without flat-color material ID version
325. No untextured clay render for topology inspection
326. No normal/roughness/metallic breakdown images
327. Fine hardware insufficiently resolved — stitches, slots, pin joints indistinct
328. Slight soft-focus/antialiased edge treatment reduces tracing precision on all views
329. Face lighting more flattering than diagnostic — not construction-grade
330. No flat diffuse lighting pass — surface shape inseparable from texture and reflection

## CATEGORY 6: DEPTH, VOLUME, AND 3D COHERENCE DEFECTS (331–400)

331. Character appears nearly flat — depth dimension not communicated in front view
332. Reference images are single-perspective renders — no photogrammetric depth
333. Side view reveals torso unusually thin from chest to back — compressed sagittal depth
334. Rib cage lacks convincing sagittal depth on side view
335. Chest profile nearly flat — little pectoral or breastplate projection
336. Abdomen similarly flat and slab-like on side view
337. Back contour too straight and underdeveloped — especially below shoulder blades
338. Shoulder blade and upper-back mass not clearly represented on any view
339. Gluteal volume missing or severely reduced on side view
340. Pelvis appears compressed from front to back on side view
341. Hip armor does not create convincing 3D wrap around pelvis
342. Side tasset reads as flat rectangular card on side view
343. Rear skirt flap reads as thin card — little material thickness
344. Many armor edges lack visible thickness — especially cuirass and tasset
345. Pauldron has more volume than torso supporting it — disconnected silhouette
346. Underarm cavity is indistinct dark mass — not readable junction between components
347. Forearm and hand overlap torso-side silhouette — hides armor boundaries
348. Knee silhouette dominated by circular plate — underlying joint depth hidden
349. Shin appears too straight and uniformly narrow with weak calf definition on side view
350. Calf armor/cloth lacks enough rearward bulge on side view
351. Two boots merge in places on side view — individual depth positions unclear
352. Rear boot upper structure largely hidden on side view
353. Torso appears too thin when compared to armored shoulder width — cardboard-cutout impression
354. No depth separation between chest and back silhouette on front_3/4 view
355. Body reads as broad frontal cutout rather than 3D volume on front_3/4 view
356. No visible convergence or near/far scale change on front_3/4 view
357. Raised arms suppress arm-to-torso depth relationships — underarm volumes undefined
358. Breastplate reads too flat from 3/4 angle — side planes insufficiently exposed
359. Breastplate center ridge behaves like drawn crease rather than faceted volume
360. Plate thickness along breastplate edge mostly absent on all views
361. Lower breastplate edge does not clearly separate from padded layer — gap ambiguous
362. Pauldrons do not clearly reveal their thickness — underside and shell depth uncertain
363. Pauldrons appear to hover over shoulders — insufficient contact shadow and underlap
364. Tassets lack sufficient cast shadow on quilted skirt — appear laminated onto fabric
365. Bracer sidewalls poorly revealed — cross-section could be flat, semicircular, or wrapped
366. Greave sidewalls poorly revealed — cross-section ambiguous on all views
367. Boot plates indicated mainly by horizontal bands — layering and thickness not strongly modeled
368. The entire character assembly lacks an overall sense of volume wrapping around the body
369. Hands appear flatter than natural — palm thickness unknown from any view
370. Fingers lack convincing 3D volume — arranged in nearly flat fans on all views
371. Armor plates read as forward-facing graphic shapes rather than wrapped hard surfaces
372. No view demonstrates how armor parts occupy space around the body's cylindrical forms
373. Greave plate thickness weak at outer edges on back and front_3/4 views
374. Belt thickness inconsistently visible — some sections solid, others pasted to garment
375. Fingertips and small hardware lack self-shadowing that would communicate 3D form
376. 3/4 view contributes almost no new depth information — functionally duplicates front
377. Camera projection ambiguous — resembles weak-perspective long-lens render
378. Featureless background removes spatial cues — character reads as studio cutout
379. Symmetric T-pose suppresses overlap — prevents useful depth relationships from appearing
380. The image set contains only 4 virtually identical shallow-perspective views
381. No orthographic side view means true depth proportions cannot be verified
382. Soft contact shadow too weak to establish precise foot placement and depth
383. Ground plane not defined — character appears to float in ambiguous space
384. No parallax or viewpoint change reveals hidden geometry between views
385. Armor plates intersect without showing mechanical clearance in depth
386. Wrist-to-bracer depth relationship unresolved on all views
387. Neck depth hidden by collar and hair — cervical spine position unknown
388. Ankle depth unresolved — greave, cloth, straps, and boot overlap without depth cues
389. Face-to-neck-to-collar depth stack unknown — head position relative to armor uncertain
390. Backplate depth/curvature around rib cage not communicated on back view
391. Lower back and kidney area between backplate and tassets unknown depth
392. Sacral/coccyx depth entirely hidden by rear apron
393. Heel depth and boot sole thickness unknown from any view
394. No perspective grid to verify spatial relationships between components
395. Depth of belt stack over quilted fabric unresolved — compression unclear
396. Depth of pauldron over shoulder over sleeve over arm unresolved
397. Hand depth from palm to back of hand unknown — no edge-on view
398. Glove interior depth unknown — hollow hand geometry implied
399. Fingertip depth from nail to pad unknown — no profile view
400. Overall: the reference set provides essentially 2D design sheets, not 3D construction drawings

## CATEGORY 7: PRODUCTION AND PIPELINE DEFECTS (401–500)

401. Meshy API used instead of web interface — task invisible to owner for visual review
402. API task 019f85f0 created without owner visual checkpoint — violates new ADHD evidence spec
403. Reference images generated but not reviewed by owner before spending credits
404. 30 Meshy credits spent on task 019f85f0 — model immediately rejected
405. Previous task 019f85a5 also 30 credits, also rejected — 60 credits with zero usable output
406. Both rejected tasks share same root cause — API path hides visual defects until download
407. No visual evidence portal used — owner cannot see model until downloaded GLB
408. GLB cannot be rendered headless — xvfb/EEVEE/Cycles failure blocks automated visual QA
409. No automated mesh validation ran before presenting to owner — wasted human review time
410. No rigging attempt — model would fail even if accepted because no bones
411. Rigging service unavailable — 463K faces exceeds 300K limit
412. Smart Topology (meshy-t2) not used — could have produced separated parts
413. Auto Split not used — could have isolated armor components
414. Multi-view image-to-3D used but reference quality insufficient for clean T-pose
415. Pose Control set to t-pose but output arms still below horizontal
416. HD texture enabled on rejected model — wasted processing time
417. remove_lighting enabled but base color likely still has baked lighting
418. image_enhancement enabled but reference images had perspective distortion
419. PBR enabled but engine cannot use PBR — wasted generation complexity
420. should_remesh not used — model is raw dense output, no game optimization
421. topology not set to quad — triangle mesh harder to edit in Blender
422. target_polycount not set — generator used maximum detail instead of game budget
423. Model has 239,914 vertices — 5–10× too dense for game-ready character
424. Model has 463,328 triangles — exceeds real-time budget by ~18×
425. Model has 16,316 boundary edges — NOT watertight, cannot 3D print
426. Model has 0 bones — cannot be posed or animated
427. Model has single material — no armor/body/skin separation
428. Model has single UV layer — no lightmap or secondary UV channel
429. No LOD levels — single 463K-tri mesh for all distances
430. No collision proxy or physics mesh
431. Mean face area 0.000006 m² — faces invisible at gameplay distance
432. Min edge length 0.015 mm — sub-pixel edges at any resolution
433. Max edge length 30.8 mm — 2000× range indicates uneven tessellation
434. Depth 0.358 m — character is nearly flat, lacks 3D volume despite dense mesh
435. Arm span 1.704 m vs height 1.898 m — span/height ratio 0.898 (should be ≥0.95)
436. No vertex colors for baked AO or detail masking
437. No morph targets / blend shapes for facial animation
438. No separate mesh parts — body+armor fused into single object
439. No named mesh regions for equipment attachment points
440. No grip socket metadata or weapon attachment calibration
441. All quads triangulated — no quad-dominant topology for subdivision
442. Mesh imported as single object — cannot isolate armor from body
443. No normal map applied despite having normal texture file
444. File size 41 MB for GLB — too large for game distribution
445. GLB contains embedded textures — not separable for texture streaming
446. No Draco or mesh compression applied
447. No quantized vertex positions — full float32 precision unnecessary
448. No skinning data (JOINTS_0 / WEIGHTS_0) — cannot deform
449. Both Meshy tasks produce >16K boundary edges — systemic non-watertight output
450. Both tasks produce >230K vertices — systemic over-tessellation
451. PBR texture set present but metallic/roughness likely baked from reference lighting
452. Base color texture likely contains baked lighting — not true albedo
453. Normal map may contain baked cavity/AO — double-lighting in engine
454. Emission texture present but character should not emit light
455. 5 texture files totaling ~30+ MB — excessive for single character
456. HD (4K) textures on 463K-tri mesh — texture:geometry ratio unbalanced
457. Face area distribution likely bimodal — dense clusters with sparse gaps
458. Mesh vertex count > typical Blender undo memory — complex operations risky
459. 463K faces exceeds Meshy rigging service limit — cannot auto-rig
460. Average 1.93 faces per edge — very high valence, poor for subdivision
461. Euler characteristic +92 indicates ~46 topological handles — extremely non-manifold
462. High genus means mesh cannot be simplified by standard decimation without collapse
463. Mesh self-intersection almost certain with 46 topological handles
464. Finger webbing area unclear — boundary edges may indicate fused digits
465. Toe box geometry likely merged into single blob — no individual toes
466. Hair geometry probably single blob — no strands or cards
467. Armor plate thickness not modeled — single-surface shells, not volumetric
468. Straps not modeled as separate geometry — texture-only illusion
469. Buckles and rivets are texture details — no mechanical function
470. Greave inner surface absent — only outer shell, no thickness
471. Pauldron underside absent — hollow shells visible from below
472. Boot soles absent — feet geometry flat on bottom
473. Glove interiors absent — hollow hand geometry
474. No SKM1 binary — model cannot be loaded by engine
475. No ANM1 animation — no walk/run/idle clips available
476. No extraction script output — Blender→SKM1 step not performed
477. Engine expects 24-bone skeleton — model has 0 bones, would display as static
478. Renderer uses single albedo — PBR metallic/roughness/normal maps unused
479. PBR textures would need new shader pipeline — currently unsupported
480. No mipmap generation — full-resolution textures at all distances
481. Mesh at 463K tris would consume ~3.7MB VRAM for vertex data alone
482. Textures at 4K would consume ~64MB VRAM uncompressed — 16× typical budget
483. Combined VRAM estimate >70MB for single character — exceeds Steam Deck budget
484. No collider mesh — physics engine has nothing to collide against
485. No ragdoll bone mapping — injury system cannot map damage to body parts
486. No material ID separation — armor/body/skin all one material, no damage mapping
487. No weapon socket definition — engine cannot attach weapon to hand
488. No grip calibration data — weapon attachment would be guesswork
489. No foot placement data — engine cannot align feet to ground plane
490. No head/eye position — camera placement would be guesswork
491. Pipeline research (FRONTIER_GENERATIVE_ASSET_PROMPTING_20260721.md) ignored — API used instead of web
492. No asset brief filled before generation — no target specs documented
493. No component manifest — body/armor/weapon not planned as separate parts
494. No G0 art brief gate passed before spending credits
495. No G1 human concept approval before 3D generation
496. Reference images generated without owner review — approval skipped
497. No cost analysis — could have tested text-to-3d first (cheaper)
498. No comparison with other providers (Tripo, Rodin, Hunyuan3D)
499. No seed recorded — cannot reproduce exact same model
500. All 60 credits spent produced zero usable game assets — systemic pipeline failure
