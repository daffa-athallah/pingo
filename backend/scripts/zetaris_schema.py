#!/usr/bin/env python3
"""Create the recall_data schema in a Zetaris instance from backend/sql/zetaris_schema_create.sql.

Dry-run by default: it only reads (SHOW LIGHTNING DATABASES) and prints the statements it would send.
--apply runs them one at a time and refuses if recall_data already exists, because the SQL file is an
initial-creation script. No credentials are printed.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

from backend.app.adapters.zetaris import JdbcSettings, ZetarisError, ZetarisJdbc

SQL_FILE = ROOT / 'backend/sql/zetaris_schema_create.sql'
DATABASE = 'recall_data'


def statements(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if not line.strip().startswith('--')]
    return [part.strip() for part in '\n'.join(lines).split(';') if part.strip()]


def schema_exists(connection: ZetarisJdbc) -> bool:
    """Native datalakes do not appear in SHOW LIGHTNING DATABASES, so probe a table instead."""
    try:
        connection.query(f'SELECT COUNT(*) FROM {DATABASE}.app.evidence')
        return True
    except ZetarisError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--apply', action='store_true', help='actually create the schema')
    args = parser.parse_args()
    for path in args.env_file:
        if not path.is_file():
            parser.error('An explicitly supplied environment file does not exist.')
        load_dotenv(path, override=False)
    plan = statements(SQL_FILE.read_text(encoding='utf-8'))
    try:
        with ZetarisJdbc(JdbcSettings.from_env()) as connection:
            present = schema_exists(connection)
            print(f'[INFO] {DATABASE} already exists: {present}')
            for number, statement in enumerate(plan, start=1):
                print(f'  {number}. {statement.splitlines()[0][:90]}')
            if not args.apply:
                print('[DRY RUN] nothing was sent. Re-run with --apply to create the schema.')
                return 0
            if present:
                print(f'[FAIL] {DATABASE} already exists; inspect it instead of re-running the creation script.')
                return 1
            for number, statement in enumerate(plan, start=1):
                try:
                    connection.query(statement)
                except ZetarisError:
                    print(f'[FAIL] statement {number}/{len(plan)} failed: {statement.splitlines()[0][:90]}')
                    raise
                print(f'[OK] statement {number}/{len(plan)}')
            print(f'[PASS] created; schema readable: {schema_exists(connection)}')
    except ZetarisError as exc:
        print('[FAIL] ' + str(exc))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
