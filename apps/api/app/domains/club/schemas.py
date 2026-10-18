"""Cosa entra ed esce dalle API del club.

Gli importi li decide sempre il server (piano, gara): il browser sceglie
quali quote paga, mai quanto (CLAUDE.md §5).
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# --- Catalogo -------------------------------------------------------------------------------------


class BeltRead(BaseModel):
    code: str
    label: str
    color: str
    stripe: str | None
    rank: int


class AgeBandRead(BaseModel):
    code: str
    label: str
    min_age: int
    max_age: int | None


class AchievementDefRead(BaseModel):
    code: str
    label: str
    description: str
    target: int


class ClubConfigRead(BaseModel):
    """Tutto ciò che l'interfaccia deve sapere per disegnare cinture,
    classifiche e medaglie senza ripeterlo nel codice del browser."""

    season: int
    season_label: str
    belts: list[BeltRead]
    age_bands: list[AgeBandRead]
    placement_labels: dict[str, str]
    #: (oro, argento, bronzo, partecipazione) per livello.
    level_points: dict[str, list[int]]
    level_labels: dict[str, str]
    achievements: list[AchievementDefRead]
    weekdays: list[str]


# --- Piani ----------------------------------------------------------------------------------------


class PlanWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    min_age: int = Field(ge=0, le=110)
    max_age: int | None = Field(default=None, ge=0, le=110)
    monthly_fee_cents: int = Field(ge=0, le=10_000_000)
    enrollment_fee_cents: int = Field(default=0, ge=0, le=10_000_000)
    due_day: int = Field(default=10, ge=1, le=28)
    billing_months: list[int] | None = None
    active: bool = True
    color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    allows_high_competition: bool = False


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    min_age: int | None = Field(default=None, ge=0, le=110)
    max_age: int | None = Field(default=None, ge=0, le=110)
    monthly_fee_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    enrollment_fee_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    due_day: int | None = Field(default=None, ge=1, le=28)
    billing_months: list[int] | None = None
    active: bool | None = None
    color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    allows_high_competition: bool | None = None


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    min_age: int
    max_age: int | None
    monthly_fee_cents: int
    enrollment_fee_cents: int
    due_day: int
    billing_months: list[int]
    active: bool
    color: str | None = None
    allows_high_competition: bool = False
    #: Gli atleti attivi con questo piano (solo nell'elenco della segreteria).
    athletes_count: int = 0


# --- Atleti ---------------------------------------------------------------------------------------


class AthleteCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    birth_date: date
    sex: str = Field(pattern="^[MF]$")
    is_self: bool = False
    fiscal_code: str | None = Field(default=None, max_length=16)
    weight_kg: Decimal | None = Field(default=None, gt=0, le=300)
    #: Per chi arriva già con una cintura; altrimenti bianca. Nei corsi
    #: JAV non ci sono cinture: va lasciato vuoto.
    belt: str | None = None
    #: Il corso a cui iscriverlo subito (nei corsi JAV: la scuola scelta).
    course_id: uuid.UUID | None = None


class AthleteUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    birth_date: date | None = None
    sex: str | None = Field(default=None, pattern="^[MF]$")
    fiscal_code: str | None = Field(default=None, max_length=16)
    weight_kg: Decimal | None = Field(default=None, gt=0, le=300)
    #: Ha il judogi bianco per le gare (lo dichiara la famiglia o la segreteria).
    white_judogi: bool | None = None


class AthleteAdminUpdate(AthleteUpdate):
    plan_id: uuid.UUID | None = None
    plan_locked: bool | None = None
    status: str | None = None
    federation_number: str | None = Field(default=None, max_length=32)
    federation_expires_on: date | None = None
    social_tier: str | None = Field(default=None, pattern="^[ABC]$")
    adapted_judo: bool | None = None


class PlanSummaryRead(BaseModel):
    id: uuid.UUID
    name: str
    monthly_fee_cents: int


class FeeRead(BaseModel):
    id: uuid.UUID
    #: None per la quota socio del genitore (MEMBERSHIP).
    athlete_id: uuid.UUID | None
    athlete_name: str | None = None
    kind: str
    period: str
    description: str
    amount_cents: int
    gross_amount_cents: int | None = None
    discount_cents: int = 0
    discount_note: str | None = None
    absence_adjustment: str | None = None
    due_date: date
    status: str
    overdue: bool
    paid_at: datetime | None
    paid_via_proof_id: uuid.UUID | None
    payment_note: str | None
    #: BANK_TRANSFER / CASH / CARD / WALLET; None se da pagare o segnata
    #: pagata prima che il metodo si registrasse.
    payment_method: str | None = None
    #: Per i contanti: a chi sono stati consegnati.
    cash_received_by_name: str | None = None
    waive_reason: str | None
    competition_id: uuid.UUID | None
    #: Nei corsi JAV: il corso a cui la mensilità è attribuita (NULL = senza corso).
    course_id: uuid.UUID | None = None
    #: La segreteria l'ha segnata «non bloccante»: anche scaduta, non ferma
    #: l'iscrizione alle gare (club/participation.py).
    non_blocking: bool = False
    #: L'ultima prova di pagamento collegata (anche rifiutata), solo negli
    #: elenchi della segreteria: la si apre dalla quota.
    proof_id: uuid.UUID | None = None
    proof_status: str | None = None
    #: NULL = condono; EXEMPT = «Isenta este mês» (club/fee_splits.py).
    waive_kind: str | None = None
    #: Il resto di un pagamento parziale: la quota da cui nasce e perché.
    split_from_fee_id: uuid.UUID | None = None
    split_reason: str | None = None


class CertificateStatusRead(BaseModel):
    #: MISSING / VALID / EXPIRING / EXPIRED
    status: str
    id: uuid.UUID | None
    type: str | None
    issued_on: date | None
    expires_on: date | None


class NextCompetitionRead(BaseModel):
    competition_id: uuid.UUID
    name: str
    starts_on: date
    location: str | None
    category: str | None


class MedalsRead(BaseModel):
    gold: int
    silver: int
    bronze: int


class AthleteCardRead(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    birth_date: date
    age: int
    season_age: int
    #: Gli anni compiuti entro il 31 dicembre di quest'anno: decidono il gruppo.
    federal_age: int = 0
    sex: str
    photo_url: str | None
    is_self: bool
    status: str
    weight_kg: Decimal | None
    fiscal_code: str | None
    federation_number: str | None
    federation_expires_on: date | None
    social_tier: str | None = None
    adapted_judo: bool = False
    plan: PlanSummaryRead | None
    plan_locked: bool
    belt: BeltRead | None
    next_fee: FeeRead | None
    due_cents: int
    overdue_count: int
    certificate: CertificateStatusRead
    next_competition: NextCompetitionRead | None
    ranking_points: int
    medals: MedalsRead
    attendances: int
    xp: int
    level: int
    level_xp_floor: int
    next_level_xp: int
    #: 0..1, verso il livello successivo.
    progress: float
    achievements_earned: int
    #: La scheda «salute sportiva»: gare, categoria, gruppo del ranking.
    competitions_count: int = 0
    weight_category: str | None = None
    age_band: str | None = None
    club_name: str | None = None
    white_judogi: bool = False
    #: Gli obblighi (club/obligations.py): judogi, certificato, quota annuale.
    obligations: dict | None = None


class BeltHistoryRead(BeltRead):
    id: uuid.UUID
    awarded_on: date
    note: str | None


class CertificateRead(BaseModel):
    id: uuid.UUID
    type: str
    issued_on: date
    expires_on: date
    status: str
    original_filename: str


class AthleteCompetitionRead(BaseModel):
    competition_id: uuid.UUID
    entry_id: uuid.UUID
    name: str
    starts_on: date
    location: str | None
    level: str
    category: str | None
    status: str
    placement: int | None
    points: int


class AchievementRead(BaseModel):
    code: str
    label: str
    description: str
    earned: bool
    current: int
    target: int


class AthleteDetailRead(AthleteCardRead):
    belt_history: list[BeltHistoryRead]
    certificates: list[CertificateRead]
    fees: list[FeeRead]
    competitions: list[AthleteCompetitionRead]
    achievements: list[AchievementRead]


# --- Famiglia -------------------------------------------------------------------------------------


class ProofRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    amount_cents: int
    #: La parte pagata con il credito del wallet.
    credit_cents: int = 0
    status: str
    note: str | None
    #: None quando il credito ha pagato tutto e non c'è una ricevuta.
    original_filename: str | None
    rejection_reason: str | None
    reviewed_at: datetime | None
    uploaded_by_user_id: uuid.UUID
    #: BANK_TRANSFER o MBWAY (con la ricevuta), CASH (consegnati a qualcuno).
    method: str = "BANK_TRANSFER"
    cash_received_by_name: str | None = None
    #: "MEN-2026-0042": il numero da dire alla segreteria.
    receipt_number: str | None = None
    #: Il giorno del pagamento dichiarato (None = quello del caricamento).
    paid_on: date | None = None
    fees: list[FeeRead]


class MonthRowRead(BaseModel):
    """Un atleta nel quadro del mese (month_board.py)."""

    athlete_id: uuid.UUID
    first_name: str
    last_name: str
    photo_url: str | None
    group: str | None
    #: PAID, DUE, OVERDUE, PARTIAL, WAIVED, MONTH_EXEMPT, EXEMPT, NONE.
    state: str
    fee: "FeeRead | None"
    arrears: list["FeeRead"]
    other_due: list["FeeRead"]
    guardian_email: str | None = None
    #: La mensilità divisa da un pagamento parziale: la parte pagata e i resti.
    parts: list["FeeRead"] = []
    paid_cents: int = 0
    due_cents: int = 0


class MonthTotalsRead(BaseModel):
    athletes: int
    expected_cents: int
    collected_cents: int
    missing_cents: int
    paid: int
    to_pay: int
    overdue: int
    exempt: int
    none: int
    arrears_cents: int
    other_due_cents: int
    partial: int = 0


class MonthBoardRead(BaseModel):
    period: str
    first_day: date
    last_day: date
    is_current: bool
    rows: list[MonthRowRead]
    totals: MonthTotalsRead


class FamilyRead(BaseModel):
    season: int
    season_label: str
    athletes: list[AthleteCardRead]
    due_fees: list[FeeRead]
    due_cents: int
    overdue_cents: int
    paid_season_cents: int
    recent_proofs: list[ProofRead]
    open_competitions: int
    season_months: list["AthleteSeasonMonthsRead"] = []
    #: «Questo mese»: la mensilità di ogni figlio e ciò che resta.
    this_month: MonthBoardRead | None = None


class AthleteSeasonMonthsRead(BaseModel):
    """Le mensilità della stagione di un atleta, in numeri: il grafico della
    pagina della famiglia."""

    athlete_id: uuid.UUID
    first_name: str
    paid_cents: int
    due_cents: int
    overdue_cents: int
    months_paid: int
    months_due: int
    months_overdue: int


class UrlRead(BaseModel):
    url: str


class ReasonWrite(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class NoteWrite(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class MarkPaidWrite(NoteWrite):
    """La segreteria segna pagata una quota: come, e per i contanti a chi
    (una persona dello staff, o un nome scritto)."""

    method: str = Field(pattern="^(BANK_TRANSFER|MBWAY|CASH|CARD)$")
    cash_received_by_user_id: uuid.UUID | None = None
    cash_received_by_name: str | None = Field(default=None, max_length=120)


class CashReceiverRead(BaseModel):
    user_id: uuid.UUID
    name: str


class MonthProofRead(BaseModel):
    id: uuid.UUID
    method: str
    has_file: bool
    status: str
    created_at: datetime


class MonthRead(BaseModel):
    period: str
    year: int
    month: int
    #: club/months.py::MONTH_STATES
    state: str
    current: bool
    federal_age: int
    group_name: str | None
    #: Solo per i mesi futuri: la previsione, con il gruppo di quell'anno.
    expected_cents: int | None
    fee: FeeRead | None
    proof: MonthProofRead | None
    attendances: int
    #: Pagamento parziale: tutte le parti della mensilità, e le somme.
    parts: list[FeeRead] = []
    paid_cents: int = 0
    due_cents: int = 0


class MonthsSummaryRead(BaseModel):
    paid_cents: int
    due_cents: int
    overdue_cents: int
    upcoming_cents: int
    months_paid: int
    months_due: int
    months_overdue: int
    months_upcoming: int
    attendances: int


class SeasonMonthsRead(BaseModel):
    season: int
    season_label: str
    months: list[MonthRead]
    summary: MonthsSummaryRead


class JobResultRead(BaseModel):
    created: int


# --- Gare -----------------------------------------------------------------------------------------


class CompetitionWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    starts_on: date
    ends_on: date | None = None
    location: str | None = Field(default=None, max_length=200)
    organizer: str | None = Field(default=None, max_length=200)
    level: str = "CLUB"
    registration_deadline: date
    fee_cents: int = Field(default=0, ge=0, le=10_000_000)
    requires_agonistic_certificate: bool = True
    min_age: int | None = Field(default=None, ge=0, le=110)
    max_age: int | None = Field(default=None, ge=0, le=110)
    categories: str | None = None
    kind: str = Field(default="COMPETITION", pattern="^(COMPETITION|STAGE)$")
    transport_needed: bool = False
    transport_entity_name: str | None = Field(default=None, max_length=200)
    transport_entity_email: str | None = Field(default=None, max_length=255)
    transport_departure: str | None = Field(default=None, max_length=300)
    transport_return: str | None = Field(default=None, max_length=300)
    transport_companions: int = Field(default=0, ge=0, le=500)
    transport_notes: str | None = Field(default=None, max_length=2000)
    transport_auto_send: bool = False


class CompetitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    location: str | None = Field(default=None, max_length=200)
    organizer: str | None = Field(default=None, max_length=200)
    level: str | None = None
    registration_deadline: date | None = None
    fee_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    requires_agonistic_certificate: bool | None = None
    min_age: int | None = Field(default=None, ge=0, le=110)
    max_age: int | None = Field(default=None, ge=0, le=110)
    categories: str | None = None
    kind: str | None = Field(default=None, pattern="^(COMPETITION|STAGE)$")
    transport_needed: bool | None = None
    transport_entity_name: str | None = Field(default=None, max_length=200)
    transport_entity_email: str | None = Field(default=None, max_length=255)
    transport_departure: str | None = Field(default=None, max_length=300)
    transport_return: str | None = Field(default=None, max_length=300)
    transport_companions: int | None = Field(default=None, ge=0, le=500)
    transport_notes: str | None = Field(default=None, max_length=2000)
    transport_auto_send: bool | None = None


class CompetitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    starts_on: date
    ends_on: date
    location: str | None
    organizer: str | None
    level: str
    registration_deadline: date
    fee_cents: int
    requires_agonistic_certificate: bool
    min_age: int | None
    max_age: int | None
    categories: str | None
    status: str
    kind: str
    transport_needed: bool
    transport_entity_name: str | None
    transport_entity_email: str | None
    transport_departure: str | None
    transport_return: str | None
    transport_companions: int
    transport_notes: str | None
    transport_auto_send: bool
    #: La foto o la locandina; None = l'icona del tipo.
    image_url: str | None = None


class AthleteEligibilityRead(BaseModel):
    athlete_id: uuid.UUID
    first_name: str
    eligible: bool
    reason: str | None
    #: REGISTERED / WITHDRAWN, o None se mai iscritto.
    entry_status: str | None
    category: str | None
    placement: int | None
    #: La segreteria ha generato la giustificazione per la scuola: il
    #: titolare la può scaricare.
    school_letter_ready: bool = False
    #: Non può per delle quote scadute (club/participation.py): il
    #: frontend offre di pagarle.
    blocked_by_debts: bool = False


class FamilyCompetitionRead(CompetitionRead):
    registrations_open: bool
    athletes: list[AthleteEligibilityRead]


class EntryCreate(BaseModel):
    athlete_id: uuid.UUID
    category: str | None = Field(default=None, max_length=120)
    weight_kg: Decimal | None = Field(default=None, gt=0, le=300)


class EntryRead(BaseModel):
    id: uuid.UUID
    competition_id: uuid.UUID
    athlete_id: uuid.UUID
    athlete_name: str
    category: str | None
    weight_kg: Decimal | None
    status: str
    placement: int | None
    points: int
    fee_status: str | None
    #: Quando è stata generata la giustificazione per la scuola, se c'è.
    school_letter_at: datetime | None = None


class ResultWrite(BaseModel):
    entry_id: uuid.UUID
    #: 1, 2, 3, 5, 7; 0 = partecipazione; null = nessun risultato.
    placement: int | None


class ResultsWrite(BaseModel):
    results: list[ResultWrite]


class RankingRowRead(BaseModel):
    position: int
    athlete_id: uuid.UUID
    display_name: str
    photo_url: str | None
    sex: str
    age_band: str
    belt: str | None
    is_mine: bool
    #: Il club dell'atleta: il ranking è di tutta la rete.
    club_name: str | None = None
    points: int
    competitions: int
    gold: int
    silver: int
    bronze: int


class RankingRead(BaseModel):
    season: int
    season_label: str
    sex: str | None
    age_band: str | None
    rows: list[RankingRowRead]


# --- Cinture --------------------------------------------------------------------------------------


class BeltAward(BaseModel):
    grade: str
    awarded_on: date
    note: str | None = Field(default=None, max_length=500)


# --- Corsi ----------------------------------------------------------------------------------------


class CourseWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    level: str | None = Field(default=None, max_length=60)
    min_age: int | None = Field(default=None, ge=0, le=110)
    max_age: int | None = Field(default=None, ge=0, le=110)
    instructor_user_id: uuid.UUID | None = None
    active: bool = True
    # Solo nei corsi JAV (club/kinds.py); in un club ufficiale si ignorano.
    venue_name: str | None = Field(default=None, max_length=200)
    venue_address: str | None = Field(default=None, max_length=300)
    venue_city: str | None = Field(default=None, max_length=120)
    public_description: str | None = Field(default=None, max_length=2000)
    public_coach_name: str | None = Field(default=None, max_length=80)
    coach_share_pct: Decimal | None = Field(default=None, ge=0, le=100)
    published: bool = False


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    level: str | None = Field(default=None, max_length=60)
    min_age: int | None = Field(default=None, ge=0, le=110)
    max_age: int | None = Field(default=None, ge=0, le=110)
    instructor_user_id: uuid.UUID | None = None
    active: bool | None = None
    venue_name: str | None = Field(default=None, max_length=200)
    venue_address: str | None = Field(default=None, max_length=300)
    venue_city: str | None = Field(default=None, max_length=120)
    public_description: str | None = Field(default=None, max_length=2000)
    public_coach_name: str | None = Field(default=None, max_length=80)
    coach_share_pct: Decimal | None = Field(default=None, ge=0, le=100)
    published: bool | None = None


class SlotWrite(BaseModel):
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    room: str | None = Field(default=None, max_length=60)


class SlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    weekday: int
    starts_at: time
    ends_at: time
    room: str | None


class CourseRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    level: str | None
    min_age: int | None
    max_age: int | None
    instructor_user_id: uuid.UUID | None
    instructor_name: str | None
    active: bool
    slots: list[SlotRead]
    athletes_count: int
    #: Per il genitore: quali dei suoi atleti sono iscritti.
    my_athlete_ids: list[uuid.UUID] = []
    #: Per il treinador: True se insegna il corso (titolare o adjunto).
    mine: bool = False
    #: Per la segreteria: gli adjunto e i treinador che NON vedono il corso.
    staff_user_ids: list[uuid.UUID] = []
    excluded_coach_ids: list[uuid.UUID] = []
    # I corsi JAV: luogo, pagina pubblica, percentuale del treinador.
    venue_name: str | None = None
    venue_address: str | None = None
    venue_city: str | None = None
    public_description: str | None = None
    public_coach_name: str | None = None
    coach_share_pct: Decimal | None = None
    published: bool = False


class EnrolWrite(BaseModel):
    athlete_id: uuid.UUID


class RosterRowRead(BaseModel):
    athlete_id: uuid.UUID
    first_name: str
    last_name: str
    photo_url: str | None
    belt: BeltRead | None
    #: None = non ancora segnata in quel giorno.
    present: bool | None
    note: str | None = None


class RosterRead(BaseModel):
    course_id: uuid.UUID
    date: date
    rows: list[RosterRowRead]


class AttendanceWrite(BaseModel):
    date: date
    athlete_id: uuid.UUID
    present: bool = True
    #: Una nota per la segreteria, facoltativa.
    note: str | None = Field(default=None, max_length=300)


class InvitedByRead(BaseModel):
    """Chi ha portato l'atleta nel club: PERSON (una persona del club, dal suo
    link «Invita un amico»; `user_id` per i suoi simboli), WRITTEN (il nome
    scritto nel modulo d'iscrizione). Senza nessuno dei due: il club."""

    kind: str
    name: str
    user_id: uuid.UUID | None = None


class AdminAthleteRead(AthleteCardRead):
    guardian_user_id: uuid.UUID
    guardian_email: str | None
    #: Il nº de sócio del club.
    member_number: str | None = None
    #: L'encarregado de educação (il titolare del conto): nome e telefono.
    guardian_name: str | None = None
    guardian_phone: str | None = None
    invited_by: InvitedByRead | None = None


class AdminCertificateRead(BaseModel):
    athlete_id: uuid.UUID
    athlete_name: str
    guardian_email: str | None
    certificate: CertificateStatusRead


class AdminProofRead(ProofRead):
    uploaded_by_email: str | None


# --- Più club -------------------------------------------------------------------------------------


class ClubSettingsWrite(BaseModel):
    bank_iban: str | None = Field(default=None, max_length=40)
    bank_account_holder: str | None = Field(default=None, max_length=200)
    bank_transfer_instructions: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=255)
    transport_entity_name: str | None = Field(default=None, max_length=200)
    transport_entity_email: str | None = Field(default=None, max_length=255)
    letters_language: str | None = Field(default=None, pattern="^(pt|it|en)$")
    late_fee_enabled: bool | None = None
    late_fee_cents: int | None = Field(default=None, gt=0, le=10_000)


