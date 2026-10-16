"""Il sito pubblico JudoArteVida: il portale dei club, le loro pagine, i
judoca, gli eventi e il ranking. Specifica: docs/club-portal.md, "Sito
pubblico".

Tutto ciò che il portale mostra **si deriva** da quello che il gestionale
sa già (corsi e orari, gare, risultati, cinture, punti): la segreteria
scrive solo i testi e carica le foto. Una gara inserita per le famiglie
compare da sola sul sito; un risultato corretto corregge il ranking pubblico.

Tre regole di privacy, che valgono per ogni funzione qui sotto:

- **un club compare solo se è attivo e ha pubblicato la sua pagina**;
- **l'unità dei corsi JAV non è un club e i suoi atleti non compaiono
  mai**, nemmeno con il consenso (club/kinds.py): ne escono solo i corsi
  pubblicati, senza persone (`public_courses`). Lo decide un predicato solo,
  `_publishable_club`, usato da ogni query che prende club o atleti;
- **un atleta compare solo con il consenso della famiglia e la
  pubblicazione del club** (`_public_athletes`), e di lui si mostrano nome e
  iniziale del cognome, cintura, club, fascia d'età, medaglie e punti — la
  foto solo se la famiglia l'ha permessa. Mai data di nascita, codice
  fiscale, peso, genitore, quote: le funzioni pubbliche costruiscono i loro
  dizionari campo per campo, e non passano mai un modello intero al router.

La scheda del judoca (`judoka_profile`) aggiunge, in stile IJF, ciò che la
segreteria scrive (profilo IJF, tecnica, guardia) e le foto e i video che
pubblica uno per uno: questi ultimi solo se la famiglia ha permesso la foto,
perché mostrano il volto come la foto del profilo.
"""

import re
import uuid
from datetime import date
from urllib.parse import parse_qs, urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import brand, kinds, seasons
from app.domains.club import competitions as competitions_service
from app.domains.club.models import (
    EVENT_KINDS,
    Club,
    ClubAthlete,
    ClubBeltGrade,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubCourse,
    ClubCourseSlot,
)
from app.domains.club.scope import ClubScope
from app.domains.club.service import (
    ClubNotFoundError,
    ClubValidationError,
    current_belts,
    list_plans,
)
from app.domains.club.site_models import ClubAthleteMedia, ClubAthletePublicProfile, ClubSite

