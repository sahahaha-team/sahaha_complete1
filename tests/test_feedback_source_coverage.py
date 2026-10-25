import unittest
from pathlib import Path
from scripts.ingest_official_materials import official_page_targets
from chatbot import verified_facts


class FeedbackSourceCoverageTests(unittest.TestCase):
    def test_every_verified_table_source_is_in_the_periodic_refresh_targets(self):
        urls = {url for _, url in official_page_targets(Path('not-a-private-workbook'))}
        for name in ('_BIRTH_URL', '_HEALTH_FEE_URL', '_KIOSK_URL', '_PASSPORT_URL', '_WASTE_URL', '_RECYCLING_URL'):
            with self.subTest(name=name):
                self.assertIn(getattr(verified_facts, name), urls)


if __name__ == '__main__':
    unittest.main()
