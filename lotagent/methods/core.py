"""Implémentations concrètes des méthodes statistiques.

Toutes ces méthodes décrivent l'historique ; aucune n'a de pouvoir prédictif
sur des tirages indépendants et uniformes (voir docs/methodes.md).
"""

import math
from collections import Counter

from .. import stats as st
from ..models import Grid
from .base import Method


class FrequencyMethod(Method):
    """Numéros « chauds » : fréquences observées sur l'historique."""

    name = "frequence"
    label = "Fréquences (numéros chauds)"
    description = "Somme des fréquences observées des numéros de la grille."

    def fit(self, draws, game):
        super().fit(draws, game)
        self._main = st.frequencies(draws, main=True)
        self._extra = st.frequencies(draws, main=False)

    def score(self, grid: Grid) -> float:
        return sum(self._main.get(n, 0) for n in grid.main) + sum(
            self._extra.get(n, 0) for n in grid.extras
        )

    def rank_numbers(self):
        return sorted(self._game.main_range, key=lambda n: (-self._main.get(n, 0), n))

    def rank_extras(self):
        return sorted(self._game.extra_range, key=lambda n: (-self._extra.get(n, 0), n))


class TrendMethod(Method):
    """Tendance récente : fréquences pondérées (les derniers tirages comptent plus)."""

    name = "tendance"
    label = "Tendance récente (pondération temporelle)"
    description = "Fréquences avec décroissance exponentielle selon l'ancienneté du tirage."

    def __init__(self, decay: float = 0.97):
        self.decay = decay

    def fit(self, draws, game):
        super().fit(draws, game)
        self._main = st.weighted_frequencies(draws, decay=self.decay, main=True)
        self._extra = st.weighted_frequencies(draws, decay=self.decay, main=False)

    def score(self, grid: Grid) -> float:
        return sum(self._main.get(n, 0.0) for n in grid.main) + sum(
            self._extra.get(n, 0.0) for n in grid.extras
        )

    def rank_numbers(self):
        return sorted(self._game.main_range, key=lambda n: (-self._main.get(n, 0.0), n))

    def rank_extras(self):
        return sorted(self._game.extra_range, key=lambda n: (-self._extra.get(n, 0.0), n))


class Chi2HotMethod(Method):
    """Écarts au chi² : numéros dont la fréquence observed s'écarte le plus (à la hausse)
    de la fréquence théorique uniforme."""

    name = "chi2"
    label = "Écart au chi² (sur-représentation)"
    description = "Somme des écarts positifs (observé - attendu) des numéros de la grille."

    def fit(self, draws, game):
        super().fit(draws, game)
        counts = st.frequencies(draws, main=True)
        expected = len(draws) * game.main_count / game.main_max
        self._dev = {n: max(0.0, counts.get(n, 0) - expected) for n in game.main_range}
        self._extra_counts = st.frequencies(draws, main=False)
        exp_e = len(draws) * game.extra_count / game.extra_max
        self._dev_e = {n: max(0.0, self._extra_counts.get(n, 0) - exp_e) for n in game.extra_range}

    def score(self, grid: Grid) -> float:
        return sum(self._dev.get(n, 0.0) for n in grid.main) + sum(
            self._dev_e.get(n, 0.0) for n in grid.extras
        )

    def rank_numbers(self):
        return sorted(self._game.main_range, key=lambda n: (-self._dev.get(n, 0.0), n))


class ColdMethod(Method):
    """Numéros « froids » / en retard (raisonnement du « numéro dû »).

    Attention : c'est exactement l'illusion du « gambler's fallacy » ; conservé
    ici comme contre-exemple documenté, désactivé par défaut dans les presets.
    """

    name = "retard"
    label = "Numéros en retard (gambler's fallacy)"
    description = "Somme des écarts (en nombre de tirages) depuis la dernière sortie."

    def fit(self, draws, game):
        super().fit(draws, game)
        self._gaps = st.gaps(draws, game)

    def score(self, grid: Grid) -> float:
        return sum(self._gaps.get(n, 0) for n in grid.main)

    def rank_numbers(self):
        return sorted(self._game.main_range, key=lambda n: (-self._gaps.get(n, 0), n))


class PairMethod(Method):
    """Paires fréquentes : co-occurrences observées des paires de numéros."""

    name = "paires"
    label = "Co-occurrences de paires"
    description = "Somme des log(1 + occurrences) des paires présentes dans la grille."

    def fit(self, draws, game):
        super().fit(draws, game)
        self._pairs = st.pair_counts(draws)

    def score(self, grid: Grid) -> float:
        from itertools import combinations

        return sum(
            math.log1p(self._pairs.get(frozenset(p), 0))
            for p in combinations(sorted(grid.main), 2)
        )

    def rank_numbers(self):
        last = self._draws[-1].main if self._draws else ()
        if not last:
            return None
        affinity = Counter()
        for a in last:
            for b in self._game.main_range:
                if b != a:
                    affinity[b] += self._pairs.get(frozenset((a, b)), 0)
        return sorted(self._game.main_range, key=lambda n: (-affinity.get(n, 0), n))


class MarkovMethod(Method):
    """Chaîne de Markov du 1er ordre entraînée sur les transitions entre tirages
    consécutifs, conditionnée par le dernier tirage connu."""

    name = "markov"
    label = "Chaîne de Markov (1er ordre)"
    description = "log-vraisemblance des numéros de la grille sachant le dernier tirage (lissage de Laplace)."

    def fit(self, draws, game):
        super().fit(draws, game)
        self._trans = st.markov_transitions(draws)
        self._k = game.main_max

    def score(self, grid: Grid) -> float:
        last = self._draws[-1].main if self._draws else ()
        if not last:
            return 0.0
        total = 0.0
        for b in grid.main:
            num = sum(self._trans.get(a, Counter()).get(b, 0) for a in last)
            den = sum(sum(self._trans.get(a, Counter()).values()) for a in last)
            total += math.log((num + 1.0) / (den + self._k))
        return total

    def rank_numbers(self):
        last = self._draws[-1].main if self._draws else ()
        if not last:
            return None
        probs = {}
        for b in self._game.main_range:
            num = sum(self._trans.get(a, Counter()).get(b, 0) for a in last)
            den = sum(sum(self._trans.get(a, Counter()).values()) for a in last)
            probs[b] = (num + 1.0) / (den + self._k)
        return sorted(self._game.main_range, key=lambda n: (-probs[n], n))


class UniformMethod(Method):
    """Témoin aléatoire : score constant (aucune information historique)."""

    name = "aleatoire"
    label = "Témoin aléatoire"
    description = "Score constant : sert de référence (baseline) dans les comparaisons."

    def score(self, grid: Grid) -> float:
        return 1.0
