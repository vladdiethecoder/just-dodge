#!/usr/bin/env python3
"""Issue a content-addressed ARDY authorization for offline MotionBricks generation.

This command deliberately does not run a model. It validates and binds the
proposal before any expensive generation may begin; `runtime_admitted` is
always false in the resulting certificate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from motionbricks_service.interaction_forward import (  # noqa: E402
    InteractionForwardProposalV1,
    OfflineGenerationCertificateV1,
    canonical_json,
    sha256_file,
    strict_json_load,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--certificate-id", required=True)
    parser.add_argument(
        "--generator-source",
        type=Path,
        default=Path(__file__),
        help="Exact generator source to bind into the authorization receipt.",
    )
    args = parser.parse_args()

    proposal = InteractionForwardProposalV1.from_dict(strict_json_load(args.proposal.read_text("utf-8")))
    generator = args.generator_source.resolve()
    if not generator.is_file():
        raise ValueError(f"generator source is not a file: {generator}")
    certificate = OfflineGenerationCertificateV1.issue(
        proposal,
        args.certificate_id,
        sha256_file(str(generator)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(certificate.to_dict()) + b"\n")
    print(
        "MOTIONBRICKS_INTERACTION_CERTIFICATE=PASS "
        f"proposal_sha256={proposal.digest} certificate_sha256={certificate.digest} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
