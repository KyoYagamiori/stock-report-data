from __future__ import annotations

import argparse
import json
from pathlib import Path

from ma5_system.publisher import verify_manifest_pointer
from ma5_system.simulation import record_simulation_day, simulation_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a private MA5 paper-trading audit day")
    parser.add_argument("--phase", default="close", choices=["preclose", "close"])
    parser.add_argument("--root", default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    screen = verify_manifest_pointer(root, args.phase)
    path = record_simulation_day(screen, root)
    print(json.dumps({"path": str(path), "status": simulation_status(root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
