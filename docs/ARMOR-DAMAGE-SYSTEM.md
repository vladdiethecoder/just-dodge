# Armor and Damage System — Just Dodge

## Purpose

Armor is not a cosmetic stat block. It changes readable combat choices by altering protection, stamina cost, speed, joint range of motion, sound, and failure behavior.

Armor is also a persistent combat record. A pristine piece starts visually clean. Physics events then write dents, tears, cracks, ring gaps, scuffs, blood, dirt, and burn marks into the piece's damage state. Armor that survives ten fights should visibly show those ten fights; no two pieces should remain visually identical after different combat histories.

This system is planned for later playable milestones. It is not part of the minimal shape prototype.

## Armor Slots

| Body Region | Armor Slot | Bones Covered |
|---|---|---|
| Head | Helm | Skull, C1-C2 neck base |
| Neck | Gorget | C3-C7 |
| Upper Torso | Breastplate | T6-T12, Sternum |
| Lower Torso | Fauld/Tasset | L1-L5, Pelvis |
| Shoulders | Pauldrons L/R | Clavicle, Scapula, Shoulder ball |
| Upper Arms | Rerebraces L/R | Humerus |
| Elbows | Couters L/R | Elbow joint |
| Forearms | Vambraces L/R | Radius/Ulna |
| Hands | Gauntlets L/R | Wrist, Metacarpals, Phalanges |
| Upper Legs | Cuisses L/R | Femur |
| Knees | Poleyns L/R | Knee joint |
| Shins | Greaves L/R | Tibia/Fibula |
| Feet | Sabatons L/R | Ankle, Subtalar, Metatarsals |

## Armor Piece Data Contract

Conceptual schema only:

```cpp
struct ArmorPiece {
    BoneID          covered_bone;
    ArmorMaterial   material;
    float           integrity;          // 0.0 - 1.0
    float           mass_kg;
    float           slash_resist;
    float           pierce_resist;
    float           blunt_resist;
    float           cleave_resist;
    JointROMClamp   rom_clamp;          // feeds motion style/constraints
    float           noise_level;
    bool            destructible;       // Warden fused pieces can be false
    MeshID          visual_mesh;        // swappable per integrity state
    MeshID          destroyed_mesh;     // exposed bone/flesh mesh
    DamageEvent[]   damage_events;      // {impact_point, force, type, timestamp}
    TextureID       deform_map;         // GPU-written per-hit dents/cuts/scuffs
    CrackGraph      crack_network;      // marble/bone fracture graph only
    RingState[]     ring_state;         // chainmail per-ring integrity only
};
```

Persistent state requirements:

- Save/load preserves exact damage state, not only the integrity percentage.
- A heavily damaged NPC armor piece communicates prior survival, not a random cosmetic variant.
- Fresh armor on a veteran communicates re-equipping.
- Recognizing a recurring fighter by their armor damage pattern is allowed.
- Damage state must stay deterministic: the same combat event stream produces the same visual and gameplay state.

## Materials

| Material | Yield Strength | Ultimate Strength | Density | Elastic Modulus | Behavior Class |
|---|---:|---:|---:|---:|---|
| Cloth/Silk | ~0.5 MPa | ~1 MPa | 0.3 kg/m² | Very low | Soft body / tear |
| Leather | 15–30 MPa | 40 MPa | 0.9 kg/m² | Low | Mass-spring / rip |
| Chainmail | 180 MPa* | 280 MPa* | 8.0 kg/m² | High | Constraint network |
| Lamellar | 160 MPa | 240 MPa | 5.5 kg/m² | Medium-high | Rigid + hinge |
| Plate, thin | 200 MPa | 400 MPa | 7.8 kg/m² | 210 GPa | FEM / plastic |
| Plate, thick | 250 MPa | 500 MPa | 7.8 kg/m² | 210 GPa | FEM / plastic |
| Rune-Marble | 380 MPa | 420 MPa | 2.7 kg/m² | 70 GPa | Brittle fracture |
| Bone, Warden | 130 MPa | 170 MPa | 1.9 kg/m² | 20 GPa | Brittle + organic |

*Chainmail yield is ring-separation threshold, not base material yield.

## Resistance Matrix

Legend: more checkmarks means stronger resistance; crosses mean vulnerability.

