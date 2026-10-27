"""Location Agent: find where a saved place is when the map's own place index does not know it.

Many small shops are missing from OpenStreetMap, but their street address is on the web and street addresses are on the map. The agent therefore:
  1. searches the web for the place and its saved suburb (DuckDuckGo's HTML results; one query, the page snippets only),
  2. a model reads those snippets and extracts the full street address of the branch in the saved suburb, citing the snippet it came from,
  3. the address is checked: the number and street must literally appear in the cited snippet, and
  4. the address is geocoded on OpenStreetMap; the result must carry the same house number and road, and lie in the saved suburb or city.
Only a verified address becomes a coordinate. Nothing is guessed, and the source (web page and map object) is stored with the coordinate."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import html
import json
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from backend.app import geocode
from backend.app.geocode import _norm, _tokens

SEARCH_URL = 'https://html.duckduckgo.com/html/'
BROWSER_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
MAX_SNIPPETS = 8
AREA_KEYS = ('suburb', 'city', 'town', 'village', 'city_district', 'neighbourhood', 'municipality', 'locality')

PROMPT = """You find the street address of one specific place from web search snippets.
Use ONLY what the snippets say. Give the full street address of the branch located in the saved suburb or city: street number, street, suburb, state, postcode.
If several branches appear, choose the one in the saved suburb. If no snippet clearly gives that branch's street address, answer null. Never guess or complete an address from memory.
Reply with JSON only: {"address": "<full street address or null>", "source_index": <index of the snippet it came from, or null>, "reason": "<one short sentence>"}"""


_SEARCH_LOCK = threading.Lock()
_last_search = [0.0]
CACHE = Path(__file__).resolve().parents[1] / 'runtime/websearch'
CACHE_SECONDS = 24 * 3600
MIN_GAP = 2.5  # be gentle: at most one search every couple of seconds, and a repeated query is served from disk


def web_search(query: str, *, timeout: float = 10.0, opener=None) -> list[dict]:
    """[{'title','snippet','url'}] for a query: from the 24-hour cache, else one DuckDuckGo HTML page (retried once if it comes back empty)."""
    key = CACHE / (hashlib.sha256(query.strip().lower().encode()).hexdigest()[:32] + '.json')
    try:
        if key.is_file() and time.time() - key.stat().st_mtime < CACHE_SECONDS:
            return json.loads(key.read_text())
    except (OSError, ValueError):
        pass
    results: list[dict] = []
    for attempt in range(2):
        with _SEARCH_LOCK:
            wait = MIN_GAP - (time.time() - _last_search[0])
            if wait > 0:
                time.sleep(wait)
            try:
                results = _fetch_results(query, timeout=timeout, opener=opener)
            finally:
                _last_search[0] = time.time()
        if results:
            break
    if results:
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            key.write_text(json.dumps(results))
        except OSError:
            pass
    return results


def _fetch_results(query: str, *, timeout: float, opener=None) -> list[dict]:
    url = SEARCH_URL + '?' + urllib.parse.urlencode({'q': query})
    request = urllib.request.Request(url, headers={'User-Agent': BROWSER_UA, 'Accept-Language': 'en'})
    with (opener or urllib.request.build_opener(urllib.request.HTTPSHandler(context=geocode._context()))).open(request, timeout=timeout) as response:
        page = response.read(1_500_000).decode('utf-8', 'replace')
    out = []
    clean = lambda text: re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', text or ''))).strip()
    chunks = page.split('class="result__a"')[1:]
    for chunk in chunks[:MAX_SNIPPETS * 2]:  # each chunk: one result's link, then (before the next result) its snippet
        link = re.match(r'[^>]*href="([^"]+)"[^>]*>(.*?)</a>', chunk, re.S)
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', chunk, re.S)
        if not link:
            continue
        href = html.unescape(link.group(1))
        target = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get('uddg', [href])[0]
        out.append({'title': clean(link.group(2)), 'snippet': clean(snippet.group(1) if snippet else ''), 'url': target})
    return out[:MAX_SNIPPETS]


def parse_choice(content: str, count: int) -> tuple[str | None, int | None, str]:
    raw = None
    for candidate in reversed(re.findall(r'\{[^{}]*\}', content or '')):  # a reasoning model may talk first; the answer is the last JSON object
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict) and 'address' in parsed:
            raw = parsed
            break
    if raw is None:
        raise ValueError('The Location Agent did not return JSON.')
    reason = raw.get('reason') if isinstance(raw.get('reason'), str) else ''
    address, index = raw.get('address'), raw.get('source_index')
    if address is None:
        return None, None, reason
    if not isinstance(address, str) or isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
        raise ValueError('The Location Agent cited a snippet it was not shown.')
    return address.strip(), index, reason


def address_parts(address: str) -> tuple[str, set[str]]:
    """(house number, street words) from "399 Clayton Rd, Clayton VIC 3168"; the number may be a range or unit ("2/399", "399-401")."""
    first = address.split(',')[0]
    numbers = re.findall(r'\d+[A-Za-z]?', first)
    street = {t for t in _norm(re.sub(r'\d+[A-Za-z]?', ' ', first)).split() if t not in {'rd', 'road', 'st', 'street', 'ave', 'avenue', 'hwy', 'highway', 'dr', 'drive', 'cres', 'ct', 'pde', 'parade', 'ln', 'lane'}}
    return (numbers[-1] if numbers else ''), street


def cited_in_snippet(address: str, snippet_text: str) -> bool:
    """The model may not invent an address: its number and street words must literally be in the snippet it cites."""
    number, street = address_parts(address)
    text = _norm(re.sub(r'[-/\u2013]', ' ', snippet_text))  # "96-98" is two numbers, not 9698
    words = set(text.split()) | set(re.findall(r'\d+[a-z]?', text))
    return bool(number) and bool(street) and number.lower() in words and street <= words


def verify_on_map(address: str, entity, *, search=None) -> dict | None:
    """The OpenStreetMap address object for this street address, only if number, road and area all agree; else None.

    A range ("96-98 Wellington Road") is searched by each of its numbers, because the map stores the individual houses."""
    search = search or geocode._search
    number, street = address_parts(address)
    first, _, rest = address.partition(',')
    numbers = list(dict.fromkeys(reversed(re.findall(r'\d+[A-Za-z]?', first))))  # the last number first ("2/399" -> 399)
    area = {t for t in _tokens(entity.location_name or '') | _tokens(entity.city or '') if t}
    wanted = {n.lower() for n in numbers}
    street_text = re.sub(r'[\d/\-\u2013]+[A-Za-z]?', ' ', first).strip()
    for n in numbers:
        query = f'{n} {street_text}, {rest.strip()}' if rest else f'{n} {street_text}'
        if entity.country and _norm(entity.country) not in _norm(query):
            query += f', {entity.country}'
        for item in search(query):
            if not geocode._valid_result(item):
                continue
            parts = item.get('address') or {}
            got = set(re.findall(r'\d+[a-z]?', _norm(re.sub(r'[-/\u2013]', ' ', str(parts.get('house_number', ''))))))
            road = set(_norm(str(parts.get('road', ''))).split())
            where = {t for key in AREA_KEYS for t in _norm(str(parts.get(key, ''))).split()}  # the place's own suburb/city, never the road's name
            if got & wanted and street <= road and (not area or area & where):
                return item
    return None


class LocationAgent:
    def __init__(self, gateway):
        self.gateway = gateway

    async def read_address(self, entity, results: list[dict]) -> tuple[str | None, int | None, str]:
        model = getattr(self.gateway, 'reasoning_model', None) or getattr(self.gateway, 'vision_model', None)
        place = {'name': entity.name, 'saved_suburb_or_city': ', '.join(p for p in (entity.location_name, entity.city) if p), 'country': entity.country}
        content = [{'type': 'text', 'text': PROMPT}, {'type': 'text', 'text': json.dumps({'place': place, 'snippets': [
            {'index': i, 'title': r['title'], 'text': r['snippet'], 'site': urllib.parse.urlsplit(r['url']).hostname} for i, r in enumerate(results)]}, ensure_ascii=False)},
            {'type': 'text', 'text': f'request_id: {uuid.uuid4().hex}'}]
        reply = await self.gateway.complete([{'role': 'user', 'content': content}], model=model, max_tokens=1500)
        return parse_choice(reply, len(results))


async def _attempt(entity, gateway, query, *, emit, web, search) -> dict:
    """{'status': 'resolved', ...metadata fields...} or {'status': 'not_found'|'unverified'|'unavailable', 'reason': str}. Never raises."""
    say = emit or (lambda *a, **k: None)
    area = ' '.join(dict.fromkeys(p for p in (entity.location_name, entity.city) if p))
    try:
        results = await asyncio.to_thread(web, query)
    except (urllib.error.URLError, OSError, ValueError):
        return {'status': 'unavailable', 'reason': 'The web search could not be reached.'}
    if not results:
        return {'status': 'not_found', 'reason': f'The web search for "{query}" returned nothing.'}
    try:
        address, index, why = await LocationAgent(gateway).read_address(entity, results)
    except Exception as exc:  # noqa: BLE001
        return {'status': 'unavailable', 'reason': f'The Location Agent could not finish ({type(exc).__name__}).'}
    if address is None:
        return {'status': 'not_found', 'reason': why or 'No snippet gave this branch\'s street address.'}
    source = results[index]
    if not cited_in_snippet(address, f"{source['title']} {source['snippet']}"):
        return {'status': 'unverified', 'reason': f'The address "{address}" is not in the web snippet it was taken from, so it was not used.'}
    item = await asyncio.to_thread(verify_on_map, address, entity, search=search)
    if item is None:
        return {'status': 'unverified', 'reason': f'"{address}" was found on the web but the map has no matching street address in {area or "the saved area"}.'}
    host = urllib.parse.urlsplit(source['url']).hostname or 'the web'
    osm = f"{item['osm_type']}:{item['osm_id']}"
    say('LOCATION', 'ADDRESS_FOUND', f'Found {entity.name}: {address} (from {host}), confirmed on the map at {float(item["lat"]):.5f}, {float(item["lon"]):.5f}.',
        input_refs=[f'entity:{entity.entity_id}'], next_step='STOP', detail={'address': address, 'source': source['url'], 'osm': osm})
    metadata = {**(entity.metadata or {}), 'latitude': f"{float(item['lat']):.7f}", 'longitude': f"{float(item['lon']):.7f}", 'location_verified': 'true',
                'location_id': f'addr:osm:{osm}', 'location_address': address,
                'location_source': f"Street address from {host} ({source['url'][:120]}), position from OpenStreetMap address {osm} ({time.strftime('%Y-%m-%d')})"}
    return {'status': 'resolved', 'address': address, 'lat': float(item['lat']), 'lon': float(item['lon']), 'metadata': metadata, 'reason': why}


async def find_location(entity, gateway, *, emit=None, web=web_search, search=None) -> dict:
    """{'status': 'resolved', ...metadata fields...} or {'status': 'not_found'|'unverified'|'unavailable', 'reason': str}. Never raises.
    Two differently worded searches at most; only an address that passes every check is used."""
    area = ' '.join(dict.fromkeys(p for p in (entity.location_name, entity.city) if p))
    result: dict = {'status': 'not_found', 'reason': 'No search was made.'}
    for query in (f'{entity.name} {area} address'.strip(), f'{entity.name} {area} store location opening hours'.strip()):
        result = await _attempt(entity, gateway, query, emit=emit, web=web, search=search)
        if result['status'] in ('resolved', 'unavailable'):
            return result
    return result


async def find_and_save(repository, entity_id: str, gateway, *, emit=None, **kw) -> dict | None:
    """Run the Location Agent for one saved entity and store a verified result. Returns the updated place row (resolved), or a row saying why not."""
    found = await _entity_lookup(repository, entity_id, gateway, emit, **kw)
    return found


async def _entity_lookup(repository, entity_id, gateway, emit, **kw):
    entities = repository.get_entities([entity_id])
    if not entities:
        return None
    entity = entities[0]
    result = await find_location(entity, gateway, emit=emit, **kw)
    meta = entity.metadata or {}
    if result['status'] == 'resolved':
        updated = replace(entity, metadata={**meta, **result['metadata'], 'location_lookup_status': 'resolved_web'})
        repository.save_entity(updated)
        return {'status': 'resolved', 'reason': f"Found by the Location Agent: {result['address']}", 'latitude': updated.metadata['latitude'],
                'longitude': updated.metadata['longitude'], 'location_id': updated.metadata['location_id'], 'candidates': []}
    if emit:
        emit('LOCATION', 'WEB_' + result['status'].upper(), result['reason'], input_refs=[f'entity:{entity_id}'], next_step='STOP')
    return {'status': result['status'], 'reason': result['reason']}
