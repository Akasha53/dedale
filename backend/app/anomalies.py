"""Comportement anormal d'un agent interne : écart à son habitude.

Pour chaque agent (`details.agent` annoncé par la passerelle), le backend apprend une
habitude à partir de ses appels d'outil : appels par minute active, outils utilisés, volume
lu par appel et par outil. Une fois l'habitude assez fournie (MIN_APPELS appels sur au moins
MIN_MINUTES minutes différentes), trois écarts ouvrent une alerte :

- pic d'appels : au moins FACTEUR_PIC fois la moyenne par minute (et PLANCHER_PIC appels)
  dans les 60 dernières secondes ;
- outil jamais utilisé : l'agent appelle un outil absent de son habitude ;
- volume lu multiplié par FACTEUR_VOLUME : un appel demande au moins dix fois le volume
  moyen de cet outil (et PLANCHER_VOLUME éléments).

Le temps est celui des événements (horodatage de la passerelle), pas l'horloge du backend :
une habitude se rejoue à l'identique au redémarrage, et un script de démonstration peut
poser une heure d'activité passée en quelques secondes.

L'état n'est pas persisté : il se reconstruit en relisant le journal des événements du
Store, dans l'ordre des identifiants, avec exactement les mêmes décisions qu'en direct.
Un appel anormal n'entre pas dans l'habitude.
"""

from __future__ import annotations

import math
import weakref
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import inventaire

MIN_APPELS = 20
MIN_MINUTES = 5
FENETRE_S = 60.0
FACTEUR_PIC = 5
PLANCHER_PIC = 10
FACTEUR_VOLUME = 10
PLANCHER_VOLUME = 20
MIN_ECHANTILLONS_VOLUME = 5
CLES_VOLUME = ("lignes", "nb_lignes", "limite", "nombre", "quantite", "n")

LIBELLES = {
    "pic_appels": "pic d'appels",
    "outil_inhabituel": "outil jamais utilisé",
    "volume_lu": "volume lu inhabituel",
}
_RANG = {"faible": 1, "moyenne": 2}


