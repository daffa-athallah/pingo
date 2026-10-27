"""Where is this saved place? Resolves a restaurant or destination to coordinates so proximity checks (phone GPS, Context Simulator) can match it.

The source is OpenStreetMap Nominatim, a free public geocoder (no key; its usage policy allows light use with an identifying User-Agent, one request
per second). A result is accepted only when it is unambiguous:
  * the result's own name has exactly the saved name's distinctive words (a longer name is a different place), and
  * the saved suburb or city appears in the result, and
  * all bounded name/locality queries are checked before accepting a single place;
  * map duplicates must lie within 50 m (different branches stay ambiguous).
What is stored on the entity: latitude, longitude, location_verified="true", location_source (what matched and how), location_id (osm:<type>:<id>).
Nothing is ever guessed: with no confident match the place stays unlocated and proximity is not evaluated. Shopping products are never geocoded;
explicit physical store entities may be located, without any inventory claim. This extends the geocode module added on main, not the four agent prompts.
"""
from __future__ import annotations

import math
import os
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.request

from backend.app.adapters.geocoding import NominatimClient, tls_context

ENDPOINT = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'Pingo-Recall-hackathon/1.0 (https://github.com/daffa-athallah/recall)'
PLACE_TYPES = {'place', 'restaurant', 'venue', 'attraction', 'destination', 'cafe', 'bar', 'store',
               'park', 'garden', 'museum', 'landmark', 'building', 'station', 'airport', 'hotel', 'bakery', 'pub'}
GENERIC = {'the', 'a', 'an', 'and', 'of', 'restaurant', 'cafe', 'bar', 'shop', 'store'}


def _context() -> ssl.SSLContext:
    """TLS trust that does not depend on the shell's SSL_CERT_FILE (a launchd job has none): certifi's bundle, else the macOS/Linux system bundle."""
    return tls_context()


def enabled() -> bool:
    setting = os.environ.get('RECALL_GEOCODE', '').strip().lower()
    if setting in ('off', '0', 'false'):
        return False
    return setting in ('on', '1', 'true') and os.environ.get('SAMPLE_MODE', 'false').lower() != 'true'


def _norm(text: str) -> str:
    text = ''.join(c for c in unicodedata.normalize('NFKD', text or '') if not unicodedata.combining(c)).casefold().replace('&', ' and ')
    return ' '.join(re.sub(r'[^\w ]+', '', text.replace("'", '').replace('’', '')).replace('_', ' ').split())


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if t and t not in GENERIC}


def _metres(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))


def _search(query: str, timeout: float = 6.0, viewbox: str | None = None) -> list[dict]:
    return NominatimClient.from_env().search(query, timeout=timeout, viewbox=viewbox)


def _area_box(entity, search) -> str | None:
    """viewbox (left,top,right,bottom) of the saved suburb/city, so a small business is searched for only inside it."""
    area = entity.location_name if entity.location_name and _norm(entity.location_name) != _norm(entity.city or '') else None
    if not area:
        return None
    found = search(', '.join(p for p in (area, entity.city, entity.country) if p))
    valid = {}
    for result in found:
        if result.get('class', result.get('category')) not in {'place', 'boundary'} or not _in_area(result, area):
            continue
        if any(not _in_area(result, value) for value in (entity.city, entity.country) if value):
            continue
        try:
            south, north, west, east = map(float, result['boundingbox'])
            if not all(math.isfinite(v) for v in (south, north, west, east)) or not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        valid[(result.get('osm_type'), result.get('osm_id'))] = f'{west},{north},{east},{south}'
    return next(iter(valid.values())) if len(valid) == 1 else None


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
    physical = entity.domain in ('food', 'travel') and entity.entity_type in PLACE_TYPES or \
        entity.domain == 'shopping' and entity.entity_type in {'store', 'shop', 'retailer'}
    return physical and not verified(entity)


def verified(entity) -> bool:
    meta = entity.metadata or {}
    try:
        lat, lon = float(meta['latitude']), float(meta['longitude'])
        return meta.get('location_verified', '').lower() == 'true' and bool(meta.get('location_source', '').strip()) and \
            math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and \
            (entity.domain != 'shopping' or meta.get('location_role') == 'store' and bool(meta.get('store_name')))
    except (KeyError, ValueError, TypeError):
        return False


def _valid_result(item):
    try:
        if not isinstance(item, dict) or not isinstance(item.get('name', ''), str) or not isinstance(item.get('display_name', ''), str):
            return False
        lat, lon = float(item['lat']), float(item['lon'])
        return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and \
            item.get('osm_type') in {'node', 'way', 'relation'} and str(item.get('osm_id', '')).isdigit()
    except (KeyError, ValueError, TypeError):
        return False


def _in_area(item, area):
    """Whole address components, never a city name occurring inside a business name."""
    wanted = _norm(area)
    address = item.get('address') or {}
    values = list(address.values()) if isinstance(address, dict) else []
    values += str(item.get('display_name', '')).split(',')
    return any(_norm(str(value)) == wanted or _norm(str(value)) == 'city of ' + wanted for value in values)


def _candidates(results) -> list[dict]:
    seen, out = set(), []
    for r in results:
        if not _valid_result(r):
            continue
        key = (r.get('osm_type'), r.get('osm_id'))
        if key in seen:
            continue
        seen.add(key)
        out.append({'label': str(r.get('display_name', ''))[:400], 'name': str(r.get('name', ''))[:200], 'lat': float(r['lat']), 'lon': float(r['lon']),
                    'location_id': f"osm:{r.get('osm_type')}:{r.get('osm_id')}"})
    return out[:5]


