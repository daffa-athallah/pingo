#!/usr/bin/env python3
"""Batch the existing Evidence Agent over a screenshot folder and export JSON for the Zetaris import.

Every image is its own model request (Evidence Agent -> Nightshift -> vision model). The batch is
resumable: an output that already validates (schema AND routing receipt) is skipped, so a stopped run
never pays twice. Outputs are written atomically and a failed call never leaves a valid-looking file.

  python backend/scripts/batch_evidence.py --input screenshot --output sample_data/evidence
  python backend/scripts/batch_evidence.py --dry-run          # zero model calls
"""
import argparse
import asyncio
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.evidence import EvidenceAgent, EvidenceError, parse_evidence

IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}
ARTIFACT_KEYS = {'source_file', 'extraction', 'receipt'}
RECEIPT_KEYS = ('requested_model', 'routed_model', 'provider')
MAX_CONSECUTIVE_FAILURES = 3
# Messages from ModelGateway that mean the whole service is unusable, not just one image.
FATAL_MARKERS = ('cannot be reached', 'credentials/access rejected', 'not advertised', 'endpoint unavailable', 'Missing ')


class BatchError(RuntimeError):
    """Safe configuration failure before or during a batch."""


def discover_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise BatchError(f'Input folder does not exist: {folder}')
    images = sorted((p for p in folder.iterdir() if p.is_file() and not p.name.startswith('.') and p.suffix.lower() in IMAGE_SUFFIXES),
                    key=lambda p: p.name)
    stems: dict[str, str] = {}
    for image in images:
        if image.stem in stems:
            raise BatchError(f'Two inputs share the stem "{image.stem}" ({stems[image.stem]} and {image.name}); outputs would collide.')
        stems[image.stem] = image.name
    return images


def sanitize_receipt(routing: dict) -> dict:
    return {key: routing.get(key) for key in RECEIPT_KEYS}


def check_receipt(receipt: object, expected_model: str, expected_provider: str) -> str | None:
    if not isinstance(receipt, dict) or set(receipt) != set(RECEIPT_KEYS):
        return 'receipt is missing or has unexpected fields'
    if receipt['provider'] != expected_provider:
        return f'unexpected provider "{receipt["provider"]}" (expected {expected_provider})'
    if receipt['requested_model'] != expected_model or receipt['routed_model'] != expected_model:
        return f'unexpected model "{receipt["routed_model"]}" (expected {expected_model})'
    return None


def validate_artifact(data: object, source_name: str, expected_model: str, expected_provider: str) -> str | None:
    """Return None when the artifact is complete and canonical, otherwise a short reason."""
    if not isinstance(data, dict) or set(data) != ARTIFACT_KEYS:
        return 'unexpected top-level fields'
    if data['source_file'] != source_name:
        return 'source_file does not match the image'
    try:
        parsed = parse_evidence(json.dumps(data['extraction']))
    except (EvidenceError, TypeError, ValueError):
        return 'extraction does not match the Evidence schema'
    if asdict(parsed) != data['extraction']:
        return 'extraction is not in canonical form'
    return check_receipt(data['receipt'], expected_model, expected_provider)


def existing_status(output: Path, source_name: str, expected_model: str, expected_provider: str) -> str | None:
    """None when a valid output exists; otherwise why a model call is needed."""
    if not output.exists():
        return 'missing'
    try:
        data = json.loads(output.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'unreadable'
    problem = validate_artifact(data, source_name, expected_model, expected_provider)
    return None if problem is None else f'invalid ({problem})'


def write_atomic(output: Path, artifact: dict, source_name: str, expected_model: str, expected_provider: str, secrets: list[str]) -> None:
    text = json.dumps(artifact, indent=2, ensure_ascii=False) + '\n'
    if any(secret and secret in text for secret in secrets):
        raise BatchError('refusing to write output that contains a credential value')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f'.{output.name}.tmp')
    try:
        temp.write_text(text, encoding='utf-8')
        problem = validate_artifact(json.loads(temp.read_text(encoding='utf-8')), source_name, expected_model, expected_provider)
        if problem:
            raise BatchError(f'output failed validation: {problem}')
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)


@dataclass
class Plan:
    image: Path
    output: Path
    action: str  # 'skip' or 'process'
    reason: str = ''


def make_plan(images: list[Path], output_dir: Path, expected_model: str, expected_provider: str, *, force: bool, limit: int | None) -> list[Plan]:
    plans = []
    budget = limit
    for image in images:
        output = output_dir / f'{image.stem}.json'
        status = existing_status(output, image.name, expected_model, expected_provider)
        if status is None and not force:
            plans.append(Plan(image, output, 'skip', 'valid output exists'))
        elif budget is not None and budget <= 0:
            plans.append(Plan(image, output, 'skip', 'over --limit'))
        else:
            plans.append(Plan(image, output, 'process', 'forced' if status is None else status))
            if budget is not None:
                budget -= 1
    return plans


