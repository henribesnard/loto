import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lotagent.games import get_game

from .helpers import write_synth_csv

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "lotagent", *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


class TestCli(unittest.TestCase):
    def test_jeux(self):
        proc = run_cli("jeux")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("loto", proc.stdout)
        self.assertIn("euromillions", proc.stdout)
        self.assertIn("eurodreams", proc.stdout)

    def test_proposer_hors_ligne(self):
        game = get_game("loto")
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "loto.csv"
            write_synth_csv(game, 300, csv_path, seed=4)
            proc = run_cli("proposer", "--jeu", "loto", "--grilles", "3",
                           "--csv", str(csv_path), "--seed", "42")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Grille 1", proc.stdout)
        self.assertIn("Grille 3", proc.stdout)
        self.assertIn("Chance", proc.stdout)
        self.assertIn("aucune valeur prédictive", proc.stdout)

    def test_stats_hors_ligne(self):
        game = get_game("eurodreams")
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "ed.csv"
            write_synth_csv(game, 120, csv_path, seed=6)
            proc = run_cli("stats", "--jeu", "eurodreams", "--csv", str(csv_path), "--derniers", "50")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("chi²", proc.stdout)
        self.assertIn("N° Dream", proc.stdout)

    def test_backtest_hors_ligne(self):
        game = get_game("euromillions")
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "em.csv"
            write_synth_csv(game, 340, csv_path, seed=8)
            proc = run_cli("backtest", "--jeu", "euromillions", "--csv", str(csv_path),
                           "--depuis", "300", "--methodes", "frequence,aleatoire")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("baseline", proc.stdout)
        self.assertIn("frequence", proc.stdout)

    def test_jeu_inconnu(self):
        proc = run_cli("proposer", "--jeu", "keno", "--csv", "/dev/null")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
