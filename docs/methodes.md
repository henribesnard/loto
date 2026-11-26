# Revue des méthodes statistiques appliquées aux jeux de tirage

Ce document résume les publications et audits consultés sur les statistiques des jeux
de tirage (LOTO, EuroMillions, EuroDreams et loteries étrangères comparables), les
méthodes implémentées dans `lotagent`, et la **politique de rétention** : seules les
méthodes qui se comportent le mieux *relativement aux autres* lors du backtest
walk-forward sont conservées dans les presets par défaut — avec une limite théorique
impossible à franchir, explicitée ci-dessous.

## 1. Fondement mathématique : pourquoi aucune méthode ne « prédit »

Les tirages de la FDJ sont des **événements aléatoires indépendants et uniformes**
(boules remises en machine, génération auditée). Conséquences :

- **Gambler's fallacy** (« un numéro absent depuis longtemps est « dû »") : faux.
  Un numéro absent depuis 60 tirages a exactement la même probabilité au prochain
  tirage que n'importe quel autre (Tversky & Kahneman, 1971 ; Clotfelter & Cook, 1993 ;
  Suetens, Galbo-Jørgensen & Tyran, *Predicting Lotto Numbers*, natural experiment).
- **Hot-hand** (« un numéro sorti récemment va resservir ») : faux pour la même raison.
- Loi des grands nombres : sur un grand nombre de tirages, les fréquences convergent
  vers l'uniformité, mais les écarts à court terme sont du **bruit statistique**.

Consensus de la littérature et des audits indépendants :

- Peter Stone (UT Austin, 2018) : machine learning sur loterie américaine → **aucune
  corrélation détectable** entre historique et tirage suivant.
- Audits statistiques longs (ex. 50 ans de Loto, 28 tests sur 444 tirages ; backtests
  20 ans multi-loteries) : toutes les p-valeurs compatibles avec le hasard pur ;
  « jouer les 5 numéros les plus sortis des 50 derniers tirages » ≈ « jouer les 5 plus
  en retard » ≈ « grille aléatoire » en nombre moyen de bons numéros.
- La FDJ rappelle elle-même sur ses pages statistiques : « il est impossible de donner
  des pronostics fiables ».

**Conséquence pour lotagent** : les scores produits sont des *heuristiques de
préférence* (quels numéros « collent le mieux à l'histoire »), **pas des probabilités
de gain**. Chaque grille valide reste à 1 sur C(49,5)×10 (LOTO), etc. Le backtest
(`python -m lotagent backtest`) le démontre empiriquement sur vos données.

## 2. Méthodes implémentées et leur statut dans la littérature

| méthode (`lotagent`) | idée publiée | statut scientifique |
|---|---|---|
| `frequence` (numéros chauds) | hot numbers | aucune valeur prédictive démontrée (hot-hand fallacy) |
| `retard` (numéros « dus ») | cold numbers / gambler's fallacy | **faux** mathématiquement ; gardé comme contre-exemple |
| `tendance` (pondération récence) | « momentum » court terme | bruit statistique à court terme |
| `chi2` (sur-représentation) | tests d'uniformité des fréquences | valide comme *audit du hasard*, pas comme prédicteur |
| `paires` (co-occurrences) | analyse des combinaisons fréquentes | les paires apparaissent à la fréquence prévue par la combinatoire |
| `markov` (1er ordre) | chaînes de Markov sur les transitions | capture du bruit ; HMM/ANN publiés n'ont pas de pouvoir prédictif validé |
| `aleatoire` | grille au hasard (témoin) | **baseline théorique optimale en espérance** |

Les publications vantant des « systèmes gagnants » ou des IA « qui prédisent le loto »
n'ont jamais été répliquées dans un cadre contrôlé ; les « succès » rapportés sont des
anecdotes (biais de survie) ou des corrélations fallacieuses sur le passé.

## 3. Politique de rétention des méthodes

Puisqu'aucune méthode ne bat le hasard en espérance, la règle appliquée est :

1. chaque méthode est évaluée en **backtest walk-forward** (entraînement strictement
   sur les tirages passés, évaluation sur le tirage suivant) ;
2. on ne retient dans les presets que les méthodes dont la moyenne de bons numéros
   est **≥ baseline aléatoire − marge de bruit** (c'est-à-dire toutes celles qui ne sont
   pas *pires* que le hasard) ;
3. la combinaison multi-méthodes (score pondéré) est préférée à une méthode seule,
   car elle lisse le bruit spécifique à chaque heuristique ;
4. le témoin `aleatoire` reste toujours disponible pour comparaison.

En pratique, sur des tirages équitables, le backtest montre des moyennes toutes
proches de l'espérance théorique (ex. LOTO : 25/49 ≈ 0,51 bon numéro principal), ce
qui est le résultat attendu — et honnêtement rapporté.

## 4. Références

- Tversky & Kahneman (1971), « Belief in the law of small numbers ».
- Clotfelter & Cook (1993), « Anomalies: The Lottery » — gambler's fallacy sur les paris.
- Suetens, Galbo-Jørgensen & Tyran (2016), *Predicting Lotto Numbers: A natural
  experiment on the gambler's fallacy and the hot-hand fallacy*, Journal of Economic Surveys.
- Granic & Lambert (Stanford), *Judgment Error in Lottery Play* — hot-hand côté parieurs.
- Hernandez, *Análisis de resultados de loterías mediante métodos estadísticos y redes
  neuronales* (revue des approches ANN, sans pouvoir prédictif validé).
- Audits indépendants de long terme (50 ans de Loto ; backtests 20 ans multi-loteries) :
  aucune stratégie historique ne surperforme le hasard.
- Pages officielles FDJ (statistiques + historique) : avertissements « jeu de hasard,
  pronostics impossibles ».

## 5. Jeu responsable

Ces outils sont destinés à l'analyse ludique de données publiques. Ne jouez que ce que
vous pouvez perdre, et si le jeu cesse d'être un divertissement :
[joueurs-info-service.fr](https://www.joueurs-info-service.fr) — 09 74 75 13 13
(appel non surtaxé, anonyme et confidentiel).