class ClubSettingsRead(BaseModel):
    bank_iban: str | None
    bank_account_holder: str | None
    bank_transfer_instructions: str | None
    contact_email: str | None
    transport_entity_name: str | None = None
    transport_entity_email: str | None = None
    letters_language: str | None = None
    #: Avvisi automatici della mensilità e multa del 16 (club/payment_reminders.py).
    late_fee_enabled: bool = False
    late_fee_cents: int = 1500


class ClubStaffRead(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    #: Falso per un treinador che viene da un altro club (club/staff_clubs.py).
    home: bool = True
    #: Per i treinador: ACTIVE, o REQUESTED se la segreteria l'ha chiesto e il
    #: superadmin non ha ancora approvato.
    membership_status: str | None = None
    #: Nome e cognome dal profilo (l'email per chi non ne ha uno).
    name: str | None = None
    #: Solo appena creato e solo se l'email d'invito non è partita: il link
    #: di primo accesso da consegnare a mano (vale 7 giorni).
    invite_link: str | None = None


class StaffAccessLinkRead(BaseModel):
    #: Il link per scegliere la password, se l'email non è partita (da
    #: consegnare a mano); None se l'email è arrivata.
    link: str | None
    emailed: bool


class ClubRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    settings: ClubSettingsRead
    athletes_active: int
    staff: list[ClubStaffRead]
    kind: str = "CLUB"
    #: Vedi ClubStaffRead.invite_link: la segreteria indicata alla creazione.
    invite_link: str | None = None


class ClubCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    #: Facoltativo: se manca si ricava dal nome.
    slug: str | None = Field(default=None, max_length=80)
    #: La segreteria del club: riceve l'invito a scegliersi la password.
    secretary_email: str | None = Field(default=None, max_length=255)
    settings: ClubSettingsWrite | None = None


class ClubUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, pattern="^(ACTIVE|SUSPENDED)$")


