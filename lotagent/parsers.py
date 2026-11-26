"""Lecture et normalisation des historiques de tirages.

Gère deux familles de fichiers :
- les archives officielles FDJ (ZIP contenant des CSV en français, séparateur
  ';' ou ',', en-têtes du type ``boule_1``, ``numero_chance``, ``etoile_1``...) ;
- le format canonique écrit par le fetcher : ``date;main_1;...;extra_1;...``.
"""

import csv
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime
from pathlib import Path

from .games import Game
from .models import Draw

_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")

_EXTRA_TOKENS = ("chance", "etoile", "dream", "complementaire", "etoiles")
_MAIN_RE = re.compile(r"^(boule|n[°\s]?\d*|main)")


def _norm(token: str) -> str:
    token = unicodedata.normalize("NFKD", token)
    token = "".join(c for c in token if not unicodedata.combining(c))
    return token.strip().lower()


def _classify_columns(headers: list[str], game: Game):
    """Repère les colonnes date / numéros principaux / complémentaires."""
    date_idx, main_idx, extra_idx = None, [], []
    for i, header in enumerate(headers):
        t = _norm(header)
        if not t:
            continue
        if "date" in t:
            date_idx = i
            continue
        if t.startswith("extra") or any(k in t for k in _EXTRA_TOKENS):
            extra_idx.append(i)
            continue
        if "tirage" in t or "jour" in t or "heure" in t or "rang" in t or "gain" in t:
            continue
        if _MAIN_RE.match(t) or ("numero" in t and "tirage" not in t):
            main_idx.append(i)

    def sort_key(i: int) -> tuple:
        m = re.search(r"(\d+)$", headers[i])
        return (int(m.group(1)) if m else 0, headers[i])

    main_idx.sort(key=sort_key)
    extra_idx.sort(key=sort_key)
    if len(main_idx) < game.main_count:
        # Repli positionnel : date, puis les k premiers numéros, puis le reste.
        date_idx = 0 if date_idx is None else date_idx
        main_idx = list(range(1, 1 + game.main_count))
        extra_idx = [i for i in range(len(headers)) if i not in (date_idx, *main_idx)]
    return date_idx, main_idx, extra_idx


def _parse_date(raw: str) -> date | None:
    raw = raw.strip().split(" ")[0].strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_int(raw: str) -> int | None:
    raw = raw.strip().replace("\xa0", " ").replace(" ", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        try:
            return int(float(raw.replace(",", ".")))
        except ValueError:
            return None


def _detect_delimiter(sample: str) -> str:
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    counts = {d: first_line.count(d) for d in (";", ",", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ";"


def parse_csv_text(text: str, game: Game) -> tuple[list[Draw], int]:
    """Parse un CSV (FDJ ou canonique) en liste de tirages valides.

    Retourne (tirages, nombre_de_lignes_rejetees).
    """
    text = text.lstrip("﻿")
    delimiter = _detect_delimiter(text[:4096])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], 0

    headers = rows[0]
    date_idx, main_idx, extra_idx = _classify_columns(headers, game)

    draws: list[Draw] = []
    rejected = 0
    for row in rows[1:]:
        if len(row) <= max(main_idx + extra_idx, default=-1):
            rejected += 1
            continue
        d = _parse_date(row[date_idx]) if date_idx is not None and date_idx < len(row) else None
        main = tuple(sorted(n for n in (_parse_int(row[i]) for i in main_idx) if n is not None))
        extras = tuple(sorted(n for n in (_parse_int(row[i]) for i in extra_idx) if n is not None))
        draw = Draw(date=d or date(1970, 1, 1), main=main, extras=extras)
        if d is not None and draw.is_valid(game):
            draws.append(draw)
        else:
            rejected += 1

    draws.sort(key=lambda dr: dr.date)
    return draws, rejected


def parse_csv_file(path: str | Path, game: Game) -> tuple[list[Draw], int]:
    path = Path(path)
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return parse_csv_text(raw.decode(encoding), game)
        except UnicodeDecodeError:
            continue
    return parse_csv_text(raw.decode("latin-1", errors="replace"), game)


def _xlsx_to_csv_text(path_in_zip: str, data: bytes) -> str:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError(
            f"L'archive contient un fichier Excel ({path_in_zip}) : installez "
            "openpyxl (pip install openpyxl) ou convertissez-le en CSV."
        ) from exc
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            writer.writerow("" if v is None else v for v in row)
    return out.getvalue()


def parse_zip_bytes(data: bytes, game: Game) -> tuple[list[Draw], int]:
    """Extrait et parse tous les fichiers de données d'une archive ZIP FDJ."""
    draws: list[Draw] = []
    rejected = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith(".csv"):
                text = zf.read(name).decode("utf-8-sig", errors="replace")
                d, r = parse_csv_text(text, game)
            elif lower.endswith((".xlsx", ".xlsm")):
                d, r = parse_csv_text(_xlsx_to_csv_text(name, zf.read(name)), game)
            else:
                continue
            draws.extend(d)
            rejected += r
    return draws, rejected


def parse_zip_file(path: str | Path, game: Game) -> tuple[list[Draw], int]:
    return parse_zip_bytes(Path(path).read_bytes(), game)


def dedupe_draws(draws: list[Draw]) -> list[Draw]:
    seen: dict[tuple, Draw] = {}
    for draw in draws:
        seen[(draw.date, draw.main, draw.extras)] = draw
    return sorted(seen.values(), key=lambda dr: dr.date)


CANONICAL_HEADER = ("date", "main", "extra")


def write_canonical_csv(draws: list[Draw], game: Game, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["date"] + [f"main_{i + 1}" for i in range(game.main_count)] + [
        f"extra_{i + 1}" for i in range(game.extra_count)
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(header)
        for draw in draws:
            writer.writerow(
                [draw.date.isoformat(), *draw.main, *draw.extras]
            )


def load_draws(path: str | Path, game: Game) -> list[Draw]:
    """Charge un CSV canonique ou brut FDJ et retourne les tirages valides triés."""
    draws, _ = parse_csv_file(path, game)
    return dedupe_draws(draws)
