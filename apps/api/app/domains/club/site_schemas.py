"""Le risposte del sito pubblico e dell'editor della pagina del club.

Gli schemi pubblici sono la seconda rete della privacy (la prima è
club/site.py): un campo che non è dichiarato qui non arriva al browser,
anche se qualcuno lo mettesse nel dizionario per sbaglio. Per questo non
c'è niente come data di nascita, peso o genitore, nemmeno facoltativo.
"""

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class PublicClubRef(BaseModel):
    name: str
    slug: str
    logo_url: str | None = None


class PublicClubCard(PublicClubRef):
    city: str | None
    tagline: str | None
    hero_image_url: str | None
    athletes_active: int
    judoka_public: int


class PublicJudoka(BaseModel):
    id: uuid.UUID
    display_name: str
    photo_url: str | None
    #: False: in classifica ma senza consenso alla pagina pubblica (niente
    #: foto, niente link a /judocas/{id}).
    has_page: bool = True
    belt: str | None
    age_band: str
    club: PublicClubRef
    points: int
    competitions: int
    gold: int
    silver: int
    bronze: int


class PublicRankingRow(PublicJudoka):
    position: int


class PublicEvent(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    level: str
    status: str
    starts_on: date
    ends_on: date
    registration_deadline: date
    location: str | None
    organizer: str | None
    #: None per un evento della rete (il calendário comune dei club).
    club: PublicClubRef | None = None
    #: Le fasce federali ammesse; vuoto = tutte.
    age_groups: list[str] = []
    transport_mode: str = "TBC"
    #: Quanto costa iscriversi (dell'organizzatore, non una quota di famiglia).
    price_cents: int = 0
    starts_at_time: time | None = None
    registration_deadline_time: time | None = None
    places: int | None = None
    circular_url: str | None = None
    #: La foto o la locandina dell'evento (bucket media); None = l'icona del tipo.
    image_url: str | None = None
    #: Quanti atleti iscritti (solo il numero).
    entries_count: int = 0


class PublicDecorPhoto(BaseModel):
    url: str
    club: str


class PublicMedal(BaseModel):
    athlete_id: uuid.UUID
    display_name: str
    photo_url: str | None
    belt: str | None
    placement: int
    category: str | None
    event_id: uuid.UUID
    event_name: str
    event_level: str
    date: date
    club: PublicClubRef


class PortalTotals(BaseModel):
    clubs: int
    athletes_active: int
    judoka_public: int


class PortalHomeRead(BaseModel):
    season: int
    season_label: str
    clubs: list[PublicClubCard]
    totals: PortalTotals
    upcoming_events: list[PublicEvent]
    top_ranking: list[PublicRankingRow]
    latest_medals: list[PublicMedal]


class GalleryItem(BaseModel):
    url: str = Field(max_length=500)
    caption: str | None = Field(default=None, max_length=200)


class CoachItem(BaseModel):
    name: str = Field(max_length=120)
    role: str | None = Field(default=None, max_length=120)
    photo_url: str | None = Field(default=None, max_length=500)
    #: Il grado ("Cinto preto 4.º dan") e due righe di presentazione.
    grade: str | None = Field(default=None, max_length=60)
    bio: str | None = Field(default=None, max_length=400)


class HighlightItem(BaseModel):
    """Un numero che il club dice di sé ("40+" · "anos de judo")."""

    value: str = Field(max_length=12)
    label: str = Field(max_length=60)


class HistoryItem(BaseModel):
    year: int = Field(ge=1882, le=2100)
    title: str = Field(max_length=120)
    text: str | None = Field(default=None, max_length=600)


class PillarItem(BaseModel):
    """Perché allenarsi qui: un titolo e due righe."""

    title: str = Field(max_length=60)
    text: str | None = Field(default=None, max_length=300)


class NewsItem(BaseModel):
    """Una novità, come un post della pagina Facebook del club."""

    date: date
    title: str = Field(max_length=140)
    text: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)


class ClubVideoItem(BaseModel):
    #: Solo l'id: il sito costruisce da sé l'indirizzo youtube-nocookie.
    youtube_id: str = Field(max_length=11)
    caption: str | None = Field(default=None, max_length=200)


