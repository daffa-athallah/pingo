#!/usr/bin/env python3
"""Daily consolidation: the Critic reviews look-alike Open Loops. Exact duplicates are merged; uncertain pairs become today's Check-in
questions. Run once a day (cron/launchd). Unanswered questions do not carry over: GET /api/check-ins only serves today's.

Model calls go Recall -> Nightshift -> Nemotron. --dry-run lists the candidate pairs without any model call or write.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import real_env
from real_env import ROOT, real_repository
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.adapters.zetaris import ZetarisError
from backend.app.agents.critic import CriticAgent
from backend.app.orchestration.consolidation import Consolidator

OUT = ROOT / 'backend/runtime/consolidation'


async def run(args) -> int:
    day = datetime.now(ZoneInfo(os.environ.get('RECALL_TIMEZONE', 'Australia/Melbourne'))).date().isoformat()
    run_id = 'run_cons_' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    with real_repository() as repo:
        async with ModelGateway.from_env() as gateway:
            consolidator = Consolidator(CriticAgent(gateway, repo), repo, judged_path=OUT / 'judged.json')
            if args.dry_run:
                loops, by_loop, pairs = consolidator.plan(day)
                titles = {l.loop_id: l.title for l in loops}
                print(f'[PLAN] {len(loops)} active loops, {len(pairs)} candidate pairs for {day}')
                for a, b in pairs:
                    print(f'  - {titles[a]}  <->  {titles[b]}')
                return 0
            result = await consolidator.run(day, run_id)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{run_id}.json').write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    for event in result.trace_events:
        print(f'  {event.agent:8}{event.action:14}| {event.reason[:140]}')
    print(f'[SUMMARY] day={day} pairs={result.candidate_pairs} judged={result.judged} merged={len(result.merged)} asked={len(result.asked)} '
          f'kept_separate={result.kept_separate} model_calls={result.model_calls} errors={result.errors}')
    return 1 if result.errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        real_env.load_env(args.env_file)
        return asyncio.run(run(args))
    except (ZetarisError, ModelGatewayError) as exc:
        print('[FAIL]', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
