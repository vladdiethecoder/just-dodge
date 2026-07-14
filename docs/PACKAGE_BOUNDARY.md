# Local Technical Package Boundary

This package is a reproducible technical-development artifact for the current Just Dodge PLAYABLE-PROOF gate. It is not a public release and makes no claim that every included asset is cleared for redistribution.

The package contains only the two release executables and the eight files currently read by the live Player path. `MANIFEST.sha256` covers every packaged file except itself. `tools/verify_release_package.sh` verifies complete manifest coverage and reconstructs a deterministic terminal replay.

Public redistribution remains fail-closed until the project records complete redistribution grants or replaces every payload whose grant is incomplete. Technical development and local evaluation may continue within the recorded source/provenance boundaries.
