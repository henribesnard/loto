"""Mise en forme des sorties utilisateur (français)."""

from .games import Game
from .models import Grid

DISCLAIMER = (
    "Rappel : chaque tirage est un événement aléatoire indépendant. Toutes les grilles "
    "valides ont exactement la même probabilité de sortir ({odds}). Les scores ci-dessus "
    "sont des heuristiques descriptives sur l'historique, sans aucune valeur prédictive. "
    "Jouez de manière responsable : joueurs-info-service.fr — 09 74 75 13 13 (appel non surtaxé)."
)


def format_disclaimer(game: Game) -> str:
    return DISCLAIMER.format(odds=f"1 sur {game.combinaisons:,}".replace(",", " "))


def format_grid(game: Game, index: int, grid: Grid) -> str:
    lines = [f"Grille {index} : {grid.format(game)}   (score combiné : {grid.total:.3f})"]
    details = ", ".join(f"{name}={value:.2f}" for name, value in sorted(grid.scores.items()))
    lines.append(f"  détail des méthodes : {details}")
    return "\n".join(lines)


def format_backtest(report: dict) -> str:
    lines = [
        f"Backtest {report['jeu']} — {report['n_eval']} tirages évalués ({report['fenetre']})",
        f"  Bons numéros principaux attendus au hasard : {report['attendu_aleatoire']:.3f} "
        f"(baseline mesurée : {report['baseline_aleatoire']:.3f})",
        "  Méthodes (moyenne de bons numéros principaux) :",
    ]
    for name, res in sorted(
        report["methodes"].items(), key=lambda kv: -kv[1]["moyenne_bons_numeros"]
    ):
        lines.append(
            f"    - {name:<12} {res['moyenne_bons_numeros']:.3f}  "
            f"(min {res['min']}, max {res['max']})"
        )
    lines.append(
        "  Interprétation : si aucune méthode ne dépasse nettement la baseline, cela confirme "
        "que l'historique n'a pas de pouvoir prédictif (tirages indépendants)."
    )
    return "\n".join(lines)
