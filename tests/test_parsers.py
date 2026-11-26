import tempfile
import unittest
from datetime import date
from pathlib import Path

from lotagent.games import get_game
from lotagent.parsers import load_draws, parse_csv_text, parse_zip_bytes, write_canonical_csv

from .helpers import (
    FDJ_EURODREAMS_CSV,
    FDJ_EUROMILLIONS_CSV,
    FDJ_LOTO_ANCIEN_FORMAT,
    FDJ_LOTO_CSV,
    FDJ_LOTO_VIRGULE,
    make_zip_bytes,
    synth_draws,
)


class TestParsers(unittest.TestCase):
    def test_loto_fdj(self):
        game = get_game("loto")
        draws, rejected = parse_csv_text(FDJ_LOTO_CSV, game)
        self.assertEqual(rejected, 0)
        self.assertEqual(len(draws), 3)
        self.assertEqual(draws[0].date, date(2026, 1, 3))
        self.assertEqual(draws[0].main, (5, 12, 23, 34, 47))
        self.assertEqual(draws[0].extras, (7,))

    def test_loto_ancien_format_rejete(self):
        game = get_game("loto")
        draws, rejected = parse_csv_text(FDJ_LOTO_ANCIEN_FORMAT, game)
        self.assertEqual(len(draws), 0)
        self.assertEqual(rejected, 1)

    def test_euromillions_fdj(self):
        game = get_game("euromillions")
        draws, rejected = parse_csv_text(FDJ_EUROMILLIONS_CSV, game)
        self.assertEqual(rejected, 0)
        self.assertEqual(draws[0].main, (3, 17, 28, 35, 49))
        self.assertEqual(draws[0].extras, (2, 11))

    def test_eurodreams_fdj(self):
        game = get_game("eurodreams")
        draws, rejected = parse_csv_text(FDJ_EURODREAMS_CSV, game)
        self.assertEqual(rejected, 0)
        self.assertEqual(draws[0].main, (2, 11, 14, 17, 18, 37))
        self.assertEqual(draws[0].extras, (2,))

    def test_virgule_et_accents(self):
        game = get_game("loto")
        draws, rejected = parse_csv_text(FDJ_LOTO_VIRGULE, game)
        self.assertEqual(rejected, 0)
        self.assertEqual(draws[0].extras, (7,))

    def test_zip(self):
        game = get_game("loto")
        draws, rejected = parse_zip_bytes(make_zip_bytes("loto.csv", FDJ_LOTO_CSV), game)
        self.assertEqual(len(draws), 3)
        self.assertEqual(rejected, 0)

    def test_canonique_aller_retour(self):
        game = get_game("eurodreams")
        synth = synth_draws(game, 50, seed=3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eurodreams.csv"
            write_canonical_csv(synth, game, path)
            loaded = load_draws(path, game)
        self.assertEqual([d.main for d in loaded], [d.main for d in synth])
        self.assertEqual([d.extras for d in loaded], [d.extras for d in synth])


if __name__ == "__main__":
    unittest.main()
