#!/usr/bin/env python3
"""Phase 3: human-readable view of the Open Loops actually persisted in Zetaris, plus the processing ledger. Read-only."""
import argparse
from collections import Counter
import json
from pathlib import Path

import real_env
from real_env import real_repository
from process_open_loops import LEDGER, load_ledger
from backend.app.adapters.zetaris import ZetarisError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    try:
        real_env.load_env(args.env_file)
        ledger = load_ledger()
        with real_repository() as repo:
            evidence = {e.evidence_id: e for e in repo.list_evidence()}
            loop_ids = sorted({v['loop_id'] for v in ledger.values() if v.get('loop_id')})
            loops = [repo.get_open_loop(i) for i in loop_ids]
            loops = [l for l in loops if l]
            links = repo.get_loop_entities([l.loop_id for l in loops])
            entities = {e.entity_id: e for e in repo.get_entities(sorted({k.entity_id for k in links}))}
            print(f'=== {len(loops)} Open Loops in Zetaris (ledger: {LEDGER.name}) ===\n')
            for loop in loops:
                decisions = [(eid, v) for eid, v in ledger.items() if v.get('loop_id') == loop.loop_id]
                supporting = sorted({i for _, v in decisions for i in v.get('supporting_evidence_ids', [])} |
                                    {eid for eid, v in decisions if v['outcome'] in ('CREATE', 'ATTACH', 'REVISE')})
                names = [entities[k.entity_id].name for k in links if k.loop_id == loop.loop_id and k.entity_id in entities]
                sensitive = any(evidence[i].sensitive for i in supporting if i in evidence)
                if sensitive:
                    print(f'{loop.loop_id}  [sensitive supporting evidence: details withheld]\n')
                    continue
                latest = max(decisions, key=lambda d: d[1]['at'])[1]
                print(f'loop_id      {loop.loop_id}')
                print(f'title        {loop.title}')
                print(f'domain       {loop.domain}   status {loop.status.value}   confidence {loop.confidence}')
                print(f'entities     {names}')
                print(f'evidence     {len(supporting)} record(s): {supporting}')
                print(f'latest       {latest["outcome"]} -- {latest["concise_reason"]}')
                if latest.get('material_uncertainty'):
                    print(f'uncertainty  {latest["material_uncertainty"]}')
                print(f'receipt      {latest.get("receipt")}\n')
        outcomes = Counter(v['outcome'] for v in ledger.values())
        print('=== Decision counts (all ledgered Evidence) ===')
        for key in ('CREATE', 'ATTACH', 'REVISE', 'RESOLVE', 'IGNORE', 'LEAVE_UNRESOLVED', 'SKIP_SENSITIVE', 'SKIP_UNSUPPORTED_DOMAIN'):
            print(f'{key:26}{outcomes.get(key, 0)}')
        model_backed = [v for v in ledger.values() if v.get('receipt') is not None]
        print(f'{"ledgered model decisions":26}{len(model_backed)}')
        print(f'{"receipts (provider)":26}{dict(Counter((v["receipt"] or {}).get("provider") for v in model_backed))}')
        print(f'{"receipts (routed_model)":26}{dict(Counter((v["receipt"] or {}).get("routed_model") for v in model_backed))}')
        return 0
    except ZetarisError as exc:
        print('[FAIL]', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
