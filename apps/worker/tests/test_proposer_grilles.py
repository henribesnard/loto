"""Tests du workflow proposer-grilles, hors-ligne et sans serveur Temporal.

Le bac à sable ne peut pas télécharger le serveur de test Temporal, donc on teste :
- l'enregistrement/découverte du workflow et son schéma d'entrée ;
- les activités directement (elles sont appelables hors worker) ;
- l'orchestration équivalente à l'entrypoint (sans appel LLM).
"""

import asyncio
import random
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

import mistralai.workflows as workflows
from worker.workflows import proposer_grilles as pg

from lotagent.games import get_game
from lotagent.models import Draw
from lotagent.parsers import write_canonical_csv


def _synth_csv(path, game, n=300, seed=1):
    rng = random.Random(seed)
    draws = []
    d = date(2024, 1, 1)
    for _ in range(n):
        main = tuple(sorted(rng.sample(list(game.main_range), game.main_count)))
        extras = tuple(sorted(rng.sample(list(game.extra_range), game.extra_count)))
        draws.append(Draw(date=d, main=main, extras=extras))
        d += timedelta(days=3)
    write_canonical_csv(draws, game, path)


def test_workflow_decouvert_et_nomme():
    classes = workflows.discover_all_workflows_in_package("worker.workflows")
    assert pg.ProposerGrillesWorkflow in classes
    definition = workflows.get_workflow_definition(pg.ProposerGrillesWorkflow)
    assert definition.name == "proposer-grilles"


def test_input_valide_les_champs():
    inp = pg.ProposerInput(jeu="eurodreams", grilles=2, avec_commentaire_llm=False, seed=1)
    assert inp.jeu == "eurodreams"
    with pytest.raises(ValidationError):
        pg.ProposerInput(jeu="keno")
    with pytest.raises(ValidationError):
        pg.ProposerInput(grilles=0)


def test_activites_et_orchestration_hors_ligne(tmp_path):
    game = get_game("loto")
    csv = tmp_path / "loto.csv"
    _synth_csv(csv, game)

    res = asyncio.run(pg.charger_proposer("loto", str(csv), 3, None, None, 42, None))
    assert res["jeu"] == "loto"
    assert res["nom_jeu"] == "LOTO"
    assert res["resume_stats"]["nb_tirages"] == 300
    assert len(res["grilles"]) == 3
    for g in res["grilles"]:
        assert len(g["numeros"]) == 5
        assert len(set(g["numeros"])) == 5
        assert all(1 <= n <= 49 for n in g["numeros"])
        assert len(g["complementaires"]) == 1
        assert 1 <= g["complementaires"][0] <= 10
        assert 0.0 <= g["score_total"] <= 1.0

    out = pg.ProposerOutput(
        jeu=res["jeu"],
        nom_jeu=res["nom_jeu"],
        nb_tirages=res["resume_stats"]["nb_tirages"],
        periode=res["resume_stats"]["periode"],
        source=res["source"],
        resume_stats=res["resume_stats"],
        grilles=[pg.GrilleProposee(**g) for g in res["grilles"]],
        commentaire_llm=None,
        avertissement=pg.AVERTISSEMENT.format(
            nom=res["nom_jeu"], odds=f"{res['combinaisons']:,}".replace(",", " ")
        ),
    )
    assert out.commentaire_llm is None
    assert "indépendant" in out.avertissement
    assert "19 068 840" in out.avertissement


def test_content_to_text():
    assert pg._content_to_text("bonjour") == "bonjour"
    assert pg._content_to_text(None) == ""
    assert pg._content_to_text([]) == ""
    blocs = [
        {"type": "thinking", "thinking": [{"type": "text", "text": "réflexion interne"}]},
        {"type": "text", "text": "Voici "},
        {"type": "text", "text": "l'analyse."},
    ]
    assert pg._content_to_text(blocs) == "Voici l'analyse."


def test_charger_proposer_eurodreams(tmp_path):
    game = get_game("eurodreams")
    csv = tmp_path / "eurodreams.csv"
    _synth_csv(csv, game, n=150, seed=7)
    res = asyncio.run(pg.charger_proposer("eurodreams", str(csv), 2, None, None, 1, None))
    assert len(res["grilles"]) == 2
    for g in res["grilles"]:
        assert len(g["numeros"]) == 6
        assert all(1 <= n <= 40 for n in g["numeros"])
        assert 1 <= g["complementaires"][0] <= 5
