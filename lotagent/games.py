"""Définitions des jeux de tirage supportés (règles officielles FDJ)."""

from dataclasses import dataclass
from math import comb


@dataclass(frozen=True)
class Game:
    key: str
    nom: str
    main_count: int
    main_max: int
    extra_count: int
    extra_max: int
    extra_label: str
    archive_url: str
    note: str = ""

    @property
    def main_range(self) -> range:
        return range(1, self.main_max + 1)

    @property
    def extra_range(self) -> range:
        return range(1, self.extra_max + 1)

    @property
    def combinaisons(self) -> int:
        """Nombre total de grilles valides (dénominateur des probabilités)."""
        return comb(self.main_max, self.main_count) * comb(self.extra_max, self.extra_count)


GAMES: dict[str, Game] = {
    "loto": Game(
        key="loto",
        nom="LOTO",
        main_count=5,
        main_max=49,
        extra_count=1,
        extra_max=10,
        extra_label="Chance",
        archive_url="https://www.fdj.fr/jeux-de-tirage/loto/historique",
        note="Format 5 boules + 1 numéro Chance en vigueur depuis le 21/10/2019 ; "
        "les tirages antérieurs (6 boules) sont ignorés pour ce jeu.",
    ),
    "euromillions": Game(
        key="euromillions",
        nom="EuroMillions - My Million",
        main_count=5,
        main_max=50,
        extra_count=2,
        extra_max=12,
        extra_label="Étoiles",
        archive_url="https://www.fdj.fr/jeux-de-tirage/euromillions-my-million/historique",
    ),
    "eurodreams": Game(
        key="eurodreams",
        nom="EuroDreams",
        main_count=6,
        main_max=40,
        extra_count=1,
        extra_max=5,
        extra_label="N° Dream",
        archive_url="https://www.fdj.fr/jeux-de-tirage/eurodreams/historique",
        note="Jeu lancé en novembre 2023.",
    ),
}

_ALIASES = {
    "loto": "loto",
    "lotto": "loto",
    "euromillions": "euromillions",
    "euromillion": "euromillions",
    "em": "euromillions",
    "euro-millions": "euromillions",
    "eurodreams": "eurodreams",
    "ed": "eurodreams",
    "euro-dreams": "eurodreams",
}


def get_game(key: str) -> Game:
    """Retourne le jeu à partir de sa clé ou d'un alias, insensible à la casse."""
    normalized = key.strip().lower()
    if normalized not in _ALIASES:
        raise KeyError(
            f"Jeu inconnu : {key!r}. Jeux supportés : {', '.join(sorted(GAMES))}"
        )
    return GAMES[_ALIASES[normalized]]
