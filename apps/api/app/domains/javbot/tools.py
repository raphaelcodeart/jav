"""Gli strumenti di JAVBOT: le sole cose che l'assistente sa leggere e fare.

Ogni strumento è una funzione tipizzata con un nome, una descrizione e i
parametri in JSON Schema (`Tool.spec()`): la stessa forma che un modello
linguistico riceve come "tool" (vedi planner.py). Oggi li chiama il
pianificatore deterministico; domani li potrà chiamare un modello, senza
cambiare una riga qui.

Le regole, uguali per ogni strumento:

- **i permessi sono quelli delle rotte**: uno strumento della famiglia
  vuole `club.family` e lavora solo sulla famiglia di chi chiede; uno della
  segreteria vuole `club.manage` (o `club.instruct` per le lezioni). Il
  club è quello di `club/scope.py`, mai uno scelto nella conversazione;
- **nessun importo si calcola qui**: le quote arrivano da
  `club/service.py`, i prezzi dello Shop da `jav_market.get_quote`;
- **gli strumenti che scrivono** (`writes=True`) non si chiamano dalla
  conversazione: li esegue solo la conferma di un compito
  (service.py::confirm_task), dopo un "sì" esplicito;
- restituiscono **dati**, non frasi: le frasi le scrive il pianificatore
  nella lingua dell'utente (texts.py).
"""

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.scope import ClubScope

FAMILY = "club.family"
MANAGE = "club.manage"
INSTRUCT = "club.instruct"
ATHLETE = "club.athlete"

#: Le prove di pagamento: gli stessi limiti di core/storage.py::upload_document
#: (documents/models.py). Qui solo per spiegarli, il controllo vero è lì.
PROOF_FORMATS = ("JPG", "PNG", "PDF")
PROOF_MAX_MB = 15

#: Le parole che fanno di un prodotto (o di una categoria) un judogi.
JUDOGI_WORDS = ("judogi", "judo gi", "kimono", "quimono", "dogi", "fato de judo")


