"""Shared helpers for the real-Zetaris reasoning scripts. No secrets are printed; no in-memory fallback exists."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from backend.app.adapters.zetaris import JdbcSettings, ZetarisError, ZetarisJdbc
from backend.app.repositories.zetaris import ZetarisRepository

DEFAULT_ENV_FILES = (ROOT / 'env.local', ROOT / 'backend/.env')


def load_env(extra: list[Path] | None = None) -> None:
    for path in [*(extra or []), *DEFAULT_ENV_FILES]:
        if path.is_file():
            load_dotenv(path, override=False)
    if os.environ.get('SAMPLE_MODE', 'false').strip().lower() == 'true':
        raise ZetarisError('SAMPLE_MODE=true: refusing to run a real-data script against the in-memory repository.')


@contextmanager
def real_repository():
    with ZetarisJdbc(JdbcSettings.from_env()) as connection:
        yield ZetarisRepository(connection)
