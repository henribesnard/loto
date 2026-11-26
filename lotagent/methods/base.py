"""Classe de base d'une méthode de scoring."""

from abc import ABC, abstractmethod

from ..games import Game
from ..models import Draw, Grid


class Method(ABC):
    """Une méthode attribue un score à une grille à partir de l'historique.

    Plus le score est élevé, plus la grille est « préférée » par l'heuristique.
    Un score n'est PAS une probabilité de gain (voir docs/methodes.md).
    """

    name: str = ""
    label: str = ""
    description: str = ""

    def fit(self, draws: list[Draw], game: Game) -> None:
        self._draws = draws
        self._game = game

    @abstractmethod
    def score(self, grid: Grid) -> float:
        """Score brut de la grille (principaux + complémentaires)."""

    def rank_numbers(self) -> list[int] | None:
        """Numéros principaux classés du « préféré » au moins préféré (optionnel)."""
        return None

    def rank_extras(self) -> list[int] | None:
        return None