class ToolDenied(Exception):
    """Chi chiede non ha il permesso, o non è in un club. `reason` è una
    chiave di texts.py, non una frase."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ToolContext:
    db: AsyncSession
    user_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    scope: ClubScope | None
    permissions: frozenset[str]
    lang: str
    today: date
    #: Il club in cui lavora il treinador (club/scope.py, X-Jav-Staff-Club):
    #: quello scelto entrando nell'area del treinador, o il club dell'account.
    staff_scope: ClubScope | None = None
    #: Falso nel club di un'altra appartenenza: lì non è segreteria.
    staff_home: bool = True

    def require(self, permission: str) -> ClubScope:
        if self.scope is None:
            raise ToolDenied("denied.noClub")
        if permission not in self.permissions:
            raise ToolDenied("denied.family" if permission == FAMILY else "denied.staff")
        return self.scope

    def require_staff(self) -> ClubScope:
        """Il club del lavoro da treinador (presenze): quello scelto
        nell'area del treinador, se c'è."""
        scope = self.staff_scope or self.scope
        if scope is None:
            raise ToolDenied("denied.noClub")
        if INSTRUCT not in self.permissions:
            raise ToolDenied("denied.staff")
        return scope

    @property
    def staff_manager(self) -> bool:
        return MANAGE in self.permissions and self.staff_home


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[ToolContext, dict], Awaitable[dict]]
    #: "private" (area riservata) o "public" (sito, nessun dato personale).
    audience: str = "private"
    writes: bool = False
    required_permission: str | None = None

    def spec(self) -> dict:
        """La definizione per un modello linguistico (formato "tool use")."""
        return {"name": self.name, "description": self.description, "input_schema": self.parameters}


def _schema(properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


# --- Famiglia: quote e pagamenti ------------------------------------------------------------------


async def family_dues(ctx: ToolContext, _args: dict) -> dict:
    """Le quote da pagare della famiglia, per atleta (più la quota socio del
    genitore), la prossima scadenza e i dati del bonifico del club."""
    from app.domains.club import clubs as clubs_service
    from app.domains.club import family as family_service
    from app.domains.club import service as club_service
    from app.domains.club.models import Club

    scope = ctx.require(FAMILY)
    athletes = await club_service.list_family_athletes(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
    by_id = {a.id: a for a in athletes}
    fees = await club_service.list_fees(
        ctx.db, scope=scope, athlete_ids=list(by_id), guardian_user_id=ctx.user_id, status="DUE"
    )
    rows = [family_service.fee_dict(f, today=ctx.today, athlete=by_id.get(f.athlete_id)) for f in fees]
    per_athlete: dict[str, dict] = {}
    for row in rows:
        athlete = by_id.get(row["athlete_id"]) if row["athlete_id"] else None
        key = str(athlete.id) if athlete else "family"
        bucket = per_athlete.setdefault(key, {
            "athlete_id": athlete.id if athlete else None,
            "first_name": athlete.first_name if athlete else None,
            "count": 0, "cents": 0, "overdue": 0,
        })
        bucket["count"] += 1
        bucket["cents"] += row["amount_cents"]
        bucket["overdue"] += 1 if row["overdue"] else 0
    club = await ctx.db.get(Club, scope.club_id)
    bank = clubs_service.club_settings(club) if club else {}
    return {
        "club_name": club.name if club else None,
        "athletes": [{"id": a.id, "first_name": a.first_name} for a in athletes],
        "fees": rows,
        "by_athlete": list(per_athlete.values()),
        "due_cents": sum(r["amount_cents"] for r in rows),
        "overdue_cents": sum(r["amount_cents"] for r in rows if r["overdue"]),
        "next_due_date": min((r["due_date"] for r in rows), default=None),
        "bank": {
            "iban": bank.get("bank_iban"), "holder": bank.get("bank_account_holder"),
            "instructions": bank.get("bank_transfer_instructions"),
        },
    }


async def shop_orders_awaiting_payment(ctx: ToolContext, _args: dict) -> dict:
    """Gli ordini dello Shop di chi chiede ancora in attesa di bonifico: sono
    gli unici a cui si può allegare una ricevuta."""
    from app.domains.jav_market import service as market

    if ctx.user_id is None or ctx.organization_id is None:
        raise ToolDenied("denied.family")
    orders = await market.list_orders(ctx.db, organization_id=ctx.organization_id, customer_user_id=ctx.user_id)
    out = []
    for order in orders:
        if order.status != "AWAITING_PAYMENT" or order.payment_method != "BANK_TRANSFER":
            continue
        out.append({
            "id": order.id, "number": market.order_number(order),
            "amount_due_cents": market.amount_due_cents(order),
            "proof_uploaded": order.payment_proof_storage_key is not None,
        })
    return {"orders": out, "formats": list(PROOF_FORMATS), "max_mb": PROOF_MAX_MB}


async def family_athletes(ctx: ToolContext, _args: dict) -> dict:
    """Gli atleti della famiglia (attivi o sospesi), con il solo nome."""
    from app.domains.club import service as club_service

    scope = ctx.require(FAMILY)
    athletes = await club_service.list_family_athletes(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
    return {"athletes": [{"id": a.id, "first_name": a.first_name, "last_name": a.last_name, "is_self": a.is_self,
                          "height_cm": a.height_cm, "weight_kg": a.weight_kg, "weight_category": a.weight_category,
                          "federation_number": a.federation_number} for a in athletes]}


# --- Famiglia: Shop e judogi ----------------------------------------------------------------------


def _is_judogi(*texts: str | None) -> bool:
    from app.domains.javbot.intents import mentions

    return any(text and mentions(text, *JUDOGI_WORDS) for text in texts)


async def find_judogi(ctx: ToolContext, args: dict) -> dict:
    """Il judogi del catalogo nella taglia giusta per un'altezza (sizes.py):
    la variante esatta se c'è, altrimenti la taglia subito sopra (una
    decina in più va ancora bene a un bambino che cresce). Il prezzo è
    quello del server (`get_quote`), con spedizione, IVA e sconto bonifico."""
    from app.domains.jav_market import service as market
    from app.domains.javbot import sizes
    from app.domains.shop_categories import service as shop_categories_service
    from app.domains.shop_categories.models import ShopCategory

    if ctx.user_id is None or ctx.organization_id is None:
        raise ToolDenied("denied.family")
    height = int(args["height_cm"])
    size = sizes.size_for_height(height)
    result: dict = {"height_cm": height, "size_cm": size, "size_number": sizes.size_number(size), "found": False}

    settings_row = await market.get_settings_row(ctx.db, organization_id=ctx.organization_id)
    if not settings_row.enabled:
        result["shop_closed"] = True
        return result
    products = [p for p in await market.list_products(ctx.db, organization_id=ctx.organization_id) if p.status == "ACTIVE"]
    categories = await shop_categories_service.category_ids_by_product(
        ctx.db, organization_id=ctx.organization_id, shop=market.SHOP, product_ids=[p.id for p in products],
    ) if products else {}
    judogi_categories = {
        c.id for c in (
            await ctx.db.execute(
                select(ShopCategory).where(
                    ShopCategory.organization_id == ctx.organization_id, ShopCategory.shop == market.SHOP,
                )
            )
        ).scalars()
        if _is_judogi(c.name)
    }
    candidates: list[tuple[int, int, object, object]] = []
    judogi_products = 0
    for product in products:
        if not (_is_judogi(product.name, product.description) or judogi_categories & set(categories.get(product.id, []))):
            continue
        judogi_products += 1
        for variant in await market._variants(ctx.db, product.id):
            cm = sizes.variant_size_cm(variant.label)
            if cm is None or not market.variant_sellable(variant) or cm < size or cm > size + 10:
                continue
            candidates.append((cm - size, variant.price_cents, product, variant))
    result["judogi_products"] = judogi_products
    if not candidates:
        return result
    # La taglia esatta prima; tra modelli diversi, il meno caro.
    _gap, _price, product, variant = min(candidates, key=lambda c: (c[0], c[1]))
    quote = await market.get_quote(
        ctx.db, organization_id=ctx.organization_id, customer_user_id=ctx.user_id, variant_id=variant.id, quantity=1,
    )
    result.update({
        "found": True,
        "exact": sizes.variant_size_cm(variant.label) == size,
        "variant_size_cm": sizes.variant_size_cm(variant.label),
        "product_id": product.id, "product_name": product.name,
        "variant_id": variant.id, "variant_label": variant.label,
        "quote": _quote_view(quote),
    })
    return result


def _quote_view(quote: dict) -> dict:
    """Solo i numeri da mostrare, tutti calcolati da get_quote."""
    return {
        "items_cents": quote["items_cents"], "vat_cents": quote["vat_cents"], "shipping_cents": quote["shipping_cents"],
        "amount_cents": quote["amount_cents"],
        "bank_transfer_amount_cents": quote["bank_transfer_amount_cents"],
        "bank_transfer_discount_percentage": quote["bank_transfer_discount_percentage"],
        "bank_transfer_available": quote["bank_transfer_available"],
        "min_order_missing_cents": quote.get("min_order_missing_cents", 0),
        "shipping_days": quote.get("shipping_days"),
    }


async def delivery_address(ctx: ToolContext, _args: dict) -> dict:
    """L'indirizzo di consegna dal profilo (Impostazioni): residenza, nome
    e telefono dell'anagrafica. `missing` dice cosa manca per spedire."""
    from app.domains.customers.models import Customer, CustomerProfile
    from app.domains.users.models import User

    if ctx.user_id is None:
        raise ToolDenied("denied.family")
    user = await ctx.db.get(User, ctx.user_id)
    customer = (
        await ctx.db.execute(select(Customer).where(Customer.user_id == ctx.user_id))
    ).scalars().first()
    profile = await ctx.db.get(CustomerProfile, customer.id) if customer else None
    name = f"{profile.first_name} {profile.last_name}".strip() if profile else ""
    address = {
        "recipient_name": name or None,
        "recipient_phone": customer.phone if customer else None,
        "address_line1": user.residence_street if user else None,
        "address_line2": None,
        "city": user.residence_city if user else None,
        "province": user.residence_province if user else None,
        "postal_code": user.residence_postal_code if user else None,
    }
    # Le stesse lunghezze minime di jav_market/schemas.py::JavMarketAddress.
    minimum = {"recipient_name": 2, "address_line1": 3, "city": 1, "province": 1, "postal_code": 3}
    missing = [k for k, n in minimum.items() if len((address[k] or "").strip()) < n]
    return {"complete": not missing, "missing": missing, "address": address}


