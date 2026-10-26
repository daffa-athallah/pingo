#!/usr/bin/env python3
"""Export the canonical historical state (read-only) to backend/demo/snapshot.json for the resettable demo workspace."""
import argparse
import json
from pathlib import Path

import real_env
from real_env import real_repository
from backend.app.demo_workspace import SNAPSHOT_PATH, export_snapshot, read_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, default=SNAPSHOT_PATH)
    args = parser.parse_args()
    real_env.load_env(args.env_file)
    with real_repository() as repo:
        data = export_snapshot(repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True))
    read_snapshot(args.output)  # validates what was written
    print(f"[PASS] wrote {args.output} ({args.output.stat().st_size // 1024} KB): {data['meta']['counts']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