| Material | Slash | Pierce | Blunt | Cleave | Notes |
|---|---|---|---|---|---|
| Bare Skin | ✗✗✗ | ✗✗✗ | ✗✗ | ✗✗✗ | No resistance |
| Cloth/Wrap | ✗✗ | ✗✗✗ | ✗ | ✗✗ | Friction only |
| Leather | ✗ | ✗✗ | ✗ | ✗ | Absorbs glancing |
| Chainmail | ✓✓ | ✗ | ✓ | ✗✗ | Pierce-vulnerable |
| Lamellar | ✓✓ | ✓ | ✗ | ✓ | Blunt-vulnerable |
| Plate, thin | ✓✓✓ | ✓✓ | ✓ | ✓✓ | Deflects most |
| Plate, thick | ✓✓✓✓ | ✓✓✓ | ✓✓ | ✓✓✓ | Blunt causes joint trauma |
| Rune-Marble | ✓✓✓✓ | ✓✓✓✓ | ✓✓✓ | ✓✓✓✓ | Divine material, brittle on crit |

## Weapon Damage Types

| Weapon | Damage Types |
|---|---|
| Cestus/Fists | Blunt + joint trauma; bypasses plate through concussion |
| Dagger | Pierce; targets gaps between plates |
| Longsword | Slash + pierce; half-swording for blunt pressure |
| Greatsword | Cleave + slash; overwhelms light/medium by force |
| Polearm | Pierce + cleave; reach negates armor approach |
| Axe | Cleave; defeats plate by hooking and leverage |
| Hammer | Blunt; plate-crusher, internal trauma through armor |
| Chain Whip | Wrap + joint lock; targets limbs and exposed joints |
| Shield | Block + bash; physics event rather than damage type |

## Resolution Pipeline

Input variables:

- `weapon_mass` in kg.
- `attack_velocity` in m/s, from MotionBricks joint velocity or equivalent motion state.
- `contact_angle` relative to armor surface normal.
- `contact_area` in cm², from weapon tip, edge, or flat.
- `armor_material` with yield, ultimate, and elastic values.
- `armor_integrity` from 0.0 to 1.0.
- `armor_thickness` in mm, per piece.
- `underlying_tissue` for bone, muscle, organ, or joint outcome.

Resolution steps:

1. Compute impact force: `F = (weapon_mass × attack_velocity²) / (2 × contact_area)`.
2. Apply angle modifier: `effective_F = F × cos(contact_angle)`.
3. If the contact angle is greater than 70°, resolve as a full deflect with armor intact.
4. Compare effective force to material thresholds:
   - below yield strength: elastic deformation only;
   - below ultimate strength: plastic deformation and dent;
   - above ultimate strength: penetration or fracture.
5. Apply integrity modifier: `threshold_modifier = armor_integrity × 0.8 + 0.2`.
6. Resolve deformation by damage family:
   - Slash checks blade sharpness against material hardness.
   - Pierce checks tip area against plate thickness.
   - Blunt computes transmission ratio and applies trauma underneath.
   - Cleave computes shear stress along the impact vector.
7. Compute residual force: `residual_F = max(0, effective_F - material_absorption)`.
8. Apply residual force to underlying anatomy.
9. Reduce armor integrity by deformation severity.
10. If integrity reaches 0, trigger destruction behavior.

## Combat Event to Damage Record

Armor damage is authored as event-driven state, not random wear.

```text
ARMOR SPAWNS PRISTINE
        ↓
Physics simulation writes damage to the mesh and material in real time
        ↓
Every dent, tear, crack, ring gap = a record of actual combat events
        ↓
Armor that has never been hit looks brand new
Armor that survived 10 fights shows exactly those 10 fights
No two armor pieces ever look the same after combat
```

Failure events:

| Trigger | Material | Result |
|---|---|---|
| Blunt impact | Plate | Dent mesh deformed at contact point; depth follows mass × velocity / contact area |
| Slash | Leather | Surface groove cut into mesh |
| Pierce | Chainmail | Ring constraint broken, creating a gap in the mesh |
| Pierce | Plate | Petal deformation around the hole site |
| Fracture threshold | Rune-Marble | Voronoi shatter into shard physics objects |
| Splinter threshold | Bone | Irregular crack into splinter geometry |
| Slash | Cloth/Silk | Edge split into hanging strip physics |

Shader/state writes:

| Event | Shader / State Write |
|---|---|
| Impact | Write scratch/scuff decal at UV contact point |
| Dent formed | Update normal map at dent region |
| Blood contact | Add to progressive blood accumulation texture layer |
| Dirt/sand contact | Add grime layer, especially in recessed geometry |
| Burn/fire | Add char overlay and soot deposit |
| Repeated impacts | Degrade metal finish from polished to matte to pitted |

## Integrity States

| Integrity | State | Gameplay/Visual Meaning |
|---:|---|---|
| 100% | Pristine | Full protection values |
| 75% | Worn | -10% protection, visual scratches |
| 50% | Damaged | -25% protection, visible dents/cracks |
| 25% | Compromised | -50% protection, piece partially detached |
| 0% | Destroyed | Piece falls off mesh, bone exposed, full damage node |