#: Quante foto può avere la galleria di un club: una pagina, non un archivio.
MAX_GALLERY = 24
MAX_COACHES = 12
#: Le liste del mini-sito: abbastanza per raccontarsi, non un archivio.
MAX_HIGHLIGHTS = 6
MAX_HISTORY = 20
MAX_PILLARS = 6
MAX_NEWS = 30
MAX_CLUB_VIDEOS = 12
#: I campi di testo della pagina che la segreteria scrive così come sono.
TEXT_FIELDS = (
    "tagline", "about", "city", "contact_phone", "contact_email", "address", "venue",
)
#: I campi che devono essere un indirizzo web (http/https).
URL_FIELDS = ("hero_image_url", "logo_url", "map_url", "website_url")
#: I social, ognuno solo verso il suo sito e in https: sulla pagina diventano
#: icone con il logo di quel social, e un'icona di Facebook che porta altrove
#: sarebbe un inganno per chi la tocca.
SOCIAL_HOSTS = {
    "facebook_url": ("Facebook", ("facebook.com", "www.facebook.com", "m.facebook.com", "fb.com", "www.fb.com")),
    "instagram_url": ("Instagram", ("instagram.com", "www.instagram.com")),
    "youtube_url": ("YouTube", ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")),
}
IMAGE_SLOTS = ("hero", "logo", "gallery", "coach", "news")
#: Quante foto e quanti video può avere la scheda di un judoca: una
#: vetrina, non l'archivio delle gare del club.
MAX_ATHLETE_PHOTOS = 24
MAX_ATHLETE_VIDEOS = 12
DOMINANT_SIDES = ("LEFT", "RIGHT")
#: Quante prove future e quanti risultati mostra la scheda.
MAX_UPCOMING = 10
MAX_RESULTS = 30


def display_name(athlete: ClubAthlete) -> str:
    """"Nome I.": come nella classifica del club, mai il cognome intero."""
    return f"{athlete.first_name} {athlete.last_name[:1]}."


def _today() -> date:
    return utcnow().date()


# --- Chi è pubblico -------------------------------------------------------------------------------

#: I tipi di unità che possono comparire sul sito come club, con i loro
#: atleti: solo i club ufficiali (kinds.py, `public_as_club`).
PUBLIC_CLUB_KINDS = tuple(k for k in (kinds.CLUB, kinds.JAV_COURSES) if kinds.rules_for(k).public_as_club)


def _publishable_club():
    """Il predicato di ogni query pubblica su club e atleti: un club attivo
    e di un tipo che può comparire. Gli atleti dei corsi JAV restano fuori
    da tutto (ranking, judoca, eventi, medaglie, bot) qualunque consenso
    abbiano; dopo il passaggio a un club seguono le regole di tutti."""
    return (Club.status == "ACTIVE") & Club.kind.in_(PUBLIC_CLUB_KINDS)


async def _public_clubs(db: AsyncSession) -> list[tuple[Club, ClubSite]]:
    rows = (
        await db.execute(
            select(Club, ClubSite)
            .join(ClubSite, ClubSite.club_id == Club.id)
            .where(_publishable_club(), ClubSite.published.is_(True))
            .order_by(Club.name)
        )
    ).all()
    return [(club, site) for club, site in rows]


async def _public_club_by_slug(db: AsyncSession, slug: str) -> tuple[Club, ClubSite]:
    row = (
        await db.execute(
            select(Club, ClubSite)
            .join(ClubSite, ClubSite.club_id == Club.id)
            .where(Club.slug == slug.strip().lower(), _publishable_club(), ClubSite.published.is_(True))
        )
    ).first()
    if row is None:
        raise ClubNotFoundError("Club non trovato.")
    return row[0], row[1]


async def public_club_by_slug(db: AsyncSession, slug: str) -> tuple[Club, ClubSite]:
    """Un club che il sito mostra (attivo, pubblicato, di un tipo che può
    comparire), o "non trovato": per chi scrive dal modulo della pagina
    (club/contact.py) un club in bozza non esiste, come per tutto il sito."""
    return await _public_club_by_slug(db, slug)


async def _public_athletes(
    db: AsyncSession, *, club_ids: list[uuid.UUID], athlete_ids: list[uuid.UUID] | None = None,
) -> list[tuple[ClubAthlete, ClubAthletePublicProfile]]:
    """Gli atleti che si possono mostrare: attivi, con il consenso della
    famiglia **e** pubblicati dal club. È l'unico punto da cui il sito
    prende atleti: un filtro dimenticato altrove non può esistere."""
    if not club_ids:
        return []
    stmt = (
        select(ClubAthlete, ClubAthletePublicProfile)
        .join(ClubAthletePublicProfile, ClubAthletePublicProfile.athlete_id == ClubAthlete.id)
        .join(Club, Club.id == ClubAthlete.club_id)
        .where(
            _publishable_club(),
            ClubAthlete.club_id.in_(club_ids),
            ClubAthlete.status == "ACTIVE",
            ClubAthletePublicProfile.consent_given_at.is_not(None),
            ClubAthletePublicProfile.published.is_(True),
        )
    )
    if athlete_ids is not None:
        stmt = stmt.where(ClubAthlete.id.in_(athlete_ids))
    rows = (await db.execute(stmt.order_by(ClubAthlete.first_name, ClubAthlete.last_name))).all()
    return [(a, p) for a, p in rows]


def _club_ref(club: Club, site: ClubSite | None = None) -> dict:
    return {"name": club.name, "slug": club.slug, "logo_url": site.logo_url if site else None}


def _judoka_dict(
    athlete: ClubAthlete, profile: ClubAthletePublicProfile | None, *, club: Club, site: ClubSite | None,
    belt: str | None, totals: dict, season: int,
) -> dict:
    # Campo per campo, di proposito: niente di ClubAthlete arriva al browser
    # se non è scritto qui. Senza `profile` (nessun consenso alla pagina
    # pubblica) resta ciò che una classifica sportiva dice di chiunque:
    # "Nome I.", club, cintura, punti. Niente foto, niente pagina.
    return {
        "id": athlete.id,
        "display_name": display_name(athlete),
        "photo_url": athlete.photo_url if profile is not None and profile.show_photo else None,
        "has_page": profile is not None,
        "belt": belt,
        "age_band": competitions_service.age_band_for(competitions_service.ranking_age(athlete.birth_date, season)).code,
        "club": _club_ref(club, site),
        "points": totals.get("points", 0),
        "competitions": totals.get("competitions", 0),
        "gold": totals.get("gold", 0),
        "silver": totals.get("silver", 0),
        "bronze": totals.get("bronze", 0),
    }


async def _ranking_athletes(
    db: AsyncSession, *, club_ids: list[uuid.UUID],
) -> list[tuple[ClubAthlete, ClubAthletePublicProfile | None]]:
    """Chi entra nelle classifiche pubbliche: **tutti** gli atleti attivi dei
    club pubblici (decisione del titolare: una classifica sportiva è
    pubblica), ma con la scheda pubblica solo chi ha il consenso della
    famiglia ed è pubblicato (_public_athletes); gli altri senza profilo."""
    if not club_ids:
        return []
    with_page = {a.id: (a, p) for a, p in await _public_athletes(db, club_ids=club_ids)}
    rows = (await db.execute(
        select(ClubAthlete).join(Club, Club.id == ClubAthlete.club_id).where(
            _publishable_club(), ClubAthlete.club_id.in_(club_ids), ClubAthlete.status == "ACTIVE",
        )
    )).scalars().all()
    return [with_page.get(a.id, (a, None)) for a in rows]


async def _judoka_list(
    db: AsyncSession, pairs: list[tuple[ClubAthlete, ClubAthletePublicProfile | None]],
    clubs: dict[uuid.UUID, tuple[Club, ClubSite]], *, season: int, points_season: int | None,
    between: tuple[date, date] | None = None,
) -> list[dict]:
    ids = [a.id for a, _ in pairs]
    belts = await current_belts(db, athlete_ids=ids)
    points = await competitions_service.athlete_points(db, athlete_ids=ids, season=points_season, between=between)
    return [
        _judoka_dict(a, p, club=clubs[a.club_id][0], site=clubs[a.club_id][1], belt=belts.get(a.id),
                     totals=points.get(a.id, {}), season=season)
        for a, p in pairs
    ]


def _event_dict(comp: ClubCompetition, club: Club | None, site: ClubSite | None) -> dict:
    """`club` None per un evento della rete (calendário comune)."""
    return {
        "id": comp.id,
        "name": comp.name,
        "kind": comp.kind,
        "level": comp.level,
        "status": comp.status,
        "starts_on": comp.starts_on,
        "ends_on": comp.ends_on,
        "registration_deadline": comp.registration_deadline,
        "location": comp.location,
        "organizer": comp.organizer,
        "club": _club_ref(club, site) if club is not None else None,
        "age_groups": list(comp.age_groups or []),
        "transport_mode": comp.transport_mode,
        "price_cents": comp.fee_cents,
        "starts_at_time": comp.starts_at_time,
        "registration_deadline_time": comp.registration_deadline_time,
        "places": comp.places,
        "circular_url": comp.circular_url,
        "image_url": comp.image_url,
    }


async def _events(
    db: AsyncSession, clubs: dict[uuid.UUID, tuple[Club, ClubSite]], *, kind: str | None = None,
    when: str | None = None, limit: int = 50, today: date, start: date | None = None, end: date | None = None,
    query: str | None = None, level: str | None = None, age_group: str | None = None,
    network: bool | None = None, organizations: set[uuid.UUID] | None = None,
) -> list[dict]:
    """Gli eventi dei club pubblici e quelli della rete (il calendário
    comune, mostrati senza club). `network`: None entrambi, True solo la
    rete, False solo i club. `start`/`end`: gli eventi che toccano il
    periodo (anche uno di più giorni a cavallo del mese). `query`: nel nome,
    nel luogo e nell'organizzatore."""
    organizations = organizations or {club.organization_id for club, _site in clubs.values()}
    if not clubs and not organizations:
        return []
    own = ClubCompetition.club_id.in_(list(clubs))
    shared = ClubCompetition.club_id.is_(None) & ClubCompetition.organization_id.in_(organizations)
    if network is False:
        # Un club: i suoi eventi e quelli della rete a cui partecipano i suoi atleti.
        joined = select(ClubCompetitionEntry.id).where(
            ClubCompetitionEntry.competition_id == ClubCompetition.id,
            ClubCompetitionEntry.club_id.in_(list(clubs)), ClubCompetitionEntry.status == "REGISTERED",
        ).exists()
        where = or_(own, shared & joined)
    else:
        where = shared if network else or_(own, shared)
    stmt = select(ClubCompetition).where(where)
    if kind:
        stmt = stmt.where(ClubCompetition.kind == kind)
    if level:
        stmt = stmt.where(ClubCompetition.level == level)
    if age_group:
        # Un evento senza escalões è per tutti.
        stmt = stmt.where(or_(ClubCompetition.age_groups.any(age_group), func.cardinality(ClubCompetition.age_groups) == 0))
    if start:
        stmt = stmt.where(ClubCompetition.ends_on >= start)
    if end:
        stmt = stmt.where(ClubCompetition.starts_on <= end)
    if query and query.strip():
        like = f"%{query.strip()[:80]}%"
        stmt = stmt.where(or_(ClubCompetition.name.ilike(like), ClubCompetition.location.ilike(like),
                              ClubCompetition.organizer.ilike(like)))
    if when == "upcoming":
        stmt = stmt.where(ClubCompetition.ends_on >= today).order_by(ClubCompetition.starts_on)
    elif when == "past":
        stmt = stmt.where(ClubCompetition.ends_on < today).order_by(ClubCompetition.starts_on.desc())
    elif start or end:
        stmt = stmt.order_by(ClubCompetition.starts_on)
    else:
        stmt = stmt.order_by(ClubCompetition.starts_on.desc())
    comps = list((await db.execute(stmt.limit(limit))).scalars())
    # Quanti iscritti (solo il numero: i nomi sono nella pagina dell'evento,
    # e solo per chi ha il consenso).
    counts = dict((await db.execute(
        select(ClubCompetitionEntry.competition_id, func.count())
        .where(ClubCompetitionEntry.competition_id.in_([c.id for c in comps]),
               ClubCompetitionEntry.status == "REGISTERED")
        .group_by(ClubCompetitionEntry.competition_id)
    )).all()) if comps else {}
    return [{**_event_dict(c, *clubs.get(c.club_id, (None, None))), "entries_count": counts.get(c.id, 0)}
            for c in comps]


async def _recent_medals(
    db: AsyncSession, clubs: dict[uuid.UUID, tuple[Club, ClubSite]], *, limit: int, today: date,
) -> list[dict]:
    """Gli ultimi podi (1°, 2°, 3°) dei judoca pubblici, dalla gara più
    recente. Gli stage non danno medaglie."""
    public = await _public_athletes(db, club_ids=list(clubs))
    by_id = {a.id: (a, p) for a, p in public}
    if not by_id:
        return []
    rows = (
        await db.execute(
            select(ClubCompetitionEntry, ClubCompetition)
            .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
            .where(
                ClubCompetitionEntry.athlete_id.in_(list(by_id)),
                ClubCompetitionEntry.status == "REGISTERED",
                ClubCompetitionEntry.placement.in_((1, 2, 3)),
                ClubCompetition.kind == "COMPETITION",
                ClubCompetition.starts_on <= today,
            )
            .order_by(ClubCompetition.starts_on.desc(), ClubCompetitionEntry.placement)
            .limit(limit)
        )
    ).all()
    belts = await current_belts(db, athlete_ids=[e.athlete_id for e, _ in rows])
    out = []
    for entry, comp in rows:
        athlete, profile = by_id[entry.athlete_id]
        club, site = clubs[athlete.club_id]
        out.append({
            "athlete_id": athlete.id,
            "display_name": display_name(athlete),
            "photo_url": athlete.photo_url if profile.show_photo else None,
            "belt": belts.get(athlete.id),
            "placement": entry.placement,
            "category": entry.category,
            "event_id": comp.id,
            "event_name": comp.name,
            "event_level": comp.level,
            "date": comp.starts_on,
            "club": _club_ref(club, site),
        })
    return out


def _ranked(rows: list[dict]) -> list[dict]:
    """Ex aequo come nel ranking del club: stessa posizione, e chi viene
    dopo salta i posti."""
    rows = [r for r in rows if r["competitions"] > 0]
    rows.sort(key=lambda r: (-r["points"], -r["gold"], r["display_name"]))
    position, previous = 0, None
    for index, row in enumerate(rows, start=1):
        if row["points"] != previous:
            position, previous = index, row["points"]
        row["position"] = position
    return rows


# --- Le pagine pubbliche --------------------------------------------------------------------------


async def _club_cards(
    db: AsyncSession, pairs: list[tuple[Club, ClubSite]],
    public: list[tuple[ClubAthlete, ClubAthletePublicProfile]],
) -> list[dict]:
    """Le card dei club (carosello ed elenco): con i numeri che dicono quanto
    è vivo un club, contati e mai scritti a mano."""
    ids = [club.id for club, _ in pairs]
    active = dict(
        (
            await db.execute(
                select(ClubAthlete.club_id, func.count())
                .where(ClubAthlete.club_id.in_(ids), ClubAthlete.status == "ACTIVE")
                .group_by(ClubAthlete.club_id)
            )
        ).all()
    ) if ids else {}
    public_counts: dict[uuid.UUID, int] = {}
    for athlete, _ in public:
        public_counts[athlete.club_id] = public_counts.get(athlete.club_id, 0) + 1
    return [
        {
            **_club_ref(club, site),
            "city": site.city,
            "tagline": site.tagline,
            "hero_image_url": site.hero_image_url,
            "athletes_active": active.get(club.id, 0),
            "judoka_public": public_counts.get(club.id, 0),
        }
        for club, site in pairs
    ]


async def portal_home(db: AsyncSession, *, today: date | None = None) -> dict:
    today = today or _today()
    season = competitions_service.ranking_year(today)
    pairs = await _public_clubs(db)
    clubs = {club.id: (club, site) for club, site in pairs}
    public = await _public_athletes(db, club_ids=list(clubs))
    cards = await _club_cards(db, pairs, public)
    ranked = await _judoka_list(db, await _ranking_athletes(db, club_ids=list(clubs)), clubs, season=season,
                                points_season=season)
    return {
        "season": season,
        "season_label": competitions_service.ranking_label(season),
        "clubs": cards,
        "totals": {
            "clubs": len(cards),
            "athletes_active": sum(c["athletes_active"] for c in cards),
            "judoka_public": len(public),
        },
        "upcoming_events": await _events(db, clubs, when="upcoming", limit=6, today=today),
        "top_ranking": _ranked(ranked)[:10],
        "latest_medals": await _recent_medals(db, clubs, limit=8, today=today),
    }


def _schedule(courses: list[ClubCourse], slots: list[ClubCourseSlot]) -> list[dict]:
    """L'orario settimanale dai corsi attivi: un giorno, i suoi turni in
    ordine di ora. Si aggiorna da solo quando l'istruttore cambia un corso."""
    by_course = {c.id: c for c in courses}
    days: dict[int, list[dict]] = {}
    for slot in sorted(slots, key=lambda s: (s.weekday, s.starts_at)):
        course = by_course[slot.course_id]
        days.setdefault(slot.weekday, []).append({
            "course": course.name,
            "level": course.level,
            "min_age": course.min_age,
            "max_age": course.max_age,
            "starts_at": slot.starts_at.strftime("%H:%M"),
            "ends_at": slot.ends_at.strftime("%H:%M"),
            "room": slot.room,
        })
    return [{"weekday": d, "slots": days[d]} for d in sorted(days)]


def _site_content(site: ClubSite) -> dict:
    return {
        "tagline": site.tagline,
        "about": site.about,
        "city": site.city,
        "hero_image_url": site.hero_image_url,
        "logo_url": site.logo_url,
        "gallery": list(site.gallery or []),
        "coaches": list(site.coaches or []),
        "contact_phone": site.contact_phone,
        "contact_email": site.contact_email,
        "address": site.address,
        "map_url": site.map_url,
        "instagram_url": site.instagram_url,
        "facebook_url": site.facebook_url,
        "youtube_url": site.youtube_url,
        "website_url": site.website_url,
        "brand_primary": site.brand_primary,
        "brand_secondary": site.brand_secondary,
        "brand_accent": site.brand_accent,
        "founded_year": site.founded_year,
        "venue": site.venue,
        "highlights": list(site.highlights or []),
        "history": list(site.history or []),
        "pillars": list(site.pillars or []),
        # Dal più recente: è il diario del club, come una pagina Facebook.
        "news": sorted(site.news or [], key=lambda n: n.get("date") or "", reverse=True),
        "videos": list(site.videos or []),
    }


def plan_slots(min_age: int | None, max_age: int | None, schedule: list[dict]) -> list[tuple[int, dict]]:
    """Gli allenamenti di un gruppo (un piano): i turni dei corsi la cui
    fascia d'età tocca quella del piano. Un corso senza età non si
    attribuisce a nessuno: non si indovina. La stessa regola per la pagina
    del club e per JAVBOT (javbot/public.py), così dicono la stessa cosa."""
    p_min, p_max = min_age or 0, max_age if max_age is not None else 999
    found: list[tuple[int, dict]] = []
    for day in schedule:
        for slot in day["slots"]:
            if slot["min_age"] is None and slot["max_age"] is None:
                continue
            s_min, s_max = slot["min_age"] or 0, slot["max_age"] if slot["max_age"] is not None else 999
            if s_min <= p_max and p_min <= s_max:
                found.append((day["weekday"], slot))
    return found


async def _groups(db: AsyncSession, *, club: Club, site: ClubSite, schedule: list[dict]) -> list[dict]:
    """I gruppi del club sulla sua pagina: gli stessi del bot (i piani attivi,
    tools.py::public_club_info) con età e allenamenti; mensilità, iscrizione,
    scadenza e mesi solo se il club ha acceso "mostra i prezzi". La
    descrizione del piano esce solo con i prezzi: può contenerne."""
    scope = ClubScope(organization_id=club.organization_id, club_id=club.id)
    out = []
    for plan in await list_plans(db, scope=scope, only_active=True):
        row = {
            "name": plan.name, "min_age": plan.min_age, "max_age": plan.max_age,
            "slots": [
                {"weekday": weekday, "starts_at": slot["starts_at"], "ends_at": slot["ends_at"], "course": slot["course"]}
                for weekday, slot in plan_slots(plan.min_age, plan.max_age, schedule)
            ],
            "monthly_price_cents": None, "enrollment_price_cents": None, "due_day": None, "billing_months": None,
            "description": None,
        }
        if site.show_prices:
            row.update(
                monthly_price_cents=plan.monthly_fee_cents, enrollment_price_cents=plan.enrollment_fee_cents,
                due_day=plan.due_day, billing_months=sorted(plan.billing_months or []), description=plan.description,
            )
        out.append(row)
    return out


async def club_page(db: AsyncSession, *, slug: str, today: date | None = None) -> dict:
    today = today or _today()
    season = competitions_service.ranking_year(today)
    club, site = await _public_club_by_slug(db, slug)
    clubs = {club.id: (club, site)}
    courses = list(
        (await db.execute(
            select(ClubCourse).where(ClubCourse.club_id == club.id, ClubCourse.active.is_(True))
        )).scalars()
    )
    slots = list(
        (await db.execute(
            select(ClubCourseSlot).where(ClubCourseSlot.course_id.in_([c.id for c in courses]))
        )).scalars()
    ) if courses else []
    public = await _public_athletes(db, club_ids=[club.id])
    athletes_active = (
        await db.execute(
            select(func.count()).select_from(ClubAthlete)
            .where(ClubAthlete.club_id == club.id, ClubAthlete.status == "ACTIVE")
        )
    ).scalar_one()
    judoka = await _judoka_list(db, public, clubs, season=season, points_season=None)
    # Il ranking del club è quello di /ranking filtrato sul club (punti della
    # stagione): lo stesso calcolo, così i due numeri non possono divergere.
    season_judoka = await _judoka_list(db, await _ranking_athletes(db, club_ids=list(clubs)), clubs, season=season,
                                       points_season=season)
    schedule = _schedule(courses, slots)
    return {
        "name": club.name,
        "slug": club.slug,
        **_site_content(site),
        "theme": brand.site_theme(site),
        "updated_at": site.updated_at,
        "season_label": competitions_service.ranking_label(season),
        "athletes_active": athletes_active,
        "schedule": schedule,
        "show_prices": site.show_prices,
        "groups": await _groups(db, club=club, site=site, schedule=schedule),
        "upcoming_events": await _events(db, clubs, when="upcoming", limit=8, today=today),
        "judoka": judoka,
        "ranking": _ranked(season_judoka)[:10],
        "recent_medals": await _recent_medals(db, clubs, limit=8, today=today),
    }


async def list_public_clubs(db: AsyncSession) -> list[dict]:
    pairs = await _public_clubs(db)
    public = await _public_athletes(db, club_ids=[club.id for club, _ in pairs])
    return await _club_cards(db, pairs, public)


async def judoka_profile(db: AsyncSession, *, athlete_id: uuid.UUID, today: date | None = None) -> dict:
    """La scheda pubblica di un judoca, in stile IJF: la card del ranking più
    risultati, prove in programma, percorso delle cinture, posto nel ranking
    della sua fascia, profilo IJF e i media pubblicati. Senza consenso e
    pubblicazione è "non trovato", come prima."""
    today = today or _today()
    season = competitions_service.ranking_year(today)
    clubs = {club.id: (club, site) for club, site in await _public_clubs(db)}
    found = await _public_athletes(db, club_ids=list(clubs), athlete_ids=[athlete_id])
    if not found:
        # Senza consenso o non pubblicato è "non trovato": non si conferma
        # nemmeno che esista.
        raise ClubNotFoundError("Judoca non trovato.")
    athlete, profile = found[0]
    [card] = await _judoka_list(db, found, clubs, season=season, points_season=None)
    season_points = await competitions_service.athlete_points(db, athlete_ids=[athlete.id], season=season)
    # Solo le iscrizioni fatte da un club pubblico (agli eventi suoi o della
    # rete): un evento che il sito non mostra non può comparire nemmeno qui.
    entries = (
        await db.execute(
            select(ClubCompetitionEntry, ClubCompetition)
            .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
            .where(
                ClubCompetitionEntry.athlete_id == athlete.id,
                ClubCompetitionEntry.status == "REGISTERED",
                ClubCompetitionEntry.club_id.in_(list(clubs)),
                or_(ClubCompetition.club_id.is_(None), ClubCompetition.club_id.in_(list(clubs))),
            )
            .order_by(ClubCompetition.starts_on.desc())
        )
    ).all()
    results = [
        (entry, comp) for entry, comp in entries
        if entry.placement is not None and comp.kind == "COMPETITION"
    ][:MAX_RESULTS]
    upcoming = sorted(
        ((entry, comp) for entry, comp in entries if comp.ends_on >= today),
        key=lambda pair: pair[1].starts_on,
    )[:MAX_UPCOMING]
    # La categoria "di adesso": quella dell'ultima gara fatta, o della
    # prossima se non ne ha ancora fatte. È il testo scritto sull'iscrizione
    # (età/peso, "-38 kg"), lo stesso che il sito mostra già nei risultati:
    # il peso vero dell'atleta non esce mai.
    past = [entry.category for entry, comp in entries if comp.starts_on <= today and entry.category]
    category = past[0] if past else next((entry.category for entry, _ in upcoming if entry.category), None)
    belts = (
        await db.execute(
            select(ClubBeltGrade.grade, ClubBeltGrade.awarded_on)
            .where(ClubBeltGrade.athlete_id == athlete.id)
            .order_by(ClubBeltGrade.awarded_on, ClubBeltGrade.created_at)
        )
    ).all()
    return {
        **card,
        "bio": profile.bio,
        "season_label": competitions_service.ranking_label(season),
        "season_points": season_points[athlete.id]["points"],
        "results": [
            {
                "event_id": comp.id,
                "event_name": comp.name,
                "level": comp.level,
                "date": comp.starts_on,
                "location": comp.location,
                "placement": entry.placement,
                "category": entry.category,
                "points": competitions_service.points_for(placement=entry.placement, level=comp.level),
            }
            for entry, comp in results
        ],
        "category": category,
        "ranking": await _ranking_position(db, athlete_id=athlete.id, age_band=card["age_band"], season=season,
                                           today=today),
        "belt_history": [{"grade": grade, "awarded_on": awarded_on} for grade, awarded_on in belts],
        "upcoming": [
            {**_event_dict(comp, *clubs.get(comp.club_id, (None, None))), "category": entry.category}
            for entry, comp in upcoming
        ],
        **await _public_media(db, athlete=athlete, profile=profile),
        "ijf_profile_url": profile.ijf_profile_url,
        "favorite_technique": profile.favorite_technique,
        "dominant_side": profile.dominant_side,
    }


async def _ranking_position(
    db: AsyncSession, *, athlete_id: uuid.UUID, age_band: str, season: int, today: date,
) -> dict | None:
    """Il posto nel ranking pubblico della stagione, nella fascia d'età del
    judoca: lo stesso calcolo della pagina /ranking, così i due numeri non
    possono mai essere diversi. None se in stagione non ha ancora gareggiato."""
    ranking = await public_ranking(db, season=season, age_band=age_band, today=today)
    for row in ranking["rows"]:
        if row["id"] == athlete_id:
            return {"position": row["position"], "total": len(ranking["rows"]), "age_band": age_band,
                    "points": row["points"]}
    return None


async def _public_media(db: AsyncSession, *, athlete: ClubAthlete, profile: ClubAthletePublicProfile) -> dict:
    """Le foto e i video pubblicati dal club. Senza il permesso della foto
    (`show_photo`) nessuno: mostrano il volto, e quella scelta è della
    famiglia. Solo i media del club di adesso: dopo un cambio di club quelli
    vecchi non seguono l'atleta."""
    if not profile.show_photo:
        return {"photos": [], "videos": []}
    items = list(
        (await db.execute(
            select(ClubAthleteMedia)
            .where(
                ClubAthleteMedia.athlete_id == athlete.id,
                ClubAthleteMedia.club_id == athlete.club_id,
                ClubAthleteMedia.published.is_(True),
            )
            .order_by(ClubAthleteMedia.created_at.desc())
        )).scalars()
    )
    return {
        "photos": [{"id": m.id, "url": m.url, "caption": m.caption} for m in items if m.kind == "PHOTO"],
        "videos": [{"id": m.id, "youtube_id": m.youtube_id, "caption": m.caption} for m in items if m.kind == "VIDEO"],
    }


#: Il "club" che vuol dire il calendário comune.
NETWORK_SLUG = "rede"
MAX_EVENTS = 500


async def list_events(
    db: AsyncSession, *, club_slug: str | None = None, kind: str | None = None, when: str | None = None,
    limit: int = 60, today: date | None = None, start: date | None = None, end: date | None = None,
    query: str | None = None, level: str | None = None, age_group: str | None = None,
) -> list[dict]:
    """La ricerca degli eventi del sito. `club_slug` = un club (solo i suoi
    eventi), "rede" = solo il calendário comune, niente = tutto."""
    from app.domains.club.models import COMPETITION_LEVELS

    if kind is not None and kind not in EVENT_KINDS:
        raise ClubValidationError("Tipo di evento non valido.")
    if when is not None and when not in ("upcoming", "past"):
        raise ClubValidationError("Filtro non valido.")
    if level is not None and level not in COMPETITION_LEVELS:
        raise ClubValidationError("Livello non valido.")
    if start and end and end < start:
        raise ClubValidationError("Il periodo non è valido.")
    pairs = await _public_clubs(db)
    clubs = {club.id: (club, site) for club, site in pairs}
    organizations = {club.organization_id for club, _site in pairs}
    network = None
    slug = (club_slug or "").strip().lower()
    if slug == NETWORK_SLUG:
        network = True
    elif slug:
        clubs = {k: v for k, v in clubs.items() if v[0].slug == slug}
        network = False
    return await _events(
        db, clubs, kind=kind, when=when, limit=min(max(limit, 1), MAX_EVENTS), today=today or _today(),
        start=start, end=end, query=query, level=level, age_group=(age_group or None), network=network,
        organizations=organizations,
    )


async def decor_photos(db: AsyncSession, *, limit: int = 24) -> list[dict]:
    """Le foto che i club hanno già pubblicato sulle loro pagine (copertina e
    galleria): il sito le usa come decorazione delle testate. Solo URL di
    immagini pubbliche, nessun dato di atleti."""
    photos: list[dict] = []
    for club, site in await _public_clubs(db):
        if site.hero_image_url:
            photos.append({"url": site.hero_image_url, "club": club.name})
        for item in site.gallery or []:
            if isinstance(item, dict) and item.get("url"):
                photos.append({"url": item["url"], "club": club.name})
    return photos[:limit]


async def event_detail(db: AsyncSession, *, event_id: uuid.UUID, today: date | None = None) -> dict:
    season = competitions_service.ranking_year(today or _today())
    comp = await db.get(ClubCompetition, event_id)
    clubs = {club.id: (club, site) for club, site in await _public_clubs(db)}
    if comp is None or (comp.club_id is not None and comp.club_id not in clubs):
        raise ClubNotFoundError("Evento non trovato.")
    entries = list(
        (await db.execute(
            select(ClubCompetitionEntry).where(
                ClubCompetitionEntry.competition_id == comp.id, ClubCompetitionEntry.status == "REGISTERED",
            )
        )).scalars()
    )
    # Solo i judoca pubblici: gli altri iscritti contano nel totale ma non
    # hanno un nome sul sito.
    # Un evento della rete ha iscritti di tutti i club pubblici.
    club_ids = [comp.club_id] if comp.club_id is not None else list(clubs)
    public = await _public_athletes(db, club_ids=club_ids, athlete_ids=[e.athlete_id for e in entries])
    by_id = {a.id: (a, p) for a, p in public}
    belts = await current_belts(db, athlete_ids=list(by_id))
    participants = []
    for entry in entries:
        if entry.athlete_id not in by_id:
            continue
        athlete, profile = by_id[entry.athlete_id]
        participants.append({
            "athlete_id": athlete.id,
            "display_name": display_name(athlete),
            "photo_url": athlete.photo_url if profile.show_photo else None,
            "belt": belts.get(athlete.id),
            "age_band": competitions_service.age_band_for(competitions_service.ranking_age(athlete.birth_date, season)).code,
            "category": entry.category,
            # Gli stage non hanno piazzamenti, anche se qualcuno ne avesse scritto uno.
            "placement": entry.placement if comp.kind == "COMPETITION" else None,
            "points": competitions_service.points_for(placement=entry.placement, level=comp.level)
            if comp.kind == "COMPETITION" else 0,
        })
    # 0 (partecipazione) va dopo i piazzamenti veri; chi non ha ancora un
    # risultato va in fondo.
    participants.sort(key=lambda p: (
        p["placement"] is None, p["placement"] == 0, p["placement"] or 0, p["display_name"],
    ))
    return {
        **_event_dict(comp, *clubs.get(comp.club_id, (None, None))),
        "description": comp.description,
        "categories": comp.categories,
        "participants_count": len(entries),
        "participants": participants,
    }


async def public_ranking(
    db: AsyncSession, *, season: int | None = None, age_band: str | None = None, club_slug: str | None = None,
    today: date | None = None, period: str = "year", month: int | None = None,
) -> dict:
    """La classifica dei judoca: dell'anno solare (`period="year"`, il
    ranking che conta), di un mese, o di sempre. La fascia d'età è quella
    dell'anno `season` (per "sempre", quella di quest'anno)."""
    current = competitions_service.ranking_year(today or _today())
    season = season if season is not None else current
    if age_band is not None and age_band not in {b.code for b in competitions_service.AGE_BANDS}:
        raise ClubValidationError("Fascia d'età non valida.")
    between = competitions_service.period_range(period=period, year=season, month=month)
    clubs = {club.id: (club, site) for club, site in await _public_clubs(db)}
    if club_slug:
        clubs = {k: v for k, v in clubs.items() if v[0].slug == club_slug.strip().lower()}
    rows = await _judoka_list(db, await _ranking_athletes(db, club_ids=list(clubs)), clubs,
                              season=season if period != "all" else current, points_season=None, between=between)
    if age_band:
        rows = [r for r in rows if r["age_band"] == age_band]
    return {
        "season": season,
        "season_label": competitions_service.ranking_label(season),
        "period": period,
        "month": month if period == "month" else None,
        "clubs": [_club_ref(c, s) for c, s in clubs.values()],
        "rows": _ranked(rows),
    }


async def _club_totals(
    db: AsyncSession, clubs: dict[uuid.UUID, tuple[Club, ClubSite]], *, between: tuple[date, date] | None,
) -> dict[uuid.UUID, dict]:
    """I punti di ogni club: la somma dei punti dei risultati dei suoi
    atleti, per il club con cui hanno gareggiato (l'iscrizione), come per il
    ranking dei judoca (stessa tabella, solo le gare)."""
    stmt = (
        select(ClubCompetitionEntry, ClubCompetition)
        .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
        .where(
            ClubCompetitionEntry.club_id.in_(list(clubs)),
            ClubCompetitionEntry.status == "REGISTERED",
            ClubCompetitionEntry.placement.is_not(None),
            ClubCompetition.kind == "COMPETITION",
        )
    )
    if between is not None:
        stmt = stmt.where(ClubCompetition.starts_on >= between[0], ClubCompetition.starts_on <= between[1])
    out: dict[uuid.UUID, dict] = {}
    for entry, comp in (await db.execute(stmt)).all():
        row = out.setdefault(entry.club_id, {"points": 0, "results": 0, "gold": 0, "silver": 0, "bronze": 0,
                                              "athletes": set(), "events": set()})
        row["points"] += competitions_service.points_for(placement=entry.placement, level=comp.level)
        row["results"] += 1
        row["athletes"].add(entry.athlete_id)
        row["events"].add(comp.id)
        if entry.placement in (1, 2, 3):
            row[("gold", "silver", "bronze")[entry.placement - 1]] += 1
    return out


def _club_rows(clubs: dict[uuid.UUID, tuple[Club, ClubSite]], totals: dict[uuid.UUID, dict]) -> list[dict]:
    rows = [
        {
            "club": _club_ref(*clubs[club_id]), "city": clubs[club_id][1].city if clubs[club_id][1] else None,
            "points": t["points"], "results": t["results"], "gold": t["gold"], "silver": t["silver"],
            "bronze": t["bronze"], "athletes": len(t["athletes"]), "events": len(t["events"]),
        }
        for club_id, t in totals.items() if t["results"] > 0
    ]
    rows.sort(key=lambda r: (-r["points"], -r["gold"], -r["silver"], r["club"]["name"]))
    position, previous = 0, None
    for index, row in enumerate(rows, start=1):
        if row["points"] != previous:
            position, previous = index, row["points"]
        row["position"] = position
    return rows


async def public_club_ranking(
    db: AsyncSession, *, season: int | None = None, period: str = "year", month: int | None = None,
    today: date | None = None,
) -> dict:
    """La Taça dos Clubes: i club per punti dei loro atleti, nel mese,
    nell'anno (quella che conta: a fine anno il primo vince la coppa) o da
    sempre. Con l'albo d'oro: il vincitore di ogni anno già chiuso."""
    today = today or _today()
    current = competitions_service.ranking_year(today)
    season = season if season is not None else current
    between = competitions_service.period_range(period=period, year=season, month=month)
    clubs = {club.id: (club, site) for club, site in await _public_clubs(db)}
    rows = _club_rows(clubs, await _club_totals(db, clubs, between=between)) if clubs else []

    # L'albo d'oro: gli anni con almeno un risultato, fino all'anno scorso.
    first = (await db.execute(
        select(func.min(ClubCompetition.starts_on))
        .join(ClubCompetitionEntry, ClubCompetitionEntry.competition_id == ClubCompetition.id)
        .where(ClubCompetitionEntry.club_id.in_(list(clubs) or [uuid.uuid4()]),
               ClubCompetitionEntry.placement.is_not(None), ClubCompetition.kind == "COMPETITION")
    )).scalar_one_or_none()
    winners = []
    if first is not None:
        for year in range(current - 1, first.year - 1, -1):
            year_rows = _club_rows(clubs, await _club_totals(
                db, clubs, between=competitions_service.period_range(period="year", year=year)))
            if year_rows:
                top = year_rows[0]
                winners.append({"year": year, "club": top["club"], "points": top["points"]})
    return {
        "season": season,
        "season_label": competitions_service.ranking_label(season),
        "period": period,
        "month": month if period == "month" else None,
        # L'anno in corso è ancora aperto: la coppa si assegna a fine anno.
        "is_final": period == "year" and season < current,
        "rows": rows,
        "winners": winners,
    }


async def ranking_card(db: AsyncSession, *, athlete_id: uuid.UUID, today: date | None = None) -> dict:
    """La scheda di un judoca della classifica pubblica, per il popup. Con il
    consenso e la pubblicazione è la scheda completa (judoka_profile: foto,
    categoria, media...). Senza, solo ciò che una classifica sportiva dice di
    chiunque: «Nome I.», club, cintura, fascia, punti, posizione e i
    risultati delle gare (evento, data, piazzamento). Mai foto, età, peso o
    categoria, e mai le prove in programma: dicono dove sarà un minorenne."""
    today = today or _today()
    season = competitions_service.ranking_year(today)
    clubs = {club.id: (club, site) for club, site in await _public_clubs(db)}
    pairs = [p for p in await _ranking_athletes(db, club_ids=list(clubs)) if p[0].id == athlete_id]
    if not pairs:
        raise ClubNotFoundError("Judoca non trovato.")
    athlete, profile = pairs[0]
    if profile is not None:
        return {"has_page": True, "profile": await judoka_profile(db, athlete_id=athlete_id, today=today), "card": None}
    [card] = await _judoka_list(db, pairs, clubs, season=season, points_season=None)
    season_points = await competitions_service.athlete_points(db, athlete_ids=[athlete.id], season=season)
    entries = (await db.execute(
        select(ClubCompetitionEntry, ClubCompetition)
        .join(ClubCompetition, ClubCompetition.id == ClubCompetitionEntry.competition_id)
        .where(
            ClubCompetitionEntry.athlete_id == athlete.id, ClubCompetitionEntry.status == "REGISTERED",
            ClubCompetitionEntry.placement.is_not(None), ClubCompetition.kind == "COMPETITION",
            ClubCompetitionEntry.club_id.in_(list(clubs)),
            or_(ClubCompetition.club_id.is_(None), ClubCompetition.club_id.in_(list(clubs))),
            ClubCompetition.starts_on <= today,
        )
        .order_by(ClubCompetition.starts_on.desc())
        .limit(MAX_RESULTS)
    )).all()
    return {
        "has_page": False,
        "profile": None,
        "card": {
            **card,
            "season_label": competitions_service.ranking_label(season),
            "season_points": season_points[athlete.id]["points"],
            "ranking": await _ranking_position(db, athlete_id=athlete.id, age_band=card["age_band"], season=season,
                                               today=today),
            "results": [
                {"event_id": comp.id, "event_name": comp.name, "level": comp.level, "date": comp.starts_on,
                 "location": comp.location, "placement": entry.placement,
                 "points": competitions_service.points_for(placement=entry.placement, level=comp.level)}
                for entry, comp in entries
            ],
        },
    }


# --- I corsi JAV nelle scuole ----------------------------------------------------------------------


def _course_card(course: ClubCourse, slots: list[ClubCourseSlot], *, unit: Club) -> dict:
    # Campo per campo, come per i judoca: di un corso si mostrano luogo,
    # orario, età e testi scritti per il pubblico. Mai iscritti, treinador
    # dal suo account, incassi.
    return {
        "id": course.id,
        "name": course.name,
        "level": course.level,
        "min_age": course.min_age,
        "max_age": course.max_age,
        "venue_name": course.venue_name,
        "venue_address": course.venue_address,
        "venue_city": course.venue_city,
        "description": course.public_description,
        "coach_name": course.public_coach_name,
        "slots": [
            {"weekday": s.weekday, "starts_at": s.starts_at.strftime("%H:%M"), "ends_at": s.ends_at.strftime("%H:%M")}
            for s in sorted(slots, key=lambda s: (s.weekday, s.starts_at))
        ],
        "signup_path": f"/c/{unit.slug}?curso={course.id}",
    }


async def public_courses(db: AsyncSession) -> dict:
    """La sezione "Cursos JAV nas escolas": i corsi pubblicati e attivi
    dell'unità dei corsi JAV (se è attiva), con i testi della sua pagina se
    la pagina è pubblicata. Nessuna persona: chi frequenta i corsi non
    compare mai sul sito (kinds.py)."""
    unit = (
        await db.execute(select(Club).where(Club.kind == kinds.JAV_COURSES, Club.status == "ACTIVE"))
    ).scalars().first()
    if unit is None:
        return {"unit": None, "courses": []}
    courses = list(
        (await db.execute(
            select(ClubCourse)
            .where(ClubCourse.club_id == unit.id, ClubCourse.active.is_(True), ClubCourse.published.is_(True))
            .order_by(ClubCourse.venue_city, ClubCourse.venue_name, ClubCourse.name)
        )).scalars()
    )
    slots: dict[uuid.UUID, list[ClubCourseSlot]] = {c.id: [] for c in courses}
    if courses:
        for slot in (await db.execute(
            select(ClubCourseSlot).where(ClubCourseSlot.course_id.in_(list(slots)))
        )).scalars():
            slots[slot.course_id].append(slot)
    site = (await db.execute(select(ClubSite).where(ClubSite.club_id == unit.id))).scalars().first()
    content = _site_content(site) if site is not None and site.published else None
    return {
        "unit": {
            "name": unit.name,
            "slug": unit.slug,
            "tagline": content["tagline"] if content else None,
            "about": content["about"] if content else None,
            "hero_image_url": content["hero_image_url"] if content else None,
            "contact_phone": content["contact_phone"] if content else None,
            "contact_email": content["contact_email"] if content else None,
        },
        "courses": [_course_card(c, slots[c.id], unit=unit) for c in courses],
    }


# --- La segreteria: la pagina del club ------------------------------------------------------------


async def get_site(db: AsyncSession, *, scope: ClubScope) -> ClubSite:
    """La pagina del club; la prima volta nasce vuota e non pubblicata."""
    site = (await db.execute(select(ClubSite).where(ClubSite.club_id == scope.club_id))).scalars().first()
    if site is None:
        site = ClubSite(**scope.columns(), gallery=[], coaches=[], published=False)
        db.add(site)
        await db.commit()
        await db.refresh(site)
    return site


def admin_site_dict(site: ClubSite, club: Club) -> dict:
    return {
        "name": club.name,
        "slug": club.slug,
        "published": site.published,
        "show_prices": site.show_prices,
        "updated_at": site.updated_at,
        **_site_content(site),
        "theme": brand.site_theme(site),
    }


def _check_url(value: str | None, *, field: str) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ClubValidationError(
            f"L'indirizzo in «{field}» non è valido: deve cominciare con https:// (copialo dalla barra del browser)."
        )
    return value


def check_social_url(value: str | None, *, field: str) -> str | None:
    """Un social, solo verso il suo sito. Chi incolla "facebook.com/club"
    senza https:// o con http:// non riceve un errore: si completa e si
    salva in https. Un altro sito, un utente o una porta nell'indirizzo no."""
    if value is None or not value.strip():
        return None
    label, hosts = SOCIAL_HOSTS[field]
    value = value.strip()
    if "://" not in value:
        value = f"https://{value}"
    elif value.lower().startswith("http://"):
        value = "https://" + value[len("http://"):]
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https" or host not in hosts or parsed.username or parsed.password or parsed.port
        or parsed.path.strip("/") == "" or any(c.isspace() for c in value)
    ):
        raise ClubValidationError(
            f"Il link {label} non è valido: apri la pagina del club su {label} e copia l'indirizzo dalla barra "
            f"del browser (per esempio https://{hosts[0]}/...)."
        )
    return value


