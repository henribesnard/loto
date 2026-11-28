"""Tests des modules combinis + winamax (aucun accès réseau).

Couvre : fusion des payloads Winamax, extraction/filtrage des matchs,
extraction de tous les marchés (Résultat, BTTS, buts plus/moins…), filtre
par catégories de marchés, construction des combinés (cote minimale, jambes
maximales, diversité, marchés disjoints) et découpage des trames engine.io.
"""

from datetime import datetime, timedelta, timezone

from worker import combinis as cb
from worker import winamax as wx


def _match(match_id, sport_id, jours=1, domicile="Equipe A", exterieur="Equipe B", forme1="WWWWL", forme2="LWLDW"):
    debut = (datetime.now(tz=timezone.utc) + timedelta(days=jours)).timestamp()
    return {
        "matchId": match_id,
        "sportId": sport_id,
        "status": "PREMATCH",
        "competitor1Name": domicile,
        "competitor2Name": exterieur,
        "matchStart": int(debut),
        "competitor1LastMatches": forme1,
        "competitor2LastMatches": forme2,
        "tournamentId": 4,
        "categoryId": 7,
    }


def _etat_compose(matchs, cotes_par_match=None):
    """Construit un état fusionné : matchs + un marché « Résultat » par match.

    'cotes_par_match' : dict matchId → liste de cotes [1, N, 2] ou [1, 2].
    """
    etat = wx.nouvel_etat()
    for m in matchs:
        etat["matches"][str(m["matchId"])] = dict(m)
        cotes = (cotes_par_match or {}).get(m["matchId"], [1.6, 3.8, 5.0])
        identifiants = []
        for index, cote in enumerate(cotes):
            oid = 100000 * int(m["matchId"]) + index
            etat["odds"][str(oid)] = cote
            etat["outcomes"][str(oid)] = {
                "betId": m["matchId"] * 10,
                "label": m["competitor1Name"] if index == 0 else (
                    m["competitor2Name"] if index == len(cotes) - 1 else "Match nul"
                ),
            }
            identifiants.append(oid)
        etat["bets"][str(m["matchId"])] = {
            "betId": m["matchId"] * 10,
            "matchId": int(m["matchId"]),
            "marketId": cb.MONEYLINE_MARKET_IDS.get(m["sportId"], 1),
            "betTypeCategory": "Résultat",
            "template": "3way" if len(cotes) == 3 else "2way",
            "outcomes": identifiants,
        }
    return etat


def _ajouter_marche(etat, m, categorie, labels, cotes, market_id=999):
    """Ajoute un marché supplémentaire (ex. BTTS, buts plus/moins) à un match."""
    bet_id = int(m["matchId"]) * 1000 + market_id
    identifiants = []
    for index, (label, cote) in enumerate(zip(labels, cotes)):
        oid = bet_id * 100 + index
        etat["odds"][str(oid)] = cote
        etat["outcomes"][str(oid)] = {"betId": bet_id, "label": label}
        identifiants.append(oid)
    etat["bets"][str(bet_id)] = {
        "betId": bet_id,
        "matchId": int(m["matchId"]),
        "marketId": market_id,
        "betTypeCategory": categorie,
        "outcomes": identifiants,
    }
    return etat


def test_fusionner_recouvre_payload():
    etat = wx.nouvel_etat()
    wx.fusionner(etat, {"matches": {"1": {"matchId": 1, "sportId": 1}}})
    wx.fusionner(etat, {"matches": {"1": {"title": "A - B"}}})
    assert etat["matches"]["1"]["sportId"] == 1
    assert etat["matches"]["1"]["title"] == "A - B"
    wx.fusionner(etat, {"odds": {"10": 1.5}})
    assert etat["odds"]["10"] == 1.5


def test_scinder_trames_engine_io():
    assert wx._scinder("2\x1e42[\"m\",{}]") == ["2", "42[\"m\",{}]"]
    assert wx._scinder("") == []


def test_extraire_matchs_fenetre_et_filtres():
    m1 = _match(1, 1, jours=0.5, domicile="Lyon", exterieur="Anderlecht")
    m2 = _match(2, 5, jours=1, domicile="Nadal", exterieur="Alcaraz")
    m3 = _match(3, 1, jours=10)  # hors fenêtre
    m4 = _match(4, 1, jours=1)
    m4["status"] = "LIVE"  # à ignorer
    etat = _etat_compose([m1, m2, m3, m4])
    debut, fin = cb.fenetre(3)
    matchs = cb.extraire_matchs(etat, debut, fin, [1, 5])
    assert {m["matchId"] for m in matchs} == {1, 2}
    # filtre par équipes (accents + casse)
    filtres = cb.extraire_matchs(etat, debut, fin, [1, 5], filtres_equipes=["LYON"])
    assert {m["matchId"] for m in filtres} == {1}
    filtres2 = cb.extraire_matchs(etat, debut, fin, [1, 5], filtres_equipes=["alcaraz"])
    assert {m["matchId"] for m in filtres2} == {2}