class ClubVideoWrite(BaseModel):
    """Un video come lo scrive la segreteria: il link di YouTube (o l'id)."""

    url: str = Field(max_length=500)
    caption: str | None = Field(default=None, max_length=200)


class ScheduleSlot(BaseModel):
    course: str
    level: str | None
    min_age: int | None
    max_age: int | None
    starts_at: str
    ends_at: str
    room: str | None


class ScheduleDay(BaseModel):
    #: 0 = lunedì, come date.weekday().
    weekday: int
    slots: list[ScheduleSlot]


class SiteContent(BaseModel):
    tagline: str | None
    about: str | None
    city: str | None
    hero_image_url: str | None
    logo_url: str | None
    gallery: list[GalleryItem]
    coaches: list[CoachItem]
    contact_phone: str | None
    contact_email: str | None
    address: str | None
    map_url: str | None
    instagram_url: str | None
    facebook_url: str | None
    youtube_url: str | None
    tiktok_url: str | None = None
    website_url: str | None
    #: I colori scelti dalla segreteria, così come sono ("#RRGGBB" o vuoti).
    brand_primary: str | None = None
    brand_secondary: str | None = None
    brand_accent: str | None = None
    founded_year: int | None = None
    venue: str | None = None
    highlights: list[HighlightItem] = []
    history: list[HistoryItem] = []
    pillars: list[PillarItem] = []
    news: list[NewsItem] = []
    videos: list[ClubVideoItem] = []


class BrandTheme(BaseModel):
    """Il tema calcolato da club/brand.py: i colori con i ripieghi e, per
    ogni fondo, il testo che si legge. Il browser lo usa così com'è."""

    primary: str
    secondary: str
    accent: str
    on_primary: str
    on_accent: str
    primary_text: str
    accent_on_dark: str
    cover_from: str
    cover_to: str
    #: False = il club non ha scelto colori: sono quelli di JudoArteVida.
    custom: bool
    #: Avvisi per l'editor: PRIMARY_DARKENED, ACCENT_LIKE_PRIMARY.
    warnings: list[str]


class GroupSlot(BaseModel):
    weekday: int
    starts_at: str
    ends_at: str
    course: str


class PublicClubGroup(BaseModel):
    """Un gruppo (piano attivo) come lo dice anche JAVBOT: età e allenamenti
    sempre, i soldi solo con "mostra i prezzi" acceso (altrimenti None).
    "price", non "fee": è il listino del club; le quote (fee) sono di una
    famiglia e non escono mai dal sito (i test lo cercano nel JSON)."""

    name: str
    min_age: int | None
    max_age: int | None
    slots: list[GroupSlot]
    monthly_price_cents: int | None
    enrollment_price_cents: int | None
    due_day: int | None
    billing_months: list[int] | None
    description: str | None


class PublicClubPage(SiteContent):
    name: str
    slug: str
    theme: BrandTheme
    updated_at: datetime
    season_label: str
    athletes_active: int
    schedule: list[ScheduleDay]
    show_prices: bool
    groups: list[PublicClubGroup]
    upcoming_events: list[PublicEvent]
    judoka: list[PublicJudoka]
    #: Il ranking del club nella stagione (i primi dieci), come /ranking.
    ranking: list[PublicRankingRow]
    recent_medals: list[PublicMedal]


class PublicResult(BaseModel):
    event_id: uuid.UUID
    event_name: str
    level: str
    date: date
    location: str | None = None
    placement: int
    category: str | None
    points: int


class PublicUpcomingEntry(PublicEvent):
    """Una prova a cui il judoca è iscritto: l'evento e la sua categoria."""

    category: str | None


class PublicBeltStep(BaseModel):
    grade: str
    awarded_on: date


class PublicRankingPosition(BaseModel):
    """Il posto nel Jav Ranking della stagione, nella sua fascia d'età."""

    position: int
    total: int
    age_band: str
    points: int


class PublicPhoto(BaseModel):
    id: uuid.UUID
    url: str
    caption: str | None


class PublicVideo(BaseModel):
    id: uuid.UUID
    #: Solo l'id: il sito costruisce da sé l'indirizzo youtube-nocookie.
    youtube_id: str
    caption: str | None