def _clean_gallery(items: list[dict]) -> list[dict]:
    if len(items) > MAX_GALLERY:
        raise ClubValidationError(f"La galleria può avere al massimo {MAX_GALLERY} foto.")
    out = []
    for item in items:
        url = _check_url(item.get("url"), field="galleria")
        if url is None:
            continue
        caption = (item.get("caption") or "").strip()[:200] or None
        out.append({"url": url, "caption": caption})
    return out


def _clean_coaches(items: list[dict]) -> list[dict]:
    if len(items) > MAX_COACHES:
        raise ClubValidationError(f"Si possono presentare al massimo {MAX_COACHES} allenatori.")
    out = []
    for item in items:
        name = (item.get("name") or "").strip()[:120]
        if not name:
            continue
        out.append({
            "name": name,
            "role": (item.get("role") or "").strip()[:120] or None,
            "photo_url": _check_url(item.get("photo_url"), field="foto allenatore"),
            "grade": (item.get("grade") or "").strip()[:60] or None,
            "bio": (item.get("bio") or "").strip()[:400] or None,
        })
    return out


def _too_many(items: list, limit: int, what: str) -> None:
    if len(items) > limit:
        raise ClubValidationError(f"{what}: al massimo {limit}.")


def _text(item: dict, key: str, limit: int) -> str | None:
    return (item.get(key) or "").strip()[:limit] or None