def test_extraire_candidats_attache_selections():
    m1 = _match(1, 1, jours=1)
    etat = _etat_compose([m1], cotes_par_match={1: [1.9, 3.4, 4.2]})
    matchs = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    assert len(matchs[0]["selections"]) == 3
    assert matchs[0]["selections"][0]["libelle"] == "Equipe A"
    assert matches_preferes(matchs) == 1.9
    assert matchs[0]["marche"] == "Résultat"
    assert matchs[0]["marcheKey"] == "1::1"


def matches_preferes(matchs):
    return min(s["cote"] for s in matchs[0]["selections"])


def test_extraire_candidats_tous_marches():
    """Un match avec Résultat + BTTS + buts : un candidat par marché."""
    m1 = _match(1, 1, jours=1)
    etat = _etat_compose([m1], cotes_par_match={1: [2.0, 3.4, 3.8]})
    _ajouter_marche(etat, m1, "Les deux équipes marquent", ["Oui", "Non"], [1.8, 2.0])
    _ajouter_marche(etat, m1, "Buts", ["Plus de 2.5", "Moins de 2.5"], [1.9, 1.9], market_id=777)
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    categories = [c["marche"] for c in candidats]
    assert categories[0] == "Résultat"  # moneyline prioritaire
    assert set(categories) == {"Résultat", "Les deux équipes marquent", "Buts"}
    assert len({c["marcheKey"] for c in candidats}) == 3
    btts = next(c for c in candidats if c["marche"] == "Les deux équipes marquent")
    assert {s["libelle"] for s in btts["selections"]} == {"Oui", "Non"}


def test_extraire_candidats_filtre_marches():
    """Le paramètre 'marches' restreint aux catégories demandées."""
    m1 = _match(1, 1, jours=1)
    etat = _etat_compose([m1], cotes_par_match={1: [2.0, 3.4, 3.8]})
    _ajouter_marche(etat, m1, "Les deux équipes marquent", ["Oui", "Non"], [1.8, 2.0])
    candidats = cb.extraire_candidats(
        etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]),
        marches=["deux équipes marquent"],
    )
    assert [c["marche"] for c in candidats] == ["Les deux équipes marquent"]


def test_construire_combines_atteint_cote_min():
    matchs = []
    for i in range(1, 41):
        m = _match(i, 1, jours=1, forme1="WWWWW", forme2="LLLLL", domicile=f"Domicile {i}", exterieur=f"Exterieur {i}")
        matchs.append(m)
    etat = _etat_compose(matchs, cotes_par_match={m["matchId"]: [2.0, 3.2, 3.8] for m in matchs})
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    combines = cb.construire_combines(candidats, cote_min=500.0, nb_combines=3, max_jambes=40)
    assert len(combines) == 3
    for combine in combines:
        assert combine["cote_totale"] >= 500.0
        assert 1 <= combine["nb_selections"] <= 40
        # cote recalculée = cote annoncée
        produit = 1.0
        for sel in combine["selections"]:
            produit *= sel["cote"]
        assert round(produit, 2) == combine["cote_totale"]
    # combinés deux à deux distincts
    cles = {tuple(sorted(s["match"] for s in c["selections"])) for c in combines}
    assert len(cles) == 3


def test_construire_combines_marches_disjoints():
    """Deux combinés ne réutilisent jamais la même sélection (match × marché)."""
    matchs = []
    for i in range(1, 41):
        m = _match(i, 1, jours=1, domicile=f"Domicile {i}", exterieur=f"Exterieur {i}")
        matchs.append(m)
    etat = _etat_compose(matchs, cotes_par_match={m["matchId"]: [2.0, 3.2, 3.8] for m in matchs})
    for m in matchs:
        _ajouter_marche(etat, m, "Les deux équipes marquent", ["Oui", "Non"], [1.7, 2.1])
        _ajouter_marche(etat, m, "Buts", ["Plus de 2.5", "Moins de 2.5"], [1.9, 1.9], market_id=777)
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    combines = cb.construire_combines(candidats, cote_min=500.0, nb_combines=3, max_jambes=40)
    assert len(combines) == 3
    cles_utilisees = []
    for combine in combines:
        selections = combine["selections"]
        # chaque sélection porte son marché
        for sel in selections:
            assert sel["marche"] in ("Résultat", "Les deux équipes marquent", "Buts")
        # un match n'apparaît qu'une fois par combiné
        assert len({s["match"] for s in selections}) == len(selections)
        cles_utilisees.append({(s["match"], s["marche"]) for s in selections})
    # pas de sélection partagée entre combinés
    for i in range(len(cles_utilisees)):
        for j in range(i + 1, len(cles_utilisees)):
            assert not (cles_utilisees[i] & cles_utilisees[j])