class ClubStaffWrite(BaseModel):
    email: str = Field(max_length=255)
    role: str = Field(pattern="^(SECRETARY|INSTRUCTOR)$")


class CurrentClubRead(BaseModel):
    """Il club su cui si sta lavorando, per l'intestazione dell'interfaccia
    e per i dati del bonifico delle quote."""

    id: uuid.UUID
    name: str
    slug: str
    #: True quando chi guarda è staff della piattaforma "entrato" nel club.
    entered: bool
    settings: ClubSettingsRead
    #: CLUB o JAV_COURSES: l'interfaccia nasconde cinture, gare e ranking
    #: nei corsi JAV (club/kinds.py).
    kind: str = "CLUB"


class PublicClubRead(BaseModel):
    name: str
    slug: str


class ClubShopOrderRead(BaseModel):
    """Un ordine dello Shop di una famiglia del club: la segreteria lo vede,
    ma lo Shop è della piattaforma e il pagamento lo conferma la piattaforma."""

    id: uuid.UUID
    number: str
    created_at: datetime
    customer_email: str | None
    athlete_name: str | None
    items_summary: str
    amount_cents: int
    status: str
    fulfillment_status: str
    payment_proof_uploaded_at: datetime | None


# --- Prezzi, inviti, trasporti --------------------------------------------------------------------


