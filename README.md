# lotagent — agent d'analyse statistique des tirages FDJ

Agent Python qui télécharge les **historiques officiels des tirages** publiés par la FDJ
pour **LOTO**, **EuroMillions - My Million** et **EuroDreams**, applique plusieurs
**méthodes statistiques et probabilistes** (sélectionnables et combinables), et propose
des grilles pour un tirage donné. Un module de **backtest walk-forward** évalue chaque
méthode sur les tirages passés, comparée à une baseline aléatoire.

> **Avertissement important.** LOTO, EuroMillions et EuroDreams sont des jeux de hasard
> pur : chaque tirage est **indépendant** des précédents et **toutes les grilles valides
> ont exactement la même probabilité de sortir** (1 sur 19 068 840 au LOTO, 1 sur
> 139 838 160 à l'EuroMillions, 1 sur 19 191 900 à l'EuroDreams). Aucune méthode
> statistique — y compris les plus sophistiquées — n'augmente cette probabilité.
> Les « scores » produits ici sont des **heuristiques descriptives** sur l'historique,
> sans valeur prédictive. Voir [docs/methodes.md](docs/methodes.md).
> Jouez de manière responsable : [joueurs-info-service.fr](https://www.joueurs-info-service.fr) — 09 74 75 13 13.

## Installation

```bash
pip install -r requirements.txt   # requests + beautifulsoup4
# optionnel, si une archive FDJ contient un .xlsx : pip install openpyxl
```

Python ≥ 3.10. Aucune autre dépendance : les statistiques (chi², gamma incomplet, etc.)
sont calculées en stdlib.

## Utilisation

```bash
# Lister les jeux supportés, leurs règles et les cotes du rang 1
python -m lotagent jeux

# Télécharger + normaliser l'historique complet d'un jeu (mis en cache dans data/)
python -m lotagent fetch --jeu loto
python -m lotagent fetch --jeu euromillions
python -m lotagent fetch --jeu eurodreams

# Statistiques de l'historique (fréquences, retards, test du chi² d'uniformité)
python -m lotagent stats --jeu loto --derniers 500

# Proposer des grilles pour le prochain tirage
python -m lotagent proposer --jeu loto --grilles 5
python -m lotagent proposer --jeu euromillions --grilles 3 --methodes frequence,markov,paires --poids markov=2
python -m lotagent proposer --jeu eurodreams --grilles 10 --seed 42

# Backtest walk-forward : quelles méthodes s'en sortent le mieux sur le passé ?
python -m lotagent backtest --jeu loto --depuis 500
```

Options communes : `--data-dir` (cache, défaut `data/`), `--csv <fichier>` pour
travailler **hors-ligne** à partir d'un CSV local, `--force` pour retélécharger.

### Méthodes disponibles (`--methodes`)

| méthode | principe |
|---|---|
| `frequence` | numéros « chauds » (fréquences observées) |
| `tendance` | fréquences pondérées par récence (décroissance exponentielle) |
| `chi2` | numéros en sur-représentation par rapport à l'uniformité (test du chi²) |
| `retard` | numéros « en retard » (gambler's fallacy — contre-exemple documenté) |
| `paires` | co-occurrences fréquentes de paires de numéros |
| `markov` | chaîne de Markov du 1er ordre conditionnée par le dernier tirage |
| `aleatoire` | témoin à score constant (baseline) |

Plusieurs méthodes peuvent être combinées : chaque méthode note un pool de grilles
candidates (normalisation min-max), puis un **score combiné pondéré** (`--poids`)
classe les grilles ; les grilles retenues sont les plus distinctes possible.

## Sources de données

Pages « historique » officielles de la FDJ (archives ZIP par période contenant des CSV) :

- LOTO : <https://www.fdj.fr/jeux-de-tirage/loto/historique> (depuis 1976 ; format 5 boules + Chance depuis le 21/10/2019)
- EuroMillions : <https://www.fdj.fr/jeux-de-tirage/euromillions-my-million/historique> (depuis février 2004)
- EuroDreams : <https://www.fdj.fr/jeux-de-tirage/eurodreams/historique> (depuis novembre 2023)

Le fetcher scrape la page, télécharge chaque ZIP une seule fois (cache `data/raw/`),
normalise tous les tirages valides et écrit `data/<jeu>.csv` au format canonique
`date;main_1;...;extra_1;...`.

## Architecture

```
lotagent/
  games.py      règles des 3 jeux (nombres, plages, cotes, URL d'archive)
  models.py     Draw (tirage) et Grid (grille proposée + scores)
  parsers.py    lecture CSV FDJ (;, virgule, accents, .xlsx optionnel) + format canonique
  fetcher.py    scraping des pages historique FDJ, téléchargement ZIP, cache
  stats.py      fréquences, retards, paires, Markov, chi² (p-valeur via gamma incomplet)
  methods/      registre de méthodes de scoring (base + implémentations)
  engine.py     pool de candidats, scoring multi-méthodes pondéré, sélection diversifiée
  backtest.py   évaluation walk-forward vs baseline aléatoire
  report.py     affichage + avertissement de jeu responsable
  cli.py        commandes jeux / fetch / stats / proposer / backtest
tests/          tests unittest (données synthétiques, aucun accès réseau)
```

## Tests

```bash
python -m unittest discover -s tests -v
```

Les tests n'accèdent jamais au réseau : parsing de fixtures au format FDJ, zips
construits en mémoire, historiques synthétiques, CLI lancée en subprocess avec `--csv`.

## Limites connues

- Le téléchargement FDJ nécessite un accès Internet ; en sandbox hors-ligne, utiliser
  `--csv` avec un export manuel des archives FDJ.
- Les archives les plus anciennes du LOTO (avant octobre 2019) utilisent l'ancien
  format 6 boules + complémentaire : elles sont ignorées pour le jeu LOTO actuel.
- Le site fdj.fr pouvant changer de structure, le fetcher lève une erreur explicite
  si plus aucun lien `.zip` n'est trouvé sur la page historique.
