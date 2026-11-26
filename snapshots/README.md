# Snapshots d'historique de secours

CSV embarqués utilisés **en dernier recours** par le fetcher quand les sources en
ligne sont indisponibles (ex. egress bloqué vers `sto.api.fdj.fr` depuis un worker
cloud).

- **Provenance** : republication CC0 des archives officielles de la FDJ
  (`fdj.fr/.../historique`) par <https://juhuj.com/donnees/>, téléchargée le
  2026-11-26.
- **Fraîcheur** : LOTO jusqu'au 2026-11-25, EuroMillions jusqu'au 2026-11-24,
  EuroDreams jusqu'au 2026-11-23.
- **Ordre des sources** (voir `lotagent/fetcher.py`) : 1) archives ZIP officielles
  FDJ, 2) miroirs CSV (juhuj.com, mes-resultats-fdj.fr), 3) ces snapshots.

Pour rafraîchir : `python -m lotagent fetch --jeu <loto|euromillions|eurodreams> --force`
puis recopier `data/<jeu>.csv` ici.
