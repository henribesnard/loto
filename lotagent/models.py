"""Modèles de données : tirages historiques et grilles proposées."""

from dataclasses import dataclass, field
from datetime import date

from .games import Game


@dataclass(frozen=True)
class Draw:
    """Un tirage historique : numéros principaux + numéros complémentaires."""

    date: date
    main: tuple[int, ...]
    extras: tuple[int, ...]

    def is_valid(self, game: Game) -> bool:
        return (
            len(self.main) == game.main_count
            and len(self.extras) == game.extra_count
            and len(set(self.main)) == len(self.main)
            and len(set(self.extras)) == len(self.extras)
            and all(n in game.main_range for n in self.main)
            and all(n in game.extra_range for n in self.extras)
        )


@dataclass
class Grid:
    """Une grille proposée, avec les scores attribués par chaque méthode."""

    main: tuple[int, ...]
    extras: tuple[int, ...]
    scores: dict[str, float] = field(default_factory=dict)
    total: float = 0.0

    def is_valid(self, game: Game) -> bool:
        return (
            len(self.main) == game.main_count
            and len(self.extras) == game.extra_count
            and len(set(self.main)) == len(self.main)
            and len(set(self.extras)) == len(self.extras)
            and all(n in game.main_range for n in self.main)
            and all(n in game.extra_range for n in self.extras)
        )

    def overlap(self, other: "Grid") -> int:
        """Nombre de numéros principaux communs avec une autre grille."""
        return len(set(self.main) & set(other.main))

    def format(self, game: Game) -> str:
        main = " - ".join(f"{n:02d}" for n in sorted(self.main))
        extras = " - ".join(str(n) for n in sorted(self.extras))
        return f"{main}  + {game.extra_label} {extras}"
