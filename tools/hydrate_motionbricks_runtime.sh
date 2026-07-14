#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$project_root/assets/motionbricks_runtime.sha256"
source_dir="${1:-${MOTIONBRICKS_ARTIFACT_SOURCE:-}}"
destination_dir="${2:-$project_root/assets}"

if [[ -z "$source_dir" ]]; then
  printf '%s\n' \
    "usage: $0 SOURCE_DIR [DESTINATION_DIR]" \
    "or set MOTIONBRICKS_ARTIFACT_SOURCE to a trusted bundle directory" >&2
  exit 64
fi

source_dir="$(cd "$source_dir" && pwd)"
mkdir -p "$destination_dir"
destination_dir="$(cd "$destination_dir" && pwd)"

printf 'Verifying MotionBricks source bundle: %s\n' "$source_dir"
(cd "$source_dir" && sha256sum --check "$manifest")

while read -r expected file; do
  [[ "$file" != */* && "$file" != .* ]] || {
    printf 'unsafe manifest path: %s\n' "$file" >&2
    exit 65
  }
  source_file="$source_dir/$file"
  destination_file="$destination_dir/$file"
  if [[ "$source_file" -ef "$destination_file" ]]; then
    continue
  fi
  staged="$destination_file.part.$$"
  rm -f "$staged"
  cp --reflink=auto -- "$source_file" "$staged"
  printf '%s  %s\n' "$expected" "$staged" | sha256sum --check --status
  mv -f -- "$staged" "$destination_file"
done < "$manifest"

printf 'Verifying hydrated MotionBricks destination: %s\n' "$destination_dir"
(cd "$destination_dir" && sha256sum --check "$manifest")
printf 'MOTIONBRICKS_HYDRATION=PASS files=%s\n' "$(wc -l < "$manifest")"
