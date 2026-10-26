#!/usr/bin/env python3
"""Read-only snapshot of what Recall keeps in Zetaris, for people who cannot reach the instance: table row counts and the queries the
agents actually run, with their real results. Writes backend/demo/zetaris_proof.json. Never writes to Zetaris."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import real_env
from real_env import real_repository

OUT = Path(__file__).resolve().parents[1] / 'demo/zetaris_proof.json'
TABLES = ['evidence', 'entities', 'evidence_entities', 'open_loops', 'loop_entities', 'context_events', 'check_ins', 'context_evaluations', 'notifications']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    real_env.load_env(args.env_file)
    with real_repository() as repo:
        t = repo._table
        q = repo.connection.query
        counts = {name: int(q(f'SELECT COUNT(*) FROM {t(name)}')[0][0]) for name in TABLES}
        queries = []

        def record(role, sql, rows, note):
            queries.append({'role': role, 'sql': ' '.join(sql.split()), 'rows_returned': len(rows), 'sample': [[str(c) for c in r] for r in rows[:3]], 'note': note})

        sql = f"SELECT l.title, COUNT(DISTINCT le.entity_id) FROM {t('open_loops')} l JOIN {t('loop_entities')} le ON l.loop_id = le.loop_id WHERE l.status IN ('OPEN','ACTIVE') GROUP BY l.title ORDER BY 2 DESC"
        record('Open Loop Agent: which saved intentions share entities', sql, q(sql), 'Active intentions and how many entities each ties together.')
        sql = f"SELECT en.name, COUNT(DISTINCT ee.evidence_id) FROM {t('entities')} en JOIN {t('evidence_entities')} ee ON en.entity_id = ee.entity_id GROUP BY en.name ORDER BY 2 DESC"
        record('Open Loop Agent: Evidence per entity (related-evidence retrieval)', sql, q(sql), 'The join behind get_related_evidence: screenshots that mention the same entity.')
        sql = f"SELECT domain, COUNT(*) FROM {t('evidence')} WHERE sensitive = false GROUP BY domain ORDER BY 2 DESC"
        record('Evidence Agent output: non-sensitive Evidence by domain', sql, q(sql), 'Sensitive Evidence is stored but excluded from every reasoning query.')
        namespace = repo.namespace if hasattr(repo, 'namespace') else 'recall_data.app'
    OUT.write_text(json.dumps({'captured_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'source': 'live Zetaris instance, read-only',
                               'namespace': namespace, 'table_counts': counts, 'queries': queries,
                               'role': 'Zetaris is the system of record: append-only Evidence, entities, links, Open Loops, Check-ins. The agents retrieve through it; without it they have no memory of what was saved.'},
                              indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(counts))
    print(f'Wrote {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
