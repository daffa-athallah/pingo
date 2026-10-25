#!/usr/bin/env python3
"""Run a clearly labeled offline Recall fixture, without Zetaris or Nightshift."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app.sample import run_sample


if __name__ == '__main__':
    print(json.dumps(asyncio.run(run_sample()), indent=2))
