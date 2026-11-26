"""Générateurs de données synthétiques et fixtures au format FDJ pour les tests."""

import io
import random
import zipfile
from datetime import date, timedelta

from lotagent.games import Game
from lotagent.models import Draw
from lotagent.parsers import write_canonical_csv


def synth_draws(game: Game, n: int, seed: int = 1, start: date = date(2024, 1, 1)) -> list[Draw]:
    rng = random.Random(seed)
    draws: list[Draw] = []
    d = start
    for _ in range(n):
        main = tuple(sorted(rng.sample(list(game.main_range), game.main_count)))
        extras = tuple(sorted(rng.sample(list(game.extra_range), game.extra_count)))
        draws.append(Draw(date=d, main=main, extras=extras))
        d += timedelta(days=3)
    return draws


def biased_draws(game: Game, n: int, hot: tuple[int, ...] = (7, 13, 21, 33, 42)) -> list[Draw]:
    """Tirages biaisés : les numéros `hot` sortent à chaque tirage (main_count == len(hot))."""
    rng = random.Random(7)
    draws = []
    d = date(2024, 1, 1)
    for _ in range(n):
        main = tuple(sorted(hot[: game.main_count]))
        extras = tuple(sorted(rng.sample(list(game.extra_range), game.extra_count)))
        draws.append(Draw(date=d, main=main, extras=extras))
        d += timedelta(days=3)
    return draws


FDJ_LOTO_CSV = """date;jour;numero_tirage;boule_1;boule_2;boule_3;boule_4;boule_5;numero_chance;code_loto;nb_gagnants_rang_1
03/01/2026;lundi;26001;5;12;23;34;47;7;AB12CD34;2
05/01/2026;mercredi;26002;1;9;18;27;40;3;ZZ99YY88;0
07/01/2026;samedi;26003;12;15;22;38;45;10;QQ11WW22;1
"""

FDJ_LOTO_ANCIEN_FORMAT = """date;boule_1;boule_2;boule_3;boule_4;boule_5;boule_6;complementaire
10/05/2008;4;11;19;28;36;44;2
"""

FDJ_EUROMILLIONS_CSV = """date;numero_tirage;boule_1;boule_2;boule_3;boule_4;boule_5;etoile_1;etoile_2;my_million
07/01/2026;26001;3;17;28;35;49;2;11;XY123456
"""

FDJ_EURODREAMS_CSV = """date;numero_tirage;boule_1;boule_2;boule_3;boule_4;boule_5;boule_6;numero_dream
04/11/2026;26091;2;11;14;17;18;37;2
"""

FDJ_LOTO_VIRGULE = """date,numero_tirage,boule_1,boule_2,boule_3,boule_4,boule_5,N° Chance
03/01/2026,26001,5,12,23,34,47,7
"""


def make_zip_bytes(csv_name: str, csv_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(csv_name, csv_text)
    return buf.getvalue()


def write_synth_csv(game: Game, n: int, path, seed: int = 1) -> None:
    write_canonical_csv(synth_draws(game, n, seed=seed), game, path)
