"""Quanto costa: sconti sulla mensilità, iscrizione annuale a pro rata, quota
socio del genitore. Specifica: docs/club-portal.md, "Prezzi e sconti".

Tutte le regole stanno qui, come funzioni pure dei parametri del club
(`clubs.settings["pricing"]`): chi genera le quote (service.py) chiede il
prezzo e lo congela sulla quota, nessuno lo ricalcola dopo (CLAUDE.md §5).

- **Mensilità**: listino del piano, meno la percentuale dell'escalão (A/B/C,
  il judo adattato vale come A; con entrambi vale il maggiore, non si
  sommano), poi meno lo sconto famiglia in euro se la
  famiglia ha abbastanza atleti attivi. Mai sotto zero.
- **Iscrizione** (anno solare, 1 gennaio–31 dicembre): l'importo annuo del
  piano, per i mesi che restano dell'anno contando quello d'ingresso. Nessuno
  sconto: comprende quota di socio, taxa de falta, assicurazione e
  iscrizioni a federazione e associazione distrettuale.
- **Quota socio del genitore**: chi ha un atleta minorenne è socio anch'egli,
  una volta per famiglia e per anno, a pro rata come l'iscrizione. Non la paga
  chi è già atleta (la sua iscrizione la comprende).
"""

from datetime import date

from app.domains.club import kinds, seasons
from app.domains.club.models import SOCIAL_TIERS, Club, ClubAthlete

#: Sotto questa età (al giorno in cui la quota si emette) un genitore deve
#: essere socio.
MINOR_AGE = 18

DEFAULT_PRICING: dict = {
    #: Percentuale di sconto sulla mensilità per escalão.
    "tier_discount_pct": {"A": 25, "B": 0, "C": 0},
    #: Sconto in centesimi su ogni mensilità quando la famiglia ha almeno
    #: `family_min_athletes` atleti attivi.
    "family_discount_cents": 500,
    "family_min_athletes": 2,
    #: Credito nel wallet di chi ha invitato, per ogni mensilità pagata da
    #: un atleta della famiglia invitata (club/referrals.py).
    "referral_credit_cents": 500,
    #: Quota socio annua del genitore di un atleta minorenne.
    "parent_member_fee_cents": 6000,
    #: Che cosa comprende l'iscrizione, come lo leggono le famiglie.
    "enrollment_includes": (
        "Quota di socio, taxa de falta, assicurazione sportiva, iscrizione alla federazione "
        "e all'associazione distrettuale"
    ),
}


def get_pricing(club: Club | None) -> dict:
    """I parametri del club, con il default per ciò che il club non ha
    ancora impostato."""
    saved = ((club.settings or {}).get("pricing") or {}) if club is not None else {}
    kind = club.kind if club is not None else kinds.CLUB
    # I default del tipo di unità (nei corsi JAV gli sconti partono spenti),
    # poi ciò che la segreteria ha scelto, poi ciò che per quel tipo è una
    # regola e non si sceglie (kinds.py).
    defaults = {**DEFAULT_PRICING, **kinds.PRICING_DEFAULTS.get(kind, {})}
    out = {**defaults, **{k: v for k, v in saved.items() if k in DEFAULT_PRICING}}
    out["tier_discount_pct"] = {**defaults["tier_discount_pct"], **(saved.get("tier_discount_pct") or {})}
    out.update(kinds.PRICING_FIXED.get(kind, {}))
    return out


def validate_pricing(changes: dict) -> dict:
    """Solo valori sensati: una percentuale tra 0 e 100, importi non negativi.
    Restituisce i soli campi noti. Solleva ValueError con un messaggio per
    chi usa l'app."""
    out: dict = {}
    for key, value in changes.items():
        if key not in DEFAULT_PRICING or value is None:
            continue
        if key == "tier_discount_pct":
            tiers = {}
            for tier, pct in (value or {}).items():
                if tier not in SOCIAL_TIERS:
                    raise ValueError("Gli escalão sono A, B e C.")
                if not isinstance(pct, int) or not 0 <= pct <= 100:
                    raise ValueError("Lo sconto di un escalão è una percentuale tra 0 e 100.")
                tiers[tier] = pct
            out[key] = tiers
        elif key == "enrollment_includes":
            out[key] = str(value).strip()[:300]
        elif key == "family_min_athletes":
            if not isinstance(value, int) or not 2 <= value <= 10:
                raise ValueError("Lo sconto famiglia parte da almeno 2 atleti.")
            out[key] = value
        else:
            if not isinstance(value, int) or not 0 <= value <= 10_000_000:
                raise ValueError("Gli importi non possono essere negativi.")
            out[key] = value
    return out


def _tier_discount(athlete: ClubAthlete, pricing: dict) -> tuple[int, str | None]:
    """(percentuale, etichetta) dello sconto dell'atleta. Escalão e judo
    adattato non si sommano: vale il maggiore. Con i default (A è lo sconto
    più alto) è sempre quello dell'A; conta solo se un club desse a B o C
    più dell'A, e allora un atleta di judo adattato non deve perderci."""
    pcts = pricing["tier_discount_pct"]
    tier = athlete.social_tier
    own = pcts.get(tier, 0) if tier else 0
    adapted = pcts.get("A", 0) if athlete.adapted_judo else 0
    if athlete.adapted_judo and adapted >= own:
        return adapted, "Judo adattato"
    return own, f"Escalão {tier}" if tier else None


def _euro(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


def monthly_price(*, list_cents: int, athlete: ClubAthlete, family_size: int, pricing: dict) -> dict:
    """Il prezzo della mensilità: {amount_cents, gross_amount_cents,
    discount_cents, discount_note}. Prima la percentuale, poi gli euro."""
    amount = list_cents
    notes: list[str] = []
    pct, label = _tier_discount(athlete, pricing)
    if pct:
        amount -= round(list_cents * pct / 100)
        notes.append(f"{label} −{pct}%")
    family_cents = pricing["family_discount_cents"]
    if family_cents and family_size >= pricing["family_min_athletes"] and amount > 0:
        cut = min(family_cents, amount)
        amount -= cut
        notes.append(f"Famiglia −{_euro(cut)}")
    return {
        "amount_cents": amount,
        "gross_amount_cents": list_cents,
        "discount_cents": list_cents - amount,
        "discount_note": " · ".join(notes) or None,
    }


def prorated(annual_cents: int, *, start_month: int) -> int:
    """L'anno solare dal mese d'ingresso a dicembre, mese d'ingresso
    compreso: a settembre si pagano 4/12."""
    return round(annual_cents * (13 - start_month) / 12)


def period_label(year: int, start_month: int) -> str:
    """"2026" per l'anno intero, "2026 (set–dic)" per un ingresso a metà anno."""
    if start_month == 1:
        return str(year)
    return f"{year} ({seasons.MONTH_NAMES[start_month - 1][:3]}–dic)"


def needs_parent_membership(athletes: list[ClubAthlete], *, on: date) -> bool:
    """Una famiglia con almeno un atleta attivo minorenne, in cui il genitore
    non sia già atleta (la sua iscrizione comprende già la quota di socio)."""
    active = [a for a in athletes if a.status == "ACTIVE"]
    if any(a.is_self for a in active):
        return False
    return any(seasons.age_on(a.birth_date, on) < MINOR_AGE for a in active)
