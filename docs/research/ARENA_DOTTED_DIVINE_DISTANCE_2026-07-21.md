# Just Dodge Arena — Real Sand / Dotted Divine Distance

**Date:** 2026-07-21
**Status:** art-direction research plus generated concept; no runtime implementation or promotion claim.
**Source:** Bobo Wong / `@poistudioltd`, direct X thread retrieved 2026-07-21.

## Verified source technique

The author calls the look “dotted old school painting” and describes a Midjourney Moodboard workflow:

1. Build one moodboard for old-school oil painting; author code `m7440400818789941258`.
2. Build one moodboard for dithering; author code `m7440402448281239591`.
3. Write the scene/object prompt and apply both moodboards.
4. Preserve successful prompts/images as a growing reference library.

Direct sources:

- <https://x.com/poistudioltd/status/2078691319451718049>
- <https://x.com/poistudioltd/status/2078691339877974518>
- <https://x.com/poistudioltd/status/2078691357443633226>
- <https://x.com/poistudioltd/status/2078691373738541494>
- <https://x.com/poistudioltd/status/2078691425093566642>

The author says some painting references came from `@BrettFromDJ` and dither references from Pinterest. That is discovery evidence, not a transferable game-development license. Just Dodge must use cleared CC0/public-domain/commissioned/internally generated references or text-only style direction with a provenance receipt.

The separate Grok share supplied by the user is an external synthesis. It does not change what the direct `@poistudioltd` thread says; Grok was not part of the verified production technique.

## Applied Just Dodge interpretation

Do not apply a full-screen dither filter. Separate the authority by depth/material:

- **Gameplay foreground:** physically grounded, readable tan sand island. Normal/roughness/macro variation may be realistic; no high-contrast dot pattern that masks foot placement, weapon arcs, contacts or injury evidence.
- **Mid/far water:** simplified cyan/turquoise planes with a world-stable painterly/dither atlas, low-frequency reflection and restrained sparkle.
- **Far sky/clouds/sun:** palette-ramped old-painting treatment plus stable halftone/dot texture. No temporal screen-space crawl.
- **Divine architecture:** silhouette-first Greco-anime monuments, ivory/gold/cool-lavender value groups, far-background stipple. Keep the center combat lane and opponent silhouette clear.
- **Characters, weapons, VFX and debug/evidence overlays:** excluded from background dithering.

## Generated concept v1

Codex/gpt-image-2-high generated the first internally controlled reference from a text brief—no third-party image was supplied:

- `docs/research/media/jd_arena_dotted_old_school_concept_v1.png`
- SHA-256: `32a84cb681196810ac12217394fe9000a1e76364baaae44940b6cc02a20d84c8`
- Pixels: 1672×941 RGB PNG.
- Producer: OpenAI Codex `gpt-image-2-high`, 2026-07-21.

Observed strengths:

- realistic and unobstructed sand foreground;
- strong first-person lane with a dark central opponent silhouette;
- dotted/painterly treatment concentrated in sky/clouds/distant architecture;
- gold/cyan/lavender palette with clear foreground/background separation;
- no HUD/text/logo contamination.

Observed defects/risks:

- architecture density and sun contrast can compete with a small distant opponent;
- concept contains generated first-person hands/weapon and is not a canonical character/weapon design;
- no proof of camera-rotation stability, temporal shimmer, actual engine cost, arena dimensions, collision or gameplay readability under blood/VFX/weather.

## Runtime implementation plan

### A. Geometry and camera proof

1. Preserve current deterministic arena truth; replace no collision or gameplay logic.
2. Build only a render-side island disk/rim/water/architecture background prototype.
3. Test first-person, birds-eye and failure-revealing edge views.
4. Target sand occupancy of roughly 20–45% of the first-person frame; record actual bounds instead of hardcoding acceptance around this estimate.
5. Keep central architecture/value contrast below the opponent silhouette at expected engagement distance.

### B. Material dither first

1. Author palette/dither atlases for sky, water and far masonry.
2. Use world- or UV-locked coordinates so pattern does not crawl with the camera.
3. Mipmap, anisotropic filtering and explicit LOD bias are measured, not guessed.
4. Exclude sand/characters/weapons from the far-material dither.
5. Capture 360° rotation and camera-translation sequences and compare temporal difference energy.

### C. Optional background-only post

Add a post pass only if material dither cannot produce the required treatment. Require explicit depth/material/object-ID masking and verify that foreground, opponent, weapon, VFX and evidence overlays remain bit/pixel equivalent with the pass enabled versus an exclusion reference.

### D. Steam Deck/RTX validation

Measure GPU time and VRAM on both targets. Start with a 2048×1024 sky treatment (~8 MiB uncompressed RGBA), 2048² atlas (~16 MiB) and 960×540 half-resolution background pass (~1.98 MiB target) only as hypotheses; measured profiler output decides final sizes.

## Falsifiable gates

- opponent silhouette remains readable against every far-background sector at minimum/normal/maximum encounter distance;
- player foot-contact and injury evidence remain readable on sand;
- no dithering reaches first-person hands/weapon, opponents, blood/VFX or debug/evidence overlays;
- no visible camera-locked crawl under slow and fast 360° yaw, strafe and FOV changes;
- stable repeated-render pixels for identical inputs after removing expected metadata;
- no truth/replay hash change with the visual profile toggled;
- fresh-launch capture and first frame match the intended profile;
- RTX 5090 and Steam Deck GPU/VRAM budgets pass measured thresholds;
- human visual review accepts the style before runtime promotion.

`runtime_admitted=false` until all gates pass.