class PricingRead(BaseModel):
    tier_discount_pct: dict[str, int]
    family_discount_cents: int
    family_min_athletes: int
    referral_credit_cents: int
    parent_member_fee_cents: int
    enrollment_includes: str


class PricingWrite(BaseModel):
    tier_discount_pct: dict[str, int] | None = None
    family_discount_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    family_min_athletes: int | None = Field(default=None, ge=2, le=10)
    referral_credit_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    parent_member_fee_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    enrollment_includes: str | None = Field(default=None, max_length=300)


class InvitedAthleteRead(BaseModel):
    athlete_id: uuid.UUID
    #: «Nome I.»: la rete di un genitore, non l'anagrafe.
    name: str
    photo_url: str | None
    status: str
    joined_on: date
    months_paid: int
    credit_cents: int


class InviteRead(BaseModel):
    code: str
    #: Da attaccare all'indirizzo del sito: /c/<slug>?invito=<codice>.
    path: str
    invited_count: int
    earned_cents: int
    credit_per_month_cents: int
    #: Il saldo JavCash di chi invita: si usa per pagare le quote.
    balance_cents: int = 0
    #: Gli atleti delle famiglie entrate dal suo link.
    network: list[InvitedAthleteRead] = []


class CreditCodeRequest(BaseModel):
    credit_cents: int = Field(gt=0, le=10_000_000)


class TransportRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    competition_id: uuid.UUID
    to_email: str | None
    subject: str
    body_text: str
    status: str
    athletes_count: int
    sent_at: datetime | None
    last_error: str | None
    #: Gli iscritti di adesso: se diversi da athletes_count la bozza è vecchia.
    current_athletes_count: int = 0


class TransportRequestWrite(BaseModel):
    to_email: str = Field(min_length=3, max_length=255)
    subject: str = Field(min_length=3, max_length=300)
    body_text: str = Field(min_length=10, max_length=20000)


class SchoolLetterRead(BaseModel):
    entry_id: uuid.UUID
    athlete_name: str
    body_text: str
    generated_at: datetime | None


class SchoolLetterWrite(BaseModel):
    body_text: str = Field(min_length=20, max_length=6000)


# --- Persone, staff, cartellino, presenze, taxa de falta ------------------------------------------


class PersonRead(BaseModel):
    #: ATHLETE (id = atleta) o USER (id = account: genitore o staff).
    kind: str
    id: uuid.UUID
    user_id: uuid.UUID | None
    name: str
    #: ATHLETE, PARENT, SECRETARY, COACH, ASSISTANT_COACH, MONITOR, ASSISTANT_MONITOR.
    kinds: list[str]
    status: str
    photo_url: str | None
    belt: str | None
    age: int | None
    email: str | None
    guardian_name: str | None
    due_cents: int
    children: list[dict] | None
    social_tier: str | None
    adapted_judo: bool


