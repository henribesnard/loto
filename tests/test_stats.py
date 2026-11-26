import math
import unittest
from collections import Counter
from datetime import date

from lotagent import stats as st
from lotagent.games import get_game
from lotagent.models import Draw

from .helpers import synth_draws


class TestStats(unittest.TestCase):
    def test_frequencies(self):
        game = get_game("loto")
        draws = synth_draws(game, 100, seed=1)
        freq = st.frequencies(draws, main=True)
        self.assertEqual(sum(freq.values()), 100 * game.main_count)
        self.assertEqual(set(freq), set(range(1, 50)) & set(freq))

    def test_gaps(self):
        game = get_game("loto")
        draws = [
            Draw(date=date(2026, 1, 1), main=(1, 2, 3, 4, 5), extras=(1,)),
            Draw(date=date(2026, 1, 4), main=(1, 6, 7, 8, 9), extras=(2,)),
        ]
        g = st.gaps(draws, game)
        self.assertEqual(g[1], 0)
        self.assertEqual(g[2], 1)
        self.assertEqual(g[49], 2)  # jamais sorti sur la fenêtre de 2 tirages

    def test_chi2_uniforme(self):
        chi2, p = st.chi2_uniform(Counter({i: 10 for i in range(1, 50)}), total_draws=490, k=49)
        self.assertAlmostEqual(chi2, 0.0, places=6)
        self.assertAlmostEqual(p, 1.0, places=6)

    def test_chi2_biaise(self):
        counts = Counter({1: 490})
        chi2, p = st.chi2_uniform(counts, total_draws=490, k=49)
        self.assertLess(p, 1e-10)

    def test_gammq_racine(self):
        # Q(1/2, x) = erfc(sqrt(x))
        for x in (0.5, 1.0, 3.7):
            self.assertAlmostEqual(st._gammq(0.5, x), math.erfc(math.sqrt(x)), places=10)

    def test_markov(self):
        game = get_game("loto")
        draws = [
            Draw(date=date(2026, 1, 1), main=(1, 2, 3, 4, 5), extras=(1,)),
            Draw(date=date(2026, 1, 4), main=(1, 6, 7, 8, 9), extras=(2,)),
        ]
        trans = st.markov_transitions(draws)
        self.assertEqual(trans[1][1], 1)
        self.assertEqual(sum(trans[1].values()), 5)

    def test_expected_matches(self):
        game = get_game("loto")
        self.assertAlmostEqual(st.expected_main_matches(game), 25 / 49)


if __name__ == "__main__":
    unittest.main()
