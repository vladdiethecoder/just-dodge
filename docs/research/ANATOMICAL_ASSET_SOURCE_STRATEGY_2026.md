# Anatomical Asset Source Strategy — 2026

Date: 2026-07-10
Status: primary-source reconciliation for Just Dodge

## Verdict

No current public model delivers a commercially usable, registered, parametric and animatable human containing skin, fascia, complete skeleton/joints, organs, major vessels and major nerves. Just Dodge therefore needs a provenance-controlled atlas construction pipeline rather than one upstream model.

Meshy remains appropriate for exterior art, clothing, armor, weapons, arena modules and non-authoritative presentation details. Meshy output is not accepted as canonical medical geometry for bones, joints, organs, vessels, nerves, fascia or tissue placement.

## Primary sources

### NLM Visible Human Project

- Official source: https://www.nlm.nih.gov/research/visible/visible_human.html
- NLM describes male and female cryosection/CT/MRI sets as a public-domain library; access no longer requires a license.
- Male color sections: 1 mm spacing, with a later 4096×2700 image set.
- Female color sections: 0.33 mm isotropic spacing, suitable for volumetric reconstruction.
- Strength: cleanest current provenance for distributed anatomy derived from raw registered volume data.
- Limitation: only one male and one female subject; segmentation, reconstruction, registration and retopology remain substantial work.

### BodyParts3D

- Official license: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html
- Current license, updated 2025-02-27: CC Attribution 4.0 International—not CC BY-SA.
- Required attribution: `BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International`.
- Official downloads provide shared-coordinate OBJ archives and anatomical relation tables.
- Strength: broad structure inventory and direct mesh access with commercial reuse permitted under attribution.
- Limitation: static atlas, older topology, no parametric registration or animation. Validate version-coordinate consistency before mixing subsets.

### TotalSegmentator

- Primary repository: https://github.com/wasserth/TotalSegmentator
- Code and the main `total`, `total_mr`, `body`, `lung_vessels`, and many other tasks are explicitly listed as Apache-2.0/open for any usage.
- The project website currently says only named specialist results—including appendicular bones, tissue types, high-resolution heart chambers and face—may not be used commercially; do not generalize that restriction to every task.
- Output is per-subject voxel labels, not registered game meshes.
- Use as a segmentation aid on provenance-clean volumes, then preserve the exact task/version/license in the asset manifest.

### Z-Anatomy and Open3DModel

- Z-Anatomy: https://github.com/Z-Anatomy/Models-of-human-anatomy — CC BY-SA 4.0, containing derivatives from older BodyParts3D releases and other mixed-attribution assets.
- Open3DModel: https://anatomytool.org/open3dmodel — planned CC BY-SA, male model, still incomplete.
- These are useful anatomical and topology references. Direct derivatives carry their stated attribution/share-alike obligations; do not mix them silently into the canonical proprietary source tree.

### SKEL

- Primary project: https://skel.is.tue.mpg.de/
- SKEL is a SIGGRAPH Asia 2023 registered skin+skeleton parametric model with improved biomechanical joints.
- Code/model are explicitly non-commercial scientific research; commercial licensing requires the project licensors.
- It contains no organs, vessels, nerves or fascia.
- Use only as a research/registration reference unless commercial rights are obtained. It is not the default production base.

## Canonical Just Dodge construction path

1. Start from NLM Visible Human volumes or another explicitly cleared clinical volume set.
2. Segment structures using version-pinned open TotalSegmentator tasks and manual anatomy review.
3. Supplement or cross-check structure inventory and spatial relations against current CC-BY BodyParts3D.
4. Surface-extract each required structure; remove segmentation artifacts and disconnected noise.
5. Register structures into a common canonical body and stable 500–1,000-structure ID schema.
6. Retopologize deformable structures, preserve rigid-detail geometry for bones, and build typed joint/vessel/nerve/fascial adjacency.
7. Construct parametric warps across sex, height, mass and body composition; validate non-intersection and attachment constraints.
8. Author deterministic deformation bases/control lattices and material-law assignments.
9. Create presentation LODs and collision acceleration data without replacing the authoritative structures.
10. Record source volume, segmentation task/version, manual edits, transforms, hashes, licenses and acceptance evidence per structure.

## Acceptance gates

- Anatomist-reviewed identity, placement and adjacency for every canonical structure.
- Shared registered coordinate frame and stable IDs.
- Manifold/closed geometry where physiologically applicable; explicit open boundaries where anatomically intended.
- No impossible intersections in canonical and sampled parametric bodies.
- Correct joints, attachments, vessel continuity and nerve routing at gameplay-relevant scale.
- Deterministic reconstruction from canonical deformation/topology state.
- Full/reduced-gore presentation derives from identical truth.
- Provenance and redistribution terms mechanically attached to every source artifact.

## Rejected conclusions from earlier delegated drafts

- BodyParts3D is not currently CC BY-SA 2.1; the official archive changed it to CC BY 4.0 on 2025-02-27.
- TotalSegmentator does not impose one blanket non-commercial weights restriction across all tasks; restrictions are task-specific in current primary documentation.
- SKEL cannot be selected as the production base while its non-commercial license remains unresolved.
- A six-to-eight-region injury model cannot substitute for the locked 500–1,000-structure deformable atlas.
