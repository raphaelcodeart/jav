"""I colori del club sulla sua pagina pubblica: la pagina del club diventa la
sua pagina, con i suoi colori, e resta leggibile qualunque colore scelga la
segreteria. Specifica: docs/club-portal.md, "Sito pubblico" → "La pagina
del club".

La segreteria sceglie tre colori (`club_sites.brand_*`):

- **principale**: la copertina, i bottoni, i titoli;
- **secondario**: le luci sfumate della copertina e i fondi delle sezioni;
- **accento**: ciò che deve saltare all'occhio sulla copertina scura (il
  bottone "Inscrever", le scritte piccole in alto).

Il browser non decide niente: il tema arriva già calcolato dall'API
(`theme`), con il colore del testo leggibile su ogni fondo (il bianco o il
quasi nero, quello che contrasta di più) e le varianti più scure o più
chiare quando un colore da solo non si leggerebbe (WCAG AA, 4,5:1 per il
testo). Un club senza colori ha quelli di JudoArteVida. L'editor della
segreteria rifà lo stesso calcolo in `apps/dashboard/lib/brand.ts` per
l'anteprima dal vivo: le due versioni devono restare uguali.
"""

import re

#: I colori di JudoArteVida: il rosso-arancio di "JUDO" e il giallo di "ARTE".
JAV_PRIMARY = "#E13F22"
JAV_SECONDARY = "#F3E017"
JAV_ACCENT = "#F3E017"
WHITE = "#FFFFFF"
#: Il quasi nero del sito (ink-950): il testo scuro sui fondi chiari.
INK = "#0A0A0A"
#: Il contrasto minimo per il testo normale (WCAG 2.1 AA).
AA_TEXT = 4.5
#: Sotto questo contrasto due colori vicini si confondono (un bottone
#: accento sulla copertina del colore principale non si vedrebbe).
DISTINCT = 1.6

BRAND_FIELDS = ("brand_primary", "brand_secondary", "brand_accent")
_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class BrandColorError(ValueError):
    """Un colore che non è un colore: il messaggio è per la segreteria."""


def normalize_hex(value: str | None) -> str | None:
    """"#e13f22", "E13F22", "#e32" → "#E13F22" / "#EE3322"; vuoto → None.
    Si salva sempre nella stessa forma: confronti e CSS non devono indovinare."""
    if value is None or not value.strip():
        return None
    match = _HEX.match(value.strip())
    if match is None:
        raise BrandColorError(
            f"«{value.strip()[:20]}» non è un colore: scegline uno dalla tavolozza o scrivilo come #E13F22."
        )
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return f"#{digits.upper()}"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    # Metà in su, come Math.round dell'anteprima (lib/brand.ts): round() di
    # Python arrotonda al pari e i due calcoli darebbero colori diversi.
    return "#" + "".join(f"{max(0, min(255, int(c + 0.5))):02X}" for c in rgb)


def luminance(hex_color: str) -> float:
    """La luminanza relativa (WCAG 2.1)."""
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(hex_color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str, b: str, weight: float) -> str:
    """`weight` di `b` dentro `a` (0 = a, 1 = b)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * weight for x, y in zip(ra, rb, strict=True)))


def readable_on(background: str) -> str:
    """Il colore del testo su un fondo: bianco o quasi nero, quello che
    contrasta di più. Con uno dei due si arriva sempre almeno a ~4,4:1."""
    return WHITE if contrast(background, WHITE) >= contrast(background, INK) else INK


def _toward(color: str, target: str, against: str, minimum: float) -> str:
    """Il colore, spostato a piccoli passi verso `target` finché contrasta
    almeno `minimum` con `against`. Resta riconoscibile: si ferma al primo
    passo che basta."""
    if contrast(color, against) >= minimum:
        return color
    for step in range(1, 21):
        candidate = mix(color, target, step / 20)
        if contrast(candidate, against) >= minimum:
            return candidate
    return target


def theme(primary: str | None, secondary: str | None, accent: str | None) -> dict:
    """Il tema della pagina: i tre colori (con i ripieghi), il testo da usare
    sopra ognuno e le varianti per i casi in cui il colore da solo non si
    legge. Un colore mancante prende il posto dell'altro prima di ricadere
    su JudoArteVida: un club con un colore solo ha comunque una pagina sua."""
    p = primary or JAV_PRIMARY
    s = secondary or accent or (JAV_SECONDARY if primary is None else p)
    a = accent or secondary or (JAV_ACCENT if primary is None else readable_on(p))
    # La copertina porta testo bianco: il suo colore di partenza si scurisce
    # quanto serve (un giallo pallido diventa un ocra), quello d'arrivo è
    # sempre scuro.
    cover_from = _toward(p, INK, WHITE, 3.0)
    warnings = []
    if contrast(p, WHITE) < AA_TEXT:
        warnings.append("PRIMARY_DARKENED")
    if contrast(a, cover_from) < DISTINCT:
        warnings.append("ACCENT_LIKE_PRIMARY")
    return {
        "primary": p,
        "secondary": s,
        "accent": a,
        "on_primary": readable_on(p),
        "on_accent": readable_on(a),
        # Titoli e link sul fondo bianco della pagina.
        "primary_text": _toward(p, INK, WHITE, AA_TEXT),
        # Le scritte piccole sulla copertina scura.
        "accent_on_dark": _toward(a, WHITE, INK, AA_TEXT),
        "cover_from": cover_from,
        "cover_to": mix(cover_from, INK, 0.65),
        "custom": primary is not None,
        "warnings": warnings,
    }


def site_theme(site) -> dict:
    return theme(site.brand_primary, site.brand_secondary, site.brand_accent)
