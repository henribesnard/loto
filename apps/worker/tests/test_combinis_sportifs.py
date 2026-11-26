"""Tests des modules combinis + winamax (aucun accès réseau).

Couvre : fusion des payloads Winamax, extraction/filtrage des matchs,
Attachement des marchés « Résultat », construction des combinés (cote
minimale, jambes maximales, diversité) et découpage des trames engine.io.
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

    ``cotes_par_match`` : dict matchId → liste de cotes [1, N, 2] ou [1, 2].
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


def matches_preferes(matchs):
    return min(s["cote"] for s in matchs[0]["selections"])


def test_construire_combines_atteint_cote_min():
    matchs = []
    for i in range(1, 21):
        m = _match(i, 1, jours=1, forme1="WWWWW", forme2="LLLLL", domicile=f"Domicile {i}", exterieur=f"Exterieur {i}")
        matchs.append(m)
    etat = _etat_compose(matchs, cotes_par_match={m["matchId"]: [2.0, 3.2, 3.8] for m in matchs})
    candidats = cb.extraire_candidats(etat, cb.extraire_matchs(etat, *cb.fenetre(3), [1]))
    combines = cb.construire_combines(candidats, cote_min=500.0, nb_combines=3)
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


def test_construire_combines_renforce_avec_reserve():
    """Peu de matchs, favoris courts : la réserve doit porter le produit à 500."""
    matchs = [_match(i, 1, jours=1) for i in range(1, 4)]
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


def test_ids_sports_coherents():
    assert wx.SPORT_IDS == {"football": 1, "basket": 2, "hockey": 4, "tennis": 5, "rugby": 12}
    for nom, ident in wx.SPORT_IDS.items():
        assert ident in cb.NOMS_SPORTS
        assert ident in cb.MONEYLINE_MARKET_IDS