def _clean_highlights(items: list[dict]) -> list[dict]:
    _too_many(items, MAX_HIGHLIGHTS, "I numeri del club")
    out = []
    for item in items:
        value, label = _text(item, "value", 12), _text(item, "label", 60)
        if value and label:
            out.append({"value": value, "label": label})
    return out


def _clean_history(items: list[dict]) -> list[dict]:
    _too_many(items, MAX_HISTORY, "Le tappe della storia")
    out = []
    for item in items:
        title = _text(item, "title", 120)
        if title and item.get("year"):
            out.append({"year": int(item["year"]), "title": title, "text": _text(item, "text", 600)})
    # Una storia si legge dal principio: l'ordine lo decide l'anno, non chi scrive.
    return sorted(out, key=lambda h: h["year"])


def _clean_pillars(items: list[dict]) -> list[dict]:
    _too_many(items, MAX_PILLARS, "I punti di forza")
    out = []
    for item in items:
        title = _text(item, "title", 60)
        if title:
            out.append({"title": title, "text": _text(item, "text", 300)})
    return out


def _clean_news(items: list[dict]) -> list[dict]:
    _too_many(items, MAX_NEWS, "Le novità")
    out = []
    for item in items:
        title = _text(item, "title", 140)
        when = item.get("date")
        if not title or not when:
            continue
        out.append({
            "date": when.isoformat() if isinstance(when, date) else str(when)[:10],
            "title": title,
            "text": _text(item, "text", 2000),
            "image_url": _check_url(item.get("image_url"), field="foto della novità"),
            "link_url": _check_url(item.get("link_url"), field="link della novità"),
        })
    return sorted(out, key=lambda n: n["date"], reverse=True)


