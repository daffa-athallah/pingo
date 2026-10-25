#!/usr/bin/env python3
"""One focused read-only JDBC connection smoke test. No secrets are printed."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.adapters.zetaris import JdbcSettings, ZetarisError, ZetarisJdbc, java_major_version


def smoke() -> None:
    settings = JdbcSettings.from_env()
    print('[PASS] required JDBC settings configured; driver archive and class verified')
    print(f'[PASS] Java {java_major_version()}')
    with ZetarisJdbc(settings) as connection:
        print('[PASS] Zetaris connection opened')
        if connection.query('SELECT 1') not in ([(1,)], [('1',)]):
            raise ZetarisError('SELECT 1 did not return the expected value.')
        print('[PASS] SELECT 1 returned 1')
        print('[INFO] JDBC transactions:', connection.supports_transactions())
    print('[PASS] Zetaris connection closed')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Local credentials file; values are never printed')
    args = parser.parse_args()
    try:
        if args.env_file:
            if not args.env_file.is_file():
                raise ZetarisError('Specified environment file is missing.')
            try:
                from dotenv import load_dotenv
            except ImportError:
                raise ZetarisError('python-dotenv is missing from this runner environment.') from None
            load_dotenv(args.env_file, override=False)
        smoke()
        return 0
    except ZetarisError as exc:
        print('[FAIL]', str(exc))
        return 1


if __name__ == '__main__':
    sys.exit(main())
