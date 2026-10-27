"""Cover photos: only a choice among the images shown is accepted, a doubtful result leaves the icon, and nothing is stored on refusal."""
import asyncio
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from backend.app import covers
from backend.app.cover_service import ensure_cover
from backend.app.domain.models import Entity
from backend.app.repositories.memory import InMemoryLoopRepository


def jpeg(color):
    out = io.BytesIO()
    Image.new('RGB', (640, 480), color).save(out, 'JPEG')
    return out.getvalue()


class Gateway:
    vision_model = 'vision'

    def __init__(self, reply):
        self.reply, self.messages = reply, []

    async def complete(self, messages, **kwargs):
        self.messages.append(messages)
        return self.reply


def candidates():
    return [covers.Candidate(f'https://img.example/{i}.jpg', f'https://img.example/t{i}.jpg', f'https://site.example/{i}', f'Photo {i}') for i in range(3)]


class CoverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        patcher = patch.object(covers, 'COVERS', Path(self.directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.directory.cleanup)
        self.entity = Entity('e1', 'place', 'food', "Elmo's Hamburger Restaurant", location_name='Fitzroy North', city='Melbourne')
        self.repository = InMemoryLoopRepository()
        self.repository.save_entity(self.entity)

    def run_case(self, reply, **kw):
        gateway = Gateway(reply)
        result = asyncio.run(ensure_cover(self.repository, self.entity, 'Interested in Elmo\'s.', gateway, search=lambda q: candidates(), fetch=lambda url: jpeg('red'), **kw))
        return result, gateway

    def test_a_chosen_image_is_stored_with_its_source_and_offered_to_home(self):
        result, gateway = self.run_case('{"choice": 1, "reason": "Storefront."}')
        self.assertEqual(result['status'], 'chosen')
        saved = self.repository.entities['e1']
        row = covers.view_for(saved)
        self.assertTrue(row['catalogue_image_verified'])
        self.assertEqual(row['catalogue_image_source'], 'https://site.example/1')
        self.assertTrue((covers.COVERS / row['catalogue_image_url'].split('/')[-1]).is_file())
        # the model saw three candidate images and the item's name, and never the person's own screenshot
        images = [p for p in gateway.messages[0][0]['content'] if p['type'] == 'image_url']
        self.assertEqual(len(images), 3)

    def test_refusal_or_a_choice_it_was_not_shown_leaves_no_cover(self):
        for reply in ('{"choice": null, "reason": "None show the restaurant."}', '{"choice": 9, "reason": "x"}', 'not json'):
            result, _ = self.run_case(reply)
            self.assertIn(result['status'], ('refused', 'failed'))
            self.assertIsNone(covers.view_for(self.repository.entities['e1']))
            self.assertFalse(list(covers.COVERS.glob('*.jpg')))

    def test_no_provider_means_no_search_and_no_cover(self):
        with patch.dict('os.environ', {}, clear=True):
            result = asyncio.run(ensure_cover(self.repository, self.entity, 'x', Gateway('{}')))
        self.assertEqual(result['status'], 'no_provider')

    def test_dry_run_chooses_but_writes_nothing(self):
        result, _ = self.run_case('{"choice": 0, "reason": "ok"}', apply=False)
        self.assertEqual((result['status'], result['applied']), ('chosen', False))
        self.assertIsNone(covers.view_for(self.repository.entities['e1']))

    def test_unsafe_or_tiny_images_are_rejected(self):
        self.assertIsNone(covers.fetch('http://insecure.example/a.jpg'))
        self.assertIsNone(covers.normalise(b'not an image', 600))
        tiny = io.BytesIO()
        Image.new('RGB', (50, 50)).save(tiny, 'JPEG')
        self.assertIsNone(covers.normalise(tiny.getvalue(), 600))
        self.assertEqual(covers.subject_query(self.entity), "Elmo's Hamburger Restaurant Fitzroy North Melbourne")


if __name__ == '__main__':
    unittest.main()
