"""Prepare pinned public Russian data, or score completed local E2E results."""

import argparse
import json
from pathlib import Path

from local_transcriber.infrastructure.public_benchmark import prepare_fleurs, score_fleurs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("output", type=Path)
    prepare.add_argument("--count", type=int, default=32)
    score = commands.add_parser("score")
    score.add_argument("dataset", type=Path)
    score.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare_fleurs(args.output, count=args.count))
    else:
        print(json.dumps(score_fleurs(args.dataset, args.report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
