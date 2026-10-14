"""Dall'altezza alla taglia del judogi.

Le taglie dei judogi si danno in centimetri d'altezza, a passi di 10: un
judogi "150" è per chi è alto circa 150 cm. **Si arrotonda per eccesso**
alla decina successiva, per due ragioni che ogni istruttore ripete ai
genitori: il cotone si ritira un poco ai primi lavaggi, e i bambini
crescono. Chi è alto esattamente 150 prende il 150.

| Altezza       | Taglia (cm) | Numero (molte marche) |
|---------------|-------------|-----------------------|
| fino a 100    | 100         | —                     |
| 101–110       | 110         | —                     |
| 111–120       | 120         | 000                   |
| 121–130       | 130         | 00                    |
| 131–140       | 140         | 0                     |
| 141–150       | 150         | 1                     |
| 151–160       | 160         | 2                     |
| 161–170       | 170         | 3                     |
| 171–180       | 180         | 4                     |
| 181–190       | 190         | 5                     |
| 191–200       | 200         | 6                     |
| oltre 200     | 200 (la più grande; si chiede al club) |

Il "numero" (0, 1, 2…) non è uguale per tutte le marche: serve solo a
riconoscere una variante scritta così nel catalogo ("Taglia 2"). Quando la
variante dice i centimetri, valgono i centimetri.
"""

import re

from app.domains.javbot.intents import normalize

MIN_SIZE_CM = 100
MAX_SIZE_CM = 200
#: Il numero di taglia -> i centimetri, come lo scrivono Mizuno, Fuji e altre.
NUMBER_TO_CM = {"000": 120, "00": 130, "0": 140, "1": 150, "2": 160, "3": 170, "4": 180, "5": 190, "6": 200}
CM_TO_NUMBER = {cm: number for number, cm in NUMBER_TO_CM.items()}


def size_for_height(height_cm: int) -> int:
    """La taglia in cm: la decina successiva, tra 100 e 200."""
    rounded = -(-height_cm // 10) * 10
    return max(MIN_SIZE_CM, min(MAX_SIZE_CM, rounded))


def size_number(size_cm: int) -> str | None:
    return CM_TO_NUMBER.get(size_cm)


def variant_size_cm(label: str | None) -> int | None:
    """La taglia scritta su una variante del catalogo, in cm: "150",
    "150 cm", "Tg. 160", "Taglia 2". None se la variante non è una taglia."""
    norm = normalize(label or "")
    for match in re.finditer(r"(?<![0-9])([0-9]{2,3})(?![0-9])", norm):
        cm = int(match.group(1))
        if 90 <= cm <= 215:
            return cm
    coded = re.fullmatch(r"(?:tg\.?|taglia|tamanho|tam\.?|size|t\.?)?\s*(000|00|0|1|2|3|4|5|6)", norm)
    if coded:
        return NUMBER_TO_CM[coded.group(1)]
    return None