def resolve(entity, *, search=_search) -> dict:
    """{'status': 'resolved', ...} | {'status': 'ambiguous'|'not_found'|'unavailable', 'reason': str, 'candidates': [...]}.

    The agent searches the map several ways (name and suburb, name and city, the street address read from the screenshot, name inside the suburb)
    and accepts a result by itself only when it is unambiguous. Everything it found but could not accept is returned as candidates for the person to confirm."""
    meta = entity.metadata or {}
    if not eligible(entity):
        return {'status': 'skipped', 'reason': 'Already verified or not a physical place/store.', 'candidates': []}
    if not entity.city and not entity.location_name:
        return {'status': 'ambiguous', 'reason': 'No city or suburb was extracted. A place name alone cannot identify the correct branch.', 'candidates': []}
    same = entity.location_name and entity.city and _norm(entity.location_name) == _norm(entity.city)
    queries = [', '.join(p for p in (entity.name, None if same else entity.location_name, entity.city, entity.country) if p),
               ', '.join(p for p in (entity.name, entity.city or entity.location_name, entity.country) if p)]
    if meta.get('address'):
        queries.insert(1, f"{entity.name}, {meta['address']}")
    name_tokens = _tokens(entity.name)
    if not name_tokens:
        return {'status': 'ambiguous', 'reason': 'No distinctive place name was extracted; no broad place search was sent.', 'candidates': []}
    pool: list[dict] = []
    context_box = None

    def judge(items):
        good = []
        for item in items:
            if not _valid_result(item):
                continue
            have = set(_norm(f"{item.get('name', '')} {item.get('display_name', '')}").split())
            # The result's own name must be the saved name, not a longer one ("Biomedical Learning and Teaching Building" is not "Learning and Teaching Building").
            named = _tokens(item.get('name') or '') == name_tokens
            areas = [area for area in (entity.location_name, entity.city, entity.country) if area]
            def in_saved_area(area):
                if _in_area(item, area):
                    return True
                if context_box and area == entity.location_name:
                    west, north, east, south = map(float, context_box.split(','))
                    return south <= float(item['lat']) <= north and west <= float(item['lon']) <= east
                return False
            if name_tokens and named and all(in_saved_area(area) for area in areas):
                good.append(item)
        if not good:
            return None
        first = (float(good[0]['lat']), float(good[0]['lon']))
        if any(_metres(first, (float(g['lat']), float(g['lon']))) > 50 for g in good[1:]):
            return {'status': 'ambiguous', 'reason': f'"{entity.name}" matches several different places; not choosing one.'}
        best = good[0]
        return {'status': 'resolved', 'lat': float(best['lat']), 'lon': float(best['lon']), 'display_name': str(best.get('display_name', ''))[:400],
                'location_id': f"osm:{best.get('osm_type')}:{best.get('osm_id')}"}

    try:
        truncated = False
        for query in dict.fromkeys(queries):
            found = search(query)
            truncated = truncated or len(found) >= 5
            pool.extend(found)
        # Evaluate the combined candidate set; never accept the first result before checking other branches.
        verdict = judge(pool)
        if verdict:
            if truncated and verdict['status'] == 'resolved':
                verdict = {'status': 'ambiguous', 'reason': 'The provider result limit was reached; additional branches may exist.'}
            return {**verdict, 'candidates': _candidates(pool)}
        context_box = _area_box(entity, search)
        if context_box:
            found = search(entity.name, viewbox=context_box)
            pool.extend(found)
            verdict = judge(pool)
            if verdict:
                if (truncated or len(found) >= 5) and verdict['status'] == 'resolved':
                    verdict = {'status': 'ambiguous', 'reason': 'The bounded search was truncated; the branch remains uncertain.'}
                return {**verdict, 'candidates': _candidates(pool)}
        # Some POIs are indexed by name but not found by the combined address parser.
        # This broadens the query, never the acceptance rule: saved city/suburb/country still must match.
        found = search(entity.name)
        pool.extend(found)
        verdict = judge(pool)
        if verdict:
            if (truncated or len(found) >= 5) and verdict['status'] == 'resolved':
                verdict = {'status': 'ambiguous', 'reason': 'The name-only fallback was truncated; the branch remains uncertain.'}
            return {**verdict, 'candidates': _candidates(pool)}
    except (urllib.error.URLError, OSError, ValueError):
        return {'status': 'unavailable', 'reason': 'The geocoder could not be reached; the place stays unlocated.', 'candidates': _candidates(pool)}
    return {'status': 'not_found', 'reason': f'The map has no exact match for "{entity.name}".', 'candidates': _candidates(pool)}


def metadata_from_pin(entity, lat: float, lon: float, *, how: str, location_id: str | None = None) -> dict:
    """A coordinate the person supplied (a map pin or link they checked themselves)."""
    return {**(entity.metadata or {}), 'latitude': f'{lat:.7f}', 'longitude': f'{lon:.7f}', 'location_verified': 'true',
            'location_id': location_id or f'pin:{lat:.5f},{lon:.5f}', 'location_source': f"{how}, supplied by the user ({time.strftime('%Y-%m-%d')})"}


def metadata_for(entity, found: dict) -> dict:
    lat, lon = float(found['lat']), float(found['lon'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or \
            not re.fullmatch(r'osm:(node|way|relation):\d+', found.get('location_id', '')):
        raise ValueError('Invalid resolved coordinate/provenance.')
    return {**(entity.metadata or {}), 'latitude': f"{found['lat']:.7f}", 'longitude': f"{found['lon']:.7f}", 'location_verified': 'true',
            'location_id': found['location_id'],
            **({'location_role': 'store', 'store_name': entity.name} if entity.domain == 'shopping' else {}),
            'location_source': f"OpenStreetMap contributors / Nominatim {found['location_id']}: {found['display_name']} (matched on name and saved locality, {time.strftime('%Y-%m-%d')})"}
