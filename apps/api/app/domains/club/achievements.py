"""Livello e medaglie dell'atleta: la parte "gioco" del portale.

Niente qui è salvato. Livello e medaglie si ricalcolano da presenze, cinture
e risultati di gara ogni volta che servono: un risultato corretto o una
presenza tolta li aggiornano senza che nessuno debba ricordarselo.

L'esperienza (XP) premia le tre cose che fanno crescere un judoka, con pesi
scelti perché nessuna delle tre basti da sola a salire di livello in fretta:
allenarsi con costanza, passare di grado, gareggiare.
"""

from dataclasses import dataclass

from app.domains.club import belts as belts_catalog

XP_PER_ATTENDANCE = 10
XP_PER_BELT = 150
#: I punti ranking (da sempre) valgono come XP, uno a uno.
XP_PER_RANKING_POINT = 1


def xp_for_level(level: int) -> int:
    """L'XP che serve per arrivare a `level` (il livello 1 parte da 0).
    Cresce in modo quadratico: 100, 300, 600, 1000... ogni livello chiede
    un po' più del precedente, come in ogni gioco."""
    return 50 * level * (level - 1)


def level_for(xp: int) -> int:
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def experience(*, attendances: int, belts_earned: int, ranking_points: int) -> dict:
    """`belts_earned` sono i passaggi di grado: la cintura di partenza non conta."""
    xp = attendances * XP_PER_ATTENDANCE + belts_earned * XP_PER_BELT + ranking_points * XP_PER_RANKING_POINT
    level = level_for(xp)
    floor, ceiling = xp_for_level(level), xp_for_level(level + 1)
    return {
        "xp": xp,
        "level": level,
        "level_xp_floor": floor,
        "next_level_xp": ceiling,
        "progress": round((xp - floor) / (ceiling - floor), 4),
    }


@dataclass(frozen=True)
class Achievement:
    code: str
    label: str
    description: str
    #: Che cosa si conta e fino a quanto: serve alla barra "3 su 10".
    metric: str
    target: int


ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement("FIRST_TRAINING", "Primo allenamento", "La prima presenza sul tatami.", "attendances", 1),
    Achievement("ATTENDANCE_10", "Costante", "10 allenamenti.", "attendances", 10),
    Achievement("ATTENDANCE_50", "Instancabile", "50 allenamenti.", "attendances", 50),
    Achievement("ATTENDANCE_100", "Cuore di judoka", "100 allenamenti.", "attendances", 100),
    Achievement("NEW_BELT", "Nuova cintura", "Il primo passaggio di grado.", "belts_earned", 1),
    Achievement("FIRST_COMPETITION", "In gara", "La prima gara disputata.", "competitions", 1),
    Achievement("FIRST_PODIUM", "Sul podio", "Il primo podio in gara.", "podiums", 1),
    Achievement("GOLD_MEDAL", "Medaglia d'oro", "Il primo oro in gara.", "gold", 1),
    Achievement("FIVE_PODIUMS", "Collezionista", "5 podi in gara.", "podiums", 5),
    Achievement("BLACK_BELT", "Cintura nera", "La cintura nera.", "black_belt", 1),
)


def achievements(*, attendances: int, belts_earned: int, current_belt: str | None, totals: dict) -> list[dict]:
    """`totals` sono i conteggi da sempre di competitions.athlete_points."""
    metrics = {
        "attendances": attendances,
        "belts_earned": belts_earned,
        "competitions": totals.get("competitions", 0),
        "podiums": totals.get("gold", 0) + totals.get("silver", 0) + totals.get("bronze", 0),
        "gold": totals.get("gold", 0),
        "black_belt": 1 if current_belt and belts_catalog.is_black(current_belt) else 0,
    }
    return [
        {
            "code": a.code,
            "label": a.label,
            "description": a.description,
            "earned": metrics[a.metric] >= a.target,
            "current": min(metrics[a.metric], a.target),
            "target": a.target,
        }
        for a in ACHIEVEMENTS
    ]
