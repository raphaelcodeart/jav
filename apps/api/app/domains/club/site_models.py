"""Il sito pubblico: la pagina di ogni club e i profili pubblici dei judoca.
Specifica: docs/club-portal.md, "Sito pubblico".

Due tabelle a parte, e non colonne su `clubs` e `club_athletes`, per una
ragione sola: tutto ciò che sta qui **è fatto per essere letto da chiunque**.
Tenerlo separato dai dati del gestionale (codice fiscale, data di nascita,
peso, genitore, quote) rende impossibile che una query del sito ne trascini
dietro uno per sbaglio.

**Un atleta compare sul sito solo se il genitore ha dato il consenso e il
club lo ha pubblicato** (GDPR: molti atleti sono minorenni). Le due cose
sono distinte di proposito: il consenso è della famiglia, la pubblicazione è
del club, e basta che una delle due manchi perché l'atleta sparisca.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin, utcnow


class ClubSite(UUIDPKMixin, TimestampMixin, Base):
    """La pagina pubblica di un club: testi, foto, contatti, social. Una per
    club; la scrive la segreteria. Finché non è pubblicata il club non
    compare sul portale, nemmeno conoscendone l'indirizzo."""

    __tablename__ = "club_sites"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), unique=True)
    #: Una frase sotto il nome ("Judo per tutti, a Lagos, dal 1985").
    tagline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: La città, per la card del carosello e l'elenco dei club.
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hero_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: [{"url": ..., "caption": ...}], nell'ordine in cui si mostrano.
    gallery: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    #: [{"name": ..., "role": ..., "photo_url": ...}]: gli allenatori come il
    #: club li vuole presentare. Scritti a mano e non presi dagli account
    #: degli istruttori: un account non è un consenso a comparire sul web.
    coaches: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    map_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    facebook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    #: Il club sceglie di far dire i prezzi dei suoi piani (mensilità e
    #: iscrizione) a chi chiede sul sito, per esempio all'assistente JAVBOT.
    #: Spento finché la segreteria non lo accende: un prezzo è una scelta
    #: commerciale del club, non un dato che il portale pubblica da sé.
    show_prices: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # I colori del club (club/brand.py), "#RRGGBB" maiuscolo o vuoto: la
    # pagina pubblica li usa per la copertina, i bottoni e i titoli. Vuoti =
    # i colori di JudoArteVida. Il vincolo è la seconda rete dopo
    # brand.normalize_hex: nel CSS della pagina non finisce altro che un colore.
    brand_primary: Mapped[str | None] = mapped_column(String(7), nullable=True)
    brand_secondary: Mapped[str | None] = mapped_column(String(7), nullable=True)
    brand_accent: Mapped[str | None] = mapped_column(String(7), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    __table_args__ = tuple(
        CheckConstraint(f"{column} IS NULL OR {column} ~ '^#[0-9A-F]{{6}}$'", name=column)
        for column in ("brand_primary", "brand_secondary", "brand_accent")
    )


class ClubAthletePublicProfile(UUIDPKMixin, TimestampMixin, Base):
    """Il consenso della famiglia e la scelta del club per un atleta. La
    riga nasce quando il genitore dà il consenso; ritirarlo azzera
    `consent_given_at` e toglie la pubblicazione, e la riga resta come
    traccia di chi ha deciso cosa."""

    __tablename__ = "club_athlete_public_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("club_athletes.id"), unique=True
    )
    #: NULL = nessun consenso (mai dato, o ritirato): l'atleta non è pubblico.
    consent_given_at: Mapped[datetime | None] = mapped_column(nullable=True)
    consent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: La foto è un consenso a parte: si può voler comparire senza il volto.
    show_photo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    #: Due righe scritte dalla famiglia ("Judo da quando avevo 5 anni").
    bio: Mapped[str | None] = mapped_column(String(280), nullable=True)
    #: La scelta del club. Vale solo con il consenso.
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # La scheda del judoca, scritta dalla segreteria. Sono dati sportivi
    # pubblici per natura (un profilo IJF lo è già), ma si vedono comunque
    # solo con consenso e pubblicazione, come tutto il resto della riga.
    #: Il profilo sul sito della Federazione Internazionale, se il judoca
    #: ne ha uno: solo ijf.org/judoka/... o judobase.ijf.org (site.py).
    ijf_profile_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: La tecnica preferita ("Seoi-nage"), scritta a mano.
    favorite_technique: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: La guardia: LEFT / RIGHT (hidari / migi), come nelle schede IJF.
    dominant_side: Mapped[str | None] = mapped_column(String(5), nullable=True)

    __table_args__ = (
        CheckConstraint("dominant_side IS NULL OR dominant_side IN ('LEFT', 'RIGHT')", name="dominant_side"),
    )


class ClubAthleteMedia(UUIDPKMixin, TimestampMixin, Base):
    """Le foto e i video della scheda pubblica di un judoca. Li carica la
    segreteria e ognuno si pubblica a parte: una foto caricata non è ancora
    una foto sul web. Sul sito escono solo quelli pubblicati, e solo se la
    famiglia ha permesso la foto (`show_photo`): una foto o un video di gara
    mostrano il volto, e il permesso del volto è della famiglia.

    I video sono solo di YouTube e si salva l'id, mai un indirizzo: il sito
    lo incorpora con youtube-nocookie.com, e un indirizzo qualsiasi non può
    finire in un iframe."""

    __tablename__ = "club_athlete_media"
    __table_args__ = (
        CheckConstraint("kind IN ('PHOTO', 'VIDEO')", name="kind"),
        CheckConstraint(
            "(kind = 'PHOTO' AND url IS NOT NULL AND youtube_id IS NULL)"
            " OR (kind = 'VIDEO' AND youtube_id IS NOT NULL AND url IS NULL)",
            name="kind_payload",
        ),
        # Lo stesso video due volte (un doppio clic) non si aggiunge: per le
        # foto youtube_id è NULL, e i NULL non si scontrano.
        UniqueConstraint("athlete_id", "youtube_id", name="uq_club_athlete_media_athlete_youtube"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("club_athletes.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    #: La foto, nel bucket pubblico dei media (upload_media).
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    youtube_id: Mapped[str | None] = mapped_column(String(11), nullable=True)
    caption: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