class PublicJudokaProfile(PublicJudoka):
    bio: str | None
    season_label: str
    season_points: int
    results: list[PublicResult]
    #: La scheda in stile IJF (docs/club-portal.md, "La scheda del judoca").
    #: Niente data di nascita, peso, contatti: la categoria è quella scritta
    #: sull'iscrizione a una gara, la stessa che si legge nei risultati.
    category: str | None = None
    ranking: PublicRankingPosition | None = None
    belt_history: list[PublicBeltStep] = []
    upcoming: list[PublicUpcomingEntry] = []
    photos: list[PublicPhoto] = []
    videos: list[PublicVideo] = []
    ijf_profile_url: str | None = None
    favorite_technique: str | None = None
    dominant_side: str | None = None


class PublicParticipant(BaseModel):
    athlete_id: uuid.UUID
    display_name: str
    #: La scheda pubblica (/judocas/<id>) c'è solo con il consenso della famiglia.
    has_page: bool = False
    club: PublicClubRef | None = None
    photo_url: str | None
    belt: str | None
    age_band: str
    category: str | None
    placement: int | None
    points: int


class PublicEventDetail(PublicEvent):
    description: str | None
    categories: str | None
    #: Tutti gli iscritti dei club pubblici, come in classifica («Nome I.»).
    participants_count: int
    participants: list[PublicParticipant]


class PublicRankingRead(BaseModel):
    season: int
    season_label: str
    #: "year" (l'anno solare, il ranking che conta), "month" o "all".
    period: str = "year"
    month: int | None = None
    clubs: list[PublicClubRef]
    rows: list[PublicRankingRow]


class PublicClubRankingRow(BaseModel):
    position: int
    club: PublicClubRef
    city: str | None
    points: int
    results: int
    gold: int
    silver: int
    bronze: int
    athletes: int
    events: int


class PublicCupWinner(BaseModel):
    year: int
    club: PublicClubRef
    points: int


class PublicClubRankingRead(BaseModel):
    """La Taça dos Clubes."""

    season: int
    season_label: str
    period: str
    month: int | None
    #: L'anno è chiuso: il primo ha vinto la coppa.
    is_final: bool
    rows: list[PublicClubRankingRow]
    #: L'albo d'oro: il vincitore di ogni anno chiuso, dal più recente.
    winners: list[PublicCupWinner]


class PublicRankingCardResult(BaseModel):
    event_id: uuid.UUID
    event_name: str
    level: str
    date: date
    location: str | None
    placement: int
    points: int


class PublicRankingCard(PublicJudoka):
    """Il judoca in classifica senza pagina pubblica: niente foto, età,
    categoria, media o prove in programma."""

    season_label: str
    season_points: int
    ranking: PublicRankingPosition | None
    results: list[PublicRankingCardResult]


class PublicRankingCardRead(BaseModel):
    has_page: bool
    profile: PublicJudokaProfile | None
    card: PublicRankingCard | None


# --- Segreteria -----------------------------------------------------------------------------------


class SiteAdminRead(SiteContent):
    name: str
    slug: str
    published: bool
    #: I prezzi dei piani si possono dire sul sito (assistente JAVBOT).
    show_prices: bool = False
    updated_at: datetime
    theme: BrandTheme


class SiteWrite(BaseModel):
    """Tutto facoltativo: si manda solo ciò che cambia."""

    tagline: str | None = Field(default=None, max_length=200)
    about: str | None = Field(default=None, max_length=8000)
    city: str | None = Field(default=None, max_length=120)
    hero_image_url: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=500)
    gallery: list[GalleryItem] | None = None
    coaches: list[CoachItem] | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    contact_email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=300)
    map_url: str | None = Field(default=None, max_length=500)
    instagram_url: str | None = Field(default=None, max_length=500)
    facebook_url: str | None = Field(default=None, max_length=500)
    youtube_url: str | None = Field(default=None, max_length=500)
    tiktok_url: str | None = Field(default=None, max_length=500)
    website_url: str | None = Field(default=None, max_length=500)
    brand_primary: str | None = Field(default=None, max_length=7)
    brand_secondary: str | None = Field(default=None, max_length=7)
    brand_accent: str | None = Field(default=None, max_length=7)
    founded_year: int | None = Field(default=None, ge=1882, le=2100)
    venue: str | None = Field(default=None, max_length=160)
    highlights: list[HighlightItem] | None = None
    history: list[HistoryItem] | None = None
    pillars: list[PillarItem] | None = None
    news: list[NewsItem] | None = None
    #: I video si scrivono come link (o id) e si salvano come id.
    videos: list[ClubVideoWrite] | None = None
    published: bool | None = None
    show_prices: bool | None = None


