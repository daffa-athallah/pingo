from argparse import Namespace
import unittest
from unittest.mock import patch

from backend.scripts.trigger_context import endpoint, payload


class TriggerContextTests(unittest.TestCase):
    def base(self, **changes):
        values = dict(kind='location', timezone='Australia/Melbourne', at='2026-10-26T12:30:00+11:00',
                      latitude=-37.8, longitude=144.967, accuracy=20, label='Carlton')
        values.update(changes)
        return Namespace(**values)

    def test_location_payload_is_clearly_simulated_and_aware(self):
        result = payload(self.base())
        event = result['events'][0]
        self.assertEqual((event['source'], event['type']), ('SIMULATED', 'LOCATION'))
        self.assertEqual(event['location']['latitude'], -37.8)
        self.assertIn('+11:00', result['now'])

    def test_calendar_and_time_payloads(self):
        calendar = self.base(kind='calendar', title='Lunch with Sarah', start='2026-11-02T12:30:00+11:00',
                             end='2026-11-02T14:00:00+11:00', location='Carlton', city='Melbourne',
                             country='Australia', description='Catch-up lunch')
        event = payload(calendar)['events'][0]
        self.assertEqual(event['type'], 'CALENDAR')
        self.assertEqual(event['location']['name'], 'Carlton')
        clock = self.base(kind='time', label='Tomorrow', latitude=None, longitude=None, accuracy=None)
        self.assertEqual(payload(clock)['events'][0]['type'], 'TIME')

    def test_invalid_calendar_order_and_endpoint(self):
        calendar = self.base(kind='calendar', title='Trip', start='2026-11-03T12:00:00+11:00',
                             end='2026-11-02T12:00:00+11:00', location='', city='', country='', description='')
        with self.assertRaisesRegex(ValueError, 'after start'):
            payload(calendar)
        self.assertEqual(endpoint('https://pingo.test/'), 'https://pingo.test/context-simulator/evaluate')
        with self.assertRaisesRegex(ValueError, 'http'):
            endpoint('pingo.test')

    def test_unique_context_id_on_each_observation(self):
        with patch('backend.scripts.trigger_context.uuid.uuid4') as new_id:
            new_id.side_effect = [Namespace(hex='a'*32), Namespace(hex='b'*32)]
            self.assertNotEqual(payload(self.base())['events'][0]['context_id'], payload(self.base())['events'][0]['context_id'])