async def create_shop_order(ctx: ToolContext, args: dict) -> dict:
    """Crea l'ordine dello Shop (bonifico, un pezzo) con `jav_market.create_order`:
    ogni importo lo ricalcola lì, e lì si controlla che l'atleta sia della
    famiglia. Solo da un compito confermato."""
    from app.domains.jav_market import service as market

    if ctx.user_id is None or ctx.organization_id is None:
        raise ToolDenied("denied.family")
    order = await market.create_order(
        ctx.db, organization_id=ctx.organization_id, customer_user_id=ctx.user_id,
        variant_id=uuid.UUID(str(args["variant_id"])), quantity=1, address=args["address"],
        athlete_id=uuid.UUID(str(args["athlete_id"])) if args.get("athlete_id") else None,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=ctx.user_id, otp_code=None,
        note=args.get("note"),
    )
    return {"order_id": order.id, "number": market.order_number(order), "amount_due_cents": market.amount_due_cents(order)}


# --- Famiglia: certificati, gare, lezioni, inviti, wallet ----------------------------------------


async def family_certificates(ctx: ToolContext, _args: dict) -> dict:
    """Lo stato del certificato medico di ogni atleta: MISSING / VALID /
    EXPIRING (entro 30 giorni) / EXPIRED."""
    from app.domains.club import service as club_service

    scope = ctx.require(FAMILY)
    athletes = [
        a for a in await club_service.list_family_athletes(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
        if a.status == "ACTIVE"
    ]
    certs = await club_service.latest_certificates(ctx.db, athlete_ids=[a.id for a in athletes])
    return {"athletes": [
        {
            "first_name": a.first_name,
            "status": club_service.certificate_status(certs.get(a.id), today=ctx.today),
            "expires_on": certs[a.id].expires_on if a.id in certs else None,
        }
        for a in athletes
    ]}


async def open_competitions(ctx: ToolContext, _args: dict) -> dict:
    """Le gare e gli stage del club con le iscrizioni aperte, e per ognuno
    quali atleti della famiglia possono iscriversi (competitions.eligibility)."""
    from app.domains.club import competitions as competitions_service
    from app.domains.club import service as club_service

    scope = ctx.require(FAMILY)
    comps = [
        c for c in await competitions_service.list_competitions(ctx.db, scope=scope, status="OPEN", from_date=ctx.today)
        if c.registration_deadline >= ctx.today
    ]
    athletes = await club_service.list_family_athletes(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
    out = []
    for comp in comps[:5]:
        eligible = []
        for athlete in athletes:
            ok, _reason = await competitions_service.eligibility(ctx.db, competition=comp, athlete=athlete, today=ctx.today)
            if ok:
                eligible.append(athlete.first_name)
        out.append({
            "id": str(comp.id), "name": comp.name, "kind": comp.kind, "starts_on": comp.starts_on,
            "ends_on": comp.ends_on,
            "location": comp.location, "registration_deadline": comp.registration_deadline, "eligible": eligible,
            "fee_cents": comp.fee_cents, "has_regulation": bool(comp.regulation_storage_key),
        })
    return {"competitions": out, "more": max(len(comps) - 5, 0)}


async def family_lessons_today(ctx: ToolContext, _args: dict) -> dict:
    """Le lezioni di oggi degli atleti della famiglia, con la presenza se già
    segnata (lessons.family_today)."""
    from app.domains.club import lessons as lessons_service

    scope = ctx.require(FAMILY)
    rows = await lessons_service.family_today(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
    return {"lessons": [
        {
            "athlete_id": r["athlete_id"], "first_name": r["athlete_name"].split(" ")[0],
            "course_id": r["course_id"], "course_name": r["course_name"],
            "starts_at": r["starts_at"].strftime("%H:%M"), "ends_at": r["ends_at"].strftime("%H:%M"),
            "present": r["present"],
        }
        for r in rows
    ]}


async def mark_attendance(ctx: ToolContext, args: dict) -> dict:
    """Segna presente oggi un atleta della famiglia a una lezione di oggi
    (lessons.family_mark: solo oggi, solo i propri atleti). Solo da un
    compito confermato."""
    from app.domains.club import lessons as lessons_service

    scope = ctx.require(FAMILY)
    await lessons_service.family_mark(
        ctx.db, scope=scope, guardian_user_id=ctx.user_id, athlete_id=uuid.UUID(str(args["athlete_id"])),
        course_id=uuid.UUID(str(args["course_id"])), present=True, note=None,
    )
    return {"ok": True}


async def invite_link(ctx: ToolContext, _args: dict) -> dict:
    """Il link personale "invita un amico" del club e quanto ha già reso
    (club/referrals.py)."""
    from app.domains.club import referrals as referrals_service
    from app.domains.club.models import Club

    scope = ctx.require(FAMILY)
    club = await ctx.db.get(Club, scope.club_id)
    info = await referrals_service.invite_link(ctx.db, organization_id=scope.organization_id, club=club, user_id=ctx.user_id)
    await ctx.db.commit()
    return info


async def wallet_balance(ctx: ToolContext, _args: dict) -> dict:
    """Il saldo del wallet (credito JavCash) di chi chiede."""
    from app.domains.wallets import service as wallets_service

    if ctx.user_id is None or ctx.organization_id is None:
        raise ToolDenied("denied.family")
    wallet = await wallets_service.get_wallet_by_user_id(ctx.db, organization_id=ctx.organization_id, user_id=ctx.user_id)
    return {"balance_cents": wallet.balance_cents if wallet else 0}


# --- Famiglia: conti, dati, percorso ---------------------------------------------------------------
#
# "Quanto ho pagato?", "che dati avete di me?", "che cintura ha Luca?": le
# stesse cifre delle pagine "I miei conti" e della figurina dell'atleta,
# lette dalle stesse funzioni, così il bot e lo schermo non si
# contraddicono mai.

#: Quanti pagamenti recenti racconta il bot: il resto è in "I miei conti".
RECENT_PAYMENTS = 6


async def family_payments(ctx: ToolContext, _args: dict) -> dict:
    """Quanto ha pagato la famiglia (quest'anno, da sempre, per persona),
    gli ultimi pagamenti, lo Shop, il credito e quanto resta da pagare
    (accounting.personal_account)."""
    from app.domains.club import accounting
    from app.domains.club import service as club_service

    scope = ctx.require(FAMILY)
    account = await accounting.personal_account(
        ctx.db, scope=scope, user_id=ctx.user_id, year=ctx.today.year, today=ctx.today,
    )
    athletes = await club_service.list_family_athletes(
        ctx.db, scope=scope, guardian_user_id=ctx.user_id, include_left=True,
    )
    by_id = {a.id: a for a in athletes}
    paid = [
        f for f in await club_service.list_fees(
            ctx.db, scope=scope, athlete_ids=list(by_id), guardian_user_id=ctx.user_id, status="PAID",
        )
        if f.paid_at is not None
    ]
    paid.sort(key=lambda f: f.paid_at, reverse=True)
    return {
        "year": account["year"],
        "totals": account["totals"],
        "people": [
            {"first_name": p["name"].split(" ")[0] if p["name"] else None, "paid_year_cents": p["paid_year_cents"]}
            for p in account["people"]
        ],
        "recent": [
            {
                "kind": f.kind, "period": f.period, "description": f.description, "amount_cents": f.amount_cents,
                "paid_on": f.paid_at.date(),
                "first_name": by_id[f.athlete_id].first_name if f.athlete_id in by_id else None,
            }
            for f in paid[:RECENT_PAYMENTS]
        ],
        "paid_count": len(paid),
        "shop": account["shop"],
        "wallet_balance_cents": account["wallet"]["balance_cents"],
    }


async def my_profile(ctx: ToolContext, _args: dict) -> dict:
    """I dati di chi chiede (nome, email, telefono, codice fiscale,
    residenza) e, per una famiglia del club, la scheda di ogni atleta:
    piano, tessera federale, peso, certificato, iscritto dal. Solo i suoi."""
    from app.domains.club import family as family_service
    from app.domains.club import service as club_service
    from app.domains.club.models import Club
    from app.domains.customers.models import Customer, CustomerProfile
    from app.domains.users.models import User

    if ctx.user_id is None:
        raise ToolDenied("denied.family")
    user = await ctx.db.get(User, ctx.user_id)
    customer = (await ctx.db.execute(select(Customer).where(Customer.user_id == ctx.user_id))).scalars().first()
    profile = await ctx.db.get(CustomerProfile, customer.id) if customer else None
    out = {
        "first_name": profile.first_name if profile else None,
        "last_name": profile.last_name if profile else None,
        "email": user.email if user else None,
        "phone": customer.phone if customer else None,
        "fiscal_code": user.fiscal_code if user else None,
        "address": {
            "street": user.residence_street, "postal_code": user.residence_postal_code,
            "city": user.residence_city, "province": user.residence_province,
        } if user and user.residence_street else None,
        "club_name": None,
        "athletes": [],
    }
    if ctx.scope is None or FAMILY not in ctx.permissions:
        return out
    club = await ctx.db.get(Club, ctx.scope.club_id)
    out["club_name"] = club.name if club else None
    athletes = await club_service.list_family_athletes(ctx.db, scope=ctx.scope, guardian_user_id=ctx.user_id)
    joined = {a.id: a.joined_on for a in athletes}
    heights = {a.id: a.height_cm for a in athletes}
    for card in await family_service.athlete_cards(ctx.db, athletes=athletes, today=ctx.today):
        out["athletes"].append({
            "first_name": card["first_name"], "last_name": card["last_name"], "is_self": card["is_self"],
            "birth_date": card["birth_date"], "age": card["age"], "status": card["status"],
            "plan_name": card["plan"]["name"] if card["plan"] else None,
            "monthly_fee_cents": card["plan"]["monthly_fee_cents"] if card["plan"] else None,
            "fiscal_code": card["fiscal_code"], "federation_number": card["federation_number"],
            "federation_expires_on": card["federation_expires_on"],
            "weight_kg": card["weight_kg"], "joined_on": joined[card["id"]],
            "height_cm": heights.get(card["id"]), "weight_category": card.get("weight_category"),
            "certificate": card["certificate"]["status"], "certificate_expires_on": card["certificate"]["expires_on"],
        })
    return out


async def my_athlete(ctx: ToolContext, _args: dict) -> dict:
    """L'atleta con il suo accesso chiede di sé: solo la sua scheda, mai
    quella di un altro (anche se della stessa famiglia)."""
    from app.domains.club import family as family_service
    from app.domains.club.models import ClubAthlete

    scope = ctx.require(ATHLETE)
    athlete = (await ctx.db.execute(select(ClubAthlete).where(
        ClubAthlete.club_id == scope.club_id, ClubAthlete.user_id == ctx.user_id))).scalars().first()
    if athlete is None:
        raise ToolDenied("denied.family")
    card = (await family_service.athlete_cards(ctx.db, athletes=[athlete], today=ctx.today))[0]
    return {
        "first_name": card["first_name"], "last_name": card["last_name"], "age": card["age"],
        "height_cm": athlete.height_cm, "weight_kg": card["weight_kg"], "weight_category": card["weight_category"],
        "belt": (card["belt"] or {}).get("label") if card.get("belt") else None,
        "federation_number": card["federation_number"], "plan": card["plan"]["name"] if card["plan"] else None,
        "certificate": card["certificate"]["status"], "attendances": card["attendances"],
        "next_competition": card["next_competition"], "medals": card["medals"],
        "due_cents": card["due_cents"],
    }


async def family_progress(ctx: ToolContext, _args: dict) -> dict:
    """Il percorso di ogni atleta della famiglia: cintura attuale e da
    quando, presenze (da sempre, nel mese, nella stagione), punti del
    ranking della stagione, medaglie, livello, prossima gara. Nei corsi JAV
    cinture e gare non ci sono (club/kinds.py) e restano None."""
    from app.domains.club import family as family_service
    from app.domains.club import kinds, seasons
    from app.domains.club import service as club_service
    from app.domains.club.models import ClubAttendance, ClubBeltGrade

    scope = ctx.require(FAMILY)
    rules = await kinds.club_rules(ctx.db, club_id=scope.club_id)
    athletes = await club_service.list_family_athletes(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
    ids = [a.id for a in athletes]
    season = seasons.season_of(ctx.today)
    first, last = seasons.season_start(season), seasons.season_end(season)
    month_start = ctx.today.replace(day=1)
    month = {a: 0 for a in ids}
    in_season = {a: 0 for a in ids}
    awarded: dict[tuple[uuid.UUID, str], date] = {}
    if ids:
        for athlete_id, on in (
            await ctx.db.execute(
                select(ClubAttendance.athlete_id, ClubAttendance.date).where(
                    ClubAttendance.athlete_id.in_(ids), ClubAttendance.present.is_(True),
                    ClubAttendance.date >= min(month_start, first),
                )
            )
        ).all():
            month[athlete_id] += on >= month_start
            in_season[athlete_id] += first <= on <= last
        for athlete_id, grade, awarded_on in (
            await ctx.db.execute(
                select(ClubBeltGrade.athlete_id, ClubBeltGrade.grade, ClubBeltGrade.awarded_on)
                .where(ClubBeltGrade.athlete_id.in_(ids))
            )
        ).all():
            awarded[(athlete_id, grade)] = awarded_on
    out = []
    for card in await family_service.athlete_cards(ctx.db, athletes=athletes, today=ctx.today):
        belt = card["belt"]["code"] if card["belt"] and rules.has_belts else None
        out.append({
            "first_name": card["first_name"],
            "belt": belt,
            "belt_since": awarded.get((card["id"], belt)) if belt else None,
            "attendances": card["attendances"],
            "attendances_month": month[card["id"]],
            "attendances_season": in_season[card["id"]],
            "ranking_points": card["ranking_points"] if rules.has_competitions else None,
            "medals": card["medals"] if rules.has_competitions else None,
            "level": card["level"],
            "achievements_earned": card["achievements_earned"],
            "next_competition": card["next_competition"] if rules.has_competitions else None,
        })
    return {
        "season_label": seasons.season_label(season), "has_belts": rules.has_belts,
        "has_competitions": rules.has_competitions, "athletes": out,
    }


async def club_contacts(ctx: ToolContext, _args: dict) -> dict:
    """Come raggiungere la segreteria del club: email dalle impostazioni,
    telefono ed email della pagina pubblica."""
    from app.domains.club import clubs as clubs_service
    from app.domains.club.models import Club
    from app.domains.club.site_models import ClubSite

    if ctx.scope is None:
        raise ToolDenied("denied.noClub")
    club = await ctx.db.get(Club, ctx.scope.club_id)
    site = (await ctx.db.execute(select(ClubSite).where(ClubSite.club_id == ctx.scope.club_id))).scalars().first()
    settings = clubs_service.club_settings(club) if club else {}
    return {
        "club_name": club.name if club else None,
        "email": settings.get("contact_email") or (site.contact_email if site else None),
        "phone": site.contact_phone if site else None,
        "address": site.address if site else None,
    }


async def send_club_message(ctx: ToolContext, args: dict) -> dict:
    """Manda un messaggio alla segreteria del club, come notifica
    (clubs.notify_club_staff). Solo da un compito confermato."""
    from app.domains.club import clubs as clubs_service
    from app.domains.users.models import User

    if ctx.scope is None:
        raise ToolDenied("denied.noClub")
    user = await ctx.db.get(User, ctx.user_id)
    text = str(args["text"]).strip()[:1000]
    await clubs_service.notify_club_staff(
        ctx.db, scope=ctx.scope, type_="JAVBOT_MESSAGE", entity_id=uuid.UUID(str(args["task_id"])),
        entity_type="javbot_task",
        title=f"Messaggio da {user.email if user else 'una famiglia'} (JAVBOT)", body=text,
    )
    return {"ok": True}


# --- Segreteria e istruttori ----------------------------------------------------------------------


async def staff_unpaid_month(ctx: ToolContext, _args: dict) -> dict:
    """Chi non ha ancora pagato la mensilità di questo mese (segreteria)."""
    from app.domains.club import service as club_service
    from app.domains.club.models import ClubAthlete

    scope = ctx.require(MANAGE)
    period = ctx.today.strftime("%Y-%m")
    # Anche il resto di una mensilità pagata in parte ("2026-10/r1", club/fee_splits.py).
    fees = [
        f for f in await club_service.list_fees(ctx.db, scope=scope, status="DUE", kind="MONTHLY")
        if f.period.split("/r", 1)[0] == period
    ]
    athletes = {
        a.id: a for a in (
            await ctx.db.execute(select(ClubAthlete).where(ClubAthlete.id.in_({f.athlete_id for f in fees})))
        ).scalars()
    } if fees else {}
    rows = sorted(
        ({"name": f"{athletes[f.athlete_id].first_name} {athletes[f.athlete_id].last_name}", "amount_cents": f.amount_cents,
          "overdue": f.due_date < ctx.today} for f in fees if f.athlete_id in athletes),
        key=lambda r: r["name"],
    )
    return {"period": period, "rows": rows, "total_cents": sum(r["amount_cents"] for r in rows)}


async def staff_lessons_today(ctx: ToolContext, _args: dict) -> dict:
    """Le lezioni di oggi: tutte per la segreteria, quelle dei corsi che vede
    per un istruttore (come /club/staff/lessons)."""
    from app.domains.club import lessons as lessons_service

    scope = ctx.require(INSTRUCT)
    now = await lessons_service.club_now(ctx.db, club_id=scope.club_id)
    rows = await lessons_service.lessons(
        ctx.db, scope=scope, start=now.date(), end=now.date(),
        teacher_user_id=None if MANAGE in ctx.permissions else ctx.user_id, now=now,
    )
    return {"lessons": [
        {"course_name": r["course_name"], "starts_at": r["starts_at"].strftime("%H:%M"),
         "ends_at": r["ends_at"].strftime("%H:%M"), "enrolled": r["enrolled"], "present": r["present"],
         "current": r["current"]}
        for r in rows
    ]}


async def staff_certificate_issues(ctx: ToolContext, _args: dict) -> dict:
    """Gli atleti attivi con il certificato scaduto, mancante o in scadenza
    (segreteria)."""
    from app.domains.club import service as club_service

    scope = ctx.require(MANAGE)
    athletes = await club_service.search_athletes(ctx.db, scope=scope, status="ACTIVE")
    certs = await club_service.latest_certificates(ctx.db, athlete_ids=[a.id for a in athletes])
    out: dict[str, list[str]] = {"EXPIRED": [], "MISSING": [], "EXPIRING": []}
    for athlete in athletes:
        status = club_service.certificate_status(certs.get(athlete.id), today=ctx.today)
        if status in out:
            out[status].append(f"{athlete.first_name} {athlete.last_name}")
    return {k: sorted(v) for k, v in out.items()}


# --- Sito pubblico: niente dati personali ---------------------------------------------------------


async def public_clubs(ctx: ToolContext, _args: dict) -> dict:
    """I club pubblicati sul portale: nome, città, indirizzo della pagina."""
    from app.domains.club import site as site_service

    return {"clubs": [
        {"name": c["name"], "slug": c["slug"], "city": c["city"], "tagline": c["tagline"]}
        for c in await site_service.list_public_clubs(ctx.db)
    ]}


async def public_club_info(ctx: ToolContext, args: dict) -> dict:
    """Di un club pubblicato: orario settimanale (dai corsi), contatti della
    pagina, link d'iscrizione, i gruppi (piani attivi: nome e fascia d'età)
    e — solo se il club ha scelto di mostrarli — i loro prezzi con le altre
    quote e gli sconti del club. Mai atleti, mai quote di qualcuno.

    Tutto viene da ciò che il club ha configurato: i piani e i parametri di
    `club/pricing.py`, gli stessi con cui si emettono le quote vere. Ciò che
    è a zero o spento non si restituisce: il bot non deve annunciare uno
    sconto che il club non fa."""
    from app.domains.club import kinds
    from app.domains.club import pricing as pricing_rules
    from app.domains.club import service as club_service
    from app.domains.club import site as site_service
    from app.domains.club.models import Club
    from app.domains.club.site_models import ClubSite

    page = await site_service.club_page(ctx.db, slug=str(args["slug"]), today=ctx.today)
    out = {
        "name": page["name"], "slug": page["slug"], "city": page["city"],
        "schedule": page["schedule"],
        "contacts": {"phone": page["contact_phone"], "email": page["contact_email"], "address": page["address"]},
        "signup_path": f"/c/{page['slug']}",
        "upcoming_events": [
            {"name": e["name"], "starts_on": e["starts_on"], "location": e["location"]} for e in page["upcoming_events"][:3]
        ],
        "show_prices": False,
        "plans": [],
        "fees": None,
        "discounts": {},
    }
    club = (await ctx.db.execute(select(Club).where(Club.slug == page["slug"]))).scalars().first()
    if club is None:
        return out
    site = (await ctx.db.execute(select(ClubSite).where(ClubSite.club_id == club.id))).scalars().first()
    # Gruppi ed età si dicono sempre (sono scritti anche nell'orario); i
    # soldi solo con "mostra i prezzi sul sito" acceso.
    show = bool(site is not None and site.show_prices)
    out["show_prices"] = show
    scope = ClubScope(organization_id=club.organization_id, club_id=club.id)
    for plan in await club_service.list_plans(ctx.db, scope=scope, only_active=True):
        row = {"name": plan.name, "min_age": plan.min_age, "max_age": plan.max_age}
        if show:
            # La descrizione del piano può contenere prezzi (le aule avulse):
            # esce solo insieme ai prezzi.
            row.update(description=plan.description, monthly_fee_cents=plan.monthly_fee_cents,
                       enrollment_fee_cents=plan.enrollment_fee_cents, due_day=plan.due_day,
                       billing_months=sorted(plan.billing_months or []))
        out["plans"].append(row)
    pricing = pricing_rules.get_pricing(club)
    # Quali sconti il club fa si dice sempre ("ha uno sconto famiglia");
    # quanto, solo con i prezzi.
    out["discounts"] = {
        "tier": any(pricing["tier_discount_pct"].values()),
        "adapted": bool(pricing["tier_discount_pct"].get("A")),
        "family": bool(pricing["family_discount_cents"]),
        "referral": bool(pricing["referral_credit_cents"]),
    }
    if show:
        saved = (club.settings or {}).get("pricing") or {}
        has_enrollment = kinds.rules_of(club).has_enrollment_fees
        out["fees"] = {
            "parent_member_fee_cents": pricing["parent_member_fee_cents"] if has_enrollment else 0,
            "minor_age": pricing_rules.MINOR_AGE,
            "family_discount_cents": pricing["family_discount_cents"],
            "family_min_athletes": pricing["family_min_athletes"],
            "tier_discount_pct": {t: p for t, p in sorted(pricing["tier_discount_pct"].items()) if p},
            "referral_credit_cents": pricing["referral_credit_cents"],
            # Il testo di default è un segnaposto della segreteria (in
            # italiano): alle famiglie va solo quello che il club ha scritto.
            "enrollment_includes": (saved.get("enrollment_includes") or "").strip() or None,
        }
    return out


async def public_events(ctx: ToolContext, _args: dict) -> dict:
    """I prossimi eventi (gare e stage) dei club pubblicati."""
    from app.domains.club import site as site_service

    events = await site_service.list_events(ctx.db, when="upcoming", limit=5, today=ctx.today)
    return {"events": [
        {"id": e["id"], "name": e["name"], "kind": e["kind"], "starts_on": e["starts_on"], "location": e["location"],
         "club": e["club"]["name"]}
        for e in events
    ]}


async def public_courses(ctx: ToolContext, _args: dict) -> dict:
    """I corsi JAV nelle scuole pubblicati: luogo, orario, età, link
    d'iscrizione, e la mensilità dei piani dell'unità. Nessuna persona
    (club/kinds.py).

    Il prezzo dei corsi si dice sempre, senza `show_prices`: è una regola
    di JAV (una mensilità, niente iscrizione né quota socio), uguale per
    tutte le scuole, e la sezione pubblica dei corsi la presenta già così."""
    from app.domains.club import kinds
    from app.domains.club import service as club_service
    from app.domains.club import site as site_service
    from app.domains.club.models import Club

    data = await site_service.public_courses(ctx.db)
    plans: list[dict] = []
    if data["unit"] is not None:
        unit = (await ctx.db.execute(
            select(Club).where(Club.slug == data["unit"]["slug"], Club.kind == kinds.JAV_COURSES)
        )).scalars().first()
        if unit is not None:
            scope = ClubScope(organization_id=unit.organization_id, club_id=unit.id)
            plans = [
                {"name": p.name, "min_age": p.min_age, "max_age": p.max_age, "monthly_fee_cents": p.monthly_fee_cents}
                for p in await club_service.list_plans(ctx.db, scope=scope, only_active=True)
            ]
    return {"courses": [
        {"name": c["name"], "venue_name": c["venue_name"], "venue_city": c["venue_city"], "min_age": c["min_age"],
         "max_age": c["max_age"], "slots": c["slots"], "signup_path": c["signup_path"]}
        for c in data["courses"]
    ], "plans": plans}


# --- Il registro ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def specs(self, *, audience: str, include_writes: bool = False) -> list[dict]:
        """Ciò che si dà a un modello: gli strumenti di quel pubblico. Quelli
        che scrivono, di norma no: un modello propone, l'utente conferma."""
        return [
            t.spec() for t in self.tools.values()
            if t.audience == audience and (include_writes or not t.writes)
        ]

    async def call(
        self, name: str, ctx: ToolContext, args: dict | None = None, *, audience: str = "private",
        allow_writes: bool = False,
    ) -> dict:
        """Il bot pubblico chiama solo strumenti pubblici, e viceversa: è il
        confine che tiene i dati personali fuori dal sito."""
        tool = self.tools[name]
        if tool.audience != audience:
            raise ToolDenied("denied.staff")
        if tool.writes and not allow_writes:
            raise ToolDenied("denied.needsConfirmation")
        return await tool.run(ctx, args or {})

REGISTRY = Registry()
_UUID = {"type": "string", "format": "uuid"}
for _tool in (
    Tool("family_dues", "Quote da pagare della famiglia per atleta, prossima scadenza e IBAN del club.", _schema(), family_dues,
         required_permission=FAMILY),
    Tool("shop_orders_awaiting_payment", "Ordini dello Shop in attesa di bonifico e limiti dei file della ricevuta.",
         _schema(), shop_orders_awaiting_payment),
    Tool("family_athletes", "Gli atleti della famiglia: nome, altezza (cm), peso, categoria di peso, tessera federale.",
         _schema(), family_athletes, required_permission=FAMILY),
    Tool("my_athlete", "La scheda dell'atleta che scrive con il suo accesso (solo sé stesso): nome, età, altezza, "
         "peso, categoria, cintura, tessera federale, gruppo, certificato, presenze del mese, prossima gara.",
         _schema(), my_athlete, required_permission=ATHLETE),
    Tool("find_judogi", "Trova nel catalogo il judogi della taglia giusta per un'altezza in cm, con il prezzo del server.",
         _schema({"height_cm": {"type": "integer", "minimum": 80, "maximum": 215}}, ["height_cm"]), find_judogi),
    Tool("delivery_address", "L'indirizzo di consegna dal profilo e che cosa manca.", _schema(), delivery_address),
    Tool("create_shop_order", "Crea un ordine dello Shop con bonifico. Solo dopo la conferma esplicita dell'utente.",
         _schema({"variant_id": _UUID, "athlete_id": _UUID, "address": {"type": "object"}, "note": {"type": "string"}},
                 ["variant_id", "address"]),
         create_shop_order, writes=True),
    Tool("family_certificates", "Stato del certificato medico di ogni atleta della famiglia.", _schema(),
         family_certificates, required_permission=FAMILY),
    Tool("open_competitions", "Gare e stage con iscrizioni aperte e chi della famiglia può iscriversi.", _schema(),
         open_competitions, required_permission=FAMILY),
    Tool("family_lessons_today", "Le lezioni di oggi degli atleti della famiglia.", _schema(), family_lessons_today,
         required_permission=FAMILY),
    Tool("mark_attendance", "Segna presente oggi un atleta della famiglia. Solo dopo conferma.",
         _schema({"athlete_id": _UUID, "course_id": _UUID}, ["athlete_id", "course_id"]), mark_attendance,
         writes=True, required_permission=FAMILY),
    Tool("invite_link", "Il link personale per invitare un amico nel club.", _schema(), invite_link,
         required_permission=FAMILY),
    Tool("wallet_balance", "Il saldo del wallet (credito) dell'utente.", _schema(), wallet_balance),
    Tool("family_payments", "Quanto ha pagato la famiglia (anno, da sempre, per persona), gli ultimi pagamenti, "
         "lo Shop, il credito e quanto resta da pagare.", _schema(), family_payments, required_permission=FAMILY),
    Tool("my_profile", "I dati personali dell'utente e la scheda anagrafica di ogni atleta della famiglia.",
         _schema(), my_profile),
    Tool("family_progress", "Cintura, presenze, punti del ranking, medaglie, livello e prossima gara di ogni "
         "atleta della famiglia.", _schema(), family_progress, required_permission=FAMILY),
    Tool("club_contacts", "Email, telefono e indirizzo della segreteria del club.", _schema(), club_contacts),
    Tool("send_club_message", "Manda un messaggio alla segreteria del club. Solo dopo conferma.",
         _schema({"text": {"type": "string", "maxLength": 1000}, "task_id": _UUID}, ["text", "task_id"]),
         send_club_message, writes=True),
    Tool("staff_unpaid_month", "Segreteria: chi non ha pagato la mensilità del mese.", _schema(), staff_unpaid_month,
         required_permission=MANAGE),
    Tool("staff_lessons_today", "Staff: le lezioni di oggi.", _schema(), staff_lessons_today, required_permission=INSTRUCT),
    Tool("staff_certificate_issues", "Segreteria: certificati scaduti, mancanti o in scadenza.", _schema(),
         staff_certificate_issues, required_permission=MANAGE),
    Tool("public_clubs", "I club pubblicati sul portale.", _schema(), public_clubs, audience="public"),
    Tool("public_club_info", "Orari, contatti, iscrizione, gruppi ed età e (se pubblici) prezzi, quote e sconti di "
         "un club pubblicato.",
         _schema({"slug": {"type": "string"}}, ["slug"]), public_club_info, audience="public"),
    Tool("public_events", "I prossimi eventi dei club pubblicati.", _schema(), public_events, audience="public"),
    Tool("public_courses", "I corsi JAV nelle scuole pubblicati: luogo, orario, età, iscrizione, mensilità.", _schema(),
         public_courses, audience="public"),
):
    REGISTRY.add(_tool)


def first_name_in(text: str, names: list[str]) -> str | None:
    """Il nome di un atleta citato nel messaggio ("per Luca"), se c'è."""
    from app.domains.javbot.intents import normalize

    norm = normalize(text)
    for name in names:
        if re.search(rf"(?<![a-z]){re.escape(normalize(name))}(?![a-z])", norm):
            return name
    return None