def _clean_club_videos(items: list[dict]) -> list[dict]:
    """I video del club come quelli della scheda di un judoca: si scrive il
    link, si salva solo l'id (un iframe verso un sito qualsiasi non si può
    mettere). Un id già pulito (11 caratteri) si accetta così com'è."""
    _too_many(items, MAX_CLUB_VIDEOS, "I video")
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        raw = (item.get("url") or item.get("youtube_id") or "").strip()
        if not raw:
            continue
        video_id = raw if _YOUTUBE_ID.match(raw) else youtube_id_from_url(raw)
        if video_id in seen:
            continue
        seen.add(video_id)
        out.append({"youtube_id": video_id, "caption": _text(item, "caption", 200)})
    return out


async def update_site(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, changes: dict,
) -> ClubSite:
    site = await get_site(db, scope=scope)
    for field in TEXT_FIELDS:
        if field in changes:
            value = changes[field]
            setattr(site, field, value.strip() or None if isinstance(value, str) else None)
    for field in URL_FIELDS:
        if field in changes:
            setattr(site, field, _check_url(changes[field], field=field))
    for field in SOCIAL_HOSTS:
        if field in changes:
            setattr(site, field, check_social_url(changes[field], field=field))
    for field in brand.BRAND_FIELDS:
        if field in changes:
            try:
                setattr(site, field, brand.normalize_hex(changes[field]))
            except brand.BrandColorError as exc:
                raise ClubValidationError(str(exc)) from exc
    if "gallery" in changes:
        site.gallery = _clean_gallery(changes["gallery"] or [])
    if "coaches" in changes:
        site.coaches = _clean_coaches(changes["coaches"] or [])
    if "founded_year" in changes:
        site.founded_year = changes["founded_year"]
    for field, clean in (
        ("highlights", _clean_highlights), ("history", _clean_history), ("pillars", _clean_pillars),
        ("news", _clean_news), ("videos", _clean_club_videos),
    ):
        if field in changes:
            setattr(site, field, clean(changes[field] or []))
    if "published" in changes and changes["published"] is not None:
        site.published = bool(changes["published"])
    if "show_prices" in changes and changes["show_prices"] is not None:
        site.show_prices = bool(changes["show_prices"])
    site.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.site_updated", entity_type="club_site", entity_id=str(site.id),
        new_value={"fields": sorted(changes), "published": site.published},
    )
    await db.commit()
    await db.refresh(site)
    return site