Degradation triggers:

- Direct hit on covered zone: -5% to -30% integrity, by weapon force.
- Critical high-force hit: -40% to -60% integrity.
- Rune-Marble critical hit: shatters to 0% instantly with visual explosion.
- Blunt vs plate: armor integrity -15% and joint trauma through armor.
- Ground impact or throw: -10% to hit-zone integrity.

Readable state bands for the simplified deterministic model:

| Integrity | Visual State | Physics Behavior Change |
|---:|---|---|
| 1.0 | Pristine / new | Full material thresholds |
| 0.8 | First marks | Cosmetic only, full protection |
| 0.6 | Visibly damaged | Threshold -15% at damage sites |
| 0.4 | Compromised | Threshold -35%, piece mobility affected |
| 0.2 | Critical | Threshold -60%, piece may detach |
| 0.0 | Destroyed | Piece removed from simulation |

## Material Failure Behavior

| Material | Pristine | Worn | Damaged | Compromised | Destroyed |
|---|---|---|---|---|---|
| Cloth | Clean | Frayed | Torn strips | Hanging tatters | Gone |
| Leather | Smooth | Scuffed | Gashed | Flapping pieces | Shredded |
| Chainmail | Tight | Loose rings | Gaps | Large holes | Coif falls |
| Plate | Polished | Scratched | Dented | Cracked | Shattered |
| Rune-Marble | Glowing | Flickering | Cracked veins | Dark cracks | Shatter |
| Bone | Smooth | Hairline cracks | Fractured | Splintered | Destroyed |

## Per-Material Simulation Notes

### Cloth/Silk

- Method: Position-Based Dynamics plus GPU cloth solver.
- Force below 0.5 MPa: elastic flutter, billowing, wind interaction.
- Force above 0.5 MPa: permanent crease or compression deformation.
- Force above 1.0 MPa: tear starts at stress concentration.
- Slash: clean linear tear along blade vector.
- Pierce: puncture hole plus radial tear propagation.
- Blunt: compression wave, absorbs by stretch.
- Fire/heat: char deformation into progressive ash state.
- Tear propagation follows grain plus stress field; no pre-authored tear lines.

### Leather

- Method: mass-spring system plus plasticity layer.
- Below 15 MPa: elastic deformation.
- 15–30 MPa: permanent creasing.
- Above 40 MPa: rip initiation.
- Slash: deep cut groove, splits if momentum is high.
- Pierce: puncture and stretch-hole.
- Blunt low velocity: compression dent.
- Blunt high velocity: bottoms out and transfers force to bone underneath.
- Repeated stress causes progressive micro-tearing.

### Chainmail

- Method: rigid body constraint network.
- Each ring is a rigid body linked by four angular constraints.
- Slash: rings deflect blade with low damage transfer.
- Low-velocity pierce: ring constraint holds and deflects.
- High-velocity pierce: ring opens, gap forms, adjacent rings cascade.
- Blunt: force distributes across the ring network and transfers about 70% to underlying layer/bone.
- Cleave: severs ring clusters and separates mail.
- Grab/grapple: fingers catch rings and pull-deform a section.
- Repeated pierce progressively opens rings into a loose, poor-protection layer.

### Plate

- Method: corotational tetrahedral FEM.
- Elastic zone below 200–250 MPa: plate vibrates/rings and returns to shape.
- Plastic zone above yield: permanent dent forms at the impact site.
- Pierce stress above ultimate/tip-area threshold: hole plus inward petal deformation.
- Shear/cleave: plate edge curls, buckles, or severs.
- Blunt hammer hit below pierce threshold: plate dents inward and transmits trauma.
- Cumulative dents create stress concentrators; repeated hits at same dent reduce fracture threshold by about 40%.
- Half-swording concentrates blunt force on joint seams to pry or lever plate open.

### Rune-Marble

- Method: brittle fracture plus Voronoi shatter.
- Below 380 MPa: near-perfect resistance; golden veins pulse brighter under stress.
- Plastic range is almost absent; micro-cracks form in golden vein network.
- Above 420 MPa: Voronoi fracture into physics shards.
- Shards retain velocity and can cause secondary projectile damage.
- Shatter causes golden energy discharge and area stagger.
- Cannot be repaired; destruction is permanent.
- Pierce causes cone fracture and catastrophic local weakening.

### Warden Bone Plates

