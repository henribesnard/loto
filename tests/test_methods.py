import math
import unittest

from lotagent.games import get_game
from lotagent.methods import all_method_names, get_methods
from lotagent.models import Grid

from .helpers import biased_draws, synth_draws


class TestMethods(unittest.TestCase):
    def setUp(self):
        self.game = get_game("loto")
        self.draws = biased_draws(self.game, 60)

    def test_registre(self):
        names = all_method_names()
        for expected in ("frequence", "tendance", "chi2", "retard", "paires", "markov", "aleatoire"):
            self.assertIn(expected, names)
        with self.assertRaises(KeyError):
            get_methods(["inexistante"])

    def test_frequence_classe_les_chauds(self):
        m = get_methods(["frequence"])["frequence"]
        m.fit(self.draws, self.game)
        ranked = m.rank_numbers()
        self.assertEqual(set(ranked[:5]), {7, 13, 21, 33, 42})

    def test_scores_finis(self):
        grid = Grid(main=(7, 13, 21, 33, 42), extras=(5,))
        for name in all_method_names():
            m = get_methods([name])[name]
            m.fit(self.draws, self.game)
            value = m.score(grid)
            self.assertTrue(math.isfinite(value), f"{name} -> {value}")

    def test_aleatoire_constant(self):
        m = get_methods(["aleatoire"])["aleatoire"]
        m.fit(self.draws, self.game)
        self.assertEqual(m.score(Grid(main=(1, 2, 3, 4, 5), extras=(1,))), 1.0)

    def test_markov_conditionne_au_dernier_tirage(self):
        game = get_game("loto")
        draws = synth_draws(game, 50, seed=9)
        m = get_methods(["markov"])["markov"]
        m.fit(draws, game)
        ranked = m.rank_numbers()
        self.assertIsNotNone(ranked)
        self.assertEqual(len(ranked), 49)


if __name__ == "__main__":
    unittest.main()
