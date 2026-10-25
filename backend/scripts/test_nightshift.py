#!/usr/bin/env python3
"""Verify Nightshift's advertised route. Provider pinning still needs instance evidence."""
import argparse
import asyncio
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.scripts.test_nvidia import IMAGE_PROMPT, SmokeFailure, image_data_url, parse_vision_result, select_image


async def run(args) -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    async with ModelGateway.from_env() as gateway:
        if args.list_models:
            models = await gateway.available_models()
            # Model IDs only, not metadata or a full response containing private config.
            secret = os.environ.get('METERLESS_API_KEY', '')
            for model in models:
                if re.fullmatch(r'meterless/[a-zA-Z0-9._/-]+', model) and (not secret or secret not in model):
                    print(model)
            if not models:
                raise ModelGatewayError('Nightshift advertised no meterless/* routing IDs.')
            print('[PASS] Nightshift discovery works; choose a route and configure NVIDIA pinning in Nightshift.')
            return 0
        result = await gateway.complete([{'role': 'user', 'content': 'Respond with exactly: NIGHTSHIFT_OK'}])
        routing = gateway.last_routing
        print(f'[INFO] requested route: {gateway.model}')
        print('[INFO] routing evidence: ' + ', '.join(f'{k}={v}' for k, v in routing.items()))
        if result != 'NIGHTSHIFT_OK':
            raise ModelGatewayError('Nightshift text did not match the required marker.')
        print('[PASS] Nightshift text inference works')
        if args.image:
            path = select_image(args.image)
            result = await gateway.complete([{'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': image_data_url(path)}},
                {'type': 'text', 'text': IMAGE_PROMPT},
            ]}])
            parse_vision_result(result)
            print('[PASS] Nightshift image request returned structured JSON; content suppressed.')
        print('[INFO] Confirm the underlying NVIDIA model in Nightshift routing/trace evidence before claiming sponsor use.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--list-models', action='store_true')
    modes.add_argument('--image', type=Path)
    try:
        return asyncio.run(run(parser.parse_args()))
    except (ModelGatewayError, SmokeFailure) as exc:
        print('[FAIL] ' + str(exc))
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception:
        print('[FAIL] Nightshift verification failed; credentials and raw payloads were not logged.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
