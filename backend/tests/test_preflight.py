"""Offline tests for preflight's safety-relevant decisions. No Docker, Tailscale or network."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / 'scripts'))
import preflight


def levels(serve_text, status):
    preflight.RESULTS.clear()

    def fake_run(args, timeout=20):
        return (0, serve_text) if 'serve' in args else (0, status)

    with patch.object(preflight, 'find', return_value='/bin/tailscale'), patch.object(preflight, 'run', side_effect=fake_run), \
            patch.object(preflight, 'http', return_value=(200, b'')), patch('builtins.print'):
        preflight.check_tailscale()
    return dict((name, level) for level, name in preflight.RESULTS)


STATUS = '{"BackendState": "Running", "Self": {"DNSName": "mac.tail.ts.net."}, "Peer": {"a": {"HostName": "ica", "Online": true}}}'
SERVED = 'https://mac.tail.ts.net:8443 (tailnet only)\n|-- / proxy http://localhost:8000\n'


class TailscaleChecks(unittest.TestCase):
    def test_public_funnel_is_a_failure(self):
        result = levels('# Funnel on:\n#     - https://mac.tail.ts.net\n' + SERVED, STATUS)
        self.assertEqual(result['Tailscale Funnel'], 'FAIL')

    def test_tailnet_only_serve_passes(self):
        result = levels(SERVED, STATUS)
        self.assertEqual((result['Tailscale Funnel'], result['Tailnet HTTPS URL'], result['Tailnet peers online']), ('PASS', 'PASS', 'PASS'))

    def test_missing_serve_is_a_failure_with_the_command_to_run(self):
        self.assertEqual(levels('', STATUS)['Tailscale serve'], 'FAIL')

    def test_disconnected_tailscale_is_a_failure(self):
        self.assertEqual(levels(SERVED, '{"BackendState": "Stopped", "Self": {}, "Peer": {}}')['Tailscale'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
