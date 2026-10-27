"""The Location Agent finds a street address on the web and verifies it on the map; it may not invent or assume either."""
import asyncio
import json
import unittest

from backend.app import location_web
from backend.app.domain.models import Entity


def place():
    return Entity('e', 'restaurant', 'food', 'Marrybrown', location_name='Clayton', city='Melbourne', country='Australia')


SNIPPETS = [{'title': 'Marrybrown Clayton - Marrybrown Australia', 'snippet': 'Marrybrown Clayton 399 Clayton Rd Clayton VIC 3168 Australia Directions', 'url': 'https://marrybrown.au/clayton'},
            {'title': 'Store locator', 'snippet': 'Find a store near you.', 'url': 'https://marrybrown.au/stores'}]
MAP = {'osm_type': 'way', 'osm_id': 42, 'lat': '-37.9277623', 'lon': '145.1188594', 'name': '', 'display_name': '399, Clayton Road, Clayton',
       'address': {'house_number': '399', 'road': 'Clayton Road', 'suburb': 'Clayton', 'city': 'Melbourne', 'state': 'Victoria'}}


class Gateway:
    reasoning_model = 'm'

    def __init__(self, reply):
        self.reply = reply

    async def complete(self, messages, **kwargs):
        return self.reply


def run(reply, **kw):
    return asyncio.run(location_web.find_location(place(), Gateway(reply), web=lambda q: SNIPPETS, search=kw.get('search', lambda q: [MAP])))


class LocationWebTests(unittest.TestCase):
    def test_address_found_on_the_web_and_confirmed_on_the_map_becomes_a_verified_coordinate(self):
        result = run('Thinking first...\n{"address": "399 Clayton Rd, Clayton VIC 3168", "source_index": 0, "reason": "Snippet 0."}')
        self.assertEqual(result['status'], 'resolved')
        meta = result['metadata']
        self.assertEqual((meta['location_verified'], meta['location_id']), ('true', 'addr:osm:way:42'))
        self.assertIn('marrybrown.au', meta['location_source'])

    def test_an_address_that_is_not_in_the_cited_snippet_is_rejected_even_if_the_map_knows_it(self):
        result = run('{"address": "12 Other Street, Clayton VIC 3168", "source_index": 0, "reason": "made up"}')
        self.assertEqual(result['status'], 'unverified')
        self.assertNotIn('metadata', result)

    def test_a_map_object_with_a_different_number_road_or_area_is_rejected(self):
        for bad in ({**MAP, 'address': {**MAP['address'], 'house_number': '401'}}, {**MAP, 'address': {**MAP['address'], 'road': 'Dandenong Road'}},
                    {**MAP, 'address': {**MAP['address'], 'suburb': 'Perth', 'city': 'Perth', 'road': 'Clayton Road'}}):
            self.assertEqual(run('{"address": "399 Clayton Rd, Clayton VIC 3168", "source_index": 0, "reason": "x"}', search=lambda q, b=bad: [b])['status'], 'unverified')

    def test_null_answers_bad_citations_and_unparseable_replies_never_produce_a_coordinate(self):
        self.assertEqual(run('{"address": null, "source_index": null, "reason": "no branch address"}')['status'], 'not_found')
        self.assertEqual(run('{"address": "399 Clayton Rd, Clayton", "source_index": 7, "reason": "x"}')['status'], 'unavailable')
        self.assertEqual(run('no json here')['status'], 'unavailable')

    def test_ranges_are_searched_by_their_individual_numbers(self):
        queries = []
        house = {**MAP, 'address': {**MAP['address'], 'house_number': '98', 'road': 'Wellington Road'}}
        place_gyg = Entity('g', 'restaurant', 'food', 'Guzman y Gomez', location_name='Clayton', city='Melbourne', country='Australia')
        found = location_web.verify_on_map('96-98 Wellington Road, Clayton, VIC 3168', place_gyg, search=lambda q: (queries.append(q), [house])[1])
        self.assertIs(found, house)
        self.assertIn('98 Wellington Road', queries[0])
        self.assertTrue(location_web.cited_in_snippet('96-98 Wellington Road, Clayton', 'GYG Clayton 96-98 Wellington Rd Clayton VIC'))


if __name__ == '__main__':
    unittest.main()
