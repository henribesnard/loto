"""Calculs statistiques de base sur les historiques de tirages (stdlib uniquement)."""

import math
from collections import Counter
from itertools import combinations

from .games import Game
from .models import Draw


def frequencies(draws: list[Draw], main: bool = True, window: int | None = None) -> Counter:
    """Fréquence d'apparition de chaque numéro (principaux par défaut)."""
    subset = draws[-window:] if window else draws
    counter: Counter = Counter()
    for draw in subset:
        counter.update(draw.main if main else draw.extras)
    return counter


def weighted_frequencies(draws: list[Draw], decay: float = 0.97, main: bool = True) -> Counter:
    """Fréquences pondérées : les tirages récents comptent plus (decay^(âge))."""
    counter: Counter = Counter()
    n = len(draws)
    for i, draw in enumerate(draws):
        w = decay ** (n - 1 - i)
        counter.update({num: w for num in (draw.main if main else draw.extras)})
    return counter


def gaps(draws: list[Draw], game: Game) -> dict[int, int]:
    """Nombre de tirages écoulés depuis la dernière sortie de chaque numéro principal."""
    last_seen: dict[int, int] = {}
    for i, draw in enumerate(draws):
        for num in draw.main:
            last_seen[num] = i
    n = len(draws)
    return {num: n - 1 - last_seen.get(num, -1) for num in game.main_range}


def pair_counts(draws: list[Draw]) -> Counter:
    """Co-occurrences des paires de numéros principaux."""
    counter: Counter = Counter()
    for draw in draws:
        for pair in combinations(sorted(draw.main), 2):
            counter[frozenset(pair)] += 1
    return counter


def markov_transitions(draws: list[Draw]) -> dict[int, Counter]:
    """Transitions du 1er ordre : pour chaque numéro a, distribution des numéros b
    sortis au tirage suivant."""
    transitions: dict[int, Counter] = {}
    for prev, nxt in zip(draws, draws[1:]):
        for a in prev.main:
            transitions.setdefault(a, Counter()).update(nxt.main)
    return transitions


def _gammq(a: float, x: float) -> float:
    """Fonction gamma incomplète supérieure régularisée Q(a, x) (Numerical Recipes)."""
    if x < 0 or a <= 0:
        raise ValueError("domaine invalide")
    if x == 0:
        return 1.0
    if x < a + 1.0:
        # Série pour P, puis Q = 1 - P.
        ap = a
        summ = 1.0 / a
        delta = summ
        for _ in range(200):
            ap += 1.0
            delta *= x / ap
            summ += delta
            if abs(delta) < abs(summ) * 1e-14:
                break
        p = summ * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return 1.0 - p
    # Fraction continue pour Q directement.
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 200):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi2_uniform(counter: Counter, total_draws: int, k: int) -> tuple[float, float]:
    """Test du chi² d'uniformité : (statistique, p-valeur).

    Hypothèse nulle : chaque numéro sort avec probabilité 1/k.
    """
    expected = total_draws / k
    chi2 = sum((counter.get(i, 0) - expected) ** 2 / expected for i in range(1, k + 1))
    p_value = _gammq((k - 1) / 2.0, chi2 / 2.0)
    return chi2, p_value


def expected_main_matches(game: Game) -> float:
    """Nombre moyen de numéros principaux communs entre deux tirages indépendants."""
    return game.main_count * game.main_count / game.main_max
