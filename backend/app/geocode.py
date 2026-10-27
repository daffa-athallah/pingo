"""Where is this saved place? Resolves a restaurant or destination to coordinates so proximity checks (phone GPS, Context Simulator) can match it.

The source is OpenStreetMap Nominatim, a free public geocoder (no key; its usage policy allows light use with an identifying User-Agent, one request
per second). A result is accepted only when it is unambiguous:
  * the result's own name has exactly the saved name's distinctive words (a longer name is a different place), and
  * the saved suburb or city appears in the result, and
  * if several results qualify they lie within 300 m of each other (otherwise it is ambiguous and nothing is written).
What is stored on the entity: latitude, longitude, location_verified="true", location_source (what matched and how), location_id (osm:<type>:<id>).
Nothing is ever guessed: with no confident match the place stays unlocated and proximity is not evaluated. Shopping products are never geocoded.
"""
from __future__ import annotations

import json
import math
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'Pingo-Recall-hackathon/1.0 (https://github.com/daffa-athallah/recall)'
PLACE_TYPES = {'place', 'restaurant', 'venue', 'attraction', 'destination', 'cafe', 'bar', 'store'}
GENERIC = {'the', 'a', 'an', 'and', 'of', 'restaurant', 'cafe', 'bar', 'shop', 'store', 'house', 'melbourne', 'australia'}
SPREAD_METERS = 300


