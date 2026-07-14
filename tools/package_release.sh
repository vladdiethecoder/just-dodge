#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
OUTPUT=${1:-"$ROOT/dist/just-dodge-linux-x86_64"}

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

install -m 0755 "$ROOT/target/release/just-dodge" "$STAGE/bin/just-dodge"
install -m 0755 "$ROOT/target/release/m3_match" "$STAGE/bin/m3_match"

ASSETS=(
    arena_rock.bin
    arena_rock_0.png
    lintel_gate.bin
    lintel_gate_0.jpg
    rune_pillar.bin
    rune_pillar_0.jpg
    source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin
    weapons/w0_sword_assembled.bin
)
for relative in "${ASSETS[@]}"; do
    install -Dm 0644 "$ROOT/assets/$relative" "$STAGE/assets/$relative"
done

install -m 0644 "$ROOT/docs/PACKAGE_BOUNDARY.md" "$STAGE/docs/PACKAGE_BOUNDARY.md"

cat > "$STAGE/just-dodge" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
PACKAGE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
export JUSTDODGE_ASSETS="$PACKAGE_ROOT/assets"
exec "$PACKAGE_ROOT/bin/just-dodge" "$@"
LAUNCHER
chmod 0755 "$STAGE/just-dodge"

cat > "$STAGE/BUILD-INFO.txt" <<EOF
package_format=just-dodge-local-technical-v1
source_revision=$REVISION
target=x86_64-unknown-linux-gnu
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
printf 'package=%s\nrevision=%s\n' "$OUTPUT" "$REVISION"
