"""Invita un amico nel club: un livello solo.

Ogni account del club (un genitore, o un atleta adulto che fa tutto da sé)
ha il suo link d'invito, `/c/<slug>?invito=<codice>`: il codice è quello di
friend_referrals (uno per persona), e chi si registra da lì finisce nella
lista degli invitati (`friend_referrals`, sorgente CLUB_LINK).

Ogni volta che un atleta della famiglia invitata paga una mensilità, chi ha
invitato riceve nel wallet il credito deciso dal club (pricing.py,
`referral_credit_cents`, 5 € di default), che usa quando paga le sue quote.
Se quel pagamento viene annullato (prova rifiutata, quota riaperta) il
credito si ritira.

L'idempotenza sta nella chiave del movimento del wallet: un pagamento è una
quota più il momento in cui è stata pagata, quindi lo stesso pagamento non
accredita due volte, e una quota ripagata dopo un rifiuto accredita di
nuovo.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.models import Club, ClubAthlete, ClubFee
from app.domains.club.pricing import get_pricing

logger = logging.getLogger(__name__)

SOURCE_CLUB_LINK = "CLUB_LINK"
WALLET_SOURCE = "CLUB_REFERRAL"


def _credit_key_prefix(fee_id: uuid.UUID) -> str:
    return f"club-referral:{fee_id}:"


async def invite_link(db: AsyncSession, *, organization_id: uuid.UUID, club: Club, user_id: uuid.UUID) -> dict:
    """Il link da condividere e quanto ha già reso."""
    from sqlalchemy import func

    from app.domains.friend_referrals import service as friend_referrals_service
    from app.domains.friend_referrals.models import FriendReferral
    from app.domains.wallets.models import Wallet, WalletTransaction

    code = await friend_referrals_service.get_or_create_code(db, organization_id=organization_id, user_id=user_id)
    invited = (
        await db.execute(
            select(func.count()).where(
                FriendReferral.referrer_user_id == user_id, FriendReferral.source == SOURCE_CLUB_LINK
            )
        )
    ).scalar_one()
    earned = (
        await db.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount_cents), 0))
            .join(Wallet, Wallet.id == WalletTransaction.to_wallet_id)
            .where(Wallet.user_id == user_id, WalletTransaction.source == WALLET_SOURCE)
        )
    ).scalar_one()
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user_id))).scalars().first()
    return {
        "code": code.code,
        "path": f"/c/{club.slug}?invito={code.code}",
        "invited_count": invited,
        "earned_cents": int(earned),
        "credit_per_month_cents": get_pricing(club)["referral_credit_cents"],
        "balance_cents": int(wallet.balance_cents) if wallet else 0,
        "network": await _network(db, club=club, user_id=user_id, wallet_id=wallet.id if wallet else None),
    }


async def _network(db: AsyncSession, *, club: Club, user_id: uuid.UUID, wallet_id: uuid.UUID | None) -> list[dict]:
    """La rete di chi invita: ogni atleta delle famiglie entrate dal suo link,
    con le mensilità pagate e il credito che gli ha reso (i crediti stornati
    da un rifiuto non contano). Solo nome e iniziale del cognome: è la rete di
    un genitore, non l'anagrafe del club."""
    from sqlalchemy import func

    from app.domains.customers.models import Customer
    from app.domains.friend_referrals.models import FriendReferral
    from app.domains.wallets.models import WalletTransaction

    rows = (
        await db.execute(
            select(Customer.user_id, FriendReferral.created_at)
            .join(FriendReferral, FriendReferral.referred_customer_id == Customer.id)
            .where(FriendReferral.referrer_user_id == user_id, FriendReferral.source == SOURCE_CLUB_LINK)
        )
    ).all()
    joined = {guardian: when for guardian, when in rows if guardian is not None}
    if not joined:
        return []
    athletes = list(
        (
            await db.execute(
                select(ClubAthlete)
                .where(ClubAthlete.club_id == club.id, ClubAthlete.guardian_user_id.in_(joined))
                .order_by(ClubAthlete.first_name)
            )
        ).scalars()
    )
    ids = [a.id for a in athletes]
    paid = dict(
        (
            await db.execute(
                select(ClubFee.athlete_id, func.count())
                .where(ClubFee.athlete_id.in_(ids), ClubFee.kind == "MONTHLY", ClubFee.status == "PAID")
                .group_by(ClubFee.athlete_id)
            )
        ).all()
    ) if ids else {}
    credit: dict[uuid.UUID, int] = {}
    if wallet_id is not None and ids:
        reversed_ids = select(WalletTransaction.reverses_transaction_id).where(
            WalletTransaction.reverses_transaction_id.is_not(None)
        )
        credits = (
            await db.execute(
                select(WalletTransaction.idempotency_key, WalletTransaction.amount_cents).where(
                    WalletTransaction.to_wallet_id == wallet_id, WalletTransaction.source == WALLET_SOURCE,
                    WalletTransaction.id.not_in(reversed_ids),
                )
            )
        ).all()
        # La chiave del credito è «club-referral:<quota>:<pagamento>».
        fee_ids: dict[uuid.UUID, int] = {}
        for key, amount in credits:
            try:
                fee_id = uuid.UUID((key or "").split(":")[1])
            except (IndexError, ValueError):
                continue
            fee_ids[fee_id] = fee_ids.get(fee_id, 0) + int(amount)
        if fee_ids:
            owners = dict(
                (await db.execute(select(ClubFee.id, ClubFee.athlete_id).where(ClubFee.id.in_(fee_ids)))).all()
            )
            for fee_id, amount in fee_ids.items():
                athlete_id = owners.get(fee_id)
                if athlete_id is not None:
                    credit[athlete_id] = credit.get(athlete_id, 0) + amount
    return [
        {
            "athlete_id": a.id,
            "name": f"{a.first_name} {a.last_name[:1]}.",
            "photo_url": a.photo_url,
            "status": a.status,
            "joined_on": joined[a.guardian_user_id].date(),
            "months_paid": int(paid.get(a.id, 0)),
            "credit_cents": credit.get(a.id, 0),
        }
        for a in athletes
    ]


