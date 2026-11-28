"""Client Winamax : collecte des matchs et cotes via le flux Socket.IO public.

Le site winamax.fr alimente son interface via un serveur Socket.IO (engine.io v4)
exposé sur ``sports-eu-west-3.winamax.fr``. Ce module reproduit le protocole
en transport HTTP *polling* uniquement, sans dépendance externe (urllib de la
stdlib) :

1. Poignée de main GET  → ``sid`` + cookie d'équilibrage AWSALB ;
2. POST ``40``          → connexion au namespace Socket.IO ;
3. POST ``42["m", ...]``→ abonnement aux routes ``sport:<id>`` puis ``match:<id>`` ;
4. Boucle de polling GET → payloads JSON ``{matches, bets, odds, outcomes, ...}``,
   avec réponse ``3`` aux pings ``2`` du serveur.

Identifiants sport Winamax (constatés sur le flux) :
1=Football, 2=Basket, 4=Hockey sur glace, 5=Tennis, 12=Rugby à XV.

Ce client est utilisé par le workflow ``combinis-sportifs`` ; tout l'accès réseau
reste confiné dans une activité. Usage privé et éducatif : les cotes affichées
appartiennent à Winamax et peuvent changer à tout moment.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable, Optional

BASE_HTTP = "https://sports-eu-west-3.winamax.fr/uof-sports-server/socket.io/"
COMMON_QUERY = "language=FR&version=3.9.1&embed=false"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Origin": "https://www.winamax.fr",
    "Referer": "https://www.winamax.fr/",
}

# Identifiants sport ↔ route Winamax
SPORT_IDS: dict[str, int] = {
    "football": 1,
    "basket": 2,
    "hockey": 4,
    "tennis": 5,
    "rugby": 12,
}

MONEYLINE_MARKET_IDS: dict[int, int] = {
    1: 1,    # Football : « Résultat » (1 N 2)
    2: 219,  # Basket : vainqueur du match (2 issues)
    4: 1,    # Hockey : « Résultat » (temps règlementaire 1 N 2)
    5: 186,  # Tennis : vainqueur du match (2 issues)
    12: 1,   # Rugby à XV : « Résultat » (1 N 2)
}


class WinamaxError(RuntimeError):
    """Erreur de communication avec le flux Winamax."""


def nouvel_etat() -> dict[str, dict]:
    """État fusionné des payloads : matches, bets, odds, outcomes, tournaments."""
    return {"matches": {}, "bets": {}, "odds": {}, "outcomes": {}, "tournaments": {}}


def fusionner(state: dict, payload: Any) -> None:
    """Fusionne incrémentalement un payload ``m`` dans l'état (idempotent)."""
    if not isinstance(payload, dict):
        return
    for clee in ("matches", "bets", "outcomes", "tournaments"):
        bloc = payload.get(clee)
        if not isinstance(bloc, dict):
            continue
        cible = state[clee]
        for ident, obj in bloc.items():
            if isinstance(obj, dict):
                cible[ident] = {**cible.get(ident, {}), **obj}
    bloc = payload.get("odds")
    if isinstance(bloc, dict):
        state["odds"].update(bloc)


