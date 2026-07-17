#!/usr/bin/env bash
# Build a Steam-depot-ready Windows x64 package of Just Dodge.
#
# The shipped executable is built with --no-default-features: the
# `motion-inference` feature (ONNX Runtime + the Python MotionBricks bridge) is
# OFF, so just-dodge.exe links no generative model and no Python interpreter.
# Motion ships as baked, validated assets. See JD-RC0 §1 clean-directory contract.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
OUTPUT=${1:-"$ROOT/dist/just-dodge-windows-x86_64"}
TARGET=x86_64-pc-windows-gnu

if [[ -n $(git -C "$ROOT" status --porcelain --untracked-files=no) ]]; then
    echo "refusing to package a tracked dirty worktree" >&2
    exit 1
fi
if [[ "$OUTPUT" == "$ROOT" || "$OUTPUT" == / ]]; then
    echo "unsafe package output: $OUTPUT" >&2
    exit 1
fi

REVISION=$(git -C "$ROOT" rev-parse HEAD)
SOURCE_DATE_EPOCH=$(git -C "$ROOT" show -s --format=%ct HEAD)
export SOURCE_DATE_EPOCH CARGO_INCREMENTAL=0

cargo build --manifest-path "$ROOT/Cargo.toml" --locked --release \
    --no-default-features --target "$TARGET" \
    --bin just-dodge --bin m3_match

STAGE="${OUTPUT}.stage.$$"
MANIFEST_TMP=$(mktemp)
cleanup() {
    rm -rf -- "$STAGE"
    rm -f -- "$MANIFEST_TMP"
}
trap cleanup EXIT
rm -rf -- "$STAGE"
mkdir -p -- "$STAGE/bin" "$STAGE/assets" "$STAGE/docs"

install -m 0755 "$ROOT/target/$TARGET/release/just-dodge.exe" "$STAGE/bin/just-dodge.exe"
install -m 0755 "$ROOT/target/$TARGET/release/m3_match.exe" "$STAGE/bin/m3_match.exe"

ASSETS=(
    arena_rock.bin
    arena_rock_0.png
    lintel_gate.bin
    lintel_gate_0.jpg
    rune_pillar.bin
    rune_pillar_0.jpg
    source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin
    source/meshy/c0_armored_duelist_001/textures/base_color.png
    source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin
    source/meshy/c0_base_fighter/rigged_001/cooked/walking.anim
    motion/pvp005_r6k/hero_strike.motionbricks.interaction.413.f32
    audio/r6k_strike_contact.wav
    weapons/w0_sword_assembled.bin
)
for relative in "${ASSETS[@]}"; do
    install -Dm 0644 "$ROOT/assets/$relative" "$STAGE/assets/$relative"
done

install -m 0644 "$ROOT/docs/PACKAGE_BOUNDARY.md" "$STAGE/docs/PACKAGE_BOUNDARY.md"

# Windows launcher: sets the asset root relative to the package and execs the exe.
cat > "$STAGE/just-dodge.cmd" <<'LAUNCHER'
@echo off
setlocal
set "PACKAGE_ROOT=%~dp0"
set "JUSTDODGE_ASSETS=%PACKAGE_ROOT%assets"
"%PACKAGE_ROOT%bin\just-dodge.exe" %*
LAUNCHER
chmod 0755 "$STAGE/just-dodge.cmd"

cat > "$STAGE/BUILD-INFO.txt" <<EOF
package_format=just-dodge-steam-depot-windows-v1
source_revision=$REVISION
target=$TARGET
build_features=no-default-features (motion-inference OFF; no generative model, no Python interpreter linked)
distribution_status=NOT_CLEARED_FOR_PUBLIC_REDISTRIBUTION
EOF

(
    cd "$STAGE"
    find . -type f ! -name MANIFEST.sha256 -print0 \
        | LC_ALL=C sort -z \
        | xargs -0 sha256sum > "$MANIFEST_TMP"
)
mv -- "$MANIFEST_TMP" "$STAGE/MANIFEST.sha256"

rm -rf -- "$OUTPUT"
mkdir -p -- "$(dirname -- "$OUTPUT")"
mv -- "$STAGE" "$OUTPUT"
trap - EXIT
printf 'package=%s\nrevision=%s\ntarget=%s\n' "$OUTPUT" "$REVISION" "$TARGET"
