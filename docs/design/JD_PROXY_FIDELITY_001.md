# JD-PROXY-FIDELITY-001 — Combat-proxy quality measurement

Status: OPEN (follow-up unit, spawned from Grab-07 promotion NO_OP_NO_DEFECT
disposition, owner 2026-07-17). This is a MEASUREMENT unit, not a collision-model
change. Change OBBs to capsules or convex proxies ONLY if these measurements
expose gameplay or visual-contact failures — never merely because valid
collision volumes overlap during contact.

## Origin

The Grab-07 capture showed a 0.020 m OBB-proxy contact overlap at the secure
grab while the skinned mesh triangles showed 0.0 mm prohibited intersection and
a visible surface clearance of ~0.60 m. The proxies are the authoritative
Combat Truth collision model and are kept. This unit measures whether that
proxy model is GOOD ENOUGH for gameplay and visual-contact fidelity, or whether
it produces measurable errors that justify a geometry refinement.

## Metrics to measure (per proxy, per contact class)

1. Contact-onset error: difference (truth ticks) between when the proxy reports
   contact onset and when the skinned mesh actually makes first surface contact.
2. False-positive distance: the maximum proxy-proxy "contact" distance at which
   the corresponding meshes are NOT in contact (proxy padding overshoot).
3. Body-region correctness: whether the proxy that reports contact maps to the
   anatomically correct body region (hand vs forearm vs torso) vs the mesh.
4. Contact-normal error: angular difference between the proxy contact normal
   and the mesh surface normal at the contact point.

## Method

- Drive scripted contacts (grab, strike, block) through PlanPhase/DuelWorld on
  the debug mannequin (c0_base_fighter), as in grab07_capture.
- For each contact, simultaneously compute (a) the OBB-proxy contact (truth)
  and (b) the skinned-mesh contact via triangle-level detection
  (grab07_pose_and_detect pattern).
- Emit a proxy-fidelity receipt with the four metrics per contact class, plus
  aggregate stats. Deterministic across reruns.

## Decision rule

- If all four metrics are within tolerances that do NOT produce gameplay or
  visual-contact failures, KEEP the current OBB proxies (they are deterministic
  and cheap). Document the measured error budget.
- If any metric exposes a real gameplay or visual-contact failure, propose the
  MINIMAL geometry refinement (capsule or convex-hull proxy) that closes it,
  with before/after measurements — an evidence-driven change, never a forced
  near-zero overlap.

## Explicitly out of scope

- Replacing proxies with raw triangle collision (breaks determinism budget).
- Forcing the proxy overlap to near-zero (overlap during valid contact is
  legitimate; the goal is fidelity, not a zero reading).
