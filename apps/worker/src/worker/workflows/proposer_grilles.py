"""Workflow Mistral « proposer-grilles » : agent qui se lance directement sur l'application lotagent.

Pipeline : téléchargement de l'historique FDJ du jeu choisi → calcul des statistiques et
proposition de N grilles par les méthodes de `lotagent` → commentaire d'analyse rédigé par
un modèle Mistral. Toute les I/O (réseau FDJ, fichiers, appels LLM) vivent dans des activités ;
le code du workflow lui-même reste déterministe.
"""

from datetime import timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field

import mistralai.workflows as workflows

Jeu = Literal["loto", "euromillions", "eurodreams"]

AVERTISSEMENT = (
    "Rappel : {nom} est un jeu de hasard pur. Chaque tirage est indépendant des précédents et "
    "toutes les grilles valides ont exactement la même probabilité de sortir (1 sur {odds}). "
    "Les scores et le commentaire sont des analyses descriptives de l'historique, sans valeur "
    "prédictive. Jouez de manière responsable : joueurs-info-service.fr — 09 74 75 13 13."
)

SYSTEM_PROMPT = (
    "Tu es un agent d'analyse statistique pour les jeux de tirage de la FDJ (LOTO, EuroMillions, "
    "EuroDreams). On te fournit des statistiques sur l'historique des tirages et des grilles "
    "proposées par des méthodes statistiques. Rédige en français un commentaire court (4 à 6 "
    "phrases) qui résume ce que montre l'historique (numéros fréquents, retards, test du chi²) et "
    "présente les grilles proposées. Tu dois TOUJOURS conclure en rappelant que chaque tirage est "
    "indépendant, qu'aucune grille n'est plus probable qu'une autre, et qu'aucune méthode ne "
    "permet de prédire le prochain tirage. Ne promets jamais de gain."
)


class ProposerInput(BaseModel):
    jeu: Jeu = "loto"
    grilles: int = Field(default=5, ge=1, le=100)
    methodes: Optional[list[str]] = None
    poids: Optional[dict[str, float]] = None
    seed: Optional[int] = None
    derniers_tirages: Optional[int] = Field(default=None, ge=50)
    csv_path: Optional[str] = None
    avec_commentaire_llm: bool = True
    modele: str = "mistral-large-latest"


class GrilleProposee(BaseModel):
    numeros: list[int]
    complementaires: list[int]
    score_total: float
    scores: dict[str, float]


class ProposerOutput(BaseModel):
    jeu: str
    nom_jeu: str
    nb_tirages: int
    periode: str
    source: str
    resume_stats: dict
    grilles: list[GrilleProposee]
    commentaire_llm: Optional[str]
    avertissement: str


@workflows.activity(start_to_close_timeout=timedelta(minutes=10), retry_policy_max_attempts=2)
async def telecharger_historique(jeu: str, data_dir: str) -> dict:
    from lotagent.fetcher import fetch_history, read_source
    from lotagent.games import get_game

    game = get_game(jeu)
    path = fetch_history(game, data_dir=data_dir)
    return {"csv": str(path), "source": read_source(data_dir, game) or str(path)}


@workflows.activity(start_to_close_timeout=timedelta(minutes=5))
async def charger_proposer(
    jeu: str,
    csv_path: str,
    grilles: int,
    methodes: Optional[list[str]],
    poids: Optional[dict[str, float]],
    seed: Optional[int],
    derniers_tirages: Optional[int],
) -> dict:
    from lotagent import stats as st
    from lotagent.engine import Engine
    from lotagent.games import get_game
    from lotagent.parsers import load_draws

    game = get_game(jeu)
    draws = load_draws(csv_path, game)
    if derniers_tirages:
        draws = draws[-derniers_tirages:]
    engine = Engine(game, method_names=methodes, weights=poids, seed=seed)
    engine.fit(draws)
    proposees = engine.propose(grilles)

    freq = st.frequencies(draws, main=True)
    chi2, p = st.chi2_uniform(freq, len(draws), game.main_max)
    gaps = st.gaps(draws, game)
    resume = {
        "nb_tirages": len(draws),
        "periode": f"{draws[0].date} → {draws[-1].date}",
        "chi2_statistique": round(chi2, 1),
        "chi2_p_valeur": round(p, 4),
        "plus_frequents": sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
        "plus_en_retard": sorted(gaps.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
        "attendu_bons_numeros_aleatoire": round(st.expected_main_matches(game), 3),
    }
    return {
        "jeu": game.key,
        "nom_jeu": game.nom,
        "combinaisons": game.combinaisons,
        "source": csv_path,
        "resume_stats": resume,
        "grilles": [
            {
                "numeros": sorted(g.main),
                "complementaires": sorted(g.extras),
                "score_total": round(g.total, 4),
                "scores": {k: round(v, 4) for k, v in g.scores.items()},
            }
            for g in proposees
        ],
    }


@workflows.activity(start_to_close_timeout=timedelta(minutes=3), retry_policy_max_attempts=2)
async def rediger_commentaire(nom_jeu: str, resume: dict, grilles: list, modele: str) -> str:
    from mistralai.workflows.client import get_mistral_client

    client = get_mistral_client()
    user = (
        f"Jeu : {nom_jeu}\n"
        f"Statistiques sur l'historique : {resume}\n"
        f"Grilles proposées : {grilles}\n\n"
        "Rédige le commentaire demandé."
    )
    resp = await client.chat.complete_async(
        model=modele,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    return resp.choices[0].message.content or ""


@workflows.workflow.define(
    name="proposer-grilles",
    workflow_display_name="Proposer des grilles FDJ (LOTO / EuroMillions / EuroDreams)",
    workflow_description=(
        "Télécharge l'historique officiel FDJ du jeu choisi, applique les méthodes statistiques "
        "de lotagent et propose N grilles, avec un commentaire d'agent Mistral. Rappel : jeu de "
        "hasard pur, aucune grille n'est plus probable qu'une autre."
    ),
)
class ProposerGrillesWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: ProposerInput) -> ProposerOutput:
        source = input.csv_path or "fichier fourni en entrée"
        if input.csv_path is None:
            infos = await telecharger_historique(input.jeu, "data")
            csv_path = infos["csv"]
            source = infos["source"]
        else:
            csv_path = input.csv_path
        stats = await charger_proposer(
            input.jeu,
            csv_path,
            input.grilles,
            input.methodes,
            input.poids,
            input.seed,
            input.derniers_tirages,
        )
        commentaire = None
        if input.avec_commentaire_llm:
            commentaire = await rediger_commentaire(
                stats["nom_jeu"], stats["resume_stats"], stats["grilles"], input.modele
            )
        return ProposerOutput(
            jeu=stats["jeu"],
            nom_jeu=stats["nom_jeu"],
            nb_tirages=stats["resume_stats"]["nb_tirages"],
            periode=stats["resume_stats"]["periode"],
            source=source,
            resume_stats=stats["resume_stats"],
            grilles=[GrilleProposee(**g) for g in stats["grilles"]],
            commentaire_llm=commentaire,
            avertissement=AVERTISSEMENT.format(
                nom=stats["nom_jeu"], odds=f"{stats['combinaisons']:,}".replace(",", " ")
            ),
        )
