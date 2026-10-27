"""Cover photos for saved places and products: find candidates on the web, let the Cover Agent choose (or refuse), cache the chosen image locally.

Search: Google Programmable Search (image search) when GOOGLE_CSE_KEY and GOOGLE_CSE_CX are set. Without them there is no provider and nothing is
fetched, so a card keeps its neutral icon (a wrong photo is worse than none). The chosen image is downloaded once, resized, and served from this
backend (/covers/<file>); the card links back to the page it came from. Web images are other people's work: the source page is always kept and shown.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request

COVERS = Path(os.environ.get('RECALL_COVER_DIR') or Path(__file__).resolve().parents[1] / 'runtime/covers')
USER_AGENT = 'Pingo-Recall-hackathon/1.0 (https://github.com/daffa-athallah/recall)'
MAX_BYTES = 3 * 1024 * 1024
KEY_PREFIX = 'catalogue_image_'


@dataclass(frozen=True)
class Candidate:
    image_url: str
    thumb_url: str | None
    page_url: str
    title: str


def provider_configured() -> bool:
    return bool(os.environ.get('GOOGLE_CSE_KEY') and os.environ.get('GOOGLE_CSE_CX'))


def _context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _https(url: str | None) -> bool:
    try:
        parsed = urllib.parse.urlparse(url or '')
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


def search_google(query: str, *, limit: int = 4, timeout: float = 8.0) -> list[Candidate]:
    params = {'key': os.environ['GOOGLE_CSE_KEY'], 'cx': os.environ['GOOGLE_CSE_CX'], 'q': query, 'searchType': 'image', 'num': limit,
              'safe': 'active', 'imgType': 'photo'}
    request = urllib.request.Request('https://www.googleapis.com/customsearch/v1?' + urllib.parse.urlencode(params), headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=_context()) as response:
        data = json.loads(response.read())
    out = []
    for item in data.get('items', []):
        image = item.get('link')
        page = (item.get('image') or {}).get('contextLink') or image
        if _https(image) and _https(page):
            out.append(Candidate(image, (item.get('image') or {}).get('thumbnailLink'), page, (item.get('title') or '')[:120]))
    return out


def fetch(url: str, *, timeout: float = 8.0) -> bytes | None:
    """The image bytes, or None when it is unreachable, too large or not an image. Only https, never a redirect to another scheme."""
    if not _https(url):
        return None
    try:
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'image/*'})
        with urllib.request.urlopen(request, timeout=timeout, context=_context()) as response:
            if not (response.headers.get('Content-Type') or '').lower().startswith('image/'):
                return None
            data = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data if 2000 < len(data) <= MAX_BYTES else None


def normalise(data: bytes, width: int) -> bytes | None:
    """A JPEG no wider than `width`, or None if it is not a decodable image. Also strips metadata."""
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            if image.width < 200 or image.height < 150:  # too small to be a cover
                return None
            image.thumbnail((width, width))
            out = io.BytesIO()
            image.save(out, 'JPEG', quality=84, optimize=True)
            return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


def store(data: bytes) -> str:
    COVERS.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(data).hexdigest()[:24] + '.jpg'
    (COVERS / name).write_bytes(data)
    return name


def subject_query(entity) -> str:
    """What to search for, from one saved entity (never the person's own screenshot text)."""
    parts = [entity.brand if entity.brand and entity.brand.lower() not in entity.name.lower() else None, entity.name,
             entity.subcategory if entity.entity_type == 'product' else None]
    if entity.entity_type != 'product':
        parts += [entity.location_name, entity.city]
    return ' '.join(p for p in dict.fromkeys(p for p in parts if p))


def metadata_for(entity, *, file: str, candidate: Candidate, alt: str, reason: str) -> dict:
    return {**(entity.metadata or {}), f'{KEY_PREFIX}file': file, f'{KEY_PREFIX}source': candidate.page_url, f'{KEY_PREFIX}verified': 'true',
            f'{KEY_PREFIX}alt': alt[:200], f'{KEY_PREFIX}reason': reason[:300]}


def view_for(entity) -> dict | None:
    """The catalogue_images row the app's Home reads, or None. Only an image whose file still exists is offered."""
    meta = entity.metadata or {}
    name = meta.get(f'{KEY_PREFIX}file')
    if not name or meta.get(f'{KEY_PREFIX}verified') != 'true' or Path(name).name != name or not (COVERS / name).is_file():
        return None
    return {'entity_id': entity.entity_id, 'catalogue_image_url': f'/covers/{name}', 'catalogue_image_source': meta.get(f'{KEY_PREFIX}source', ''),
            'catalogue_image_verified': True, 'alt': meta.get(f'{KEY_PREFIX}alt') or entity.name}


def has_cover(entity) -> bool:
    return view_for(entity) is not None


Search = Callable[[str], list[Candidate]]
