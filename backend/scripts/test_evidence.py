#!/usr/bin/env python3
"""Run the Evidence Agent on one screenshot through Nightshift (content hidden by default)."""
import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.evidence import EvidenceAgent, EvidenceError


async def run(args) -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    async with ModelGateway.from_env() as gateway:
        evidence = await EvidenceAgent(gateway).observe(args.image)
        routing = gateway.last_routing
    print(f"[INFO] vision model: {gateway.vision_model}; routing: " + ', '.join(f'{k}={v}' for k, v in routing.items()))
    print(f'[PASS] Evidence parsed: domain={evidence.domain}, entities={len(evidence.entities)}, '
          f'sensitive={evidence.sensitive}, confidence={evidence.confidence}')
    if args.show_result:
        print(json.dumps(asdict(evidence), indent=2, ensure_ascii=False))
    else:
        print('[INFO] Content suppressed; add --show-result to view it locally.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--show-result', action='store_true')
    try:
        return asyncio.run(run(parser.parse_args()))
    except (ModelGatewayError, EvidenceError) as exc:
        print('[FAIL] ' + str(exc))
        return 1
    except Exception:
        print('[FAIL] Evidence run failed; credentials and raw payloads were not logged.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
