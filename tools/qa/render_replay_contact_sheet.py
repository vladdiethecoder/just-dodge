#!/usr/bin/env python3
"""Render validated ResolvePacket evidence as a deterministic SVG contact sheet.

The source of truth is the native reducer (`just-dodge --reduce-replay`), not this
illustration. The tool refuses reports without `verdict=PASS`, then records both
source hashes alongside the SVG so a sheet remains attributable to one replay.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Packet:
    frame: int
    action_tick: int
    first_physics_tick: int
    second_physics_tick: int
    outcome: str
    contact_count: int
    player_action: str
    opponent_action: str
    truth_hash: str


@dataclass(frozen=True)
class Contact:
    frame: int
    action_tick: int
    physics_tick: int
    time_of_impact: float
    attacker_role: str
    defender_role: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_report(report: str) -> tuple[dict[str, str], list[Packet], list[Contact]]:
    metadata: dict[str, str] = {}
    packets: list[Packet] = []
    contacts: list[Contact] = []
    for line in report.splitlines():
        if "=" in line and not line.startswith(" "):
            key, value = line.split("=", 1)
            metadata[key] = value
            continue
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "contact":
            if len(fields) == 2 and fields[1] == "(none)":
                continue
            if len(fields) != 7:
                raise ValueError(f"malformed reducer contact row: {line!r}")
            contacts.append(
                Contact(
                    frame=int(fields[1]),
                    action_tick=int(fields[2]),
                    physics_tick=int(fields[3]),
                    time_of_impact=float(fields[4]),
                    attacker_role=fields[5],
                    defender_role=fields[6],
                )
            )
            continue
        if fields[0].isdigit():
            if len(fields) != 8 or "/" not in fields[2]:
                raise ValueError(f"malformed reducer packet row: {line!r}")
            first_tick, second_tick = fields[2].split("/", 1)
            packets.append(
                Packet(
                    frame=int(fields[0]),
                    action_tick=int(fields[1]),
                    first_physics_tick=int(first_tick),
                    second_physics_tick=int(second_tick),
                    outcome=fields[3],
                    contact_count=int(fields[4]),
                    player_action=fields[5],
                    opponent_action=fields[6],
                    truth_hash=fields[7],
                )
            )
    if metadata.get("verdict") != "PASS":
        raise ValueError("reducer report lacks verdict=PASS")
    if int(metadata.get("resolve_packets", "-1")) != len(packets):
        raise ValueError("reducer packet count does not match parsed rows")
    contact_counts: dict[int, int] = {packet.frame: 0 for packet in packets}
    for contact in contacts:
        if contact.frame not in contact_counts:
            raise ValueError(f"contact references absent ResolvePacket frame {contact.frame}")
        contact_counts[contact.frame] += 1
    for packet in packets:
        if contact_counts[packet.frame] != packet.contact_count:
            raise ValueError(
                f"frame {packet.frame} reports {packet.contact_count} contacts but parsed {contact_counts[packet.frame]}"
            )
    return metadata, packets, contacts


def svg_text(x: int, y: int, text: str, size: int = 22, color: str = "#e8edf7") -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-family="monospace" '
        f'font-size="{size}">{html.escape(text)}</text>'
    )


def render_svg(metadata: dict[str, str], packets: list[Packet], contacts: list[Contact]) -> str:
    width = 1600
    height = 250 + max(1, len(packets)) * 270
    rows: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0a101d"/>',
        svg_text(56, 54, "JUST DODGE — RESOLVE PACKET CONTACT SHEET", 30, "#ffffff"),
        svg_text(
            56,
            88,
            f"seed={metadata.get('seed', '?')} frames={metadata.get('frames', '?')} packets={len(packets)} verdict=PASS",
            18,
            "#aab9d6",
        ),
        svg_text(
            56,
            114,
            "DATA SOURCE: validated ResolvePacket receipt — timeline markers are not rendered poses",
            15,
            "#aab9d6",
        ),
        '<line x1="56" y1="132" x2="1544" y2="132" stroke="#31425f" stroke-width="2"/>',
    ]
    contacts_by_frame: dict[int, list[Contact]] = {packet.frame: [] for packet in packets}
    for contact in contacts:
        contacts_by_frame[contact.frame].append(contact)
    for packet_index, packet in enumerate(packets):
        top = 160 + packet_index * 270
        palette = {"Guard": "#49d17d", "Body": "#ff7b7b", "Whiff": "#82a8ff"}
        outcome_color = palette.get(packet.outcome, "#e8edf7")
        rows.extend(
            [
                f'<rect x="48" y="{top}" width="1504" height="240" rx="16" fill="#111c30" stroke="#31425f" stroke-width="2"/>',
                svg_text(76, top + 42, f"FRAME {packet.frame}  ACTION TICK {packet.action_tick}", 24, "#ffffff"),
                svg_text(76, top + 76, f"{packet.player_action}  vs  {packet.opponent_action}", 20),
                svg_text(76, top + 110, f"OUTCOME  {packet.outcome.upper()}", 24, outcome_color),
                svg_text(
                    76,
                    top + 144,
                    f"truth={packet.truth_hash}  physics={packet.first_physics_tick}/{packet.second_physics_tick}",
                    16,
                    "#aab9d6",
                ),
                f'<line x1="600" y1="{top + 132}" x2="1460" y2="{top + 132}" stroke="#6b7e9e" stroke-width="4"/>',
                svg_text(592, top + 170, "substep start", 15, "#aab9d6"),
                svg_text(1368, top + 170, "substep end", 15, "#aab9d6"),
            ]
        )
        packet_contacts = contacts_by_frame[packet.frame]
        if not packet_contacts:
            rows.append(svg_text(760, top + 102, "NO PHYSICAL CONTACT", 22, "#82a8ff"))
        for contact_index, contact in enumerate(packet_contacts):
            x = round(600 + 860 * contact.time_of_impact)
            y = top + 132
            rows.extend(
                [
                    f'<circle cx="{x}" cy="{y}" r="13" fill="{outcome_color}" stroke="#ffffff" stroke-width="3"/>',
                    svg_text(
                        600,
                        top + 198 + contact_index * 20,
                        f"toi={contact.time_of_impact:.6f} tick={contact.physics_tick} {contact.attacker_role} -> {contact.defender_role}",
                        15,
                        "#dce6fb",
                    ),
                ]
            )
    rows.append("</svg>")
    return "\n".join(rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path, help="built just-dodge binary")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    if not args.replay.is_file():
        raise SystemExit(f"replay not found: {args.replay}")
    if not args.binary.is_file():
        raise SystemExit(f"binary not found: {args.binary}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        [str(args.binary), "--reduce-replay", str(args.replay)],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"reducer failed rc={completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    metadata, packets, contacts = parse_report(completed.stdout)
    report_path = args.output_dir / "reducer_report.txt"
    svg_path = args.output_dir / "contact_sheet.svg"
    receipt_path = args.output_dir / "receipt.json"
    report_path.write_text(completed.stdout, encoding="utf-8")
    svg_path.write_text(render_svg(metadata, packets, contacts), encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "source_replay": str(args.replay.resolve()),
        "source_replay_sha256": sha256_file(args.replay),
        "reducer_report_sha256": sha256_file(report_path),
        "contact_sheet_sha256": sha256_file(svg_path),
        "resolve_packet_count": len(packets),
        "contact_count": len(contacts),
        "verdict": metadata["verdict"],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
