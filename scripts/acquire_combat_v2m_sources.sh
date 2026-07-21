#!/usr/bin/env bash
set -euo pipefail

DEST='/run/media/vdubrov/Bulk-SSD/combat_mocap_sources/v2m_videos/real_life'
CACHE="$DEST/.source_cache"
mkdir -p "$CACHE"

# Curated public YouTube source pages. Each is cropped locally into short V2M clips;
# source metadata is retained as provenance before the cache is removed.
urls=(
  'https://www.youtube.com/watch?v=qN5QMETjwx4' # MMA blend/takedown drills
  'https://www.youtube.com/watch?v=HmYe8ythRv8' # MMA floor movement/ground transitions
  'https://www.youtube.com/watch?v=HoWdEb7XUVg' # boxing combinations
  'https://www.youtube.com/watch?v=JYJOZ3UtYnQ' # Muay Thai clinch drills
  'https://www.youtube.com/watch?v=p2GoHX3lnWc' # judo throw compilation
  'https://www.youtube.com/watch?v=iiiznDpoapQ' # WKF kata
  'https://www.youtube.com/watch?v=3qGuXsn6kfc' # karate kumite/footwork
  'https://www.youtube.com/watch?v=iZ2QCtxlaag' # kendo keiko
  'https://www.youtube.com/watch?v=XorFeDBDMt8' # Shaolin staff form
  'https://www.youtube.com/watch?v=ENhK2w0Znqs' # wrestling partner drills
)

yt-dlp \
  --no-playlist \
  --write-info-json \
  --no-write-comments \
  --no-write-thumbnail \
  --remux-video mp4 \
  -f 'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[ext=mp4]/b' \
  -o "$CACHE/%(id)s.%(ext)s" \
  "${urls[@]}"

# A metadata-only JSONL snapshot makes the source title/uploader/duration stable even
# if a page later changes or is removed.
for meta in "$CACHE"/*.info.json; do
  jq -c '{id,title,channel,uploader,duration,license,availability,webpage_url,upload_date,description}' "$meta"
done > "$CACHE/source_metadata.jsonl"
