"""Il club: atleti, piani, quote, prove di pagamento, certificati, cinture,
corsi, presenze, gare. Specifica: docs/club-portal.md.

Tre regole attraversano tutte le tabelle qui sotto.

**Ogni riga è di un club** (`club_id`): la piattaforma ospita più club, e
ogni query di questo dominio filtra per club, mai solo per organizzazione.
Su quale club lavora chi chiama lo decide club/scope.py, non il chiamante.

**L'idempotenza sta nei vincoli UNIQUE** (CLAUDE.md §5): la quota di un mese,
la presenza di un giorno, l'iscrizione a una gara, un promemoria già inviato
esistono una volta sola perché il database non ne accetta una seconda, non
perché qualcuno ha controllato un flag prima di scriverle. I job automatici
possono girare due volte; il risultato è lo stesso.

**Ciò che si può calcolare non si salva**: la cintura attuale è la più alta
dello storico, i punti del ranking si sommano dai risultati, il livello e le
medaglie dell'atleta si derivano da presenze, cinture e gare. Una colonna da
tenere allineata è una colonna che prima o poi non lo sarà.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin
from app.domains.club.belts import BELT_CODES

CLUB_STATUSES = ("ACTIVE", "SUSPENDED")
#: CLUB è un club ufficiale; JAV_COURSES è l'unità "Cursos JAV": i corsi
#: extrascolastici che JudoArteVida tiene nelle scuole. Le regole che
#: cambiano da un tipo all'altro stanno in un posto solo, club/kinds.py.
CLUB_KINDS = ("CLUB", "JAV_COURSES")
ATHLETE_STATUSES = ("ACTIVE", "SUSPENDED", "LEFT")
#: MEMBERSHIP è la quota socio del genitore di un atleta minorenne: una per
#: famiglia e per anno, legata al genitore e non a un atleta.
#: FINE è una multa decisa dalla segreteria (es. le assenze agli allenamenti),
#: EQUIPMENT il prezzo di un ordine di judogi del club (club_equipment_orders).
FEE_KINDS = ("MONTHLY", "ENROLLMENT", "COMPETITION", "MEMBERSHIP", "FINE", "EQUIPMENT")
#: L'escalão (fascia di reddito per gli aiuti sociali, in Portogallo A/B/C):
#: dà uno sconto in percentuale sulla mensilità, deciso dal club.
SOCIAL_TIERS = ("A", "B", "C", "D")
#: Lo sconto personale di un atleta (oltre a escalão e famiglia): in
#: percentuale o in centesimi, sulla mensilità, sulle quote annuali o su
#: entrambe. Lo decide la segreteria, con la sua descrizione.
CUSTOM_DISCOUNT_KINDS = ("PERCENT", "FIXED")
CUSTOM_DISCOUNT_SCOPES = ("MONTHLY", "ANNUAL", "BOTH")
#: COMPETITION conta per il Jav Ranking; gli altri no: STAGE (allenamento
#: collegiale, stage tecnico), REFEREEING (corso o servizio di arbitraggio),
#: EDUCATION (formazione, seminario, clinic), MEETING (riunione, assemblea).
EVENT_KINDS = ("COMPETITION", "STAGE", "REFEREEING", "EDUCATION", "MEETING", "OTHER")
#: Come si va all'evento: con il trasporto del club, ognuno per conto suo, o
#: ancora da decidere.
TRANSPORT_MODES = ("CLUB", "OWN", "TBC")
TRANSPORT_REQUEST_STATUSES = ("DRAFT", "SENT")
#: Le funzioni di chi insegna nel club. Treinador e treinador adjunto hanno
#: un account (ruolo INSTRUCTOR) e la loro area; monitor e monitor adjunto
#: sono un'etichetta, su un atleta o su un account.
CLUB_FUNCTIONS = ("COACH", "ASSISTANT_COACH", "MONITOR", "ASSISTANT_MONITOR")
#: Taxa de falta: la mensilità di un mese con poche presenze. HALF: meno di
#: metà delle lezioni; FULL: nessuna presenza.
ABSENCE_ADJUSTMENTS = ("HALF", "FULL")
FEE_STATUSES = ("DUE", "PAID", "WAIVED")
PROOF_STATUSES = ("ACCEPTED", "REJECTED")
#: Come è stata pagata una quota. BANK_TRANSFER e CASH li può dichiarare il
#: genitore (la ricevuta del bonifico, o a chi ha dato i contanti); CARD
#: solo la segreteria (POS in palestra) finché il pagamento online non c'è;
#: WALLET quando il credito del wallet copre tutto.
#: MBWAY (il pagamento da telefono portoghese) si dichiara come il bonifico,
#: con la schermata della conferma.
PAYMENT_METHODS = ("BANK_TRANSFER", "MBWAY", "CASH", "CARD", "WALLET")
PROOF_METHODS = ("BANK_TRANSFER", "MBWAY", "CASH")
CERTIFICATE_TYPES = ("NON_AGONISTIC", "AGONISTIC")
#: I livelli dei club portoghesi, dal regionale ai Giochi Olimpici; CLUB e
#: INTERNATIONAL (generico) per le gare che non ne hanno uno preciso.
COMPETITION_LEVELS = (
    "CLUB", "REGIONAL", "ZONAL", "OPENS", "NATIONAL", "INTERNATIONAL", "EUROPEAN_CUP",
    "EUROPEAN_CHAMPIONSHIP", "WORLD_CHAMPIONSHIP", "OLYMPIC_GAMES",
)
COMPETITION_STATUSES = ("OPEN", "CLOSED", "DONE")
ENTRY_STATUSES = ("REGISTERED", "WITHDRAWN")
#: 0 è la partecipazione senza piazzamento; 5 e 7 sono i quinti e settimi
#: posti del judo (le due finali di recupero).
PLACEMENTS = (0, 1, 2, 3, 5, 7)

#: La stagione del judo va da settembre a giugno: luglio e agosto di solito
#: non si pagano. Il piano lo può cambiare, questo è solo il punto di partenza.
DEFAULT_BILLING_MONTHS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6]


def _in(values) -> str:
    return ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in values)


class Club(UUIDPKMixin, TimestampMixin, Base):
    """Un club della piattaforma (es. "Judo Clube de Lagos"). Lo crea il
    superadmin; la sua segreteria vede e gestisce solo i suoi atleti, quote,
    corsi e gare. Lo Shop, il catalogo e JavCash restano della piattaforma,
    uno solo per tutti i club (docs/club-portal.md, "Più club")."""

    __tablename__ = "clubs"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_clubs_org_slug"),
        CheckConstraint(f"status IN ({_in(CLUB_STATUSES)})", name="status"),
        # Lo slug finisce nell'indirizzo del club (/c/<slug>): solo minuscole,
        # cifre e trattini, niente che vada codificato nell'URL.
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
        CheckConstraint(f"kind IN ({_in(CLUB_KINDS)})", name="kind"),
        # Un'unità "Cursos JAV" sola per organizzazione: i corsi nelle scuole
        # stanno tutti lì dentro, ognuno amministrabile per conto suo.
        Index(
            "uq_clubs_one_jav_courses_unit", "organization_id",
            unique=True, postgresql_where=text("kind = 'JAV_COURSES'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80))
    #: SUSPENDED: genitori, segreteria e istruttori del club non entrano
    #: più, i dati restano. Il superadmin ci entra comunque, per sistemare.
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    #: Dove le famiglie pagano le quote (IBAN, intestatario, istruzioni): le
    #: quote sono del club, lo Shop è della piattaforma.
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    #: CLUB o JAV_COURSES (vedi CLUB_KINDS): niente cinture, gare e ranking
    #: nei corsi JAV, e il treinador è pagato a percentuale.
    kind: Mapped[str] = mapped_column(String(16), default="CLUB", server_default="CLUB")


class ClubPlan(UUIDPKMixin, TimestampMixin, Base):
    """Un piano d'iscrizione per fascia d'età. Il sistema lo assegna da solo
    all'atleta in base all'età al 1° settembre della stagione (vedi
    service.assign_plan); la segreteria può forzarlo atleta per atleta."""

    __tablename__ = "club_plans"
    __table_args__ = (
        CheckConstraint("min_age >= 0", name="min_age_non_negative"),
        CheckConstraint("max_age IS NULL OR max_age >= min_age", name="age_range"),
        CheckConstraint("monthly_fee_cents >= 0", name="monthly_fee_non_negative"),
        CheckConstraint("enrollment_fee_cents >= 0", name="enrollment_fee_non_negative"),
        # Fino al 28: ogni mese ha un giorno 28, nessuna quota cade in un
        # giorno che non esiste.
        CheckConstraint("due_day BETWEEN 1 AND 28", name="due_day_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    min_age: Mapped[int] = mapped_column(Integer)
    #: Incluso. NULL = nessun limite superiore (gli adulti).
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_fee_cents: Mapped[int] = mapped_column(BigInteger)
    enrollment_fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    due_day: Mapped[int] = mapped_column(SmallInteger, default=10)
    #: I mesi (1-12) in cui la quota mensile si emette.
    billing_months: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), default=lambda: list(DEFAULT_BILLING_MONTHS)
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ClubAthlete(UUIDPKMixin, TimestampMixin, Base):
    """Un atleta. Lo gestisce il titolare del conto (`guardian_user_id`): il
    genitore, o l'adulto stesso con l'atleta `is_self`. Può avere in più un
    suo accesso (`user_id`, ruolo ATHLETE) per la sua area: lezioni,
    presenze, quote in lettura, formazione (club/athlete_access.py)."""

    __tablename__ = "club_athletes"
    __table_args__ = (
        CheckConstraint("sex IN ('M', 'F')", name="sex"),
        CheckConstraint(f"status IN ({_in(ATHLETE_STATUSES)})", name="status"),
        CheckConstraint("weight_kg IS NULL OR weight_kg > 0", name="weight_positive"),
        CheckConstraint(f"social_tier IS NULL OR social_tier IN ({_in(SOCIAL_TIERS)})", name="social_tier"),
        CheckConstraint(
            f"custom_discount_kind IS NULL OR custom_discount_kind IN ({_in(CUSTOM_DISCOUNT_KINDS)})",
            name="custom_discount_kind",
        ),
        CheckConstraint(
            f"custom_discount_scope IN ({_in(CUSTOM_DISCOUNT_SCOPES)})", name="custom_discount_scope",
        ),
        CheckConstraint(
            "custom_discount_kind IS NULL OR (custom_discount_value > 0 AND "
            "(custom_discount_kind <> 'PERCENT' OR custom_discount_value <= 100))",
            name="custom_discount_value",
        ),
        CheckConstraint("height_cm IS NULL OR (height_cm > 40 AND height_cm < 250)", name="height_range"),
        # Il nº de sócio è del club: lo stesso numero in due club va bene.
        Index(
            "uq_club_athletes_club_member_number", "club_id", "member_number",
            unique=True, postgresql_where=text("member_number IS NOT NULL"),
        ),
        # Una persona è "me stesso" una volta sola per account.
        Index(
            "uq_club_athletes_one_self_per_guardian", "guardian_user_id",
            unique=True, postgresql_where=text("is_self"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    guardian_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    #: L'accesso dell'atleta alla sua area, se il titolare gliel'ha creato.
    #: Per un atleta `is_self` è il titolare stesso.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True
    )
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(1))
    fiscal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_self: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_plans.id"), nullable=True, index=True
    )
    #: True quando la segreteria ha scelto il piano a mano: il ricalcolo per
    #: età di inizio stagione non lo tocca più.
    plan_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    federation_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    federation_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: L'escalão, lo imposta la segreteria dopo aver visto il documento.
    social_tier: Mapped[str | None] = mapped_column(String(1), nullable=True)
    #: Judo adattato: ha lo sconto dell'escalão A, qualunque sia il suo.
    adapted_judo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    joined_on: Mapped[date] = mapped_column(Date)
    left_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # --- La ficha de inscrição: ciò che serve alla segreteria e alla
    # federazione. I dati d'identità (documenti, indirizzo, contatti dei
    # genitori) stanno in club_athlete_records, letti solo dalla segreteria. ---
    #: Il nº de sócio, del club (unico nel club).
    member_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Il nome da ricamare sul judogi (sotto i 13 anni solo il nome proprio).
    kimono_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    height_cm: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: La categoria di peso come la scrive la federazione ("-66kg").
    weight_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: L'ultimo anno in cui la licenza federale è stata rivalidata.
    federation_renewal_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # --- Esenzioni e sconto personale (club/pricing.py). ---
    #: Non paga la mensilità (staff, órgãos sociais, borsa del club).
    exempt_monthly: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    #: Non paga le quote annuali (iscrizione e quota socio).
    exempt_annual: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    custom_discount_kind: Mapped[str | None] = mapped_column(String(8), nullable=True)
    #: Percentuale (1-100) o centesimi, secondo il tipo.
    custom_discount_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_discount_scope: Mapped[str] = mapped_column(String(8), default="MONTHLY", server_default="MONTHLY")
    custom_discount_note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ClubPaymentProof(UUIDPKMixin, TimestampMixin, Base):
    """La foto (o il PDF) di un pagamento, caricata dal genitore. Copre una o
    più quote (`club_payment_proof_fees`): due figli, un bonifico solo.

    Nasce ACCEPTED: caricarla segna subito le quote come pagate (docs/club-
    portal.md, "Regola di autogestione"). La segreteria può rifiutarla dopo,
    e allora le quote tornano da pagare."""

    __tablename__ = "club_payment_proofs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PROOF_STATUSES)})", name="status"),
        CheckConstraint("amount_cents >= 0", name="amount_non_negative"),
        CheckConstraint("credit_cents >= 0 AND credit_cents <= amount_cents", name="credit_range"),
        Index(
            "uq_club_payment_proofs_club_receipt", "club_id", "receipt_number",
            unique=True, postgresql_where=text("receipt_number IS NOT NULL"),
        ),
        CheckConstraint(f"method IN ({_in(PROOF_METHODS)})", name="method"),
        # Senza foto solo se il credito paga tutto, o se sono contanti: lì la
        # prova è la persona che li ha ricevuti.
        CheckConstraint(
            "storage_key IS NOT NULL OR credit_cents = amount_cents OR method = 'CASH'", name="file_or_credit"
        ),
        CheckConstraint(
            "method <> 'CASH' OR cash_received_by_user_id IS NOT NULL OR cash_received_by_name IS NOT NULL",
            name="cash_receiver",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    #: NULL quando il credito del wallet copre tutto: non c'è un bonifico da
    #: fotografare.
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: La somma delle quote coperte al momento del caricamento, congelata.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    #: La parte pagata con il credito del wallet (sconti invito, rimborsi):
    #: il bonifico è amount_cents meno questa. Si restituisce se la prova
    #: viene rifiutata.
    credit_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACCEPTED", index=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Bonifico (la foto della ricevuta) o contanti consegnati a qualcuno del
    #: club (niente foto: chi li ha presi è avvisato e può dire di no).
    method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER", server_default="BANK_TRANSFER")
    cash_received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: Il nome di chi ha ricevuto i contanti, congelato: resta leggibile
    #: anche se l'account cambia nome o se ne va.
    cash_received_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Il numero della ricevuta, per chi parla con la segreteria al telefono:
    #: "MEN-2026-0042". Unico nel club (indice), lo assegna il server
    #: (club_receipt_counters): nessun conteggio di righe che due richieste
    #: insieme possano duplicare.
    receipt_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    #: Il giorno del pagamento dichiarato da chi carica la prova (il bonifico
    #: di ieri caricato oggi); NULL = il giorno del caricamento.
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class ClubReceiptCounter(Base):
    """L'ultimo numero di ricevuta dato, per club, prefisso e anno. Il
    numero nuovo si prende con un INSERT ... ON CONFLICT DO UPDATE ...
    RETURNING: due pagamenti insieme non avranno mai lo stesso numero."""

    __tablename__ = "club_receipt_counters"

    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(4), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class ClubCompetition(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "club_competitions"
    __table_args__ = (
        CheckConstraint(f"level IN ({_in(COMPETITION_LEVELS)})", name="level"),
        CheckConstraint(f"kind IN ({_in(EVENT_KINDS)})", name="kind"),
        CheckConstraint("transport_companions >= 0", name="transport_companions_non_negative"),
        CheckConstraint(f"status IN ({_in(COMPETITION_STATUSES)})", name="status"),
        CheckConstraint("ends_on >= starts_on", name="date_range"),
        CheckConstraint("registration_deadline <= starts_on", name="deadline_before_start"),
        CheckConstraint("fee_cents >= 0", name="fee_non_negative"),
        CheckConstraint("max_age IS NULL OR min_age IS NULL OR max_age >= min_age", name="age_range"),
        CheckConstraint(f"transport_mode IN ({_in(TRANSPORT_MODES)})", name="transport_mode"),
        CheckConstraint("places IS NULL OR places > 0", name="places_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: NULL = un evento **della rete** (il calendário comune: gare della
    #: federazione, opens, estágios, formazioni): lo crea la piattaforma, lo
    #: vede ogni club dell'organizzazione, e ogni club ci iscrive i suoi
    #: atleti (le iscrizioni e le quote hanno il club dell'atleta).
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_on: Mapped[date] = mapped_column(Date, index=True)
    ends_on: Mapped[date] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    level: Mapped[str] = mapped_column(String(24), default="CLUB")
    #: Ultimo giorno utile per iscriversi, incluso.
    registration_deadline: Mapped[date] = mapped_column(Date)
    fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    requires_agonistic_certificate: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Età (al giorno della gara) ammessa, se la gara la limita.
    min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Le categorie di età/peso, come le scrive l'organizzatore.
    categories: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: Gara (conta per il ranking) o stage (no).
    kind: Mapped[str] = mapped_column(String(16), default="COMPETITION", server_default="COMPETITION")
    # --- Trasporto: la richiesta al comune (o all'ente che sostiene il club)
    # che parte quando le iscrizioni sono chiuse e si sa quanti sono. ---
    transport_needed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    transport_entity_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transport_entity_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Luogo e ora di partenza e di ritorno, come li scrive la segreteria.
    transport_departure: Mapped[str | None] = mapped_column(String(300), nullable=True)
    transport_return: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: Allenatori e accompagnatori che viaggiano con gli atleti.
    transport_companions: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    transport_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: True: alla chiusura delle iscrizioni la richiesta parte da sola. False
    #: (il default): la bozza si prepara da sola e la segreteria la manda
    #: con un clic dopo averla riletta.
    transport_auto_send: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    #: Come ci si va (TRANSPORT_MODES) e le note per le famiglie.
    transport_mode: Mapped[str] = mapped_column(String(8), default="TBC", server_default="TBC")
    transport_info: Mapped[str | None] = mapped_column(String(300), nullable=True)
    starts_at_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    ends_at_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    #: L'ora del giorno di scadenza (NULL = fino a fine giornata).
    registration_deadline_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    #: Posti disponibili, se l'organizzatore li limita.
    places: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Le fasce federali ammesse (benj_inf_inic, juvenis, cadetes, juniores,
    #: sub23, seniores, veteranos, adaptado, katas, formacao); vuoto = tutte.
    age_groups: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), default=list, server_default=text("'{}'::varchar[]")
    )
    #: La circolare o il regolamento dell'organizzatore (PDF o immagine) nel
    #: bucket media: è pensata per essere letta da tutti.
    circular_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    circular_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ClubTransportRequest(UUIDPKMixin, TimestampMixin, Base):
    """La richiesta di trasporto di un evento: una per evento. Nasce come
    bozza alla chiusura delle iscrizioni (con il numero vero di iscritti), la
    segreteria la rilegge e la corregge, poi la manda con un clic. Il testo
    salvato è esattamente quello partito."""

    __tablename__ = "club_transport_requests"
    __table_args__ = (
        # Un evento della rete ha una richiesta per club: ognuno porta i suoi.
        UniqueConstraint("competition_id", "club_id", name="uq_club_transport_requests_competition_club"),
        CheckConstraint(f"status IN ({_in(TRANSPORT_REQUEST_STATUSES)})", name="status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    competition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_competitions.id"))
    to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(String(300))
    body_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    #: Quanti atleti erano iscritti quando la bozza è stata scritta: se poi
    #: cambiano, l'interfaccia propone di rigenerarla.
    athletes_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: L'ultimo invio fallito, in parole, per chi riprova.
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ClubFee(UUIDPKMixin, TimestampMixin, Base):
    """Una quota da pagare. Il prezzo è congelato alla creazione: cambiare il
    piano non riscrive le quote già emesse (CLAUDE.md §5)."""

    __tablename__ = "club_fees"
    __table_args__ = (
        # È questo vincolo a rendere idempotente la generazione automatica.
        UniqueConstraint("athlete_id", "kind", "period", name="uq_club_fees_athlete_kind_period"),
        # La quota socio del genitore non ha un atleta: l'unicità è per
        # famiglia (genitore) e anno.
        Index(
            "uq_club_fees_guardian_membership", "club_id", "guardian_user_id", "period",
            unique=True, postgresql_where=text("kind = 'MEMBERSHIP'"),
        ),
        CheckConstraint(f"kind IN ({_in(FEE_KINDS)})", name="kind"),
        CheckConstraint(f"status IN ({_in(FEE_STATUSES)})", name="status"),
        CheckConstraint("amount_cents >= 0", name="amount_non_negative"),
        CheckConstraint("discount_cents >= 0", name="discount_non_negative"),
        CheckConstraint(
            f"absence_adjustment IS NULL OR absence_adjustment IN ({_in(ABSENCE_ADJUSTMENTS)})",
            name="absence_adjustment",
        ),
        CheckConstraint(
            "(kind = 'MEMBERSHIP' AND athlete_id IS NULL AND guardian_user_id IS NOT NULL)"
            " OR (kind <> 'MEMBERSHIP' AND athlete_id IS NOT NULL)",
            name="owner",
        ),
        CheckConstraint(
            "coach_share_pct IS NULL OR (coach_share_pct >= 0 AND coach_share_pct <= 100)",
            name="coach_share_pct_range",
        ),
        CheckConstraint(
            f"payment_method IS NULL OR payment_method IN ({_in(PAYMENT_METHODS)})", name="payment_method"
        ),
        CheckConstraint(
            "(installment_no IS NULL AND installments_total IS NULL) OR "
            "(installment_no >= 1 AND installments_total >= 2 AND installment_no <= installments_total)",
            name="installments",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    #: NULL solo per la quota socio del genitore (MEMBERSHIP).
    athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id"), nullable=True, index=True
    )
    #: Il genitore della quota socio (MEMBERSHIP); NULL per le altre, che
    #: appartengono alla famiglia attraverso l'atleta.
    guardian_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    #: `YYYY-MM` per le mensili, l'anno solare per iscrizione e quota socio,
    #: l'id della gara per le gare, l'id dell'ordine per un judogi, un
    #: codice della segreteria per una multa. Una rata aggiunge `/n`
    #: ("2026/2"): la quota divisa resta una riga per rata, e l'unicità
    #: (atleta, tipo, periodo) vale per ognuna.
    period: Mapped[str] = mapped_column(String(40))
    #: La rata (1..installments_total) di una quota divisa in rate (1-4
    #: prestações); NULL per una quota intera.
    installment_no: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    installments_total: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    description: Mapped[str] = mapped_column(String(200))
    #: Quanto si paga: il listino meno gli sconti. Congelato.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    #: Il prezzo di listino prima degli sconti (escalão, famiglia), per far
    #: vedere al genitore quanto risparmia. Congelato come il resto.
    gross_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    discount_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    #: Gli sconti applicati, già in parole: "Escalão A −25% · Famiglia −5,00 €".
    discount_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Taxa de falta applicata dalla segreteria (HALF / FULL), se applicata.
    absence_adjustment: Mapped[str | None] = mapped_column(String(8), nullable=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), default="DUE", index=True)
    competition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_competitions.id"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: La prova che l'ha pagata, se pagata con una prova. NULL se segnata
    #: pagata a mano dalla segreteria (contanti in palestra).
    paid_via_proof_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_payment_proofs.id"), nullable=True, index=True
    )
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    payment_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Come è stata pagata (PAYMENT_METHODS) e, per i contanti, a chi sono
    #: stati dati. NULL finché è da pagare, e per le quote segnate pagate
    #: prima che il metodo si registrasse.
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cash_received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cash_received_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    waived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    waived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    waive_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # --- Solo nell'unità Cursos JAV (club/kinds.py): a quale corso va la
    # mensilità e quanto ne spetta al treinador. Congelati all'emissione,
    # come il prezzo: se l'atleta cambia corso, o il corso cambia treinador
    # o percentuale, gli incassi e le quote del treinador dei mesi già
    # emessi non cambiano. NULL nei club ufficiali (staff pagato a ore). ---
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_courses.id"), nullable=True, index=True
    )
    #: Il treinador responsabile del corso quando la quota è stata emessa.
    coach_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    #: La sua percentuale di quella quota, quando sarà pagata.
    coach_share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)


class ClubPaymentProofFee(UUIDPKMixin, Base):
    __tablename__ = "club_payment_proof_fees"
    __table_args__ = (UniqueConstraint("proof_id", "fee_id", name="uq_club_payment_proof_fees_proof_fee"),)

    proof_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_payment_proofs.id", ondelete="CASCADE"), index=True
    )
    fee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_fees.id"), index=True)


class ClubMedicalCertificate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "club_medical_certificates"
    __table_args__ = (
        CheckConstraint(f"type IN ({_in(CERTIFICATE_TYPES)})", name="type"),
        CheckConstraint("expires_on >= issued_on", name="date_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    type: Mapped[str] = mapped_column(String(16))
    issued_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date, index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class ClubBeltGrade(UUIDPKMixin, TimestampMixin, Base):
    """Lo storico delle cinture. Un grado si ottiene una volta sola."""

    __tablename__ = "club_belt_grades"
    __table_args__ = (
        UniqueConstraint("athlete_id", "grade", name="uq_club_belt_grades_athlete_grade"),
        CheckConstraint(f"grade IN ({_in(BELT_CODES)})", name="grade"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    grade: Mapped[str] = mapped_column(String(16))
    awarded_on: Mapped[date] = mapped_column(Date)
    awarded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ClubCourse(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "club_courses"
    __table_args__ = (
        CheckConstraint("max_age IS NULL OR min_age IS NULL OR max_age >= min_age", name="age_range"),
        CheckConstraint(
            "coach_share_pct IS NULL OR (coach_share_pct >= 0 AND coach_share_pct <= 100)",
            name="coach_share_pct_range",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: "Principianti", "Agonisti"... testo libero, lo mostra l'orario.
    level: Mapped[str | None] = mapped_column(String(60), nullable=True)
    min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instructor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # --- I corsi dell'unità Cursos JAV: ognuno in una scuola o in un luogo
    # suo, con il suo treinador pagato a percentuale (club/kinds.py). ---
    #: La scuola (o il luogo) dove si tiene il corso.
    venue_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    venue_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    venue_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Il testo per le famiglie nella pagina pubblica dei corsi.
    public_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Il nome del treinador come compare sul sito, scritto a mano: un
    #: account da istruttore non è un consenso a comparire sul web.
    public_coach_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: La parte degli incassi del corso che va al treinador responsabile
    #: (default 50). NULL nei club ufficiali, dove lo staff è pagato a ore.
    coach_share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    #: Compare nella sezione pubblica "Cursos JAV nas escolas".
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class ClubCourseSlot(UUIDPKMixin, Base):
    __tablename__ = "club_course_slots"
    __table_args__ = (
        # 0 = lunedì, come date.weekday().
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("ends_at > starts_at", name="time_range"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_courses.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    room: Mapped[str | None] = mapped_column(String(60), nullable=True)


class ClubCourseAthlete(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "club_course_athletes"
    __table_args__ = (UniqueConstraint("course_id", "athlete_id", name="uq_club_course_athletes_course_athlete"),)

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_courses.id", ondelete="CASCADE"), index=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)


class ClubAttendance(UUIDPKMixin, TimestampMixin, Base):
    """Una presenza (o assenza) a un corso in un giorno. Segnarla di nuovo
    aggiorna la riga, non ne crea un'altra."""

    __tablename__ = "club_attendances"
    __table_args__ = (
        UniqueConstraint("athlete_id", "course_id", "date", name="uq_club_attendances_athlete_course_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_courses.id", ondelete="CASCADE"), index=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: Una nota per la segreteria ("è arrivato tardi", "ha male al ginocchio").
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: Chi l'ha segnata: STAFF (istruttore o segreteria) o FAMILY (il
    #: genitore, solo il giorno stesso).
    recorded_by_kind: Mapped[str] = mapped_column(String(8), default="STAFF", server_default="STAFF")


class ClubFunction(UUIDPKMixin, TimestampMixin, Base):
    """La funzione di una persona nel club: treinador, treinador adjunto,
    monitor, monitor adjunto. Su un account (chi insegna e ha l'area
    riservata) o su un atleta (i monitor sono spesso ragazzi grandi)."""

    __tablename__ = "club_functions"
    __table_args__ = (
        CheckConstraint(f"function IN ({_in(CLUB_FUNCTIONS)})", name="function"),
        CheckConstraint("(user_id IS NULL) <> (athlete_id IS NULL)", name="one_person"),
        # Una funzione per persona: cambiarla è un aggiornamento, non una riga in più.
        UniqueConstraint("club_id", "user_id", name="uq_club_functions_club_user"),
        UniqueConstraint("club_id", "athlete_id", name="uq_club_functions_club_athlete"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    function: Mapped[str] = mapped_column(String(24))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id"), nullable=True
    )


class ClubCourseStaff(UUIDPKMixin, TimestampMixin, Base):
    """Chi insegna in un corso oltre al titolare (`ClubCourse.instructor_user_id`):
    i treinador adjunto. Vedono il corso nel loro calendario e segnano le
    presenze."""

    __tablename__ = "club_course_staff"
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_club_course_staff_course_user"),)

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_courses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)


class ClubWorkSession(UUIDPKMixin, TimestampMixin, Base):
    """Il cartellino: un'entrata e un'uscita di chi lavora nel club. Una sola
    aperta per persona (indice UNIQUE parziale): due "Entro" di fila non
    aprono due turni."""

    __tablename__ = "club_work_sessions"
    __table_args__ = (
        Index(
            "uq_club_work_sessions_one_open", "user_id", unique=True, postgresql_where=text("ended_at IS NULL"),
        ),
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="time_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(index=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: La segreteria che ha corretto il turno, se l'ha corretto.
    corrected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubCompetitionEntry(UUIDPKMixin, TimestampMixin, Base):
    """L'iscrizione di un atleta a una gara, e il suo risultato. Ritirarsi e
    reiscriversi riusa la stessa riga."""

    __tablename__ = "club_competition_entries"
    __table_args__ = (
        UniqueConstraint("competition_id", "athlete_id", name="uq_club_competition_entries_competition_athlete"),
        CheckConstraint(f"status IN ({_in(ENTRY_STATUSES)})", name="status"),
        CheckConstraint(f"placement IS NULL OR placement IN ({_in(PLACEMENTS)})", name="placement"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    competition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_competitions.id"), index=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="REGISTERED")
    registered_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    #: NULL finché la segreteria non inserisce i risultati.
    placement: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: La posizione vera in classifica quando non è un podio né un 5°/7°
    #: (il 9° di un open): `placement` resta 0, la partecipazione.
    rank: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    result_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ClubSchoolLetter(UUIDPKMixin, TimestampMixin, Base):
    """La giustificazione per la scuola di un atleta iscritto a una gara: il
    club dichiara di averlo selezionato e chiede di giustificare le assenze.
    La segreteria ne corregge il testo e genera il PDF, che resta nel bucket
    privato dei documenti (dati di un minore). Una per iscrizione:
    rigenerarla sostituisce testo e file."""

    __tablename__ = "club_school_letters"
    __table_args__ = (UniqueConstraint("entry_id", name="uq_club_school_letters_entry_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_competition_entries.id"))
    competition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_competitions.id"), index=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    #: Il testo esattamente come è stato stampato.
    body_text: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(String(500))
    generated_at: Mapped[datetime] = mapped_column()
    generated_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class ClubReminderSent(UUIDPKMixin, TimestampMixin, Base):
    """Un promemoria automatico già inviato. Il job giornaliero può girare due
    volte: il vincolo fa sì che il genitore riceva l'avviso una volta sola."""

    __tablename__ = "club_reminders_sent"
    __table_args__ = (
        UniqueConstraint("kind", "entity_id", "stage", name="uq_club_reminders_sent_kind_entity_stage"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: FEE_OVERDUE / CERTIFICATE / FEDERATION / COMPETITION_DEADLINE
    kind: Mapped[str] = mapped_column(String(32))
    #: L'entità a cui si riferisce (quota, certificato, atleta, gara+genitore).
    entity_id: Mapped[str] = mapped_column(String(80))
    #: Il gradino: "30", "7", "expired", "overdue", ...
    stage: Mapped[str] = mapped_column(String(16))


# --- Contabilità del club (docs/club-portal.md, "Contabilità") --------------------------------
#
# Si salvano solo i fatti che non si possono ricavare da nient'altro: una
# spesa sostenuta, un costo fisso promesso, la tariffa oraria di una persona,
# la percentuale che il club riconosce alla piattaforma. Incassi, debiti,
# costo dello staff, commissione della piattaforma e risultato si calcolano
# a ogni lettura (club/accounting.py): una quota corretta corregge il conto.

#: Le categorie di spesa, quelle che un club di judo riconosce nel suo
#: estratto conto. La commissione della piattaforma non c'è: si calcola.
#: COLLABORATORS: i pagamenti a chi aiuta il club senza un contratto da staff;
#: CLEANING: le pulizie della palestra (club_cleaning_logs); EXTERNAL_COACH: i
#: compensi dei treinadores esterni (club_external_coach_fees).
EXPENSE_CATEGORIES = (
    "RENT", "STAFF", "FEDERATION", "INSURANCE", "EQUIPMENT", "TRANSPORT", "EVENTS", "UTILITIES",
    "MARKETING", "ADMIN", "COLLABORATORS", "CLEANING", "EXTERNAL_COACH", "OTHER",
)
#: Come il club ha pagato un fornitore (non come le famiglie pagano il club:
#: quello resta bonifico o JavCash).
EXPENSE_PAYMENT_METHODS = ("BANK_TRANSFER", "MBWAY", "CASH", "CARD", "DIRECT_DEBIT", "CHEQUE", "OTHER")
#: La percentuale degli incassi che un club riconosce alla piattaforma,
#: finché il superadmin non ne decide un'altra.
DEFAULT_PLATFORM_FEE_PCT = Decimal(10)


class ClubRecurringExpense(UUIDPKMixin, TimestampMixin, Base):
    """Un costo fisso mensile (affitto della palestra, compenso del
    treinador, assicurazione a rate): ogni mese diventa da solo una spesa in
    `club_expenses`, una volta sola per mese (UNIQUE su costo fisso + mese)."""

    __tablename__ = "club_recurring_expenses"
    __table_args__ = (
        CheckConstraint(f"category IN ({_in(EXPENSE_CATEGORIES)})", name="category"),
        CheckConstraint(f"payment_method IN ({_in(EXPENSE_PAYMENT_METHODS)})", name="payment_method"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        # Come la scadenza delle quote: ogni mese ha un giorno 28.
        CheckConstraint("day_of_month BETWEEN 1 AND 28", name="day_of_month_range"),
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="date_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    category: Mapped[str] = mapped_column(String(16))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(200))
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    day_of_month: Mapped[int] = mapped_column(SmallInteger, default=1)
    starts_on: Mapped[date] = mapped_column(Date)
    #: Incluso. NULL = finché non lo si ferma.
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: False: sospeso, i mesi nuovi non si registrano (quelli già registrati restano).
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubExpense(UUIDPKMixin, TimestampMixin, Base):
    """Una spesa del club, con la ricevuta (facoltativa) nel bucket privato
    dei documenti, come le prove di pagamento. Le spese nate da un costo
    fisso portano `recurring_id` e il mese (`period`): il vincolo UNIQUE è
    ciò che rende idempotente il job che le registra."""

    __tablename__ = "club_expenses"
    __table_args__ = (
        UniqueConstraint("recurring_id", "period", name="uq_club_expenses_recurring_period"),
        CheckConstraint(f"category IN ({_in(EXPENSE_CATEGORIES)})", name="category"),
        CheckConstraint(f"payment_method IN ({_in(EXPENSE_PAYMENT_METHODS)})", name="payment_method"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("(recurring_id IS NULL) = (period IS NULL)", name="recurring_period"),
        Index("ix_club_expenses_club_spent_on", "club_id", "spent_on"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    spent_on: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(16))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(200))
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    receipt_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_recurring_expenses.id"), nullable=True, index=True
    )
    #: `YYYY-MM`, solo per le spese nate da un costo fisso.
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)


class ClubStaffRate(UUIDPKMixin, TimestampMixin, Base):
    """La tariffa oraria di chi timbra il cartellino, da una data in poi.
    Il costo dello staff di un mese è ore timbrate × tariffa valida in quel
    giorno: si calcola, non si salva. Una tariffa nuova vale da `valid_from`
    e non riscrive i mesi passati."""

    __tablename__ = "club_staff_rates"
    __table_args__ = (
        UniqueConstraint("club_id", "user_id", "valid_from", name="uq_club_staff_rates_club_user_from"),
        CheckConstraint("hourly_rate_cents >= 0", name="rate_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    hourly_rate_cents: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[date] = mapped_column(Date)
    set_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubPlatformFee(UUIDPKMixin, TimestampMixin, Base):
    """La percentuale degli incassi che il club riconosce alla piattaforma,
    da un mese in poi (`valid_from` è sempre il primo del mese). Senza righe
    vale DEFAULT_PLATFORM_FEE_PCT. La decide solo il superadmin
    (`clubs.manage`); la commissione di un mese si calcola dagli incassi di
    quel mese con la percentuale di quel mese, e cambiarla non riscrive il
    passato."""

    __tablename__ = "club_platform_fees"
    __table_args__ = (
        UniqueConstraint("club_id", "valid_from", name="uq_club_platform_fees_club_from"),
        CheckConstraint("pct >= 0 AND pct <= 100", name="pct_range"),
        CheckConstraint("EXTRACT(DAY FROM valid_from) = 1", name="first_of_month"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    valid_from: Mapped[date] = mapped_column(Date)
    set_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ClubAthleteLoginCode(UUIDPKMixin, TimestampMixin, Base):
    """Il QR per entrare al volo nell'area dell'atleta (i più piccoli non
    ricordano una password). Lo crea il titolare; vale finché scade o finché
    lui lo revoca, e si salva solo la sua impronta (sha256): chi legge il
    database non può entrare."""

    __tablename__ = "club_athlete_login_codes"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