def _context() -> ssl.SSLContext:
    """TLS trust that does not depend on the shell's SSL_CERT_FILE (a launchd job has none): certifi's bundle, else the macOS/Linux system bundle."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context(cafile='/etc/ssl/cert.pem') if os.path.exists('/etc/ssl/cert.pem') else ssl.create_default_context()


def enabled() -> bool:
    setting = os.environ.get('RECALL_GEOCODE', '').strip().lower()
    if setting in ('off', '0', 'false'):
        return False
    return setting in ('on', '1', 'true') or 'unittest' not in sys.argv[0]  # tests never touch the network unless they opt in


def _norm(text: str) -> str:
    return re.sub(r'[^a-z0-9 ]+', '', (text or '').lower().replace('’', "'").replace("'", '')).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if t and t not in GENERIC}


def _metres(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))


def _search(query: str, timeout: float = 6.0, viewbox: str | None = None) -> list[dict]:
    time.sleep(1.1)  # the public service allows one request per second
    params = {'q': query, 'format': 'jsonv2', 'limit': 5, 'addressdetails': 1, **({'viewbox': viewbox, 'bounded': 1} if viewbox else {})}
    url = ENDPOINT + '?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Language': 'en'})
    with urllib.request.urlopen(request, timeout=timeout, context=_context()) as response:
        return json.loads(response.read())


def _area_box(entity, search) -> str | None:
    """viewbox (left,top,right,bottom) of the saved suburb/city, so a small business is searched for only inside it."""
    area = entity.location_name if entity.location_name and _norm(entity.location_name) != _norm(entity.city or '') else None
    if not area:
        return None
    found = search(', '.join(p for p in (area, entity.city, entity.country) if p))
    if not found or 'boundingbox' not in found[0]:
        return None
    south, north, west, east = found[0]['boundingbox']
    return f'{west},{north},{east},{south}'


def parse_maps_link(text: str, *, follow=None) -> tuple[float, float] | None:
    """Latitude/longitude from a pasted Google Maps link or a plain "lat, lon". Short links are followed once (follow(url) -> final url)."""
    text = (text or '').strip()
    if not text:
        return None
    if re.fullmatch(r'-?\d{1,2}(\.\d+)?\s*[, ]\s*-?\d{1,3}(\.\d+)?', text):
        lat, lon = (float(x) for x in re.split(r'[, ]+', text))
        return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None
    if re.match(r'https?://(maps\.app\.goo\.gl|goo\.gl/maps)/', text) and follow:
        text = follow(text) or text
    for pattern in (r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', r'@(-?\d+\.\d+),(-?\d+\.\d+)', r'[?&](?:q|ll|query|destination)=(-?\d+\.\d+)(?:,|%2C)(-?\d+\.\d+)'):
        m = re.search(pattern, text)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
    return None


def follow_redirect(url: str) -> str | None:
    try:
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=6, context=_context()) as response:
            return response.geturl()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def eligible(entity) -> bool:
    return entity.domain in ('food', 'travel') and entity.entity_type in PLACE_TYPES and \
        (entity.metadata or {}).get('location_verified', '').lower() != 'true'


def _candidates(results) -> list[dict]:
    seen, out = set(), []
    for r in results:
        key = (r.get('osm_type'), r.get('osm_id'))
        if key in seen:
            continue
        seen.add(key)
        out.append({'label': r.get('display_name'), 'name': r.get('name'), 'lat': float(r['lat']), 'lon': float(r['lon']),
                    'location_id': f"osm:{r.get('osm_type')}:{r.get('osm_id')}"})
    return out[:5]


def resolve(entity, *, search=_search) -> dict:
    """{'status': 'resolved', ...} | {'status': 'ambiguous'|'not_found'|'unavailable', 'reason': str, 'candidates': [...]}.

    The agent searches the map several ways (name and suburb, name and city, the street address read from the screenshot, name inside the suburb)
    and accepts a result by itself only when it is unambiguous. Everything it found but could not accept is returned as candidates for the person to confirm."""
    meta = entity.metadata or {}
    same = entity.location_name and entity.city and _norm(entity.location_name) == _norm(entity.city)
    queries = [', '.join(p for p in (entity.name, None if same else entity.location_name, entity.city, entity.country) if p),
               ', '.join(p for p in (entity.name, entity.city or entity.location_name) if p)]
    if meta.get('address'):
        queries.insert(1, f"{entity.name}, {meta['address']}")
    name_tokens = _tokens(entity.name)
    area_tokens = {t for t in _tokens(entity.location_name or '') | _tokens(entity.city or '') if t not in name_tokens}
    pool: list[dict] = []

    def judge(items):
        good = []
        for item in items:
            have = set(_norm(f"{item.get('name', '')} {item.get('display_name', '')}").split())
            # The result's own name must be the saved name, not a longer one ("Biomedical Learning and Teaching Building" is not "Learning and Teaching Building").
            named = _tokens(item.get('name') or '') == name_tokens if item.get('name') else name_tokens <= have
            if name_tokens and named and name_tokens <= have and (not area_tokens or area_tokens & have):
                good.append(item)
        if not good:
            return None
        first = (float(good[0]['lat']), float(good[0]['lon']))
        if any(_metres(first, (float(g['lat']), float(g['lon']))) > SPREAD_METERS for g in good[1:]):
            return {'status': 'ambiguous', 'reason': f'"{entity.name}" matches several different places; not choosing one.'}
        best = good[0]
        return {'status': 'resolved', 'lat': float(best['lat']), 'lon': float(best['lon']), 'display_name': best.get('display_name'),
                'location_id': f"osm:{best.get('osm_type')}:{best.get('osm_id')}"}

    try:
        for query in queries:
            found = search(query)
            pool.extend(found)
            verdict = judge(pool)
            if verdict:
                return {**verdict, 'candidates': _candidates(pool)}
        box = _area_box(entity, search)  # a small business is often missing from a broad search: look for it only inside its suburb
        if box:
            pool.extend(search(entity.name, viewbox=box))
            verdict = judge(pool)
            if verdict:
                return {**verdict, 'candidates': _candidates(pool)}
    except (urllib.error.URLError, OSError, ValueError):
        return {'status': 'unavailable', 'reason': 'The geocoder could not be reached; the place stays unlocated.', 'candidates': _candidates(pool)}
    return {'status': 'not_found', 'reason': f'The map has no exact match for "{entity.name}".', 'candidates': _candidates(pool)}


def metadata_from_pin(entity, lat: float, lon: float, *, how: str, location_id: str | None = None) -> dict:
    """A coordinate the person supplied (a map pin or link they checked themselves)."""
    return {**(entity.metadata or {}), 'latitude': f'{lat:.7f}', 'longitude': f'{lon:.7f}', 'location_verified': 'true',
            'location_id': location_id or f'pin:{lat:.5f},{lon:.5f}', 'location_source': f"{how}, supplied by the user ({time.strftime('%Y-%m-%d')})"}


def metadata_for(entity, found: dict) -> dict:
    return {**(entity.metadata or {}), 'latitude': f"{found['lat']:.7f}", 'longitude': f"{found['lon']:.7f}", 'location_verified': 'true',
            'location_id': found['location_id'],
            'location_source': f"OpenStreetMap Nominatim {found['location_id']}: {found['display_name']} (matched on name and suburb, {time.strftime('%Y-%m-%d')})"}
