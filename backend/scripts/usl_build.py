"""Build, activate and verify the Pingo Unified Semantic Layer (USL) on a running Zetaris platform, and record the real results.

  1. export the two file-based sources (usl_export.py) and copy them into the Zetaris driver container
  2. onboard them as Lightning filestore tables (usl/sql/01_sources.sql)
  3. compile and deploy the USL from its DDL (usl/sql/02_usl_ddl.sql), activate each logical table (03_activate.sql)
  4. register and run the data-quality rules (04_data_quality.sql), then the exploratory and USL queries (05_queries.sql)

Everything is written to usl/results/: RUN.md (every statement with its real output), pingo_usl.compiled.json (the compiled USL).
Run: backend/.venv/bin/python backend/scripts/usl_build.py        Needs the Zetaris platform up (docker compose) and env.local/backend/.env.
Re-runnable: existing objects are replaced or skipped. Read-only on recall_data.app (the Pingo lakehouse is never written).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/scripts'))
sys.path.insert(0, str(ROOT))

from real_env import load_env  # noqa: E402

SQL = ROOT / 'usl/sql'
RESULTS = ROOT / 'usl/results'
CONTAINER = 'zetaris-driver-1'
REMOTE = '/home/zetaris/customer-data/shared/pingo'
NAMESPACE = 'lightning.metastore.pingo'
USL = 'pingo_usl'
RULES = {'verified_place_has_valid_coordinates': 'saved_place', 'confidence_is_a_probability': 'saved_intention', 'model_receipt_is_complete': 'agent_decision', 'active_intention_has_a_screenshot': 'saved_intention'}
log: list[str] = []


def statements(name: str) -> list[tuple[str, str]]:
    """(heading comment, statement) pairs from a file whose statements are separated by a line of four dashes."""
    pairs = []
    for block in (SQL / name).read_text().split('\n----\n'):
        comments = [line[2:].strip() for line in block.splitlines() if line.startswith('--')]
        body = '\n'.join(line for line in block.splitlines() if not line.startswith('--')).strip()
        if body:
            pairs.append((' '.join(comments), body))
    return pairs


def cell(value) -> str:
    text = '' if value is None else str(value)
    return text if len(text) <= 160 else text[:157] + '...'


class Session:
    def __init__(self, connection):
        self.connection = connection

    def run(self, sql: str, *, tolerate: str | None = None, heading: str = '', record: bool = True):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = [tuple(r) for r in cursor.fetchall()] if cursor.description else []
            outcome = 'OK'
        except Exception as error:  # noqa: BLE001 - the server's own message is the evidence
            message = str(error).replace('\n', ' ')
            if tolerate and tolerate.lower() in message.lower():
                columns, rows, outcome = [], [], 'SKIPPED (already exists)'
            else:
                columns, rows, outcome = [], [], 'ERROR ' + message[:400]
        finally:
            cursor.close()
        if record:
            log.append(f'### {heading}\n\n```sql\n{sql}\n```\n\n**{outcome}**' + (f' · {len(rows)} rows' if outcome == 'OK' else ''))
            if rows and len(columns) and len(rows[0]) == len(columns) and sum(len(str(c)) for c in rows[0]) < 900:
                log.append('| ' + ' | '.join(columns) + ' |\n|' + '---|' * len(columns) + '\n' + '\n'.join('| ' + ' | '.join(cell(c) for c in r) + ' |' for r in rows[:12]))
            elif rows:
                log.append('```\n' + '\n'.join(cell(r[0]) if len(r) == 1 else str(tuple(cell(c) for c in r)) for r in rows[:6]) + '\n```')
            log.append('')
        return outcome, rows


def main():
    import usl_export
    from backend.app.adapters.zetaris import JdbcSettings, ZetarisJdbc
    usl_export.main()
    subprocess.run(['docker', 'exec', '-u', 'root', CONTAINER, 'mkdir', '-p', REMOTE], check=True)
    for folder in ('place_directory', 'agent_trace'):
        subprocess.run(['docker', 'cp', str(ROOT / 'usl/data' / folder), f'{CONTAINER}:{REMOTE}/'], check=True)
    subprocess.run(['docker', 'exec', '-u', 'root', CONTAINER, 'sh', '-c', f'chown -R zetaris:zetaris {REMOTE}; chmod -R a+rwX {REMOTE}'], check=True)
    load_env()
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    log.append(f'# Pingo USL · build and verification run\n\nRun at {stamp}. Every output below is the platform\'s own response.\n')
    with ZetarisJdbc(JdbcSettings.from_env()) as connection:
        db = Session(connection._connection)
        log.append('## 1. Onboard the data sources\n')
        for comment, sql in statements('01_sources.sql'):
            db.run(sql, tolerate='already exist', heading=comment or sql.splitlines()[0][:70])
        log.append('### Verify each source is operable\n')
        for sql in ('SELECT count(*) AS rows FROM recall_data.app.evidence', 'SELECT count(*) AS rows FROM pingo_sources.place_directory',
                    'SELECT count(*) AS rows FROM pingo_sources.agent_trace'):
            db.run(sql, heading='Source check')
        log.append('## 2. Compile and deploy the USL\n')
        db.run(f'CREATE NAMESPACE lightning.metastore', tolerate='exist', record=False)
        db.run(f'CREATE NAMESPACE {NAMESPACE}', tolerate='exist', record=False)
        db.run(f'REMOVE USL {USL} NAMESPACE {NAMESPACE}', record=False)
        ddl = (SQL / '02_usl_ddl.sql').read_text()
        ddl = '\n'.join(line for line in ddl.splitlines() if not line.startswith('--'))
        outcome, rows = db.run(f'COMPILE OR REPLACE USL {USL} DEPLOY NAMESPACE {NAMESPACE} DDL\n{ddl}', heading='Compile and deploy (DDL in usl/sql/02_usl_ddl.sql)')
        if rows:
            (RESULTS / 'pingo_usl.compiled.json').write_text(json.dumps(json.loads(rows[0][0]), indent=1))
        db.run(f'SHOW NAMESPACES OR TABLES IN {NAMESPACE}.{USL}', heading='The USL tables')
        log.append('## 3. Activate: bind each logical table to the physical sources\n')
        for comment, sql in statements('03_activate.sql'):
            db.run(sql, heading=sql.splitlines()[0])
        log.append('## 4. Data quality\n')
        for rule, table in RULES.items():
            db.run(f'REMOVE DQ {rule} TABLE {NAMESPACE}.{USL}.{table}', record=False)
        for comment, sql in statements('04_data_quality.sql'):
            db.run(sql, heading=sql.split(' AS ')[0][:90])
        db.run(f'LIST DQ USL {NAMESPACE}.{USL}', heading='Rules registered on the USL (custom + key constraints)')
        log.append('## 5. Queries\n')
        for comment, sql in statements('05_queries.sql'):
            db.run(sql, heading=comment or sql[:80])
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / 'RUN.md').write_text('\n'.join(log) + '\n')
    errors = [entry for entry in log if '**ERROR' in entry]
    print(f'wrote usl/results/RUN.md · {len(errors)} statements failed')
    for entry in errors:
        print(entry[:600])


if __name__ == '__main__':
    main()
