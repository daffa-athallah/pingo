"""Zetaris JDBC boundary. No agent logic, SQL rewriting, or provider fallback.

Importing this module starts no JVM and opens no connection. The optional JDBC
packages are imported only by connect(), so offline/sample startup can avoid them.
Driver/server exceptions are intentionally not included in application errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
from threading import RLock
from typing import Any, Mapping, Sequence
from zipfile import BadZipFile, ZipFile

DRIVER_CLASS = 'com.zetaris.lightning.jdbc.LightningDriver'


class ZetarisError(RuntimeError):
    """Sanitized connection/query failure; never contains SQL or credentials."""


@dataclass(frozen=True)
class JdbcSettings:
    url: str = field(repr=False)
    username: str = field(repr=False)
    password: str = field(repr=False)
    jar: Path

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> JdbcSettings:
        env = os.environ if environment is None else environment
        names = ('ZETARIS_JDBC_URL', 'ZETARIS_USERNAME', 'ZETARIS_PASSWORD', 'ZETARIS_JDBC_JAR')
        missing = [key for key in names if not env.get(key, '').strip()]
        if missing:
            raise ZetarisError('Missing environment variables: ' + ', '.join(missing))
        url = env['ZETARIS_JDBC_URL'].strip()
        if not re.fullmatch(r'jdbc:zetaris:lightning@(?:\[[0-9a-fA-F:]+\]|[A-Za-z0-9._-]+):[0-9]{1,5}', url):
            raise ZetarisError('ZETARIS_JDBC_URL must specify a Zetaris host and port without credentials or URL parameters.')
        port = int(url.rsplit(':', 1)[1])
        if not 1 <= port <= 65535:
            raise ZetarisError('ZETARIS_JDBC_URL has an invalid port.')
        jar = Path(env['ZETARIS_JDBC_JAR']).expanduser().resolve()
        if not jar.is_file():
            raise ZetarisError('ZETARIS_JDBC_JAR does not point to an existing file.')
        try:
            with ZipFile(jar) as archive:
                if DRIVER_CLASS.replace('.', '/') + '.class' not in archive.namelist():
                    raise ZetarisError('JAR does not contain the Zetaris Lightning JDBC driver class.')
        except (BadZipFile, OSError):
            raise ZetarisError('Cannot read ZETARIS_JDBC_JAR as a JAR archive.') from None
        return cls(url, env['ZETARIS_USERNAME'], env['ZETARIS_PASSWORD'], jar)


def java_major_version() -> int:
    home = os.environ.get('JAVA_HOME', '')
    executable = str(Path(home) / 'bin/java') if home else 'java'
    try:
        result = subprocess.run([executable, '-version'], capture_output=True, text=True, timeout=10)
        match = re.search(r'version\s+"(\d+)(?:\.(\d+))?', result.stderr + result.stdout)
        if result.returncode or not match:
            raise ZetarisError('Cannot verify Java. Set JAVA_HOME to a JDK 11 or newer installation.')
        version = int(match.group(2)) if match.group(1) == '1' else int(match.group(1))
        if version < 11:
            raise ZetarisError('Java 11 or newer is required. Set JAVA_HOME to the correct installation.')
        return version
    except (OSError, subprocess.TimeoutExpired):
        raise ZetarisError('Cannot execute Java. Configure JAVA_HOME; no runtime was installed automatically.') from None


class ZetarisJdbc:
    def __init__(self, settings: JdbcSettings, *, connector=None):
        self.settings = settings
        self._connector = connector
        self._connection: Any = None
        self._lock = RLock()

    def connect(self) -> ZetarisJdbc:
        with self._lock:
            if self._connection is not None:
                return self
            java_major_version()
            connector = self._connector
            if connector is None:
                try:
                    import jaydebeapi
                except ImportError:
                    raise ZetarisError('JDBC Python runner dependencies are missing; install requirements-zetaris.txt in a virtual environment.') from None
                connector = jaydebeapi.connect
            try:
                self._connection = connector(DRIVER_CLASS, self.settings.url,
                                             [self.settings.username, self.settings.password], str(self.settings.jar))
            except Exception:
                raise ZetarisError('Zetaris JDBC connection failed. Check the endpoint, account and driver compatibility; details withheld.') from None
            return self

    def query(self, sql: str, parameters: Sequence[Any] = ()) -> list[tuple]:
        """Execute exactly one caller-supplied statement. Values use JDBC binding.

        Parameter binding must be verified against the live driver before a
        repository relies on it; this adapter does not interpolate values.
        """
        with self._lock:
            if self._connection is None:
                raise ZetarisError('JDBC connection is not open.')
            cursor = None
            try:
                cursor = self._connection.cursor()
                if parameters:
                    cursor.execute(sql, tuple(parameters))
                else:
                    cursor.execute(sql)
                return [tuple(row) for row in cursor.fetchall()] if cursor.description else []
            except Exception:
                raise ZetarisError('Zetaris statement failed; SQL, parameters and server response withheld.') from None
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass

    def supports_transactions(self) -> bool | None:
        if self._connection is None:
            raise ZetarisError('JDBC connection is not open.')
        try:
            return bool(self._connection.jconn.getMetaData().supportsTransactions())
        except Exception:
            return None

    def close(self) -> None:
        with self._lock:
            connection, self._connection = self._connection, None
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    raise ZetarisError('JDBC close failed; connection details withheld.') from None

    def __enter__(self) -> ZetarisJdbc:
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.close()
        except ZetarisError:
            if exc_type is None:
                raise
