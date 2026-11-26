import unittest

from lotagent.fetcher import extract_zip_links
from lotagent.games import get_game
from lotagent.parsers import parse_zip_bytes

from .helpers import FDJ_LOTO_CSV, make_zip_bytes

HTML_PAGE = """
<html><body>
  <a href="/generated/game/loto/loto_2026.zip">De novembre 2019 à novembre 2026</a>
  <a href="https://cdn-media.fdj.fr/generated/game/loto/loto_2017.zip">De mars 2017 à février 2019</a>
  <a href="/generated/game/loto/loto_2026.zip">doublon</a>
  <a href="https://www.sto.api.fdj.fr/anonymous/service-draw-info/v3/documentations/1a2b3c4d-9876-4562-b3fc-2c963f66afa5"
     aria-label="Historique EuroDreams de novembre 2023 à novembre 2026">Télécharger - zip</a>
  <a href="/jeux-de-tirage/loto/resultats">pas une archive</a>
  <a href="/generated/game/loto/loto_1976.zip?dl=1">avec query</a>
</body></html>
"""


class TestFetcher(unittest.TestCase):
    def test_extract_zip_links(self):
        links = extract_zip_links(HTML_PAGE, "https://www.fdj.fr/jeux-de-tirage/loto/historique")
        self.assertEqual(len(links), 4)
        self.assertIn("https://www.fdj.fr/generated/game/loto/loto_2026.zip", links)
        self.assertIn("https://cdn-media.fdj.fr/generated/game/loto/loto_2017.zip", links)
        self.assertIn("https://www.fdj.fr/generated/game/loto/loto_1976.zip?dl=1", links)
        self.assertIn(
            "https://www.sto.api.fdj.fr/anonymous/service-draw-info/v3/documentations/"
            "1a2b3c4d-9876-4562-b3fc-2c963f66afa5",
            links,
        )
        for link in links:
            self.assertTrue(".zip" in link.lower() or "/documentations/" in link)

    def test_parse_zip_bytes(self):
        game = get_game("loto")
        draws, rejected = parse_zip_bytes(make_zip_bytes("loto.csv", FDJ_LOTO_CSV), game)
        self.assertEqual(len(draws), 3)
        self.assertEqual(rejected, 0)


if __name__ == "__main__":
    unittest.main()
