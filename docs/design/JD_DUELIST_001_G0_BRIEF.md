# JD_Duelist_001 — G0 Art + Legal Brief (frozen before any generation call)

Schema: just-dodge.asset-brief.v1. Asset family: JD_Duelist_001 (purpose-built,
part-separated armored duelist). This is the FIRST high-fidelity build after the
game-first loop passed its visual check. It REPLACES the fused C0 armored
duelist (unresolved penetrations); it is NOT a repair of that mesh.

Authority boundary (locked): FAL + Meshy are OFFLINE candidate producers only.
Blender + versioned headless workers are the SOLE asset authority and promotion
boundary. Cooked Rust/wgpu assets are the shipping form. No generative model or
service ships in the executable; runtime never calls FAL/Meshy.

## 1. Canonical technical contract

- asset_id root: `jd_duelist_001`
- Scale: meters, real-world humanoid (~1.8 m tall).
- Forward axis: +Z (Meshy rig/detect contract and engine convention).
- Canonical skeleton: the accepted 24-bone humanoid rig (same joint contract as
  the c0_base_fighter debug mannequin; bone names must match so retarget +
  OBB proxies + injury atlas map 1:1). Skeleton definition is authoritative in
  Blender, not Meshy auto-rig (Meshy rig is a diagnostic source only).
- Weapon socket: canonical `weapon_r` right-hand socket (two-hand-capable);
  exact transform authored in Blender and recorded in the manifest.
- Determinism: all provider requests record seed; every artifact is sha256
  content-addressed; receipts are immutable canonical JSON.
- Output: untextured fit/rig/proxy vertical slice first (geometry + rig +
  proxies proven). Texture ONLY after geometry/rig/proxy clears its gates.

## 2. Component manifest (each a SEPARATE, separately-addressable mesh)

No body/armor/weapon mesh may be fused merely for a prettier thumbnail. Each
component is generated as its OWN Meshy task (one component per task), then
assembled in Blender WITHOUT joining.

| component_id | role | notes |
|---|---|---|
| body_anatomy_carrier | clean T-pose anatomical base (undersuit) | the deformable body; injury atlas maps here |
| helmet_head | helmet + neck guard | rigid-parented |
| torso_cuirass | chest/back plates | rigid or semi-rigid |
| pauldron_l / pauldron_r | shoulder plates | clearance to cuirass + arm |
| vambrace_l / vambrace_r | forearm guards | clearance to elbow |
| gauntlet_l / gauntlet_r | hand armor | must not block grab/hand proxies |
| belt_fauld | waist + tassets | clearance to hip/leg motion |
| greave_l / greave_r | lower-leg armor | clearance to knee |
| boot_l / boot_r | foot armor | ground contact; OBB foot proxy |
| sword_blade | blade | hard-surface, canonical length |
| sword_guard | crossguard | clearance blade<->grip |
| sword_grip | grip | fits weapon_r socket, two-hand |
| sword_pommel | pommel | hard-surface |
| scabbard | scabbard | hip-mounted, no body penetration |
| fracture_proxies | breakable/fracture sub-objects | deterministic fracture pieces |
| collision_damage_proxies | OBB collision + damage proxy set | engine truth consumes these |

Each component carries: canonical skeleton mapping, weapon socket (if weapon),
meter scale, +Z forward, material slot names, allowed-overlap/clearance margins,
LOD and texture budgets (recorded even though this slice is untextured).

## 3. Fit/rig/proxy acceptance targets (untextured slice)

- Every component: non-manifold-free, correct scale/axes/origin/pivot, real
  object separation (not a single fused mesh).
- Body carrier: clean deformation loops at shoulders/elbows/hips/knees/neck;
  T-pose; ≤ influence budget per vertex; bind-pose matches canonical skeleton.
- Clearance: no body<->armor or armor<->armor or weapon<->body penetration at
  bind or at the stress poses (Mesh Doctor pair-detect threshold, signed
  penetration <= 0.5 mm target, zero prohibited contact).
- Weapon: fits weapon_r socket; blade/guard/grip clearance; hand/grab proxies
  unblocked.
- Proxies: OBB collision + damage proxies authored and named; map to the
  intent/truth hitbox model (OBB per bone).
- Cooked: deterministic GLB -> cooked SKM1/ANM1 proof in the first-person duel
  camera; Khronos GLB validation passes; re-import passes.

## 4. Source-rights register (freeze BEFORE spending credits)

Every generation call must first snapshot the provider terms and record the
rights disposition. Missing licensed input, terms snapshot, or component
definition = STOP before spending credits (G0 gate).

- FAL: snapshot FAL ToS + each selected model-page/model-provider term at
  generation time. Record terms URL + retrieval RFC3339 + terms sha256. FAL
  output is non-unique and carries no originality/non-infringement warranty;
  concept/reference use only, human concept gate G1 required.
- Meshy plan: record the active plan tier. Free-plan output is CC BY 4.0
  (attribution required) — do NOT ship free-plan output without an explicit
  attribution/rights decision. Paid/Enterprise privacy/training terms must be
  resolved contractually before sending proprietary designs. Download outputs
  immediately (non-Enterprise outputs deleted after 3 days). Never publish
  accepted assets to Meshy Community.
- Blender: GPL tool; artwork/.blend/generated files are the artist's property,
  commercial use allowed. Keep proprietary game assets distinct from any
  distributed Blender add-on/scripts.
- Concept sources: owned/licensed/generated only; no IP-copying of existing
  characters. G1 gate includes a no-IP-copy review.

## 5. Pipeline gates (from HIGH_FIDELITY_ASSET_PIPELINE.md, authoritative)

G0 art+legal brief approval (this doc) -> G1 concept/silhouette/no-IP review ->
G2 raw component geometry -> G3 topology/anatomical-fit -> G4 bind/stress-pose/
clearance -> G5 repair disposition -> G6 material/readability (deferred, textured
phase) -> G7 runtime integration -> G8 final first-person + evidence sign-off.

This slice targets G0-G5 + G7 geometry/rig/proxy proof (untextured). G6 texture
is a later unit.

## 6. Status

FROZEN for G0. Awaiting human G0 approval before the first FAL concept call.
