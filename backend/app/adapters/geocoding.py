"""Bounded Nominatim search transport/cache. Never a source of application truth.

Public usage: https://operations.osmfoundation.org/policies/nominatim/
One host/process family, serialized requests, identifying User-Agent, cached results.
An alternative compatible endpoint can be configured without changing code.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ENDPOINT = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'Pingo-Recall-hackathon/1.0 (https://github.com/daffa-athallah/recall)'
_THREAD_LOCK = threading.RLock()


def tls_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context(cafile='/etc/ssl/cert.pem') if os.path.isfile('/etc/ssl/cert.pem') else ssl.create_default_context()


class NominatimClient:
    def __init__(self, *, endpoint=DEFAULT_ENDPOINT, cache_dir=None, user_agent=USER_AGENT,
                 transport=None, clock=time.time, sleep=time.sleep):
        parsed = urllib.parse.urlsplit(endpoint)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError('Geocoding endpoint must be HTTPS, without credentials, query or fragment.')
        if not user_agent.strip() or user_agent.startswith(('Python-', 'curl/')):
            raise ValueError('Geocoding requires an identifying application User-Agent.')
        self.endpoint, self.user_agent = endpoint, user_agent
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[2] / 'runtime/geocode')
        self.transport = transport or self._http
        self.clock, self.sleep = clock, sleep

    @classmethod
    def from_env(cls):
        return cls(endpoint=os.environ.get('RECALL_GEOCODE_URL') or DEFAULT_ENDPOINT,
                   cache_dir=os.environ.get('RECALL_GEOCODE_CACHE_DIR') or None,
                   user_agent=os.environ.get('RECALL_GEOCODE_USER_AGENT') or USER_AGENT)

    def _http(self, query, *, viewbox=None, timeout=6.0):
        params = {'q': query, 'format': 'jsonv2', 'limit': 5, 'addressdetails': 1,
                  **({'viewbox': viewbox, 'bounded': 1} if viewbox else {})}
        request = urllib.request.Request(self.endpoint + '?' + urllib.parse.urlencode(params),
                                        headers={'User-Agent': self.user_agent, 'Accept-Language': 'en'})
        with urllib.request.urlopen(request, timeout=timeout, context=tls_context()) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Geocoding response exceeded size limit.')
            return json.loads(raw)

    @contextmanager
    def _locked(self):
        self.cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with _THREAD_LOCK, (self.cache_dir / '.requests.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def _read(path):
        try:
            value = json.loads(path.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write(path, value):
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(value, ensure_ascii=False))
        tmp.replace(path)

    def search(self, query, *, viewbox=None, timeout=6.0):
        if not query.strip() or len(query) > 500:
            raise ValueError('Geocoding query is empty or too long.')
        key = hashlib.sha256(json.dumps([self.endpoint, query, viewbox], ensure_ascii=False).encode()).hexdigest()
        with self._locked():
            path = self.cache_dir / (key + '.json')
            cached = self._read(path)
            if isinstance(cached.get('expires_at'), (int, float)) and cached['expires_at'] > self.clock() and \
                    isinstance(cached.get('results'), list) and len(cached['results']) <= 5 and all(isinstance(item, dict) for item in cached['results']):
                return cached['results']
            timing_path = self.cache_dir / '.timing.json'
            timing = self._read(timing_path)
            if timing.get('blocked_until', 0) > self.clock():
                raise OSError('Geocoding provider is in backoff; no request sent.')
            delay = max(0, min(1.1, timing.get('last_started', 0) + 1.1 - self.clock()))
            if delay:
                self.sleep(delay)
            self._write(timing_path, {'last_started': self.clock()})
            try:
                results = self.transport(query, viewbox=viewbox, timeout=timeout)
                if not isinstance(results, list) or len(results) > 5 or any(not isinstance(item, dict) for item in results):
                    raise ValueError('Malformed geocoding result.')
            except (OSError, ValueError) as exc:
                backoff = 60
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                    try:
                        backoff = max(60, min(3600, int(exc.headers.get('Retry-After', '60'))))
                    except (TypeError, ValueError):
                        pass
                self._write(timing_path, {'last_started': self.clock(), 'blocked_until': self.clock() + backoff})
                raise OSError('Geocoding lookup unavailable; request details withheld.') from None
            self._write(path, {'expires_at': self.clock() + 86400, 'results': results})
            return results
