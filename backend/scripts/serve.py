#!/usr/bin/env python3
"""Host HTTP entrypoint with explicit local env files; Docker passes env directly.

  serve.py                 canonical: Zetaris + real models (port 8000)
  serve.py --demo          resettable demo workspace: in-memory copy of the historical snapshot + real models (port 8100).
                           Loads only backend/.env (Nightshift); no Zetaris credentials, no Zetaris connection, nothing canonical is written.
  SAMPLE_MODE=true serve.py   credential-free scripted sample
"""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int)
    parser.add_argument('--demo', action='store_true', help='run the resettable demo workspace instead of canonical Zetaris')
    args = parser.parse_args()
    if any(not path.is_file() for path in args.env_file):
        parser.error('An explicitly supplied environment file does not exist.')
    if args.demo:
        os.environ['RECALL_MODE'] = 'demo'
    from dotenv import load_dotenv
    defaults = [ROOT / 'backend/.env'] if args.demo else [ROOT / 'backend/.env.local']
    for path in [*args.env_file, *defaults]:
        if path.is_file():
            load_dotenv(path, override=False)
    import uvicorn
    uvicorn.run('backend.app.main:app', host=args.host, port=args.port or (8100 if args.demo else 8000), workers=1)
