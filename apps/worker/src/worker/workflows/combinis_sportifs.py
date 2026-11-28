"""Workflow Mistral « combinis-sportifs » : combinés Winamax ≥ cible sur 5 sports.

Pipeline : collecte des matchs et cotes Winamax (flux public Socket.IO, transport
polling, sans navigateur) pour le football, le tennis, le basket, le hockey et
le rugby à XV → filtrage des matchs des prochains jours (3 par défaut) →
extraction de tous les marchés exposés par le flux (Résultat, les deux équipes
marquent, buts plus/moins, handicap, etc. ; restreignable via « marches ») →
construction déterministe de combinés dont la cote totale atteint au minimum la
cible (500 par défaut) → commentaire rédigé par un modèle Mistral.

Toute les I/O (réseau Winamax, appels LLM) vivent dans des activités ; le code du
workflow lui-même reste déterministe. Usage personnel : les cotes appartiennent à
Winamax et peuvent changer à tout moment ; une cote de 500 correspond à une
probabilité implicite d'environ 0,2 %.
"""

from datetime import timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field

import mistralai.workflows as workflows

Sport = Literal["football", "basket", "hockey", "tennis", "rugby"]
SPORTS_PAR_DEFAUT: list[Sport] = ["football", "basket", "hockey", "tennis", "rugby"]

AVERTISSEMENT = (
    "Rappel : les paris sportifs comportent un risque de perte. Un combiné à la cote de 500 a une "
    "probabilité implicite d'environ 0,2 % : aucune analyse ni forme récente ne garantit un gain. "
    "Les cotes affichées sont celles de winamax.fr au moment de la collecte et peuvent changer. "
    "Jouez de manière responsable : joueurs-info-service.fr (09 74 75 13 13, interdiction "
    "volontaire possible auprès de l'ANJ)."
)

SYSTEM_PROMPT = (
    "Tu es un analyste sportif francophone. On te fournit des combinés construits à partir des "
    "cotes réelles de Winamax (matchs professionnels de football, tennis, basket, hockey et rugby "
    "à XV), sur tous les marchés proposés (résultat, les deux équipes marquent, buts plus/moins, "
    "handicap, etc.). Rédige en français un commentaire court (5 à 8 phrases) qui explicite la "
    "logique de chaque combiné (favoris choisis, marchés utilisés, forme récente des équipes, "
    "répartition entre sports), sans jamais promettre de gain ni présenter les cotes comme une "
    "opportunité sure. Tu dois TOUJOURS conclure en rappelant qu'un combiné à très haute cote est "
    "mathématiquement très improbable et en invitant à jouer de manière responsable. Reste "
    "factuel : les cotes viennent de winamax.fr et la probabilité implicite d'un combiné à la "
    "cote C est 1/C."
)


class CombinesInput(BaseModel):
    sports: list[Sport] = SPORTS_PAR_DEFAUT
    jours: int = Field(default=3, ge=1, le=7)
    cote_minimale: float = Field(default=500.0, ge=1.5, le=100000.0)
    nb_combines: int = Field(default=3, ge=1, le=10)
    filtres_equipes: Optional[list[str]] = Field(
        default=None,
        description=(
            "Restriction aux matchs dont le titre contient au moins une de ces chaînes "
            "(utile pour cibler une compétition : passer les noms d'équipes, ex. "
            "['Lyon', 'Anderlecht']). Insensible à la casse et aux accents."
        ),
    )
    marches: Optional[list[str]] = Field(
        default=None,
        description=(
            "Restriction aux marchés dont la catégorie contient au moins une de ces "
            "chaînes (ex. ['Résultat', 'Les deux équipes marquent', 'Buts']). "
            "Insensible à la casse et aux accents ; None = tous les marchés "
            "proposés par Winamax pour chaque match. Les catégories réellement "
            "rencontrées sont listées dans le champ 'marches_disponibles' du résultat."
        ),
    )
    avec_commentaire_llm: bool = True
    modele: str = "mistral-large-latest"


class Selection(BaseModel):
    sport: str
    match: str
    marche: Optional[str] = None
    pari: str
    cote: float
    debut_iso: str
    forme_domicile: Optional[str] = None
    forme_exterieur: Optional[str] = None


class Combine(BaseModel):
    titre: str
    cote_totale: float
    nb_selections: int
    selections: list[Selection]


class CombinesOutput(BaseModel):
    source: str
    sports: list[str]
    fenetre: str
    nb_matchs_analyses: int
    nb_matchs_avec_cotes: int
    marches_disponibles: dict[str, int]
    combines: list[Combine]
    commentaire_llm: Optional[str]
    avertissement: str


