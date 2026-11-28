"""Logique métier des combinés sportifs : fonctions pures, testables sans réseau.

Reçoit l'état fusionné du flux Winamax (voir worker.winamax), filtre les matchs
des prochains jours, en extrait tous les marchés exposés par le flux (Résultat,
les deux équipes marquent, buts plus/moins, handicap, etc.) avec leurs cotes,
puis construit des combinés dont la cote totale atteint au minimum la cible
demandée (500 par défaut).

Aucune prétention prédictive : une cote de 500 correspond à une probabilité
implicite d'environ 0,2 %. Les heuristiques de forme servent un classement
documentaire, pas une garantie.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

MONEYLINE_MARKET_IDS: dict[int, int] = {
    1: 1,    # Football : « Résultat » (1 N 2)
    2: 219,  # Basket : vainqueur du match
    4: 1,    # Hockey : « Résultat »
    5: 186,  # Tennis : vainqueur du match
    12: 1,   # Rugby à XV : « Résultat »
}

NOMS_SPORTS: dict[int, str] = {
    1: "Football",
    2: "Basket",
    4: "Hockey",
    5: "Tennis",
    12: "Rugby à XV",
}


def _normaliser(texte: Any) -> str:
    if texte is None:
        return ""
    brut = unicodedata.normalize("NFKD", str(texte))
    return "".join(c for c in brut if not unicodedata.combining(c)).casefold().strip()


def _contient_filtre(titre: str, filtres: Optional[list[str]]) -> bool:
    if not filtres:
        return True
    normalise = _normaliser(titre)
    return any(_normaliser(f) in normalise for f in filtres)


def extraire_matchs(
    etat: dict,
    fenetre_debut: float,
    fenetre_fin: float,
    ids_sports: list[int],
    filtres_equipes: Optional[list[str]] = None,
) -> list[dict]:
    """Filtre les matchs « PREMATCH » dans la fenêtre de dates.

    Renvoie des dictionnaires plats : matchId, sportId, titre, domicile,
    exterieur, debut (unix), forme_domicile, forme_exterieur, classements,
    tournamentId, categoryId.
    """
    matchs = []
    for ident, m in (etat.get("matches") or {}).items():
        if not isinstance(m, dict):
            continue
        if m.get("status") not in (None, "PREMATCH"):
            continue
        domicile = (m.get("competitor1Name") or "").strip()
        exterieur = (m.get("competitor2Name") or "").strip()
        if not domicile or not exterieur:
            continue
        sport = m.get("sportId")
        if sport not in ids_sports:
            continue
        debut = m.get("matchStart")
        if not isinstance(debut, (int, float)) or not (fenetre_debut <= debut <= fenetre_fin):
            continue
        m_ = {
            "matchId": int(ident),
            "sportId": int(sport),
            "titre": f"{domicile} - {exterieur}",
            "domicile": domicile,
            "exterieur": exterieur,
            "debut": int(debut),
            "forme_domicile": m.get("competitor1LastMatches") or None,
            "forme_exterieur": m.get("competitor2LastMatches") or None,
            "classement_domicile": m.get("competitor1Ranking"),
            "classement_exterieur": m.get("competitor2Ranking"),
            "tournamentId": m.get("tournamentId"),
            "categoryId": m.get("categoryId"),
        }
        if _contient_filtre(m_["titre"], filtres_equipes):
            matchs.append(m_)
    matchs.sort(key=lambda x: (x["debut"], x["matchId"]))
    return matchs


def _paris_du_match(etat: dict, match_id: int) -> list[dict]:
    paris = []
    for bet in (etat.get("bets") or {}).values():
        if not isinstance(bet, dict):
            continue
        try:
            if int(bet.get("matchId")) == match_id:  # type: ignore[arg-type]
                paris.append(bet)
        except (TypeError, ValueError):
            continue
    return paris


def _selections_completes(etat: dict, bet: dict) -> Optional[list[dict]]:
    """Cotes + libellés des issues d'un marché si TOUTES sont disponibles."""
    issues = bet.get("outcomes") or []
    identifiants = issues if isinstance(issues, list) else list(issues)
    selections = []
    for oid in identifiants:
        cote = (etat.get("odds") or {}).get(str(oid))
        info = (etat.get("outcomes") or {}).get(str(oid)) or {}
        libelle = (info.get("label") or "").strip()
        if cote is None or isinstance(cote, (dict, list)):
            return None
        selections.append({"libelle": libelle, "cote": float(cote)})
    if not selections or any(s["cote"] <= 1.0 for s in selections):
        return None
    return selections


def _marche_admis(categorie: str, filtres: Optional[list[str]]) -> bool:
    """Vrai si la catégorie de marché est demandée (filtre absent = tous)."""
    if not filtres:
        return True
    normalisee = _normaliser(categorie)
    return any(_normaliser(f) in normalisee for f in filtres)


