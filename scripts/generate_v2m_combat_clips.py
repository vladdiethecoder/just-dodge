#!/usr/bin/env python3
"""Produce short, provenance-tracked V2M clips from yt-dlp-acquired source videos."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path('/run/media/vdubrov/Bulk-SSD/combat_mocap_sources/v2m_videos/real_life')
CACHE = ROOT / '.source_cache'
USAGE_NOTE = (
    'No explicit reuse license was supplied by the YouTube extractor. Public availability is not a '
    'license grant. Retain for internal V2M research/evaluation only; do not redistribute, publish, '
    'or use for external/commercial model training without obtaining rights clearance from the rights holder.'
)

# filename, category, source id, start seconds, end seconds, action annotation
SPECS = [
    ('mma_001_clinch_entry.mp4', 'mma_grappling', 'qN5QMETjwx4', 12, 27, 'two-person striking-to-clinch entry'),
    ('mma_002_level_change.mp4', 'mma_grappling', 'qN5QMETjwx4', 27, 42, 'two-person level-change takedown entry'),
    ('mma_003_takedown_chain.mp4', 'mma_grappling', 'qN5QMETjwx4', 42, 57, 'two-person takedown chain drill'),
    ('mma_004_clinch_finish.mp4', 'mma_grappling', 'qN5QMETjwx4', 57, 72, 'two-person clinch-to-takedown finish'),
    ('mma_005_ground_shrimp.mp4', 'mma_grappling', 'HmYe8ythRv8', 24, 39, 'solo ground mobility / shrimp transition'),
    ('mma_006_ground_roll.mp4', 'mma_grappling', 'HmYe8ythRv8', 47, 62, 'solo ground roll and recovery transition'),
    ('mma_007_ground_sitthrough.mp4', 'mma_grappling', 'HmYe8ythRv8', 77, 92, 'solo sit-through / base transition'),
    ('mma_008_ground_standup.mp4', 'mma_grappling', 'HmYe8ythRv8', 107, 122, 'solo ground-to-standing transition'),
    ('boxing_001_bag_combo_a.mp4', 'boxing', 'HoWdEb7XUVg', 5, 22, 'full-body bag combination'),
    ('boxing_002_bag_combo_b.mp4', 'boxing', 'HoWdEb7XUVg', 35, 52, 'full-body bag combination'),
    ('boxing_003_bag_combo_c.mp4', 'boxing', 'HoWdEb7XUVg', 65, 82, 'full-body bag combination'),
    ('boxing_004_bag_combo_d.mp4', 'boxing', 'HoWdEb7XUVg', 125, 142, 'full-body bag combination'),
    ('boxing_005_bag_combo_e.mp4', 'boxing', 'HoWdEb7XUVg', 185, 202, 'full-body bag combination and head movement'),
    ('boxing_006_bag_combo_f.mp4', 'boxing', 'HoWdEb7XUVg', 245, 262, 'full-body bag combination and evasive footwork'),
    ('muay_thai_001_clinch_knees_a.mp4', 'muay_thai', 'JYJOZ3UtYnQ', 25, 43, 'two-person clinch knee drill'),
    ('muay_thai_002_clinch_knees_b.mp4', 'muay_thai', 'JYJOZ3UtYnQ', 53, 71, 'two-person clinch control and knee drill'),
    ('muay_thai_003_clinch_knees_c.mp4', 'muay_thai', 'JYJOZ3UtYnQ', 83, 101, 'two-person clinch pummeling and knee drill'),
    ('muay_thai_004_clinch_knees_d.mp4', 'muay_thai', 'JYJOZ3UtYnQ', 113, 131, 'two-person clinch knee sequence'),
    ('muay_thai_005_clinch_knees_e.mp4', 'muay_thai', 'JYJOZ3UtYnQ', 143, 161, 'two-person clinch knee sequence'),
    ('judo_001_throw_a.mp4', 'judo', 'p2GoHX3lnWc', 10, 25, 'paired throw compilation segment'),
    ('judo_002_throw_b.mp4', 'judo', 'p2GoHX3lnWc', 28, 43, 'paired throw compilation segment'),
    ('judo_003_throw_c.mp4', 'judo', 'p2GoHX3lnWc', 46, 61, 'paired throw compilation segment'),
    ('judo_004_throw_d.mp4', 'judo', 'p2GoHX3lnWc', 64, 79, 'paired throw compilation segment'),
    ('judo_005_throw_e.mp4', 'judo', 'p2GoHX3lnWc', 82, 97, 'paired throw compilation segment'),
    ('karate_kata_001_sequence_a.mp4', 'karate_kata', 'iiiznDpoapQ', 25, 45, 'competition kata full-body sequence'),
    ('karate_kata_002_sequence_b.mp4', 'karate_kata', 'iiiznDpoapQ', 55, 75, 'competition kata full-body sequence'),
    ('karate_kata_003_sequence_c.mp4', 'karate_kata', 'iiiznDpoapQ', 85, 105, 'competition kata full-body sequence'),
    ('karate_kata_004_sequence_d.mp4', 'karate_kata', 'iiiznDpoapQ', 115, 135, 'competition kata full-body sequence'),
    ('karate_kumite_001_footwork_a.mp4', 'karate_kumite', '3qGuXsn6kfc', 20, 38, 'two-person kumite footwork drill'),
    ('karate_kumite_002_footwork_b.mp4', 'karate_kumite', '3qGuXsn6kfc', 50, 68, 'two-person kumite entry and footwork drill'),
    ('karate_kumite_003_footwork_c.mp4', 'karate_kumite', '3qGuXsn6kfc', 80, 98, 'two-person kumite footwork drill'),
    ('karate_kumite_004_footwork_d.mp4', 'karate_kumite', '3qGuXsn6kfc', 110, 128, 'two-person kumite footwork drill'),
    ('kendo_001_keiko_a.mp4', 'kendo', 'iZ2QCtxlaag', 2, 12, 'two-person kendo keiko exchange'),
    ('kendo_002_keiko_b.mp4', 'kendo', 'iZ2QCtxlaag', 12, 22, 'two-person kendo keiko exchange'),
    ('kendo_003_keiko_c.mp4', 'kendo', 'iZ2QCtxlaag', 22, 32, 'two-person kendo keiko exchange'),
    ('kendo_004_keiko_d.mp4', 'kendo', 'iZ2QCtxlaag', 32, 42, 'two-person kendo keiko exchange'),
    ('kung_fu_staff_001_form_a.mp4', 'kung_fu_weapons', 'XorFeDBDMt8', 3, 17, 'full-body Shaolin staff form'),
    ('kung_fu_staff_002_form_b.mp4', 'kung_fu_weapons', 'XorFeDBDMt8', 17, 31, 'full-body Shaolin staff form'),
    ('kung_fu_staff_003_form_c.mp4', 'kung_fu_weapons', 'XorFeDBDMt8', 31, 45, 'full-body Shaolin staff form'),
    ('kung_fu_staff_004_form_d.mp4', 'kung_fu_weapons', 'XorFeDBDMt8', 45, 59, 'full-body Shaolin staff form'),
    ('wrestling_001_shot_drill_a.mp4', 'wrestling', 'ENhK2w0Znqs', 75, 92, 'two-person takedown drill'),
    ('wrestling_002_shot_drill_b.mp4', 'wrestling', 'ENhK2w0Znqs', 105, 122, 'two-person takedown drill'),
    ('wrestling_003_shot_drill_c.mp4', 'wrestling', 'ENhK2w0Znqs', 165, 182, 'two-person takedown drill'),
    ('wrestling_004_shot_drill_d.mp4', 'wrestling', 'ENhK2w0Znqs', 285, 302, 'two-person takedown drill'),
    ('wrestling_005_shot_drill_e.mp4', 'wrestling', 'ENhK2w0Znqs', 315, 332, 'two-person takedown drill'),
    ('wrestling_006_shot_drill_f.mp4', 'wrestling', 'ENhK2w0Znqs', 375, 392, 'two-person takedown drill'),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path) -> dict:
    output = subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries',
        'format=duration,size:stream=codec_name,width,height,avg_frame_rate',
        '-of', 'json', str(path),
    ], text=True)
    data = json.loads(output)
    video = next(stream for stream in data['streams'] if 'width' in stream)
    return {
        'duration_seconds': round(float(data['format']['duration']), 3),
        'size_bytes': int(data['format']['size']),
        'codec': video['codec_name'],
        'width': video['width'],
        'height': video['height'],
        'frame_rate': video.get('avg_frame_rate'),
    }


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    source_meta = {}
    for meta_path in CACHE.glob('*.info.json'):
        data = json.loads(meta_path.read_text())
        source_meta[data['id']] = data

    records = []
    for number, (name, category, source_id, start, end, action) in enumerate(SPECS, start=1):
        input_path = CACHE / f'{source_id}.mp4'
        output_dir = ROOT / category
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / name
        if not input_path.exists():
            raise FileNotFoundError(input_path)
        expected_duration = end - start
        # Re-encode to make crop bounds exact even if a requested timestamp is not a source keyframe.
        subprocess.run([
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-ss', str(start), '-i', str(input_path), '-t', str(expected_duration),
            '-map', '0:v:0', '-an', '-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', '19', '-b:v', '0',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output_path),
        ], check=True)
        meta = source_meta[source_id]
        extracted_license = meta.get('license')
        record = {
            'clip_number': number,
            'file': str(output_path.relative_to(ROOT)),
            'category': category,
            'action_annotation': action,
            'source_id': source_id,
            'source_url': meta['webpage_url'],
            'source_title': meta.get('title'),
            'source_channel': meta.get('channel') or meta.get('uploader'),
            'source_upload_date': meta.get('upload_date'),
            'source_duration_seconds': meta.get('duration'),
            'source_license_extractor_value': extracted_license,
            'license_status': 'not specified by extractor' if not extracted_license else extracted_license,
            'usage_note': USAGE_NOTE,
            'clip_start_seconds': start,
            'clip_end_seconds': end,
            'intended_duration_seconds': expected_duration,
            **probe(output_path),
            'sha256': sha256(output_path),
        }
        records.append(record)
        print(f'[{number:02d}/{len(SPECS)}] {record["file"]} {record["duration_seconds"]:.3f}s')

    (ROOT / 'provenance.json').write_text(json.dumps({
        'dataset': 'real-life-combat-v2m-sources',
        'clip_count': len(records),
        'source_count': len(source_meta),
        'usage_policy': USAGE_NOTE,
        'clips': records,
    }, indent=2) + '\n')
    with (ROOT / 'provenance.csv').open('w', newline='') as handle:
        fields = list(records[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    (ROOT / 'README.md').write_text(
        '# Real-life combat V2M clips\n\n'
        f'- **{len(records)}** short H.264/MP4 clips (10–20 seconds each) across MMA, boxing, Muay Thai, judo, karate kata/kumite, kendo, kung fu staff, and wrestling.\n'
        '- Source acquisition used `yt-dlp`; individual clips were precisely cropped/re-encoded with `ffmpeg`.\n'
        '- `provenance.json` and `provenance.csv` contain source URLs, titles, exact bounds, technical checks, hashes, and rights notes.\n'
        '- **Rights:** source metadata did not report an explicit reusable license. Treat every clip as internal research/evaluation material only pending direct clearance; public access is not a license grant.\n'
    )
    # Full source files are intentionally removed: the deliverable keeps only short clips.
    for path in CACHE.glob('*.mp4'):
        path.unlink()
    shutil.rmtree(CACHE / 'contact_sheets', ignore_errors=True)


if __name__ == '__main__':
    main()
