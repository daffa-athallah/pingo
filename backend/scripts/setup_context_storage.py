#!/usr/bin/env python3
"""Print the two-table dry-run by default. --apply requires explicit reviewed approval."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    statements = [s.strip() for s in '\n'.join(line for line in (ROOT/'backend/sql/context_notifications.sql').read_text().splitlines() if not line.lstrip().startswith('--')).split(';') if s.strip()]
    if not args.apply:
        print(';\n\n'.join(statements)+';')
        return
    from dotenv import load_dotenv
    for path in args.env_file:
        if not path.is_file():
            parser.error('Explicit env file is missing.')
        load_dotenv(path, override=False)
    from backend.app.adapters.zetaris import JdbcSettings, ZetarisJdbc
    try:
        with ZetarisJdbc(JdbcSettings.from_env()) as connection:
            assert int(connection.query('SELECT 1')[0][0]) == 1
            print('[PASS] JDBC SELECT 1')
            for name, sql in zip(('context_evaluations', 'notifications'), statements):
                connection.query(sql)
                connection.query(f'SELECT * FROM recall_data.app.{name} LIMIT 0')
                print('[PASS] Verified', name)
        print('[INFO] REST was not checked; this setup uses JDBC only.')
    except Exception as exc:
        print('[FAIL]', type(exc).__name__, '; connection details withheld')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