async def record_club_invite(
    db: AsyncSession, *, club: Club, invite_code: str | None, customer_id: uuid.UUID
) -> None:
    """Alla registrazione dal link: chi ha invitato, se il codice è valido
    ed è di una persona dello stesso club. Un codice sbagliato non blocca la
    registrazione: semplicemente non conta come invito. Non committa."""
    from app.domains.friend_referrals import service as friend_referrals_service
    from app.domains.users.models import User

    if not invite_code:
        return
    code = await friend_referrals_service.get_active_code(
        db, organization_id=club.organization_id, code=invite_code.strip()
    )
    if code is None:
        return
    referrer = await db.get(User, code.user_id)
    if referrer is None or referrer.club_id != club.id:
        return
    await friend_referrals_service.record_referral(
        db, organization_id=club.organization_id, referrer_user_id=referrer.id,
        referred_customer_id=customer_id, code_used=code.code, source=SOURCE_CLUB_LINK,
    )


async def _referrer_of(db: AsyncSession, *, guardian_user_id: uuid.UUID, club_id: uuid.UUID):
    from app.domains.customers.models import Customer
    from app.domains.friend_referrals.models import FriendReferral
    from app.domains.users.models import User

    referrer = (
        await db.execute(
            select(User)
            .join(FriendReferral, FriendReferral.referrer_user_id == User.id)
            .join(Customer, Customer.id == FriendReferral.referred_customer_id)
            .where(Customer.user_id == guardian_user_id, FriendReferral.source == SOURCE_CLUB_LINK)
        )
    ).scalars().first()
    if referrer is None or referrer.club_id != club_id or referrer.status != "ACTIVE":
        return None
    return referrer


async def on_fee_paid(db: AsyncSession, *, fee: ClubFee) -> None:
    """Una mensilità pagata: il credito a chi ha invitato quella famiglia.
    Dopo il commit del pagamento, e senza mai farlo fallire."""
    from app.domains.notifications import service as notifications_service
    from app.domains.wallets import service as wallets_service

    if fee.kind != "MONTHLY" or fee.status != "PAID" or fee.athlete_id is None or fee.paid_at is None:
        return
    try:
        athlete = await db.get(ClubAthlete, fee.athlete_id)
        club = await db.get(Club, fee.club_id)
        if athlete is None or club is None:
            return
        amount = get_pricing(club)["referral_credit_cents"]
        referrer = await _referrer_of(db, guardian_user_id=athlete.guardian_user_id, club_id=fee.club_id)
        if referrer is None or amount <= 0:
            return
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=fee.organization_id, user_id=referrer.id
        )
        await wallets_service.credit_wallet(
            db, organization_id=fee.organization_id, wallet_id=wallet.id, amount_cents=amount,
            type_="ADMIN_CREDIT", actor_user_id=None, source=WALLET_SOURCE,
            note=f"Sconto invito: {athlete.first_name} ha pagato la {fee.description.lower()}",
            idempotency_key=f"{_credit_key_prefix(fee.id)}{fee.paid_at.isoformat()}",
        )
        await notifications_service.notify_user(
            db, organization_id=fee.organization_id, user_id=referrer.id, type_="CLUB_REFERRAL_CREDIT",
            entity_type="club_fee", entity_id=fee.id,
            title=f"{amount / 100:.2f} € di sconto nel tuo wallet",
            body="Una famiglia che hai invitato ha pagato la mensilità: usali quando paghi le tue quote.",
        )
        await db.commit()
    except Exception:
        logger.exception("Club referral credit failed for fee %s", fee.id)
        await db.rollback()


async def on_fee_unpaid(db: AsyncSession, *, fee: ClubFee, actor_user_id: uuid.UUID) -> None:
    """Il pagamento di una mensilità annullato: si ritira il credito che
    aveva dato. Se nel frattempo è già stato speso, resta speso (lo dice il
    log): non si va mai in negativo sul wallet di qualcun altro."""
    from app.domains.wallets import service as wallets_service
    from app.domains.wallets.models import WalletTransaction

    if fee.kind != "MONTHLY":
        return
    credits = (
        await db.execute(
            select(WalletTransaction).where(
                WalletTransaction.idempotency_key.like(f"{_credit_key_prefix(fee.id)}%"),
                WalletTransaction.type == "ADMIN_CREDIT",
            )
        )
    ).scalars().all()
    for credit in credits:
        try:
            await wallets_service.reverse_transaction(
                db, organization_id=credit.organization_id, transaction_id=credit.id, actor_user_id=actor_user_id,
                reason="Il pagamento della famiglia invitata è stato annullato",
                idempotency_key=f"club-referral-reversal:{credit.id}",
            )
        except wallets_service.InsufficientBalanceError:
            logger.warning("Referral credit %s already spent: not reversed", credit.id)
        except Exception:
            logger.exception("Referral credit %s reversal failed", credit.id)
            await db.rollback()