async def upload_site_image(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, slot: str, file_bytes: bytes,
    content_type: str, caption: str | None = None,
) -> tuple[ClubSite, str]:
    """Carica una foto della pagina nel bucket pubblico (come le foto degli
    atleti). La copertina e il logo si sostituiscono; una foto della
    galleria si aggiunge in fondo; la foto di un allenatore torna solo come
    indirizzo, da mettere nella scheda dell'allenatore."""
    from app.core.storage import UploadValidationError, upload_media

    if slot not in IMAGE_SLOTS:
        raise ClubValidationError("Tipo di foto non valido.")
    site = await get_site(db, scope=scope)
    if slot == "gallery" and len(site.gallery or []) >= MAX_GALLERY:
        raise ClubValidationError(f"La galleria ha già {MAX_GALLERY} foto: togline una prima di aggiungerne altre.")
    try:
        url = upload_media(file_bytes=file_bytes, content_type=content_type, key_prefix=f"club-sites/{scope.club_id}/{slot}")
    except UploadValidationError as exc:
        raise ClubValidationError("La foto deve essere un'immagine JPG, PNG o WebP di massimo 5 MB.") from exc
    if slot == "hero":
        site.hero_image_url = url
    elif slot == "logo":
        site.logo_url = url
    elif slot == "gallery":
        # Una lista nuova, non append: SQLAlchemy non vede le modifiche in
        # place di un JSONB e non le salverebbe.
        site.gallery = [*(site.gallery or []), {"url": url, "caption": (caption or "").strip()[:200] or None}]
    site.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.site_image_uploaded", entity_type="club_site", entity_id=str(site.id),
        new_value={"slot": slot},
    )
    await db.commit()
    await db.refresh(site)
    return site, url


