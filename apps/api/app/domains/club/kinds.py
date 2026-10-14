"""Club ufficiale o "Cursos JAV": le regole che cambiano con il tipo di unità.

JudoArteVida non è un club: gestisce i club e, in più, i **corsi
extrascolastici nelle scuole** (primarie e secondarie che chiedono un corso
di judo). Questi corsi stanno in un'unità sola, un `clubs` con `kind =
JAV_COURSES`, e ogni corso (`club_courses`) è tenuto in una scuola e si
amministra per conto suo: iscritti, presenze, quote, incassi, parte del
treinador. Specifica: docs/club-portal.md, "Cursos JAV".

Le differenze rispetto a un club ufficiale stanno **tutte qui**, come
attributi di `KindRules`: chi ha bisogno di sapere se un'unità ha le cinture
o le gare chiede a `rules_for`, non confronta stringhe sparse per il codice.

- niente cinture, niente gare, niente ranking: sono corsi per bambini, chi
  vuole fare sul serio poi passa a un club;
- iscrizione 0 e quota socio del genitore 0: si paga solo la mensilità
  (default 25 € al mese, un piano modificabile creato con l'unità);
- sconti escalão, famiglia e invito a 0 di default (si possono attivare):
  sono soldi di JAV, decide JAV se farne;
- commissione della piattaforma 0%: i soldi sono già di JAV;
- il treinador responsabile di un corso prende una percentuale degli
  incassi del suo corso (default 50%), invece di essere pagato a ore;
- **gli atleti dell'unità non compaiono mai sul sito pubblico** (ranking,
  judoca, eventi, medaglie, bot), qualunque consenso abbiano: il sito
  mostra solo i corsi (luogo, orario, età), nessuna persona.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.models import Club

CLUB = "CLUB"
JAV_COURSES = "JAV_COURSES"

#: Il nome e l'indirizzo con cui l'unità nasce (si possono cambiare).
COURSES_UNIT_NAME = "Cursos JAV"
COURSES_UNIT_SLUG = "cursos-jav"
#: La mensilità dei corsi nelle scuole, finché JAV non decide altro.
COURSES_MONTHLY_FEE_CENTS = 2500
#: La parte degli incassi di un corso che va al suo treinador.
DEFAULT_COACH_SHARE_PCT = Decimal(50)


@dataclass(frozen=True)
class KindRules:
    kind: str
    #: Cintura di partenza, passaggi di grado.
    has_belts: bool
    #: Gare, stage, iscrizioni, risultati.
    has_competitions: bool
    #: Jav Ranking del club e pubblico, medaglie, judoca sul sito.
    in_rankings: bool
    #: Può comparire nel carosello e nell'elenco dei club del sito, e i
    #: suoi atleti (con consenso) possono comparire sul sito.
    public_as_club: bool
    #: Iscrizione annuale e quota socio del genitore possibili.
    has_enrollment_fees: bool
    #: Percentuale degli incassi alla piattaforma, se il superadmin non ne
    #: ha decisa un'altra. None = la regola è fissa e non si cambia.
    default_platform_fee_pct: Decimal
    platform_fee_editable: bool
    #: Il treinador di un corso è pagato a percentuale degli incassi del
    #: corso (non a ore dal cartellino).
    coach_paid_by_share: bool


_RULES = {
    CLUB: KindRules(
        kind=CLUB, has_belts=True, has_competitions=True, in_rankings=True, public_as_club=True,
        has_enrollment_fees=True, default_platform_fee_pct=Decimal(10), platform_fee_editable=True,
        coach_paid_by_share=False,
    ),
    JAV_COURSES: KindRules(
        kind=JAV_COURSES, has_belts=False, has_competitions=False, in_rankings=False, public_as_club=False,
        has_enrollment_fees=False, default_platform_fee_pct=Decimal(0), platform_fee_editable=False,
        coach_paid_by_share=True,
    ),
}

#: I default dei prezzi che cambiano con il tipo (pricing.py li sovrappone
#: ai suoi). Nei corsi JAV gli sconti partono spenti.
PRICING_DEFAULTS = {
    JAV_COURSES: {
        "tier_discount_pct": {"A": 0, "B": 0, "C": 0},
        "family_discount_cents": 0,
        "referral_credit_cents": 0,
        "parent_member_fee_cents": 0,
        "enrollment_includes": "",
    },
}
#: Ciò che nel tipo è una regola, non un default: la segreteria non lo
#: può cambiare (niente quota socio nei corsi JAV).
PRICING_FIXED = {
    JAV_COURSES: {"parent_member_fee_cents": 0},
}

#: I messaggi per chi prova a fare nei corsi JAV ciò che lì non esiste.
NO_BELTS = "Nei corsi JAV non ci sono cinture: le cinture arrivano quando l'atleta passa a un club."
NO_COMPETITIONS = "Nei corsi JAV non ci sono gare né stage: sono corsi per imparare, le gare si fanno nei club."
NO_PLATFORM_FEE = "I corsi JAV sono di JudoArteVida: la commissione della piattaforma è sempre 0%."


def rules_for(kind: str | None) -> KindRules:
    return _RULES.get(kind or CLUB, _RULES[CLUB])


def rules_of(club: Club | None) -> KindRules:
    return rules_for(club.kind if club is not None else None)


async def club_rules(db: AsyncSession, *, club_id: uuid.UUID) -> KindRules:
    return rules_of(await db.get(Club, club_id))


def is_courses_unit(club: Club | None) -> bool:
    return club is not None and club.kind == JAV_COURSES