@workflows.activity(start_to_close_timeout=timedelta(minutes=8), retry_policy_max_attempts=2)
async def collecter_analyser(
    sports: list[str],
    jours: int,
    cote_minimale: float,
    nb_combines: int,
    filtres_equipes: Optional[list[str]],
    marches: Optional[list[str]],
) -> dict:
    from worker import combinis
    from worker import winamax

    etat = winamax.collecter_matchs(sports, duree_s=30.0)
    maintenant, fin = combinis.fenetre(jours)
    ids = [winamax.SPORT_IDS[s] for s in sports]
    matchs = combinis.extraire_matchs(etat, maintenant, fin, ids, filtres_equipes)
    nb_matchs = len(matchs)
    candidats = combinis.extraire_candidats(etat, matchs, marches)
    matchs_avec_cotes = {c["matchId"] for c in candidats}
    marches_disponibles: dict[str, int] = {}
    for c in candidats:
        marches_disponibles[c["marche"]] = marches_disponibles.get(c["marche"], 0) + 1
    combines = combinis.construire_combines(candidats, cote_min=cote_minimale, nb_combines=nb_combines)
    return {
        "sports": sports,
        "fenetre": combinis.plage_lisible(maintenant, fin),
        "nb_matchs_analyses": nb_matchs,
        "nb_matchs_avec_cotes": len(matchs_avec_cotes),
        "marches_disponibles": marches_disponibles,
        "combines": combines,
    }


def _content_to_text(content) -> str:
    """Extrait le texte d'un contenu de réponse Mistral (str ou blocs)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parties: list[str] = []
    for bloc in content:
        if isinstance(bloc, dict):
            if bloc.get("type") == "text" and isinstance(bloc.get("text"), str):
                parties.append(bloc["text"])
        else:
            if getattr(bloc, "type", "text") == "text":
                texte = getattr(bloc, "text", None)
                if isinstance(texte, str):
                    parties.append(texte)
    return "".join(parties)


@workflows.activity(start_to_close_timeout=timedelta(minutes=3), retry_policy_max_attempts=2)
async def rediger_commentaire_combinis(analyse: dict, cote_minimale: float, modele: str) -> str:
    from mistralai.workflows.client import get_mistral_client

    client = get_mistral_client()
    resume = {
        "fenetre": analyse["fenetre"],
        "nb_matchs_analyses": analyse["nb_matchs_analyses"],
        "cote_minimale": cote_minimale,
        "combines": [
            {
                "titre": c["titre"],
                "cote_totale": c["cote_totale"],
                "nb_selections": c["nb_selections"],
                "selections": c["selections"][:12],
            }
            for c in analyse["combines"]
        ],
    }
    utilisateur = (
        f"Analyse à commenter (JSON) : {resume}\n\n"
        "Rédige le commentaire demandé : une phrase de cadrage, la logique de chaque combiné, "
        "puis la conclusion de jeu responsable obligatoire."
    )
    reponse = await client.chat.complete_async(
        model=modele,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": utilisateur},
        ],
        temperature=0.4,
    )
    return _content_to_text(reponse.choices[0].message.content)


@workflows.workflow.define(
    name="combinis-sportifs",
    workflow_display_name="Combinés sportifs Winamax (5 sports, 3 prochains jours, tous marchés)",
    workflow_description=(
        "Collecte les cotes réelles de winamax.fr (football, tennis, basket, hockey, rugby à XV) "
        "sur les prochains jours, sur tous les marchés proposés (résultat, les deux équipes "
        "marquent, buts plus/moins, handicap, etc.), et construit des combinés dont la cote "
        "totale atteint au minimum la cible (500 par défaut). Peut être restreint à des équipes "
        "données (filtres_equipes) ou à certaines catégories de marchés (marches ; les catégories "
        "rencontrées sont listées dans marches_disponibles). Ajoute un commentaire d'analyse "
        "Mistral. Rappel : très haute cote = très faible probabilité, jouer reste un risque."
    ),
)
class CombinisSportifsWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: CombinesInput) -> CombinesOutput:
        analyse = await collecter_analyser(
            list(input.sports),
            input.jours,
            input.cote_minimale,
            input.nb_combines,
            input.filtres_equipes,
            input.marches,
        )
        commentaire = None
        if input.avec_commentaire_llm and analyse["combines"]:
            commentaire = await rediger_commentaire_combinis(analyse, input.cote_minimale, input.modele)
        return CombinesOutput(
            source="winamax.fr (flux public, collecte en direct)",
            sports=analyse["sports"],
            fenetre=analyse["fenetre"],
            nb_matchs_analyses=analyse["nb_matchs_analyses"],
            nb_matchs_avec_cotes=analyse["nb_matchs_avec_cotes"],
            marches_disponibles=analyse["marches_disponibles"],
            combines=[Combine(**c) for c in analyse["combines"]],
            commentaire_llm=commentaire,
            avertissement=AVERTISSEMENT,
        )
