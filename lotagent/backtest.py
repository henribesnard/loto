"""Backtest walk-forward : évalue chaque méthode sur les tirages passés.

Pour chaque tirage t (à partir d'un point de départ), la méthode est entraînée
uniquement sur les tirages < t, puis on compte combien de numéros de la grille
proposée correspondent au tirage réel. On compare à une baseline aléatoire.

Sur des tirages équitables, aucune méthode ne dépasse la baseline en espérance :
ce module sert à le démontrer et à ne retenir que les méthodes les moins
mauvaises relativement (voir docs/methodes.md).
"""

import random

from . import stats as st
from .engine import Engine
from .games import Game
from .methods import get_methods
from .models import Draw


def run_backtest(
    game: Game,
    draws: list[Draw],
    method_names: list[str] | None = None,
    depuis: int = 300,
    pool_size: int = 300,
    seed: int = 42,
    random_baselines: int = 200,
) -> dict:
    """Retourne un rapport : par méthode, nombre moyen de bons numéros principaux."""
    if len(draws) <= depuis + 1:
        raise ValueError(
            f"Historique trop court pour un backtest ( {len(draws)} tirages, il en faut > {depuis + 1} )."
        )
    methods = get_methods(method_names)
    rng = random.Random(seed)

    matches: dict[str, list[int]] = {name: [] for name in methods}
    baseline: list[float] = []
    n_eval = 0

    for t in range(depuis, len(draws)):
        history = draws[:t]
        target = draws[t]
        for name, proto in methods.items():
            engine = Engine(game, method_names=[name], seed=seed)
            engine.fit(history)
            grid = engine.propose(1, pool_size=pool_size)[0]
            matches[name].append(len(set(grid.main) & set(target.main)))
        # Baseline aléatoire : grilles tirées au sort sur la même fenêtre.
        rand_matches = []
        for _ in range(random_baselines):
            main = rng.sample(list(game.main_range), game.main_count)
            rand_matches.append(len(set(main) & set(target.main)))
        baseline.append(sum(rand_matches) / len(rand_matches))
        n_eval += 1

    report = {
        "jeu": game.key,
        "n_eval": n_eval,
        "fenetre": f"tirages {depuis + 1} à {len(draws)}",
        "attendu_aleatoire": st.expected_main_matches(game),
        "baseline_aleatoire": sum(baseline) / len(baseline),
        "methodes": {
            name: {
                "moyenne_bons_numeros": sum(v) / len(v),
                "min": min(v),
                "max": max(v),
            }
            for name, v in matches.items()
        },
    }
    return report
