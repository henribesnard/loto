import unittest

from lotagent.backtest import run_backtest
from lotagent.games import get_game

from .helpers import synth_draws


class TestBacktest(unittest.TestCase):
    def test_backtest_loto_synthetique(self):
        game = get_game("loto")
        draws = synth_draws(game, 360, seed=11)
        report = run_backtest(game, draws, method_names=["frequence", "markov", "aleatoire"],
                              depuis=300, pool_size=100, random_baselines=50)
        self.assertEqual(report["n_eval"], 60)
        self.assertAlmostEqual(report["attendu_aleatoire"], 25 / 49, places=6)
        self.assertAlmostEqual(report["baseline_aleatoire"], 25 / 49, delta=0.15)
        for name in ("frequence", "markov", "aleatoire"):
            res = report["methodes"][name]
            self.assertGreaterEqual(res["moyenne_bons_numeros"], 0)
            self.assertLessEqual(res["moyenne_bons_numeros"], game.main_count)

    def test_historique_trop_court(self):
        game = get_game("eurodreams")
        draws = synth_draws(game, 50, seed=1)
        with self.assertRaises(ValueError):
            run_backtest(game, draws, depuis=300)


if __name__ == "__main__":
    unittest.main()
