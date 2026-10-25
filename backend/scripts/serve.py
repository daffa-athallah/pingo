#!/usr/bin/env python3
"""Host HTTP entrypoint with explicit local env files; Docker passes env directly."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if any(not path.is_file() for path in args.env_file):
        parser.error('An explicitly supplied environment file does not exist.')
    from dotenv import load_dotenv
    for path in [*args.env_file, ROOT / 'backend/.env.local']:
        if path.is_file():
            load_dotenv(path, override=False)
    import uvicorn
    uvicorn.run('backend.app.main:app', host=args.host, port=args.port, workers=1)