class FunctionWrite(BaseModel):
    function: str | None = Field(default=None, pattern="^(COACH|ASSISTANT_COACH|MONITOR|ASSISTANT_MONITOR)$")
    user_id: uuid.UUID | None = None
    athlete_id: uuid.UUID | None = None


class PersonKindsRead(BaseModel):
    """Solo i simboli di una persona (people.py::list_people), senza soldi né contatti."""

    kind: str
    id: uuid.UUID
    user_id: uuid.UUID | None
    kinds: list[str]


class SupportWrite(BaseModel):
    """Un costo pagato dal club per un atleta (club/support.py)."""

    category: str = Field(pattern="^(TRANSPORT|MATERIAL|COMPETITION|EXAM|TRAINING_CAMP|OTHER)$")
    amount_cents: int = Field(gt=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=300)
    paid_on: date


class RefereeWrite(BaseModel):
    referee: bool
    user_id: uuid.UUID | None = None
    athlete_id: uuid.UUID | None = None


class PersonCardRead(BaseModel):
    debts: list[FeeRead]
    payments: list[FeeRead]
    proofs: list[dict]
    results: list[dict]
    belts: list[dict]
    investments: list[dict]
    totals: dict[str, int]


class InvestmentWrite(BaseModel):
    amount_cents: int = Field(gt=0, le=10_000_000)
    note: str = Field(min_length=3, max_length=300)