def extraire_candidats(
    etat: dict,
    matchs: list[dict],
    marches: Optional[list[str]] = None,
) -> list[dict]:
    """Pour chaque match, extrait tous les marchés retenus et leurs issues.

    Renvoie une liste de candidats « match × marché » : chaque candidat porte
    les champs du match, 'marche' (catégorie du marché, ex. « Résultat »,
    « Les deux équipes marquent ») et 'selections' (issues complètes du
    marché : libellés + cotes). 'marches' restreint aux catégories dont le nom
    contient une des chaînes données (insensible à la casse et aux accents) ;
    None = tous les marchés exposés par le flux Winamax pour chaque match.

    Le marché « Résultat » (moneyline) garde la priorité en tête de la liste
    de chaque match (tri stable par identifiant de marché connu).
    """
    candidats: list[dict] = []
    for m in matchs:
        cible = MONEYLINE_MARKET_IDS.get(m["sportId"])
        retenus: list[tuple[int, str, list[dict]]] = []
        for bet in _paris_du_match(etat, m["matchId"]):
            if bet.get("available") is False:
                continue
            selections = _selections_completes(etat, bet)
            if not selections or len(selections) < 2:
                continue
            categorie = str(bet.get("betTypeCategory") or "").strip() or "Autre"
            if not _marche_admis(categorie, marches):
                continue
            identifiant_marche = bet.get("marketId")
            if identifiant_marche is None:
                identifiant_marche = bet.get("betId", -1)
            try:
                identifiant_marche = int(identifiant_marche)
            except (TypeError, ValueError):
                identifiant_marche = -1
            retenus.append((0 if identifiant_marche == cible else 1, categorie, selections, identifiant_marche))
        retenus.sort(key=lambda r: r[0])
        for _priorite, categorie, selections, identifiant_marche in retenus:
            c = dict(m)
            c["marche"] = categorie
            # Clé unique par marché réel (plusieurs marchés peuvent partager
            # une même catégorie, ex. « Stats joueurs ») : sans cela, un même
            # marché pouvait apparaître deux fois dans un combiné.
            c["marcheKey"] = f"{m['matchId']}::{identifiant_marche}"
            c["selections"] = selections
            candidats.append(c)
    return candidats


def _bonus_forme(forme: Optional[str]) -> float:
    """Part de victoires récentes ('LWWWW' → 0.8), 0.5 si inconnue."""
    if not forme or not isinstance(forme, str):
        return 0.5
    lettres = [c.upper() for c in forme if c.upper() in ("W", "L", "D")]
    if not lettres:
        return 0.5
    return lettres.count("W") / len(lettres)


def _jambe_favorite(m: dict) -> Optional[dict]:
    """Sélection la plus probable (plus petite cote) d'un marché."""
    selections = m.get("selections") or []
    if not selections:
        return None
    favorite = min(selections, key=lambda s: s["cote"])
    return _faire_jambe(m, favorite)


def _faire_jambe(m: dict, selection: dict) -> dict:
    bonus = 0.5
    nom = _normaliser(selection["libelle"])
    if nom and nom == _normaliser(m.get("domicile")):
        bonus = _bonus_forme(m.get("forme_domicile"))
    elif nom and nom == _normaliser(m.get("exterieur")):
        bonus = _bonus_forme(m.get("forme_exterieur"))
    return {
        "sport": NOMS_SPORTS.get(m["sportId"], str(m["sportId"])),
        "match": m["titre"],
        "matchId": m["matchId"],
        "sportId": m["sportId"],
        "marche": m.get("marche"),
        "marcheKey": m.get("marcheKey") or str(m["matchId"]),
        "debut": m["debut"],
        "pari": selection["libelle"] or "-",
        "cote": selection["cote"],
        "score_confiance": round((1.0 / selection["cote"]) * (0.85 + 0.3 * bonus), 4),
        "forme_domicile": m.get("forme_domicile"),
        "forme_exterieur": m.get("forme_exterieur"),
    }


def _produit(jambes: list[dict]) -> float:
    produit = 1.0
    for j in jambes:
        produit *= j["cote"]
    return produit


def _completer(favoris: list[dict], autres: list[dict], cote_min: float, max_jambes: int) -> Optional[list[dict]]:
    """Ajoute des jambes jusqu'à dépasser la cote cible ; None si impossible.

    Un même match n'apparaît qu'une seule fois (pas de jambes corrélées).
    Deux ordres sont tentés : favoris puis réserve, puis réserve puis favoris
    (utile quand peu de jambes suffisent via la réserve).
    """
    def _sequence(ordre: list[dict]) -> Optional[list[dict]]:
        jambes: list[dict] = []
        matchs_vus: set[int] = set()
        for jambe in ordre:
            if jambe["matchId"] in matchs_vus:
                continue
            matchs_vus.add(jambe["matchId"])
            jambes.append(jambe)
            if _produit(jambes) >= cote_min or len(jambes) >= max_jambes:
                return jambes if _produit(jambes) >= cote_min else None
        return jambes if _produit(jambes) >= cote_min else None

    resultat = _sequence(list(favoris) + list(autres))
    if resultat:
        return resultat
    return _sequence(list(autres) + list(favoris))


