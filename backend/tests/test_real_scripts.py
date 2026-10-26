"""Offline tests for the real-data reasoning scripts' local policy and the list_evidence helper."""
from pathlib import Path
import sys
import unittest

from backend.app.repositories.zetaris import ZetarisRepository
from test_zetaris_repository import SqlHarness, evidence

# Appended last so the scripts directory cannot shadow test modules of the same name.
sys.path.append(str(Path(__file__).resolve().parents[1] / 'scripts'))
import process_open_loops as pol


class LocalPolicy(unittest.TestCase):
    def test_sensitive_and_unsupported_are_skipped_locally(self):
        self.assertEqual(pol.eligibility(evidence(sensitive=True)), 'SKIP_SENSITIVE')
        self.assertEqual(pol.eligibility(evidence(domain='health')), 'SKIP_UNSUPPORTED_DOMAIN')

    def test_supported_domains_are_eligible(self):
        for domain in ('food', 'shopping', 'travel'):
            self.assertIsNone(pol.eligibility(evidence(domain=domain)))

    def test_reprocess_generation_changes_the_loop_id(self):
        self.assertEqual(pol.loop_id_for('ev_1'), pol.loop_id_for('ev_1', 0))
        self.assertNotEqual(pol.loop_id_for('ev_1'), pol.loop_id_for('ev_1', 1))

    def test_loop_id_is_deterministic_per_evidence(self):
        self.assertEqual(pol.loop_id_for('ev_1'), pol.loop_id_for('ev_1'))
        self.assertNotEqual(pol.loop_id_for('ev_1'), pol.loop_id_for('ev_2'))


class ListEvidence(unittest.TestCase):
    def test_stable_order_and_canonical_objects(self):
        repo = ZetarisRepository(SqlHarness())
        for item in (evidence('ev_b', timestamp='2026-10-25T10:00:00+00:00'), evidence('ev_a', timestamp='2026-10-25T10:00:00+00:00'),
                     evidence('ev_c', timestamp='2026-10-24T10:00:00+00:00')):
            repo.save_evidence(item, [], [])
        listed = repo.list_evidence()
        self.assertEqual([e.evidence_id for e in listed], ['ev_c', 'ev_a', 'ev_b'])
        self.assertTrue(all(type(e).__name__ == 'Evidence' for e in listed))


if __name__ == '__main__':
    unittest.main()