class PublishWrite(BaseModel):
    published: bool


class SiteImageRead(BaseModel):
    url: str
    site: SiteAdminRead


class AthletePublicStatusRead(BaseModel):
    athlete_id: uuid.UUID
    first_name: str
    last_name: str
    display_name: str
    photo_url: str | None
    belt: str | None
    consent: bool
    consent_given_at: datetime | None
    show_photo: bool
    published: bool


class AthleteMediaRead(BaseModel):
    id: uuid.UUID
    kind: str
    url: str | None
    youtube_id: str | None
    caption: str | None
    published: bool
    created_at: datetime


class AthletePageAdminRead(BaseModel):
    """La scheda pubblica di un atleta vista dalla segreteria: tutto, anche
    ciò che non è (ancora) pubblico, con lo stato del consenso accanto."""

    athlete_id: uuid.UUID
    display_name: str
    photo_url: str | None
    consent: bool
    show_photo: bool
    published: bool
    #: True quando la scheda si vede davvero sul sito (consenso, pubblicazione, club pubblico).
    live: bool
    public_path: str
    bio: str | None
    ijf_profile_url: str | None
    favorite_technique: str | None
    dominant_side: str | None
    media: list[AthleteMediaRead]
    max_photos: int
    max_videos: int


class AthletePageWrite(BaseModel):
    """Tutto facoltativo: si manda solo ciò che cambia; "" cancella."""

    ijf_profile_url: str | None = Field(default=None, max_length=300)
    bio: str | None = Field(default=None, max_length=1500)
    favorite_technique: str | None = Field(default=None, max_length=80)
    dominant_side: str | None = Field(default=None, max_length=5)


class AthleteVideoWrite(BaseModel):
    url: str = Field(max_length=300)
    caption: str | None = Field(default=None, max_length=200)


class AthleteMediaWrite(BaseModel):
    published: bool | None = None
    caption: str | None = Field(default=None, max_length=200)


# --- Famiglia -------------------------------------------------------------------------------------


class PublicProfileConsentRead(BaseModel):
    athlete_id: uuid.UUID
    display_name: str
    consent: bool
    consent_given_at: datetime | None
    show_photo: bool
    bio: str | None
    published: bool


class PublicProfileConsentWrite(BaseModel):
    consent: bool | None = None
    show_photo: bool | None = None
    bio: str | None = Field(default=None, max_length=1500)


# --- Cursos JAV nas escolas -----------------------------------------------------------------------


class PublicCourseSlot(BaseModel):
    weekday: int
    starts_at: str
    ends_at: str


class PublicCourse(BaseModel):
    """Un corso nelle scuole: luogo, orario, età. Nessuna persona."""

    id: uuid.UUID
    name: str
    level: str | None
    min_age: int | None
    max_age: int | None
    venue_name: str | None
    venue_address: str | None
    venue_city: str | None
    #: Il logo della scuola, se il corso l'ha.
    venue_logo_url: str | None = None
    description: str | None
    #: Il nome scritto a mano per il sito, non quello dell'account.
    coach_name: str | None
    slots: list[PublicCourseSlot]
    #: Dove ci si iscrive: /c/<slug>?curso=<id>.
    signup_path: str


class PublicCoursesUnit(BaseModel):
    name: str
    slug: str
    tagline: str | None
    about: str | None
    hero_image_url: str | None
    contact_phone: str | None
    contact_email: str | None


class PublicCoursesRead(BaseModel):
    unit: PublicCoursesUnit | None
    courses: list[PublicCourse]
