#!/usr/bin/env python3
"""Explicit live repository checks using labeled synthetic fixture records only."""
import argparse
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    if not args.env_file.is_file():
        parser.error('Environment file does not exist.')
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    os.environ['RUN_ZETARIS_INTEGRATION'] = 'true'
    suite = unittest.defaultTestLoader.loadTestsFromName('backend.tests.test_zetaris_live')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print('These are synthetic storage fixture checks, not the OMB Burger real-data proof.')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
