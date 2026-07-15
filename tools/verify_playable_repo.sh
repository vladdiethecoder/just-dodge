#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
if [[ -n $(git -C "$ROOT" status --porcelain --untracked-files=no) ]]; then
    echo "refusing to verify a tracked dirty worktree" >&2
    exit 1
fi

cd "$ROOT"
cargo fmt --check
python3 tools/verify_pvp005_revision_baseline.py
python3 tools/verify_pvp005_candidate_packet.py
python3 tools/qa/pvp005_visual_contract.py
python3 tools/qa/test_pvp005_visual_contract.py
RUSTFLAGS='-D warnings' cargo clippy --locked --all-targets -- -D warnings
RUSTFLAGS='-D warnings' cargo test --locked --all-targets -- --test-threads=1
(cd assets && sha256sum --check motionbricks_runtime.sha256)
RUSTFLAGS='-D warnings' cargo test --locked --lib \
    motion_runtime::tests::preloaded_m3_clips_are_finite_rigid_and_cached -- \
    --ignored --exact --test-threads=1
RUSTFLAGS='-D warnings' cargo test --locked --test c0_official_motion -- \
    --ignored --exact --test-threads=1
RUSTFLAGS='-D warnings' cargo test --locked --test motion_service_integration -- \
    --ignored --exact --test-threads=1

VERIFY_ROOT="$ROOT/target/playable-package-verify"
rm -rf -- "$VERIFY_ROOT"
mkdir -p -- "$VERIFY_ROOT"
tools/package_release.sh "$VERIFY_ROOT/package-a"
tools/package_release.sh "$VERIFY_ROOT/package-b"
tools/verify_release_package.sh "$VERIFY_ROOT/package-a"
tools/verify_release_package.sh "$VERIFY_ROOT/package-b"

diff -u \
    "$VERIFY_ROOT/package-a/MANIFEST.sha256" \
    "$VERIFY_ROOT/package-b/MANIFEST.sha256"
diff -qr "$VERIFY_ROOT/package-a" "$VERIFY_ROOT/package-b"
git diff --check

printf 'PLAYABLE_REPO_VERIFY=PASS package_assemblies=2 identical=true pvp005_candidate_packet=hash_bound_pending_human_trials\n'