async def _profiles(db: AsyncSession, *, athlete_ids: list[uuid.UUID]) -> dict[uuid.UUID, ClubAthletePublicProfile]:
    if not athlete_ids:
        return {}
    rows = (
        await db.execute(select(ClubAthletePublicProfile).where(ClubAthletePublicProfile.athlete_id.in_(athlete_ids)))
    ).scalars()
    return {p.athlete_id: p for p in rows}


async def list_athletes_public_status(db: AsyncSession, *, scope: ClubScope) -> list[dict]:
    """Gli atleti del club con lo stato del loro profilo pubblico: la
    segreteria vede chi ha il consenso e decide chi pubblicare."""
    athletes = list(
        (await db.execute(
            select(ClubAthlete)
            .where(ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE")
            .order_by(ClubAthlete.last_name, ClubAthlete.first_name)
        )).scalars()
    )
    profiles = await _profiles(db, athlete_ids=[a.id for a in athletes])
    belts = await current_belts(db, athlete_ids=[a.id for a in athletes])
    out = []
    for athlete in athletes:
        profile = profiles.get(athlete.id)
        consent = profile is not None and profile.consent_given_at is not None
        out.append({
            "athlete_id": athlete.id,
            "first_name": athlete.first_name,
            "last_name": athlete.last_name,
            "display_name": display_name(athlete),
            "photo_url": athlete.photo_url,
            "belt": belts.get(athlete.id),
            "consent": consent,
            "consent_given_at": profile.consent_given_at if consent else None,
            "show_photo": bool(profile and profile.show_photo),
            "published": bool(consent and profile.published),
        })
    return out


async def set_athlete_published(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, published: bool, actor_user_id: uuid.UUID,
) -> ClubAthletePublicProfile:
    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != scope.club_id:
        raise ClubNotFoundError("Atleta non trovato.")
    if published and not kinds.rules_of(await db.get(Club, scope.club_id)).public_as_club:
        raise ClubValidationError("Gli atleti dei corsi JAV non compaiono sul sito: sul sito ci sono solo i corsi.")
    profile = (await _profiles(db, athlete_ids=[athlete.id])).get(athlete.id)
    if published and (profile is None or profile.consent_given_at is None):
        raise ClubValidationError(
            "La famiglia non ha ancora dato il consenso: senza il consenso l'atleta non può comparire sul sito."
        )
    if profile is None:
        # Togliere dal sito chi non c'è mai stato: niente da fare.
        profile = ClubAthletePublicProfile(**scope.columns(), athlete_id=athlete.id, published=False)
        db.add(profile)
    profile.published = published
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_public_published" if published else "club.athlete_public_unpublished",
        entity_type="club_athlete", entity_id=str(athlete.id),
    )
    await db.commit()
    await db.refresh(profile)
    return profile


# --- La segreteria: la scheda pubblica di un judoca -----------------------------------------------

#: I due indirizzi IJF che hanno una scheda di judoca: il sito della
#: federazione (www.ijf.org/judoka/<id>) e JudoBase
#: (judobase.ijf.org/#/competitor/profile/<id>). Il numero è l'id IJF.
_IJF_JUDOKA_PATH = re.compile(r"^/judoka/\d+(/[^\s]*)?$")
_JUDOBASE_PROFILE = re.compile(r"^/?competitor/profile/\d+(/[^\s]*)?$")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
                  "youtube-nocookie.com", "www.youtube-nocookie.com")
NO_PUBLIC_PAGE = (
    "Gli atleti dei corsi JAV non hanno una pagina pubblica: sul sito ci sono solo i corsi, mai le persone."
)
IJF_URL_ERROR = (
    "Il link IJF non è valido: apri la scheda del judoca su ijf.org (www.ijf.org/judoka/...) o su "
    "JudoBase (judobase.ijf.org) e copia l'indirizzo dalla barra del browser."
)
YOUTUBE_URL_ERROR = (
    "Il link non è un video di YouTube: apri il video su YouTube, tocca «Condividi» e copia il link "
    "(per esempio https://youtu.be/...)."
)


def check_ijf_url(value: str | None) -> str | None:
    """Il link al profilo IJF, solo verso le due schede ufficiali. Un
    indirizzo qualsiasi non diventa un bottone sul sito di un minore."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ClubValidationError(IJF_URL_ERROR)
    host = (parsed.hostname or "").lower()
    if host in ("www.ijf.org", "ijf.org") and _IJF_JUDOKA_PATH.match(parsed.path):
        return value
    # JudoBase è un'applicazione a pagina singola: la scheda sta dopo il #.
    if host == "judobase.ijf.org" and _JUDOBASE_PROFILE.match(parsed.fragment or parsed.path):
        return value
    raise ClubValidationError(IJF_URL_ERROR)


def youtube_id_from_url(value: str) -> str:
    """L'id di un video da un link di YouTube (watch, youtu.be, shorts,
    embed, live). Si salva solo l'id: è ciò che rende impossibile mettere
    nella pagina un iframe verso un sito qualsiasi."""
    parsed = urlparse((value or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        raise ClubValidationError(YOUTUBE_URL_ERROR)
    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in _YOUTUBE_HOSTS:
        parts = [p for p in parsed.path.split("/") if p]
        if parts[:1] == ["watch"]:
            candidate = (parse_qs(parsed.query).get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
            candidate = parts[1]
    if not _YOUTUBE_ID.match(candidate):
        raise ClubValidationError(YOUTUBE_URL_ERROR)
    return candidate


async def _page_athlete(db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID) -> ClubAthlete:
    """Un atleta del club di chi chiede, e di un club che può avere judoca
    sul sito: l'unità dei corsi JAV no, nemmeno per preparare la scheda."""
    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != scope.club_id:
        raise ClubNotFoundError("Atleta non trovato.")
    if not kinds.rules_of(await db.get(Club, scope.club_id)).public_as_club:
        raise ClubValidationError(NO_PUBLIC_PAGE)
    return athlete


async def _page_profile(db: AsyncSession, athlete: ClubAthlete) -> ClubAthletePublicProfile:
    """La riga del profilo pubblico; se manca nasce senza consenso e non
    pubblicata. La segreteria può preparare la scheda prima del consenso:
    finché la famiglia non lo dà, non la vede nessuno."""
    profile = (await _profiles(db, athlete_ids=[athlete.id])).get(athlete.id)
    if profile is None:
        profile = ClubAthletePublicProfile(
            organization_id=athlete.organization_id, club_id=athlete.club_id, athlete_id=athlete.id,
            show_photo=False, published=False,
        )
        db.add(profile)
        await db.flush()
    return profile


async def _athlete_media(db: AsyncSession, athlete: ClubAthlete) -> list[ClubAthleteMedia]:
    return list(
        (await db.execute(
            select(ClubAthleteMedia)
            .where(ClubAthleteMedia.athlete_id == athlete.id, ClubAthleteMedia.club_id == athlete.club_id)
            .order_by(ClubAthleteMedia.created_at.desc())
        )).scalars()
    )


async def athlete_page_admin(db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID) -> dict:
    athlete = await _page_athlete(db, scope=scope, athlete_id=athlete_id)
    profile = (await _profiles(db, athlete_ids=[athlete.id])).get(athlete.id)
    consent = profile is not None and profile.consent_given_at is not None
    public_clubs = [club.id for club, _ in await _public_clubs(db) if club.id == athlete.club_id]
    live = bool(await _public_athletes(db, club_ids=public_clubs, athlete_ids=[athlete.id]))
    return {
        "athlete_id": athlete.id,
        "display_name": display_name(athlete),
        "photo_url": athlete.photo_url,
        "consent": consent,
        "show_photo": bool(profile and profile.show_photo),
        "published": bool(consent and profile.published),
        "live": live,
        "public_path": f"/judocas/{athlete.id}",
        "bio": profile.bio if profile else None,
        "ijf_profile_url": profile.ijf_profile_url if profile else None,
        "favorite_technique": profile.favorite_technique if profile else None,
        "dominant_side": profile.dominant_side if profile else None,
        "media": [
            {"id": m.id, "kind": m.kind, "url": m.url, "youtube_id": m.youtube_id, "caption": m.caption,
             "published": m.published, "created_at": m.created_at}
            for m in await _athlete_media(db, athlete)
        ],
        "max_photos": MAX_ATHLETE_PHOTOS,
        "max_videos": MAX_ATHLETE_VIDEOS,
    }


