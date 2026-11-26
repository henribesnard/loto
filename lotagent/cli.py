"""Interface en ligne de commande (en français).

Exemples :
    python -m lotagent jeux
    python -m lotagent fetch --jeu loto
    python -m lotagent stats --jeu euromillions --derniers 100
    python -m lotagent proposer --jeu loto --grilles 5
    python -m lotagent backtest --jeu eurodreams --depuis 100
"""

import argparse
import sys
from pathlib import Path

from . import __version__, stats as st
from .backtest import run_backtest
from .engine import Engine
from .fetcher import fetch_history, load_or_fetch
from .games import GAMES, get_game
from .report import format_backtest, format_disclaimer, format_grid


def _parse_poids(raw: str | None) -> dict[str, float]:
    weights: dict[str, float] = {}
    if not raw:
        return weights
    for part in raw.split(","):
        name, _, value = part.partition("=")
        weights[name.strip()] = float(value)
    return weights


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--jeu", required=True, help="loto, euromillions ou eurodreams")
    parser.add_argument("--data-dir", default="data", help="dossier de cache des historiques (défaut: data)")
    parser.add_argument("--csv", default=None, help="lire un CSV local au lieu de télécharger (hors-ligne)")
    parser.add_argument("--force", action="store_true", help="forcer le re-téléchargement des archives FDJ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lotagent",
        description="Agent d'analyse statistique des tirages FDJ (LOTO, EuroMillions, EuroDreams).",
    )
    parser.add_argument("--version", action="version", version=f"lotagent {__version__}")
    sub = parser.add_subparsers(dest="commande", required=True)

    sub.add_parser("jeux", help="lister les jeux supportés et leurs règles")

    p_fetch = sub.add_parser("fetch", help="télécharger et normaliser l'historique d'un jeu")
    _add_common_args(p_fetch)

    p_stats = sub.add_parser("stats", help="afficher les statistiques de l'historique")
    _add_common_args(p_stats)
    p_stats.add_argument("--derniers", type=int, default=None, help="ne considérer que les N derniers tirages")

    p_prop = sub.add_parser("proposer", help="proposer des grilles pour le prochain tirage")
    _add_common_args(p_prop)
    p_prop.add_argument("--grilles", type=int, default=5, help="nombre de grilles à proposer (défaut: 5)")
    p_prop.add_argument("--methodes", default="all",
                        help="méthodes à appliquer, séparées par des virgules, ou 'all' (défaut)")
    p_prop.add_argument("--poids", default=None,
                        help="poids des méthodes, ex. 'frequence=1.5,markov=2'")
    p_prop.add_argument("--seed", type=int, default=None, help="graine aléatoire (reproductibilité)")
    p_prop.add_argument("--depuis", type=int, default=None,
                        help="n'entraîner que sur les N derniers tirages")

    p_bt = sub.add_parser("backtest", help="évaluer les méthodes sur les tirages passés (walk-forward)")
    _add_common_args(p_bt)
    p_bt.add_argument("--methodes", default="all")
    p_bt.add_argument("--depuis", type=int, default=300, help="tirage de départ du backtest (défaut: 300)")
    p_bt.add_argument("--seed", type=int, default=42)

    return parser


def _cmd_jeux() -> int:
    for game in GAMES.values():
        print(f"- {game.key} : {game.nom}")
        print(
            f"    grille : {game.main_count} numéros parmi 1..{game.main_max} "
            f"+ {game.extra_count} {game.extra_label} parmi 1..{game.extra_max}"
        )
        print(f"    rang 1 : 1 chance sur {game.combinaisons:,}".replace(",", " "))
        print(f"    archive FDJ : {game.archive_url}")
        if game.note:
            print(f"    note : {game.note}")
    return 0


def _load(args, game):
    draws, path = load_or_fetch(game, data_dir=args.data_dir, csv_path=args.csv, force=args.force)
    return draws, path


def _cmd_fetch(args) -> int:
    game = get_game(args.jeu)
    fetch_history(game, data_dir=args.data_dir, force=args.force)
    return 0


def _cmd_stats(args) -> int:
    game = get_game(args.jeu)
    draws, path = _load(args, game)
    window = args.derniers
    subset = draws[-window:] if window else draws
    print(f"Jeu : {game.nom} — {len(draws)} tirages au total ({draws[0].date} → {draws[-1].date})")
    print(f"Source : {path}")
    if window:
        print(f"Fenêtre analysée : les {len(subset)} derniers tirages")

    freq = st.frequencies(subset, main=True)
    total = len(subset) * game.main_count
    expected = total / game.main_max
    chi2, p = st.chi2_uniform(freq, len(subset), game.main_max)
    print(f"\nNuméros principaux (attendu uniforme : {expected:.2f} sorties/numéro) :")
    print(f"  test du chi² : statistique={chi2:.1f}, p-valeur={p:.3f} "
          f"({'écart significatif au seuil 5%' if p < 0.05 else 'compatible avec l\'uniformité'})")
    hot = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    cold = sorted(freq.items(), key=lambda kv: (kv[1], kv[0]))[:10]
    print("  plus fréquents : " + ", ".join(f"{n} ({c})" for n, c in hot))
    print("  moins fréquents : " + ", ".join(f"{n} ({c})" for n, c in cold))

    g = st.gaps(draws, game)
    retard = sorted(g.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    print("  plus en retard : " + ", ".join(f"{n} ({c} tirages)" for n, c in retard))

    efreq = st.frequencies(subset, main=False)
    print(f"\n{game.extra_label} : " + ", ".join(f"{n} ({efreq.get(n, 0)})" for n in game.extra_range))
    return 0


def _cmd_proposer(args) -> int:
    game = get_game(args.jeu)
    draws, path = _load(args, game)
    if args.depuis:
        draws = draws[-args.depuis:]
    names = [m for m in args.methodes.split(",") if m.strip()]
    weights = _parse_poids(args.poids)
    engine = Engine(game, method_names=names, weights=weights, seed=args.seed)
    engine.fit(draws)
    grids = engine.propose(args.grilles)

    print(f"Jeu : {game.nom} — historique : {len(draws)} tirages "
          f"({draws[0].date} → {draws[-1].date}) — source : {path}")
    print("Méthodes appliquées : " + ", ".join(sorted(engine.methods)))
    print()
    for i, grid in enumerate(grids, 1):
        print(format_grid(game, i, grid))
    print()
    print(format_disclaimer(game))
    return 0


def _cmd_backtest(args) -> int:
    game = get_game(args.jeu)
    draws, path = _load(args, game)
    names = [m for m in args.methodes.split(",") if m.strip()]
    report = run_backtest(game, draws, method_names=names, depuis=args.depuis, seed=args.seed)
    print(format_backtest(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.commande == "jeux":
            return _cmd_jeux()
        if args.commande == "fetch":
            return _cmd_fetch(args)
        if args.commande == "stats":
            return _cmd_stats(args)
        if args.commande == "proposer":
            return _cmd_proposer(args)
        if args.commande == "backtest":
            return _cmd_backtest(args)
    except (KeyError, ValueError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # erreur réseau, fichier illisible, etc.
        print(f"Erreur : {type(exc).__name__} : {exc}", file=sys.stderr)
        print("Astuce : utilisez --csv <fichier.csv> pour travailler hors-ligne.", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