def _epoch(horodatage) -> float | None:
    if not isinstance(horodatage, str) or not horodatage:
        return None
    try:
        dt = datetime.fromisoformat(horodatage.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def _minute(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M")


def volume(details: dict) -> int | None:
    """Volume demandé ou lu par un appel : `volume_lu`, sinon un paramètre de taille."""
    v = details.get("volume_lu")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
        return int(v)
    params = details.get("parametres")
    if isinstance(params, dict):
        for cle in CLES_VOLUME:
            x = params.get(cle)
            if isinstance(x, bool):
                continue
            if isinstance(x, (int, float)) and x >= 0:
                return int(x)
            if isinstance(x, str) and x.strip().isdigit():
                return int(x.strip())
    return None


def est_appel(ev: dict) -> bool:
    details = ev.get("details") or {}
    return (ev.get("source") == "interne" and ev.get("type") == "appel_outil"
            and bool(ev.get("outil")) and details.get("maillon") != "intention")


@dataclass
class Habitude:
    minutes: dict = field(default_factory=dict)        # "AAAA-MM-JJTHH:MM" -> appels
    outils: dict = field(default_factory=dict)         # outil -> appels
    volumes: dict = field(default_factory=dict)        # outil -> [somme, n]
    recents: deque = field(default_factory=lambda: deque(maxlen=2000))
    appels: int = 0                                    # appels entrés dans l'habitude
    vus: int = 0                                       # tous les appels, anormaux compris
    alertes: int = 0

    def prete(self) -> bool:
        return self.appels >= MIN_APPELS and len(self.minutes) >= MIN_MINUTES

    def par_minute(self, avant: float | None = None) -> float:
        """Appels par minute active. Avec `avant`, seules les minutes antérieures à cet instant
        comptent : les premiers appels d'une rafale ne font pas monter leur propre seuil."""
        minutes = self.minutes
        if avant is not None:
            limite = _minute(avant)
            anciennes = {k: n for k, n in minutes.items() if k < limite}
            minutes = anciennes or minutes
        return sum(minutes.values()) / len(minutes) if minutes else 0.0

    def resume(self) -> dict:
        return {
            "prete": self.prete(),
            "appels_observes": self.vus,
            "appels_dans_l_habitude": self.appels,
            "minutes_actives": len(self.minutes),
            "appels_par_minute": round(self.par_minute(), 2),
            "outils": sorted(self.outils, key=lambda o: (-self.outils[o], o)),
            "volume_moyen": {o: round(s / n, 1) for o, (s, n) in sorted(self.volumes.items()) if n},
            "alertes": self.alertes,
            "seuils": {"min_appels": MIN_APPELS, "min_minutes": MIN_MINUTES,
                       "facteur_pic": FACTEUR_PIC, "plancher_pic": PLANCHER_PIC,
                       "facteur_volume": FACTEUR_VOLUME, "plancher_volume": PLANCHER_VOLUME},
        }


class Suivi:
    """Habitudes de tous les agents d'un Store, tenues à jour au fil du journal."""

    def __init__(self) -> None:
        self.vus = 0
        self.habitudes: dict[str, Habitude] = {}
        self.deja: set[tuple] = set()  # (session, code, outil) déjà signalés

    def _agent(self, store, ev: dict) -> str | None:
        sess = store.sessions.get(ev.get("session_id"))
        agent = sess.agent if sess is not None else None
        if agent is None:
            brut = (ev.get("details") or {}).get("agent")
            agent = brut if isinstance(brut, str) and brut.strip() else None
        return agent

    def _detecter(self, h: Habitude, ev: dict, t: float) -> tuple[dict | None, bool]:
        """(anomalie ou None, appel à garder hors de l'habitude ?)."""
        details = ev.get("details") or {}
        sid, outil = ev.get("session_id"), ev.get("outil")
        if not h.prete():
            return None, False
        trouvailles: list[dict] = []
        exclure = False

        dans_fenetre = 1 + sum(1 for x in h.recents if t - FENETRE_S <= x <= t)
        moyenne = h.par_minute(avant=t - FENETRE_S)
        seuil = max(PLANCHER_PIC, math.ceil(FACTEUR_PIC * moyenne))
        if dans_fenetre >= seuil:
            exclure = True
            if (sid, "pic_appels", None) not in self.deja:
                self.deja.add((sid, "pic_appels", None))
                trouvailles.append({
                    "code": "pic_appels", "gravite": "moyenne", "mesure": dans_fenetre,
                    "habitude": round(moyenne, 1), "facteur": round(dans_fenetre / max(moyenne, 0.1), 1),
                    "raison": (f"{dans_fenetre} appels en une minute, contre {moyenne:.0f} par minute "
                               "d'habitude"),
                })

        if outil not in h.outils:
            exclure = True
            if (sid, "outil_inhabituel", outil) not in self.deja:
                self.deja.add((sid, "outil_inhabituel", outil))
                scope = details.get("scope_requis")
                sensible = inventaire.outil_sortant(outil) or scope in inventaire.SENSIBLES
                trouvailles.append({
                    "code": "outil_inhabituel", "gravite": "moyenne" if sensible else "faible",
                    "outil": outil, "mesure": 0, "habitude": None, "facteur": None,
                    "raison": f"outil {outil} jamais utilisé par cet agent jusqu'ici",
                })

        v = volume(details)
        somme_n = h.volumes.get(outil)
        if v is not None and somme_n and somme_n[1] >= MIN_ECHANTILLONS_VOLUME:
            moyenne_v = somme_n[0] / somme_n[1]
            if v >= PLANCHER_VOLUME and v >= FACTEUR_VOLUME * max(moyenne_v, 1):
                exclure = True
                if (sid, "volume_lu", outil) not in self.deja:
                    self.deja.add((sid, "volume_lu", outil))
                    facteur = v / max(moyenne_v, 1)
                    trouvailles.append({
                        "code": "volume_lu", "gravite": "moyenne", "outil": outil, "mesure": v,
                        "habitude": round(moyenne_v, 1), "facteur": round(facteur, 1),
                        "raison": (f"{v} éléments demandés à {outil} en un appel, contre "
                                   f"{moyenne_v:.0f} d'habitude (x{facteur:.0f})"),
                    })
        if not trouvailles:
            return None, exclure
        gravite = max((a["gravite"] for a in trouvailles), key=lambda g: _RANG[g])
        return {
            "code": trouvailles[0]["code"],
            "codes": [a["code"] for a in trouvailles],
            "gravite": gravite,
            "raison": " ; ".join(a["raison"] for a in trouvailles),
            "signaux": trouvailles,
            "libelle": ", ".join(LIBELLES[a["code"]] for a in trouvailles),
        }, exclure

    def traiter(self, store, ev: dict, *, signaler: bool) -> dict | None:
        """Passe un événement dans l'habitude de son agent ; renvoie l'anomalie s'il y en a une."""
        if not est_appel(ev):
            return None
        agent = self._agent(store, ev)
        t = _epoch(ev.get("horodatage"))
        if agent is None or t is None:
            return None
        h = self.habitudes.setdefault(agent, Habitude())
        # En rejeu (`signaler=False`), les décisions sont les mêmes qu'en direct ; seul
        # l'appelant direct écrit l'anomalie dans l'événement.
        anomalie, exclure = self._detecter(h, ev, t)
        h.recents.append(t)
        h.vus += 1
        if anomalie is not None:
            h.alertes += 1
            anomalie["agent"] = agent
        if not exclure and anomalie is None:
            h.appels += 1
            minute = _minute(t)
            h.minutes[minute] = h.minutes.get(minute, 0) + 1
            h.outils[ev["outil"]] = h.outils.get(ev["outil"], 0) + 1
            v = volume(ev.get("details") or {})
            if v is not None:
                somme_n = h.volumes.setdefault(ev["outil"], [0, 0])
                somme_n[0] += v
                somme_n[1] += 1
        return anomalie

    def rattraper(self, store, jusqu_a: int) -> None:
        """Rejoue sans rien écrire les événements que ce suivi n'a pas encore vus."""
        for i in range(self.vus + 1, jusqu_a + 1):
            ev = store.evenements.get(i)
            if ev is not None:
                self.traiter(store, ev, signaler=False)
        self.vus = max(self.vus, jusqu_a)


_suivis: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _suivi(store) -> Suivi:
    suivi = _suivis.get(store)
    if suivi is None:
        suivi = _suivis[store] = Suivi()
    return suivi


def vider(store=None) -> None:
    """Oublie les habitudes (tests, remise à zéro du Store)."""
    if store is None:
        _suivis.clear()
    else:
        _suivis.pop(store, None)


def examiner(store, enreg: dict) -> dict | None:
    """Appelé à l'ingestion d'un événement déjà rangé dans le Store. Renvoie l'anomalie."""
    suivi = _suivi(store)
    eid = enreg.get("id") or 0
    if eid <= suivi.vus:
        # Le Store a été vidé (tests) ou remplacé : on repart de zéro.
        suivi = _suivis[store] = Suivi()
    suivi.rattraper(store, eid - 1)
    suivi.vus = eid
    return suivi.traiter(store, enreg, signaler=True)


def habitude(store, agent_id: str) -> dict:
    """Habitude d'un agent, à jour du journal (lecture de l'inventaire)."""
    suivi = _suivi(store)
    dernier = max(store.evenements, default=0)
    if dernier < suivi.vus:
        suivi = _suivis[store] = Suivi()
    suivi.rattraper(store, dernier)
    h = suivi.habitudes.get(agent_id)
    return (h or Habitude()).resume()