@dataclass
class Report:
    ok: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    stopped: str | None = None


async def run_batch(plans: list[Plan], agent, gateway, expected_model: str, expected_provider: str, secrets: list[str],
                    out: Callable[[str], None] = print) -> Report:
    report = Report()
    total = len(plans)
    consecutive = 0
    for index, plan in enumerate(plans, start=1):
        tag = f'[{index:02d}/{total:02d}] {plan.image.name}'
        if plan.action == 'skip':
            report.skipped += 1
            out(f'{tag}  SKIP ({plan.reason})')
            continue
        out(f'{tag}  PROCESSING')
        try:
            gateway.last_routing = {}
            extraction = await agent.observe(plan.image)
            receipt = sanitize_receipt(dict(gateway.last_routing))
            problem = check_receipt(receipt, expected_model, expected_provider)
            if problem:
                raise BatchError(problem)
            write_atomic(plan.output, {'source_file': plan.image.name, 'extraction': asdict(extraction), 'receipt': receipt},
                         plan.image.name, expected_model, expected_provider, secrets)
        except Exception as exc:  # noqa: BLE001 - one image must never take the batch down
            safe = isinstance(exc, (EvidenceError, ModelGatewayError, BatchError))
            message = str(exc) if safe else f'unexpected error ({type(exc).__name__})'
            out(f'{tag}  FAILED: {message}')
            report.failed.append(plan.image.name)
            consecutive += 1
            if isinstance(exc, ModelGatewayError) and any(marker in message for marker in FATAL_MARKERS):
                report.stopped = f'Nightshift is unavailable: {message}'
            elif consecutive >= MAX_CONSECUTIVE_FAILURES and isinstance(exc, (ModelGatewayError, BatchError)):
                report.stopped = f'{consecutive} consecutive failures; stopping instead of repeating them.'
            if report.stopped:
                out(f'STOPPED: {report.stopped}')
                return report
            continue
        consecutive = 0
        report.ok += 1
        out(f'{tag}  OK')
    return report


def summarize(images: list[Path], plans: list[Plan], input_dir: Path, output_dir: Path, model: str, provider: str, out=print) -> int:
    valid = sum(1 for p in plans if p.reason == 'valid output exists')
    calls = sum(1 for p in plans if p.action == 'process')
    out(f'Input:   {input_dir}  ({len(images)} images found)')
    out(f'Output:  {output_dir}')
    out(f'Already valid (skipped): {valid}')
    out(f'Model calls required:    {calls}')
    out(f'Expected route:          {provider} / {model}, one request per image')
    return calls


def secret_values() -> list[str]:
    names = ('METERLESS_API_KEY', 'NVIDIA_API_KEY', 'OPENAI_API_KEY', 'GOOGLE_API_KEY')
    return [value for name in names if len(value := os.environ.get(name, '').strip()) >= 8]


async def main_async(args) -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    expected_model = os.environ.get('METERLESS_VISION_MODEL', '').strip()
    if not expected_model:
        raise BatchError('Missing METERLESS_VISION_MODEL; set the Evidence vision model first.')
    images = discover_images(args.input)
    plans = make_plan(images, args.output, expected_model, args.provider, force=args.force, limit=args.limit)
    calls = summarize(images, plans, args.input, args.output, expected_model, args.provider)
    if args.dry_run:
        for index, plan in enumerate(plans, start=1):
            label = 'WOULD PROCESS' if plan.action == 'process' else 'WOULD SKIP'
            print(f'[{index:02d}/{len(plans):02d}] {plan.image.name}  {label} ({plan.reason})')
        print('Dry run: no model calls were made and nothing was written.')
        return 0
    if calls == 0:
        print('Nothing to do.')
        return 0
    async with ModelGateway.from_env() as gateway:
        report = await run_batch(plans, EvidenceAgent(gateway), gateway, expected_model, args.provider, secret_values())
    print(f'Done: {report.ok} written, {report.skipped} skipped, {len(report.failed)} failed.')
    if report.failed:
        print('Failed: ' + ', '.join(report.failed))
    return 2 if report.stopped else 1 if report.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', type=Path, default=ROOT / 'screenshot')
    parser.add_argument('--output', type=Path, default=ROOT / 'sample_data/evidence')
    parser.add_argument('--force', action='store_true', help='regenerate outputs that are already valid')
    parser.add_argument('--limit', type=int, help='make at most N model calls this run')
    parser.add_argument('--dry-run', action='store_true', help='show the plan; make no model calls and write nothing')
    parser.add_argument('--provider', default='openai', help='expected provider in the routing receipt')
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args))
    except (BatchError, ModelGatewayError) as exc:
        print('[FAIL] ' + str(exc))
        return 2
    except KeyboardInterrupt:
        print('Interrupted. Completed outputs are kept; rerun the same command to resume.')
        return 130


if __name__ == '__main__':
    sys.exit(main())
