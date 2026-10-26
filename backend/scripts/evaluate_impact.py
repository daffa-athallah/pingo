#!/usr/bin/env python3
"""Measures what Recall actually does on the saved history, from data in the repository only (no model, no Zetaris). Prints markdown."""
from collections import Counter
import json
from pathlib import Path
import statistics

DEMO = Path(__file__).resolve().parents[1] / 'demo'


def main():
    snap = json.loads((DEMO / 'snapshot.json').read_text())
    hist = json.loads((DEMO / 'history.json').read_text())['records']
    evidence = {e['evidence_id']: e for e in snap['evidence']}
    links = snap['evidence_entities']
    loops = [l for l in snap['loops'] if l['status'] in ('OPEN', 'ACTIVE')]
    ent_by_loop = {}
    for k in snap['loop_entities']:
        ent_by_loop.setdefault(k['loop_id'], set()).add(k['entity_id'])
    ev_by_ent = {}
    for k in links:
        ev_by_ent.setdefault(k['entity_id'], set()).add(k['evidence_id'])
    support = {l['loop_id']: set().union(*[ev_by_ent.get(e, set()) for e in ent_by_loop.get(l['loop_id'], set())] or [set()]) for l in loops}
    usable = [e for e in evidence.values() if not e['sensitive']]
    sizes = [len(v) for v in support.values()]
    grouped = sum(1 for n in sizes if n >= 2)
    ungrounded = sum(1 for n in sizes if n == 0)
    surfaced = [r for r in hist if r['result']['final_action'] == 'SURFACE']
    silent = [r for r in hist if r['result']['final_action'] == 'STAY_SILENT']
    cited = sum(1 for r in surfaced if (r['result'].get('message_payload') or {}).get('evidence_ids'))
    out = {
        'screenshots': len(evidence), 'sensitive_screenshots': len(evidence) - len(usable), 'active_intentions': len(loops),
        'screenshots_per_intention_mean': round(statistics.mean(sizes), 2) if sizes else 0, 'screenshots_per_intention_max': max(sizes, default=0),
        'intentions_backed_by_2_or_more_screenshots': grouped, 'intentions_without_evidence': ungrounded,
        'context_runs_saved': len(hist), 'surfaced': len(surfaced), 'stayed_silent': len(silent),
        'surfaced_with_cited_evidence': cited, 'decisions': dict(Counter(r['result']['final_action'] for r in hist))}
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
