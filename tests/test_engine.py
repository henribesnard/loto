import unittest

from lotagent.engine import Engine
from lotagent.games import get_game

from .helpers import biased_draws, synth_draws


class TestEngine(unittest.TestCase):
    def setUp(self):
        self.game = get_game("loto")
        self.draws = synth_draws(self.game, 300, seed=5)

    def test_propose_grilles_valides_et_distinctes(self):
        engine = Engine(self.game, method_names=["frequence", "markov", "paires"], seed=42)
        engine.fit(self.draws)
        grids = engine.propose(5, pool_size=1500)
        self.assertEqual(len(grids), 5)
        seen = set()
        for grid in grids:
            self.assertTrue(grid.is_valid(self.game))
            key = (grid.main, grid.extras)
            self.assertNotIn(key, seen)
            seen.add(key)
        for i, a in enumerate(grids):
            for b in grids[i + 1:]:
                self.assertLessEqual(a.overlap(b), 1)

    def test_reproductibilite_avec_graine(self):
        g1 = Engine(self.game, seed=7).fit(self.draws).propose(3)
        g2 = Engine(self.game, seed=7).fit(self.draws).propose(3)
        self.assertEqual([g.main for g in g1], [g.main for g in g2])

    def test_frequence_seule_propose_les_plus_frequents(self):
        biased = biased_draws(self.game, 80)
        engine = Engine(self.game, method_names=["frequence"], seed=1)
        engine.fit(biased)
        grid = engine.propose(1)[0]
        self.assertEqual(set(grid.main), {7, 13, 21, 33, 42})

    def test_jeux_differents(self):
        for key in ("euromillions", "eurodreams"):
            game = get_game(key)
            draws = synth_draws(game, 200, seed=2)
            engine = Engine(game, seed=3).fit(draws)
            grids = engine.propose(4, pool_size=800)
            self.assertEqual(len(grids), 4)
            for grid in grids:
                self.assertTrue(grid.is_valid(game))

    def test_fit_obligatoire(self):
        engine = Engine(self.game, seed=1)
        with self.assertRaises(ValueError):
            engine.propose(1)


if __name__ == "__main__":
    unittest.main()
