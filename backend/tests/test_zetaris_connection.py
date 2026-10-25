"""Offline JDBC boundary checks; no JVM, network, or sponsor service is required."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from backend.app.adapters.zetaris import DRIVER_CLASS, JdbcSettings, ZetarisError, ZetarisJdbc


class JdbcBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.jar = Path(self.directory.name) / 'driver.jar'
        with ZipFile(self.jar, 'w') as archive:
            archive.writestr(DRIVER_CLASS.replace('.', '/') + '.class', b'offline-test-placeholder')
        self.env = dict(ZETARIS_JDBC_URL='jdbc:zetaris:lightning@localhost:10000',
                        ZETARIS_USERNAME='offline-user', ZETARIS_PASSWORD='offline-secret',
                        ZETARIS_JDBC_JAR=str(self.jar))

    def settings(self):
        return JdbcSettings.from_env(self.env)

    def test_settings_repr_hides_credentials_and_url(self):
        value = repr(self.settings())
        for key in ('ZETARIS_USERNAME', 'ZETARIS_PASSWORD', 'ZETARIS_JDBC_URL'):
            self.assertNotIn(self.env[key], value)

    def test_missing_configuration_reports_names_only(self):
        with self.assertRaisesRegex(ZetarisError, 'ZETARIS_PASSWORD') as error:
            JdbcSettings.from_env({**self.env, 'ZETARIS_PASSWORD': ''})
        self.assertNotIn(self.env['ZETARIS_USERNAME'], str(error.exception))

    def test_wrong_driver_archive_is_rejected(self):
        with ZipFile(self.jar, 'w') as archive:
            archive.writestr('org/example/HiveDriver.class', b'placeholder')
        with self.assertRaisesRegex(ZetarisError, 'Zetaris Lightning'):
            self.settings()

    def test_missing_driver_is_rejected(self):
        self.jar.unlink()
        with self.assertRaisesRegex(ZetarisError, 'existing file'):
            self.settings()

    def test_only_zetaris_urls_without_embedded_credentials_are_allowed(self):
        for url in ('jdbc:hive2://localhost:10000', 'jdbc:zetaris:lightning@user:secret@host:10000',
                    'jdbc:zetaris:lightning@localhost:0', 'jdbc:zetaris:lightning@localhost:10000?password=x'):
            with self.subTest(url=url), self.assertRaises(ZetarisError):
                JdbcSettings.from_env({**self.env, 'ZETARIS_JDBC_URL': url})

    def test_constructing_adapter_does_not_connect(self):
        connector = Mock()
        ZetarisJdbc(self.settings(), connector=connector)
        connector.assert_not_called()

    @patch('backend.app.adapters.zetaris.java_major_version', return_value=11)
    def test_select_one_closes_cursor_and_connection(self, _java):
        cursor = Mock(description=[('one',)])
        cursor.fetchall.return_value = [(1,)]
        connection = Mock()
        connection.cursor.return_value = cursor
        connector = Mock(return_value=connection)
        settings = self.settings()
        with ZetarisJdbc(settings, connector=connector) as jdbc:
            self.assertEqual(jdbc.query('SELECT 1'), [(1,)])
        connector.assert_called_once_with(DRIVER_CLASS, settings.url, [settings.username, settings.password], str(settings.jar))
        cursor.execute.assert_called_once_with('SELECT 1')
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    @patch('backend.app.adapters.zetaris.java_major_version', return_value=11)
    def test_binding_passes_values_separately(self, _java):
        cursor = Mock(description=[('value',)])
        cursor.fetchall.return_value = [('value',)]
        connection = Mock()
        connection.cursor.return_value = cursor
        with ZetarisJdbc(self.settings(), connector=Mock(return_value=connection)) as jdbc:
            jdbc.query('SELECT ?', ["quoted ' value"])
        cursor.execute.assert_called_once_with('SELECT ?', ("quoted ' value",))

    @patch('backend.app.adapters.zetaris.java_major_version', return_value=11)
    def test_query_failure_is_sanitized_and_resources_close(self, _java):
        cursor = Mock()
        cursor.execute.side_effect = RuntimeError('offline-secret raw SQL payload')
        connection = Mock()
        connection.cursor.return_value = cursor
        with self.assertRaises(ZetarisError) as error:
            with ZetarisJdbc(self.settings(), connector=Mock(return_value=connection)) as jdbc:
                jdbc.query('SELECT private_content')
        self.assertNotIn('offline-secret', str(error.exception))
        self.assertNotIn('private_content', str(error.exception))
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    @patch('backend.app.adapters.zetaris.java_major_version', return_value=11)
    def test_connection_failure_is_sanitized(self, _java):
        connector = Mock(side_effect=RuntimeError('offline-secret'))
        with self.assertRaises(ZetarisError) as error:
            ZetarisJdbc(self.settings(), connector=connector).connect()
        self.assertNotIn('offline-secret', str(error.exception))


if __name__ == '__main__':
    unittest.main()
