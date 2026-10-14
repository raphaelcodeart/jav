"""La scala delle cinture, in un posto solo.

L'ordine della tupla È il grado: tutto ciò che deve sapere se una cintura è
"più alta" di un'altra (la cintura attuale, il controllo su un passaggio di
grado) usa `rank()` e non confronta stringhe. Etichette e colori vivono qui
perché li mostra l'interfaccia, ma li decide il dominio: una cintura
marrone-che-sembra-arancione non è un dettaglio grafico.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Belt:
    code: str
    label: str
    #: Colore principale della cintura (esadecimale), per la striscia sulla card.
    color: str
    #: Secondo colore per le cinture bicolori; None per quelle a tinta unita.
    stripe: str | None = None


BELTS: tuple[Belt, ...] = (
    Belt("WHITE", "Bianca", "#f8fafc"),
    Belt("WHITE_YELLOW", "Bianco-gialla", "#f8fafc", "#facc15"),
    Belt("YELLOW", "Gialla", "#facc15"),
    Belt("YELLOW_ORANGE", "Giallo-arancio", "#facc15", "#f97316"),
    Belt("ORANGE", "Arancio", "#f97316"),
    Belt("ORANGE_GREEN", "Arancio-verde", "#f97316", "#16a34a"),
    Belt("GREEN", "Verde", "#16a34a"),
    Belt("BLUE", "Blu", "#2563eb"),
    Belt("BROWN", "Marrone", "#78350f"),
    *(Belt(f"BLACK_{dan}", f"Nera {dan}° dan", "#111827") for dan in range(1, 11)),
)

BELT_CODES: tuple[str, ...] = tuple(b.code for b in BELTS)
_BY_CODE = {b.code: b for b in BELTS}
_RANK = {b.code: i for i, b in enumerate(BELTS)}

#: La cintura di chi comincia: ogni atleta nuovo la riceve alla creazione,
#: così la "cintura attuale" non è mai vuota.
STARTING_BELT = "WHITE"


def get(code: str) -> Belt:
    return _BY_CODE[code]


def rank(code: str) -> int:
    return _RANK[code]


def is_black(code: str) -> bool:
    return code.startswith("BLACK_")
