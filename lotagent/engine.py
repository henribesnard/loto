"""Moteur de proposition de grilles : génération de candidats, scoring multi-méthodes,
combinaison pondérée et sélection de grilles distinctes."""

import random
from itertools import combinations

from . import stats as st
from .games import Game
from .methods import get_methods
from .methods.base import Method
from .models import Draw, Grid

DEFAULT_POOL_SIZE = 2000


class Engine:
    """Combine plusieurs méthodes pour proposer des grilles."""

    def __init__(
        self,
        game: Game,
        method_names: list[str] | None = None,
        weights: dict[str, float] | None = None,
        seed: int | None = None,
    ):
        self.game = game
        self.methods: dict[str, Method] = get_methods(method_names)
        self.weights = weights or {}
        self.rng = random.Random(seed)
        self._draws: list[Draw] = []

    def fit(self, draws: list[Draw]) -> "Engine":
        if not draws:
            raise ValueError("L'historique est vide : aucun tirage à analyser.")
        self._draws = list(draws)
        for method in self.methods.values():
            method.fit(self._draws, self.game)
        return self

    def _random_grid(self) -> Grid:
        main = tuple(sorted(self.rng.sample(list(self.game.main_range), self.game.main_count)))
        extras = tuple(sorted(self.rng.sample(list(self.game.extra_range), self.game.extra_count)))
        return Grid(main=main, extras=extras)

    def _method_grid(self, method: Method) -> Grid | None:
        ranked = method.rank_numbers()
        if ranked:
            main = tuple(sorted(ranked[: self.game.main_count]))
        else:
            return None
        ranked_extras = method.rank_extras()
        if ranked_extras:
            extras = tuple(sorted(ranked_extras[: self.game.extra_count]))
        else:
            freq = st.frequencies(self._draws, main=False)
            extras = tuple(
                sorted(
                    sorted(self.game.extra_range, key=lambda n: (-freq.get(n, 0), n))[
                        : self.game.extra_count
                    ]
                )
            )
        return Grid(main=main, extras=extras)

    def _candidate_pool(self, pool_size: int) -> list[Grid]:
        pool: dict[tuple, Grid] = {}
        for method in self.methods.values():
            grid = self._method_grid(method)
            if grid is not None and grid.is_valid(self.game):
                pool[(grid.main, grid.extras)] = grid
        while len(pool) < pool_size:
            grid = self._random_grid()
            pool.setdefault((grid.main, grid.extras), grid)
        return list(pool.values())

    def _score_pool(self, pool: list[Grid]) -> list[Grid]:
        raw: dict[str, list[float]] = {name: [] for name in self.methods}
        for grid in pool:
            for name, method in self.methods.items():
                raw[name].append(method.score(grid))

        normalized: dict[str, list[float]] = {}
        for name, values in raw.items():
            lo, hi = min(values), max(values)
            if hi - lo < 1e-12:
                normalized[name] = [0.0] * len(values)
            else:
                normalized[name] = [(v - lo) / (hi - lo) for v in values]

        scored: list[Grid] = []
        for i, grid in enumerate(pool):
            grid.scores = {name: normalized[name][i] for name in self.methods}
            total = 0.0
            weight_sum = 0.0
            for name, value in grid.scores.items():
                w = self.weights.get(name, 1.0)
                total += w * value
                weight_sum += w
            grid.total = total / weight_sum if weight_sum else 0.0
            scored.append(grid)
        scored.sort(key=lambda g: (-g.total, g.main, g.extras))
        return scored

    def propose(self, n_grids: int = 5, pool_size: int = DEFAULT_POOL_SIZE,
                max_overlap: int | None = None) -> list[Grid]:
        """Propose ``n_grids`` grilles valides, les plus distinctes possibles."""
        if not self._draws:
            raise ValueError("fit() doit être appelé avant propose().")
        if max_overlap is None:
            max_overlap = max(1, self.game.main_count // 3)

        scored = self._score_pool(self._candidate_pool(pool_size))

        selected: list[Grid] = []
        for grid in scored:
            if all(grid.overlap(other) <= max_overlap for other in selected):
                selected.append(grid)
            if len(selected) == n_grids:
                return selected
        # Assouplissement si le pool ne permet pas assez de grilles distinctes.
        for grid in scored:
            if grid not in selected:
                selected.append(grid)
            if len(selected) == n_grids:
                break
        return selected[:n_grids]


def expected_random_score_note(game: Game) -> str:
    return (
        f"Espérance théorique d'une grille aléatoire : "
        f"{st.expected_main_matches(game):.3f} bon numéro principal sur {game.main_count}"
    )


def grid_pairs_diversity(grids: list[Grid]) -> float:
    """Diversité moyenne (1 - recouvrement moyen des paires) entre grilles proposées."""
    if len(grids) < 2:
        return 1.0
    total = 0.0
    count = 0
    for a, b in combinations(grids, 2):
        overlap = a.overlap(b)
        total += 1.0 - overlap / max(1, len(a.main))
        count += 1
    return total / count
