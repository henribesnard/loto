"""Téléchargement des historiques officiels depuis les pages FDJ.

Chaque jeu possède une page « historique » listant des archives ZIP par période.
Le fetcher scrape ces pages, télécharge les ZIP manquantes, extrait les CSV et
les normalise dans ``<data_dir>/<jeu>.csv`` (format canonique, mis en cache).
"""

import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .games import Game
from .models import Draw
from .parsers import dedupe_draws, parse_zip_bytes, write_canonical_csv

USER_AGENT = "loto-agent/0.1 (+https://github.com/henribesnard/loto)"
TIMEOUT = 30
PAUSE_SECONDS = 0.5


def extract_zip_links(html: str, base_url: str) -> list[str]:
    """Retourne les URL absolues des archives .zip référencées dans la page."""
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().split("?")[0].endswith(".zip"):
            links.add(urljoin(base_url, href))
    return sorted(links)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def list_archives(game: Game, session: requests.Session | None = None) -> list[str]:
    """Liste les URL des archives ZIP publiées sur la page historique du jeu."""
    session = session or _session()
    resp = session.get(game.archive_url, timeout=TIMEOUT)
    resp.raise_for_status()
    return extract_zip_links(resp.text, game.archive_url)


def download_archives(game: Game, raw_dir: str | Path, session: requests.Session | None = None) -> list[Path]:
    """Télécharge les archives ZIP du jeu dans ``raw_dir`` (cache local)."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = session or _session()
    urls = list_archives(game, session)
    if not urls:
        raise RuntimeError(
            f"Aucune archive .zip trouvée sur {game.archive_url} : la page a peut-être changé de structure."
        )
    paths: list[Path] = []
    for i, url in enumerate(urls):
        target = raw_dir / url.split("/")[-1].split("?")[0]
        if not target.exists():
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            target.write_bytes(resp.content)
            time.sleep(PAUSE_SECONDS)
        paths.append(target)
    return paths


def fetch_history(game: Game, data_dir: str | Path = "data", force: bool = False) -> Path:
    """Télécharge (si besoin) puis normalise l'historique complet du jeu.

    Retourne le chemin du CSV canonique mis en cache.
    """
    data_dir = Path(data_dir)
    canonical = data_dir / f"{game.key}.csv"
    if canonical.exists() and not force:
        return canonical

    zip_paths = download_archives(game, data_dir / "raw" / game.key)
    draws: list[Draw] = []
    rejected = 0
    for zp in zip_paths:
        d, r = parse_zip_bytes(zp.read_bytes(), game)
        draws.extend(d)
        rejected += r
    if not draws:
        raise RuntimeError(f"Aucun tirage valide extrait pour {game.nom} ({rejected} lignes rejetées).")

    draws = dedupe_draws(draws)
    write_canonical_csv(draws, game, canonical)
    print(
        f"{game.nom} : {len(draws)} tirages normalisés "
        f"({draws[0].date.isoformat()} → {draws[-1].date.isoformat()}), "
        f"{rejected} lignes ignorées → {canonical}"
    )
    return canonical


def load_or_fetch(game: Game, data_dir: str | Path = "data", csv_path: str | Path | None = None,
                  force: bool = False) -> tuple[list[Draw], Path]:
    """Charge les tirages depuis ``csv_path`` si fourni, sinon via le fetcher/cache."""
    from .parsers import load_draws

    if csv_path is not None:
        return load_draws(csv_path, game), Path(csv_path)
    path = fetch_history(game, data_dir=data_dir, force=force)
    return load_draws(path, game), path