def test_construire_combines_utilise_plusieurs_marches():
    """Avec tous les marchés, un combiné peut mêler Résultat et BTTS."""
    matchs = []
    for i in range(1, 21):
        m = _match(i, 1, jours=1, domicile=f"Domicile {i}", exterieur=f"Exterieur {i}")
        matchs.append(m)
    etat = _etat_compose(matchs, cotes_par_match={m["matchId"]: [1.5, 3.2, 5.0] for m in matchs})
    for m in matchs[:3]:
        _ajouter_marche(etat, m, "Les deux équipes marquent", ["Oui", "Non"], [2.2, 2.4])
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    combines = cb.construire_combines(candidats, cote_min=12.0, nb_combines=1)
    assert len(combines) == 1
    marches_vus = {s["marche"] for s in combines[0]["selections"]}
    assert marches_vus == {"Résultat", "Les deux équipes marquent"}


def test_construire_combines_renforce_avec_reserve():
    """Peu de matchs, favoris courts : la réserve doit porter le produit à 500."""
    matchs = [_match(i, 1, jours=1) for i in range(1, 6)]
    cotes = {m["matchId"]: [1.2, 8.0, 12.0] for m in matchs}
    etat = _etat_compose(matchs, cotes_par_match=cotes)
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    combines = cb.construire_combines(candidats, cote_min=500.0, nb_combines=1)
    assert len(combines) == 1
    assert combines[0]["cote_totale"] >= 500.0


def test_construire_combines_impossible_sans_matieres():
    matchs = [_match(1, 1, jours=1)]
    etat = _etat_compose(matchs, cotes_par_match={1: [1.05, 9.0]})
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    assert cb.construire_combines(candidats, cote_min=500.0, nb_combines=1) == []


def test_bonus_forme_et_jambe_favorite():
    assert cb._bonus_forme("LWWWW") == 0.8
    assert cb._bonus_forme(None) == 0.5
    m = _match(7, 1, jours=1, forme1="WWWWW")
    etat = _etat_compose([m], cotes_par_match={7: [1.5, 4.0, 6.0]})
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    jambe = cb._jambe_favorite(candidats[0])
    assert jambe["pari"] == "Equipe A"
    assert jambe["score_confiance"] > 0.5
    assert jambe["marche"] == "Résultat"
    assert jambe["marcheKey"] == "7::1"


def test_ids_sports_coherents():
    assert wx.SPORT_IDS == {"football": 1, "basket": 2, "hockey": 4, "tennis": 5, "rugby": 12}
    for nom, ident in wx.SPORT_IDS.items():
        assert ident in cb.NOMS_SPORTS
        assert ident in cb.MONEYLINE_MARKET_IDS


def test_construire_combines_max_4_par_defaut():
    """Par défaut, un combiné ne dépasse pas quatre sélections."""
    matchs = [_match(i, 1, jours=1) for i in range(1, 6)]
    etat = _etat_compose(matchs, cotes_par_match={m["matchId"]: [3.0, 12.0, 15.0] for m in matchs})
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    combines = cb.construire_combines(candidats, cote_min=20.0, nb_combines=3)
    assert combines
    for combine in combines:
        assert combine["nb_selections"] <= 4
        assert combine["cote_totale"] >= 20.0


def test_construire_combines_pas_de_doublon_de_match():
    """Un même match ne peut pas fournir deux jambes du même combiné."""
    m1 = _match(1, 1, jours=1, domicile="Equipe A", exterieur="Equipe B")
    m2 = _match(2, 1, jours=1, domicile="Equipe C", exterieur="Equipe D")
    etat = _etat_compose([m1, m2], cotes_par_match={1: [1.5, 3.2, 5.0], 2: [1.5, 3.2, 5.0]})
    for m in (m1, m2):
        _ajouter_marche(etat, m, "Les deux équipes marquent", ["Oui", "Non"], [1.7, 2.1])
        _ajouter_marche(etat, m, "Buts", ["Plus de 2.5", "Moins de 2.5"], [1.9, 1.9], market_id=777)
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    combines = cb.construire_combines(candidats, cote_min=3.0, nb_combines=1)
    assert len(combines) == 1
    selections = combines[0]["selections"]
    assert len({s["match"] for s in selections}) == len(selections)
