#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <package-directory>" >&2
    exit 2
fi

PACKAGE=$(cd -- "$1" && pwd -P)
MANIFEST="$PACKAGE/MANIFEST.sha256"
[[ -f "$MANIFEST" ]] || { echo "missing MANIFEST.sha256" >&2; exit 1; }

EXPECTED=(
    BUILD-INFO.txt
    MANIFEST.sha256
    bin/just-dodge
    bin/m3_match
    docs/PACKAGE_BOUNDARY.md
    just-dodge
    assets/arena_rock.bin
    assets/arena_rock_0.png
    assets/lintel_gate.bin
    assets/lintel_gate_0.jpg
    assets/rune_pillar.bin
    assets/rune_pillar_0.jpg
    assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin
    assets/weapons/w0_sword_assembled.bin
)
for relative in "${EXPECTED[@]}"; do
    [[ -f "$PACKAGE/$relative" ]] || { echo "missing package file: $relative" >&2; exit 1; }
done

if find "$PACKAGE" -type l -print -quit | grep -q .; then
    echo "package contains a symbolic link" >&2
    exit 1
fi

while IFS= read -r line; do
    relative=${line#*  }
    if [[ "$relative" != ./* || "$relative" == *../* ]]; then
        echo "unsafe manifest path: $relative" >&2
        exit 1
    fi
done < "$MANIFEST"

(
    cd "$PACKAGE"
    sha256sum --check --strict MANIFEST.sha256
)

mapfile -t ACTUAL < <(cd "$PACKAGE" && find . -type f ! -name MANIFEST.sha256 -print | LC_ALL=C sort)
mapfile -t DECLARED < <(sed -n 's/^[0-9a-f]\{64\}  //p' "$MANIFEST" | LC_ALL=C sort)
if [[ "${ACTUAL[*]}" != "${DECLARED[*]}" ]]; then
    echo "manifest does not cover exactly the package files" >&2
    exit 1
fi

grep -qx 'package_format=just-dodge-local-technical-v1' "$PACKAGE/BUILD-INFO.txt"
grep -Eq '^source_revision=[0-9a-f]{40}$' "$PACKAGE/BUILD-INFO.txt"
grep -qx 'distribution_status=NOT_CLEARED_FOR_PUBLIC_REDISTRIBUTION' "$PACKAGE/BUILD-INFO.txt"

REPLAY_DIR=$(mktemp -d)
cleanup() {
    rm -rf -- "$REPLAY_DIR"
}
trap cleanup EXIT
"$PACKAGE/bin/m3_match" --autoplay 1 "$REPLAY_DIR" > "$REPLAY_DIR/autoplay.log"
"$PACKAGE/bin/m3_match" --verify "$REPLAY_DIR/match_00.ron" > "$REPLAY_DIR/verify.log"
grep -q 'frame=342 hash=d1a3cc1bfb9c2f67' "$REPLAY_DIR/autoplay.log"
grep -q 'frames=343 winner=Some(Player) hash=d1a3cc1bfb9c2f67' "$REPLAY_DIR/verify.log"

printf 'PACKAGE_VERIFY=PASS files=%d replay_hash=d1a3cc1bfb9c2f67\n' "${#EXPECTED[@]}"