class CourseStaffWrite(BaseModel):
    user_ids: list[uuid.UUID]


class CourseCoachExclusionsWrite(BaseModel):
    """I treinador che NON vedono il corso (vuoto = lo vedono tutti)."""

    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class LessonRead(BaseModel):
    """Una lezione: un orario settimanale di un corso, in un giorno preciso."""

    course_id: uuid.UUID
    course_name: str
    slot_id: uuid.UUID
    date: date
    starts_at: time
    ends_at: time
    room: str | None
    enrolled: int
    present: int
    #: True per la lezione in corso adesso (o la prossima, oggi).
    current: bool = False
    #: True se chi chiede insegna il corso (titolare o adjunto).
    mine: bool = False


class WorkSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    note: str | None
    minutes: int = 0
    #: Ritoccato dalla persona stessa (club/workclock.py, own_update), quando.
    edited_at: datetime | None = None
    #: Scritto dopo, a mano, non timbrato.
    added_later: bool = False
    #: Corretto dalla segreteria.
    corrected: bool = False


class ClockRead(BaseModel):
    open_session: WorkSessionRead | None
    today_minutes: int
    month_minutes: int
    sessions: list[WorkSessionRead]


class ClockWrite(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class WorkSessionUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    note: str | None = Field(default=None, max_length=300)


class StaffHoursRead(BaseModel):
    user_id: uuid.UUID
    name: str
    minutes: int
    sessions: list[WorkSessionRead]


class FamilyLessonRead(BaseModel):
    athlete_id: uuid.UUID
    athlete_name: str
    course_id: uuid.UUID
    course_name: str
    starts_at: time
    ends_at: time
    present: bool | None
    note: str | None


class FamilyAttendanceWrite(BaseModel):
    athlete_id: uuid.UUID
    course_id: uuid.UUID
    note: str | None = Field(default=None, max_length=300)


class DayAttendanceRead(BaseModel):
    athlete_id: uuid.UUID
    athlete_name: str
    course_id: uuid.UUID
    course_name: str
    present: bool
    note: str | None
    recorded_by_kind: str


class AbsenceRowRead(BaseModel):
    fee: FeeRead
    athlete_name: str
    lessons_held: int
    presences: int
    #: HALF / FULL se le presenze danno diritto alla taxa de falta, altrimenti None.
    suggestion: str | None
    applied: str | None


class AbsenceWrite(BaseModel):
    adjustment: str | None = Field(default=None, pattern="^(HALF|FULL)$")


# --- Corsi JAV: il passaggio a un club ufficiale --------------------------------------------------


class MoveTargetRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class MoveToClubWrite(BaseModel):
    target_club_id: uuid.UUID


class MoveResultRead(BaseModel):
    user_id: uuid.UUID
    club_id: uuid.UUID
    club_name: str
    athletes: int


class FeeBlockingWrite(BaseModel):
    #: True = la quota non impedisce l'iscrizione alle gare anche se scaduta.
    non_blocking: bool
