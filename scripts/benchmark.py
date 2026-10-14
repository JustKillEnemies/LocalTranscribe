"""Hardware benchmark launcher; uses AppSettings and a separate test database."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from local_transcriber.infrastructure.benchmark import run_manifest
    from local_transcriber.infrastructure.settings import load_settings

    try:
        return run_manifest(
            args.manifest,
            load_settings(args.env_file),
            Path(__file__).resolve().parents[1],
            args.output,
        )
    except Exception as error:
        print("BENCHMARK FAILED:", type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
