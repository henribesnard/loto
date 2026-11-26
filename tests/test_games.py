import unittest
from math import comb

from lotagent.games import GAMES, get_game


class TestGames(unittest.TestCase):
    def test_combinaisons_rang1(self):
        self.assertEqual(GAMES["loto"].combinaisons, comb(49, 5) * 10)
        self.assertEqual(GAMES["loto"].combinaisons, 19_068_840)
        self.assertEqual(GAMES["euromillions"].combinaisons, comb(50, 5) * comb(12, 2))
        self.assertEqual(GAMES["euromillions"].combinaisons, 139_838_160)
        self.assertEqual(GAMES["eurodreams"].combinaisons, comb(40, 6) * 5)
        self.assertEqual(GAMES["eurodreams"].combinaisons, 19_191_900)

    def test_aliases(self):
        self.assertEqual(get_game("LOTO").key, "loto")
        self.assertEqual(get_game("EM").key, "euromillions")
        self.assertEqual(get_game("euro-dreams").key, "eurodreams")

    def test_inconnu(self):
        with self.assertRaises(KeyError):
            get_game("keno")


if __name__ == "__main__":
    unittest.main()