def construire_combines(
    candidats: list[dict],
    cote_min: float = 500.0,
    nb_combines: int = 3,
    max_jambes: int = 4,
) -> list[dict]:
    """Construit jusqu'à nb_combines combinés distincts ≥ cote_min.

    Trois stratégies déterministes, chacune partant des favoris (plus petite
    cote par marché, toutes catégories confondues), complétées au besoin par
    les autres issues des marchés :
      1. « Cible »   : favoris triés par cote décroissante (moins de jambes) ;
      2. « Équilibré »: alternance entre sports pour répartir le risque ;
      3. « Forme »   : favoris triés par score de confiance (forme récente).

    Un marché déjà consommé par un combiné (clé matchId × identifiant de
    marché) n'est pas réutilisé par les combinés suivants : les combinés
    produits n partagent aucune sélection. Au sein d'un combiné, un même
    match n'apparaît qu'une seule fois (pas de jambes corrélées). Par défaut
    un combiné compte au maximum quatre sélections (max_jambes). Les cotes
    ultra-courtes (< 1.15)
    n'alimentent pas les jambes principales mais restent en réserve de secours.
    """
    candidats = [m for m in candidats if m.get("selections")]
    favoris: list[dict] = []
    reserve: list[dict] = []
    for m in candidats:
        jambe = _jambe_favorite(m)
        if jambe:
            favoris.append(jambe)
        for sel in sorted(m["selections"], key=lambda s: -s["cote"]):
            autre = _faire_jambe(m, sel)
            if not jambe or autre["pari"] != jambe["pari"]:
                reserve.append(autre)

    if not favoris:
        return []

    # Les cotes extrêmes (> 12 : buteurs, score exact…) restent en réserve :
    # en jambes principales elles produiraient des combinés à une seule sélection.
    utiles = [j for j in favoris if 1.15 <= j["cote"] <= 12.0] or list(favoris)

    strategies: list[tuple[str, list[dict]]] = []

    ordonnee_cote = sorted(utiles, key=lambda j: -j["cote"])
    strategies.append(("Cote cible (favoris)", ordonnee_cote))

    par_sport: dict[int, list[dict]] = {}
    for jambe in sorted(utiles, key=lambda j: -j["score_confiance"]):
        par_sport.setdefault(jambe["sportId"], []).append(jambe)
    alternes: list[dict] = []
    voyageurs = list(par_sport.values())
    index = 0
    while any(index < len(pile) for pile in voyageurs) and len(alternes) < max_jambes:
        for pile in voyageurs:
            if index < len(pile):
                alternes.append(pile[index])
        index += 1
    strategies.append(("Équilibré multi-sports", alternes))

    par_forme = sorted(utiles, key=lambda j: -j["score_confiance"])
    strategies.append(("Confiance / forme récente", par_forme))

    combines: list[dict] = []
    deja_vus: set[tuple] = set()
    exclus_globaux: set[str] = set()
    reserve_desc = sorted(reserve, key=lambda j: -j["cote"])
    for titre, jambes in strategies:
        disponibles = [j for j in jambes if j["marcheKey"] not in exclus_globaux]
        complement = [j for j in reserve_desc if j["marcheKey"] not in exclus_globaux]
        complet = _completer(disponibles, complement, cote_min, max_jambes)
        if not complet:
            continue
        cle = tuple(sorted(j["marcheKey"] for j in complet))
        if cle in deja_vus:
            continue
        deja_vus.add(cle)
        exclus_globaux.update(j["marcheKey"] for j in complet)
        combines.append({
            "titre": titre,
            "cote_totale": round(_produit(complet), 2),
            "nb_selections": len(complet),
            "selections": completes_formatees(complet),
        })
        if len(combines) >= nb_combines:
            break
    return combines


def completes_formatees(jambes: list[dict]) -> list[dict]:
    formatees = []
    for j in jambes:
        formatees.append({
            "sport": j["sport"],
            "match": j["match"],
            "marche": j.get("marche"),
            "pari": j["pari"],
            "cote": j["cote"],
            "debut_iso": datetime.fromtimestamp(j["debut"], tz=timezone.utc).isoformat(),
            "forme_domicile": j.get("forme_domicile"),
            "forme_exterieur": j.get("forme_exterieur"),
        })
    return formatees


def fenetre(jours: int) -> tuple[float, float]:
    debut = datetime.now(tz=timezone.utc).timestamp()
    return debut, debut + jours * 86400.0


def plage_lisible(debut_unix: float, fin_unix: float) -> str:
    a = datetime.fromtimestamp(debut_unix, tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    b = datetime.fromtimestamp(fin_unix, tz=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"{a} → {b}"


def jambes_max_par_cote(cote_min: float, cote_moyenne: float = 1.7) -> int:
    """Nombre indicatif de jambes pour atteindre la cible à cote moyenne donnée."""
    nb = 1
    produit = cote_moyenne
    while produit < cote_min and nb < 30:
        nb += 1
        produit *= cote_moyenne
    return nb


def timedelta_jours(jours: int) -> timedelta:
    return timedelta(days=jours)