class _Session:
    """Session engine.io en polling, avec gestion du cookie AWSALB."""

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout
        self.cookies: dict[str, str] = {}
        self.sid: Optional[str] = None

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = dict(HEADERS)
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if extra:
            h.update(extra)
        return h

    def _retenir_cookies(self, info) -> None:
        try:
            items = info.get_all("Set-Cookie") or []
        except AttributeError:
            items = []
        for entete in items:
            partie = entete.split(";")[0]
            if "=" in partie:
                nom, valeur = partie.split("=", 1)
                self.cookies[nom.strip()] = valeur.strip()

    def _url(self, with_sid: bool) -> str:
        params = f"EIO=4&transport=polling&{COMMON_QUERY}&t={time.time_ns() // 1_000_000}"
        if with_sid and self.sid:
            params += f"&sid={urllib.parse.quote(self.sid)}"
        return f"{BASE_HTTP}?{params}"

    def get(self) -> list[str]:
        req = urllib.request.Request(self._url(with_sid=True), headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as rep:
                self._retenir_cookies(rep.headers)
                texte = rep.read().decode("utf-8", "replace")
        except urllib.error.URLError as exc:  # proxy, DNS, timeout…
            raise WinamaxError(f"GET polling Winamax impossible : {exc}") from exc
        return _scinder(texte)

    def post(self, corps: str) -> list[str]:
        req = urllib.request.Request(
            self._url(with_sid=True),
            data=corps.encode("utf-8"),
            headers=self._headers({"Content-Type": "text/plain;charset=UTF-8"}),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as rep:
                texte = rep.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise WinamaxError(f"POST Winamax {exc.code} : {detail}") from exc
        except urllib.error.URLError as exc:
            raise WinamaxError(f"POST polling Winamax impossible : {exc}") from exc
        return _scinder(texte)

    def connecter(self) -> None:
        """Poignée de main + connexion au namespace Socket.IO."""
        req = urllib.request.Request(self._url(with_sid=False), headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as rep:
                self._retenir_cookies(rep.headers)
                texte = rep.read().decode("utf-8", "replace")
        except urllib.error.URLError as exc:
            raise WinamaxError(f"Poignée de main Winamax impossible : {exc}") from exc
        trames = _scinder(texte)
        for trame in trames:
            if trame.startswith("0"):
                try:
                    self.sid = json.loads(trame[1:])["sid"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise WinamaxError("Poignée de main Winamax : format inattendu") from exc
                break
        if not self.sid:
            raise WinamaxError("Poignée de main Winamax : aucun sid reçu")
        reponse = self.post("40")
        if not any(t.startswith("40") or t == "ok" for t in reponse):
            raise WinamaxError(f"Connexion namespace refusée : {reponse[:3]}")

    def emettre_m(self, routes: Iterable[str], pause: float = 0.15) -> None:
        """Émet les abonnements ``["m", {route: ..., requestId: ...}]``."""
        instant = time.time_ns() // 1_000_000
        for index, route in enumerate(routes):
            message = "42" + json.dumps(["m", {"route": route, "requestId": f"r{instant}_{index}"}])
            self.post(message)
            if pause > 0:
                time.sleep(pause)

    def collecter(self, duree_s: float, a_chaque_message: Optional[Callable[[Any], None]] = None) -> int:
        """Boucle de polling pendant ``duree_s`` ; répond aux pings.

        Retourne le nombre de payloads ``m`` traités. ``a_chaque_message``
        (typiquement ``fusionner``) est appelé pour chaque payload utile.
        """
        objectif = time.monotonic() + duree_s
        recus = 0
        while time.monotonic() < objectif:
            try:
                trames = self.get()
            except WinamaxError:
                time.sleep(0.5)
                continue
            for trame in trames:
                if trame == "2":
                    self.post("3")
                    continue
                if not trame.startswith("42"):
                    continue
                try:
                    evenement = json.loads(trame[2:])
                except json.JSONDecodeError:
                    continue
                if not (isinstance(evenement, list) and evenement and evenement[0] == "m"):
                    continue
                payload = evenement[1] if len(evenement) > 1 else {}
                recus += 1
                if a_chaque_message is not None:
                    a_chaque_message(payload)
        return recus


def _scinder(texte: str) -> list[str]:
    """Scinde une réponse polling en trames engine.io (séparateur RS 0x1e)."""
    return [t for t in texte.split("\x1e") if t]


def collecter_matchs(
    sports: list[str],
    duree_s: float = 30.0,
    complement_match_s: float = 30.0,
    routes_matchs: Optional[list[str]] = None,
) -> dict:
    """Ouvre une session, s'abonne aux sports demandés et renvoie l'état fusionné.

    ``routes_matchs`` permet de compléter par des abonnements ``match:<id>``
    (cotes détaillées des matchs qui manquent après le premier passage).
    """
    ids = [SPORT_IDS[s] for s in sports if s in SPORT_IDS]
    if not ids:
        raise WinamaxError(f"Sports inconnus : {sports}")
    session = _Session()
    session.connecter()
    session.emettre_m([f"sport:{i}" for i in ids], pause=0.2)
    etat = nouvel_etat()
    session.collecter(duree_s, lambda p: fusionner(etat, p))
    if routes_matchs:
        session.emettre_m(routes_matchs, pause=0.1)
        session.collecter(complement_match_s, lambda p: fusionner(etat, p))
    return etat