async def update_athlete_page(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, actor_user_id: uuid.UUID, changes: dict,
) -> dict:
    """I testi della scheda: profilo IJF, due righe, tecnica, guardia. Le due
    righe sono le stesse che la famiglia scrive dal suo portale: le vedono e
    le correggono entrambi."""
    athlete = await _page_athlete(db, scope=scope, athlete_id=athlete_id)
    profile = await _page_profile(db, athlete)
    if "ijf_profile_url" in changes:
        profile.ijf_profile_url = check_ijf_url(changes["ijf_profile_url"])
    if "bio" in changes:
        profile.bio = (changes["bio"] or "").strip()[:280] or None
    if "favorite_technique" in changes:
        profile.favorite_technique = (changes["favorite_technique"] or "").strip()[:80] or None
    if "dominant_side" in changes:
        side = (changes["dominant_side"] or "").strip().upper() or None
        if side is not None and side not in DOMINANT_SIDES:
            raise ClubValidationError("La guardia è sinistra o destra.")
        profile.dominant_side = side
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_page_updated", entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"fields": sorted(changes)},
    )
    await db.commit()
    return await athlete_page_admin(db, scope=scope, athlete_id=athlete.id)


async def _count_media(db: AsyncSession, athlete: ClubAthlete, kind: str) -> int:
    return (await db.execute(
        select(func.count()).select_from(ClubAthleteMedia)
        .where(ClubAthleteMedia.athlete_id == athlete.id, ClubAthleteMedia.club_id == athlete.club_id,
               ClubAthleteMedia.kind == kind)
    )).scalar_one()


async def add_athlete_photo(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, actor_user_id: uuid.UUID, file_bytes: bytes,
    content_type: str, caption: str | None = None,
) -> dict:
    """Una foto nella scheda, nel bucket pubblico come le foto degli atleti.
    Nasce non pubblicata: la segreteria la guarda e poi la mette sul sito."""
    from app.core.storage import UploadValidationError, upload_media

    athlete = await _page_athlete(db, scope=scope, athlete_id=athlete_id)
    if await _count_media(db, athlete, "PHOTO") >= MAX_ATHLETE_PHOTOS:
        raise ClubValidationError(
            f"La scheda ha già {MAX_ATHLETE_PHOTOS} foto: togline una prima di aggiungerne altre."
        )
    try:
        url = upload_media(file_bytes=file_bytes, content_type=content_type,
                           key_prefix=f"club-athletes/{athlete.id}/page")
    except UploadValidationError as exc:
        raise ClubValidationError("La foto deve essere un'immagine JPG, PNG o WebP di massimo 5 MB.") from exc
    media = ClubAthleteMedia(
        **scope.columns(), athlete_id=athlete.id, kind="PHOTO", url=url,
        caption=(caption or "").strip()[:200] or None, published=False, created_by_user_id=actor_user_id,
    )
    db.add(media)
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_media_added", entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"media_id": str(media.id), "kind": "PHOTO"},
    )
    await db.commit()
    return await athlete_page_admin(db, scope=scope, athlete_id=athlete.id)


async def add_athlete_video(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, actor_user_id: uuid.UUID, url: str,
    caption: str | None = None,
) -> dict:
    athlete = await _page_athlete(db, scope=scope, athlete_id=athlete_id)
    youtube_id = youtube_id_from_url(url)
    existing = (await db.execute(
        select(ClubAthleteMedia.id).where(ClubAthleteMedia.athlete_id == athlete.id,
                                          ClubAthleteMedia.youtube_id == youtube_id)
    )).first()
    if existing is not None:
        raise ClubValidationError("Questo video è già nella scheda.")
    if await _count_media(db, athlete, "VIDEO") >= MAX_ATHLETE_VIDEOS:
        raise ClubValidationError(
            f"La scheda ha già {MAX_ATHLETE_VIDEOS} video: togline uno prima di aggiungerne altri."
        )
    media = ClubAthleteMedia(
        **scope.columns(), athlete_id=athlete.id, kind="VIDEO", youtube_id=youtube_id,
        caption=(caption or "").strip()[:200] or None, published=False, created_by_user_id=actor_user_id,
    )
    db.add(media)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Due clic nello stesso istante: il vincolo UNIQUE ne tiene uno.
        await db.rollback()
        raise ClubValidationError("Questo video è già nella scheda.") from exc
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_media_added", entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"media_id": str(media.id), "kind": "VIDEO", "youtube_id": youtube_id},
    )
    await db.commit()
    return await athlete_page_admin(db, scope=scope, athlete_id=athlete.id)


async def _media_of(db: AsyncSession, athlete: ClubAthlete, media_id: uuid.UUID) -> ClubAthleteMedia:
    media = await db.get(ClubAthleteMedia, media_id)
    if media is None or media.athlete_id != athlete.id or media.club_id != athlete.club_id:
        raise ClubNotFoundError("Foto o video non trovato.")
    return media


async def update_athlete_media(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, media_id: uuid.UUID,
    actor_user_id: uuid.UUID, changes: dict,
) -> dict:
    """Pubblica o toglie una foto o un video, o ne cambia la didascalia.
    Pubblicare si può anche prima del consenso: sul sito non esce comunque
    nulla finché la famiglia non lo dà e permette la foto."""
    athlete = await _page_athlete(db, scope=scope, athlete_id=athlete_id)
    media = await _media_of(db, athlete, media_id)
    if changes.get("published") is not None:
        media.published = bool(changes["published"])
    if "caption" in changes:
        media.caption = (changes["caption"] or "").strip()[:200] or None
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_media_published" if media.published else "club.athlete_media_unpublished",
        entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"media_id": str(media.id), "fields": sorted(changes)},
    )
    await db.commit()
    return await athlete_page_admin(db, scope=scope, athlete_id=athlete.id)


async def delete_athlete_media(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, media_id: uuid.UUID, actor_user_id: uuid.UUID,
) -> dict:
    athlete = await _page_athlete(db, scope=scope, athlete_id=athlete_id)
    media = await _media_of(db, athlete, media_id)
    await db.delete(media)
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_media_deleted", entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"media_id": str(media_id), "kind": media.kind},
    )
    await db.commit()
    return await athlete_page_admin(db, scope=scope, athlete_id=athlete.id)


# --- La famiglia: il consenso ---------------------------------------------------------------------


def consent_dict(athlete: ClubAthlete, profile: ClubAthletePublicProfile | None) -> dict:
    consent = profile is not None and profile.consent_given_at is not None
    return {
        "athlete_id": athlete.id,
        "display_name": display_name(athlete),
        "consent": consent,
        "consent_given_at": profile.consent_given_at if consent else None,
        "show_photo": bool(profile and profile.show_photo),
        "bio": profile.bio if profile else None,
        # La famiglia vede se il club l'ha messo davvero sul sito.
        "published": bool(consent and profile.published),
    }


async def get_consent(db: AsyncSession, *, athlete: ClubAthlete) -> dict:
    return consent_dict(athlete, (await _profiles(db, athlete_ids=[athlete.id])).get(athlete.id))


async def update_consent(
    db: AsyncSession, *, athlete: ClubAthlete, actor_user_id: uuid.UUID, changes: dict,
) -> dict:
    """Il genitore dà o ritira il consenso, e sceglie foto e due righe.
    L'atleta arriva già controllato (get_owned_athlete). Ritirare il
    consenso toglie subito l'atleta dal sito: la pubblicazione del club non
    sopravvive al ritiro, e un nuovo consenso non la ripristina da sola."""
    profile = (await _profiles(db, athlete_ids=[athlete.id])).get(athlete.id)
    if profile is None:
        profile = ClubAthletePublicProfile(
            organization_id=athlete.organization_id, club_id=athlete.club_id, athlete_id=athlete.id,
            show_photo=False, published=False,
        )
        db.add(profile)
    consent = changes.get("consent")
    if consent is True and profile.consent_given_at is None:
        profile.consent_given_at = utcnow()
        profile.consent_by_user_id = actor_user_id
    elif consent is False:
        profile.consent_given_at = None
        profile.consent_by_user_id = actor_user_id
        profile.published = False
        profile.show_photo = False
        # Come la pubblicazione: anche foto e video tornano privati, e un
        # nuovo consenso non li ripubblica da solo.
        for media in (await db.execute(
            select(ClubAthleteMedia).where(ClubAthleteMedia.athlete_id == athlete.id)
        )).scalars():
            media.published = False
    if changes.get("show_photo") is not None and profile.consent_given_at is not None:
        profile.show_photo = bool(changes["show_photo"])
    if "bio" in changes:
        bio = (changes["bio"] or "").strip()
        profile.bio = bio[:280] or None
    await audit_service.record(
        db, organization_id=athlete.organization_id, actor_user_id=actor_user_id,
        action="club.athlete_public_consent", entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"consent": profile.consent_given_at is not None, "show_photo": profile.show_photo},
    )
    await db.commit()
    await db.refresh(profile)
    return consent_dict(athlete, profile)
