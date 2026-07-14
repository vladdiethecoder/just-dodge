#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
OUTPUT=${1:-"$ROOT/qa_runs/pvp005_visual_harness"}
MANIFEST="$ROOT/assets/motion/pvp005_candidates/manifest.json"

if [[ -e "$OUTPUT" ]]; then
    echo "refusing to overwrite visual evidence: $OUTPUT" >&2
    exit 1
fi
if ! command -v montage >/dev/null 2>&1; then
    echo "ImageMagick montage is required" >&2
    exit 1
fi

cd "$ROOT"
python3 tools/verify_pvp005_candidate_packet.py
cargo build --locked --bin shot
mkdir -p -- "$OUTPUT"

while IFS=$'\t' read -r action candidate frame attach; do
    action_dir="$OUTPUT/$candidate"
    mkdir -p -- "$action_dir"
    touch "$action_dir/render.log"
    JUSTDODGE_QA_F413="$ROOT/assets/motion/pvp005_candidates/$action/$candidate.413.f32" \
    JUSTDODGE_QA_FRAME="$frame" \
    JUSTDODGE_QA_ATTACH_W0="$attach" \
    JUSTDODGE_QA_OUT_DIR="$action_dir" \
    JUSTDODGE_QA_LABEL="${candidate}_f$(printf '%02d' "$frame")" \
        "$ROOT/target/debug/shot" >> "$action_dir/render.log" 2>&1
done < <(
    python3 - "$MANIFEST" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
for action in ("strike", "block", "grab"):
    entry = manifest["actions"][action]
    attach = int(entry["weapon_in_reveal"])
    for frame in entry["tell_frames"]:
        print(action, entry["candidate"], frame, attach, sep="\t")
PY
)

while IFS=$'\t' read -r candidate; do
    for view in front side; do
        mapfile -t images < <(
            find "$OUTPUT/$candidate" -maxdepth 1 -type f \
                -name "${candidate}_f*_${view}.png" -print | LC_ALL=C sort
        )
        if [[ ${#images[@]} -ne 8 ]]; then
            echo "$candidate/$view expected 8 images, got ${#images[@]}" >&2
            exit 1
        fi
        montage "${images[@]}" -thumbnail 512x512 -tile 8x1 -geometry +4+4 \
            -background '#111111' "$OUTPUT/${candidate}_${view}_reveal.png"
    done
done < <(
    python3 - "$MANIFEST" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
for action in ("strike", "block", "grab"):
    print(manifest["actions"][action]["candidate"])
PY
)

python3 tools/qa/analyze_pvp005_c0_visuals.py \
    --render-root "$OUTPUT" \
    --manifest "$MANIFEST" \
    --output "$OUTPUT/visual_report.json"
sha256sum "$OUTPUT/visual_report.json" "$OUTPUT/index.html" > "$OUTPUT/SHA256SUMS.txt"
printf 'PVP005_VISUAL_HARNESS_OUTPUT=%s\n' "$OUTPUT"