- Method: brittle FEM plus organic surface deformation.
- Below 130 MPa: slight organic flex.
- 130–170 MPa: crack propagation and hairline fractures.
- Above 170 MPa: irregular splintered fracture.
- Splinters become wound extenders on exit.
- Fused pieces cannot be removed; fracture remains on body.
- Broken bone-plate fragments shift into new injury nodes.
- Destroyed pieces can become weapons: bone shards embedded in attacker on close-range hit.

## Class Loadouts

| Class | Philosophy | Simulation Identity |
|---|---|---|
| Ascetic | Zero armor, full ROM; bare/wraps only | Speed + technique wins; every hit lands on flesh; pure martial arts expression |
| Duelist | Partial leather/light plate protects vitals only | Speed + selective coverage; gaps are the skill challenge; parry/dodge over tank |
| Sentinel | Chain + segmented plate over torso/limbs | Balanced coverage vs ROM; deliberate methodical fighter; some joint gaps remain |
| Juggernaut | Full gothic heavy plate, all slots filled | Walking tank; severe ROM restriction; near-immune to light weapons; half-swording essential |
| Mystic | Flowing silk + divine sigil, rune-etched cloth | Low physical protection; Rune-Marble accessories; asymmetric unpredictable coverage |
| Warden | Bone/organic + partial metal, asymmetric coverage | Horror identity; bone plates fused to body; some pieces non-removable or non-destructible |

## Weight, Stamina, Speed, and ROM

| Armor Class | Total Weight | Stamina Drain | Speed Mod | Joint ROM Restriction |
|---|---:|---:|---:|---|
| Ascetic | 0 kg | ×1.0 | ×1.0 | None |
| Duelist | 4–8 kg | ×1.1 | ×0.95 | Slight shoulder/elbow |
| Sentinel | 12–18 kg | ×1.3 | ×0.87 | Shoulder, hip, knee |
| Juggernaut | 25–40 kg | ×1.7 | ×0.72 | Major: all major joints |
| Mystic | 2–5 kg | ×1.05 | ×0.98 | Near-none |
| Warden | 8–14 kg | ×1.2 | ×0.90 | Asymmetric bone coverage |

ROM examples:

- Pauldrons limit shoulder abduction and overhead attacks.
- Couters block elbow hyperextension.
- Gauntlets alter finger curl and grip strength.
- Cuisses restrict hip flexion and high kicks.
- Poleyns restrict knee ROM and deep squats.
- Greaves affect ankle plantarflexion and footwork.
- Great helms reduce neck rotation by about 60% and peripheral vision by about 40%.

## Noise and Detection

| Material | Noise Level | Detection Range |
|---|---|---:|
| Cloth/Wrap | Silent | 0 m |
| Leather | Whisper | 2 m |
| Chainmail | Jingle | 8 m passive / 15 m sprint |
| Lamellar | Clatter | 10 m passive / 20 m sprint |
| Plate | Clank | 15 m passive / 30 m sprint |
| Rune-Marble | Resonant hum | Constant 20 m |

## Critical Hit Consequences

| Hit Zone | Weapon Type | Consequence |
|---|---|---|
| Neck, unarmored | Cleave/Slash | Decapitation; instant kill |
| Neck, gorget | Cleave | Gorget destroyed, stagger |
| Limb joint | Cleave crit | De-limbing; limb physics detach |
| Limb joint | Blunt crit | Joint dislocation; ROM becomes 0, dangling |
| Spine | Blunt crit | Knockdown, possible paralysis state |
| Skull, no helm | Blunt | Concussion, vision blur, stagger |
| Skull, great helm | Blunt crit | Helm deforms, neck trauma, stagger |
| Knee, no poleyn | Sweep/Kick | Knee collapse; injured-leg locomotion |
| Ribs, no chest | Blunt | Breathing interrupt, stamina penalty |
| Hands, no gauntlets | Slash | Finger severance; grip becomes 0, weapon dropped |
| Ankle, no sabatons | Sweep | Ankle break; drag-foot locomotion |

## Recommended Simulation Stack

This stack is a research direction, not an immediate implementation requirement:

- Cloth/leather: XPBD / Position-Based Dynamics.
- Chainmail: custom rigid-body constraint graph, GPU-parallelized constraint solver.
- Plate: corotational tetrahedral FEM, using ARCSim-style sheet deformation references.
- Rune-Marble: Voronoi pre-fracture plus runtime crack propagation.
- Bone plates: brittle FEM with irregular Voronoi and surface-normal bias.
- Visual updates: GPU mesh deformation, per-impact dent maps, integrity-driven crack/shatter shaders.

## Prototype Gate

Armor simulation is allowed only after the core YOMI loop is fun without it. Its gate is not visual fidelity; it passes only if loadout choice creates clearer, more interesting combat reads and counterplay.
