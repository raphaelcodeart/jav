"""L'aiuto del club a un atleta: i costi che il club paga per lui
(trasporto, materiale, gara, esame, stage). Specifica: docs/club-portal.md,
"L'aiuto del club".

Ogni costo è una riga di `club_athlete_supports` e, nel wallet della
famiglia, due movimenti legati all'atleta: la ricarica del club e subito
l'addebito del costo. Il saldo resta com'era, ma la famiglia (e l'atleta)
vede quando e quanto il club l'ha aiutata. La scheda dell'atleta mostra il
totale, insieme al saldo del wallet e agli investimenti del club.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.club.models import ClubAthlete
from app.domains.club.operations_models import SUPPORT_CATEGORIES, ClubAthleteSupport
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

SOURCE = "CLUB_SUPPORT"
LABELS_PT = {"TRANSPORT": "Transporte", "MATERIAL": "Material", "COMPETITION": "Inscrição em prova",
             "EXAM": "Exame de graduação", "TRAINING_CAMP": "Estágio", "OTHER": "Outro"}


def support_dict(s: ClubAthleteSupport) -> dict:
    return {"id": s.id, "category": s.category, "amount_cents": s.amount_cents, "note": s.note,
            "paid_on": s.paid_on, "created_at": s.created_at}


async def record(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, category: str, amount_cents: int,
    note: str | None, paid_on: date, actor_user_id: uuid.UUID,
) -> ClubAthleteSupport:
    from app.domains.wallets import service as wallets_service

    athlete = await db.get(ClubAthlete, athlete_id)
    if athlete is None or athlete.club_id != scope.club_id:
        raise ClubNotFoundError("Atleta non trovato.")
    if category not in SUPPORT_CATEGORIES:
        raise ClubValidationError("Scegli che cosa ha pagato il club.")
    if amount_cents <= 0 or amount_cents > 1_000_000:
        raise ClubValidationError("L'importo deve essere maggiore di zero.")
    note = (note or "").strip()[:300] or None
    row = ClubAthleteSupport(**scope.columns(), athlete_id=athlete.id, category=category, amount_cents=amount_cents,
                             note=note, paid_on=paid_on, recorded_by_user_id=actor_user_id)
    db.add(row)
    await db.flush()
    label = f"{LABELS_PT[category]}{': ' + note if note else ''}"
    wallet = await wallets_service.get_or_create_wallet(db, organization_id=scope.organization_id, user_id=athlete.guardian_user_id)
    # La ricarica del club e subito l'addebito del costo: il saldo non cambia,
    # lo storico racconta l'aiuto.
    await wallets_service.credit_wallet(
        db, organization_id=scope.organization_id, wallet_id=wallet.id, amount_cents=amount_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, reference_club_athlete_id=athlete.id, source=SOURCE,
        note=f"O clube pagou por {athlete.first_name} — {label}"[:500], idempotency_key=f"club-support:{row.id}:credit",
    )
    await wallets_service._debit_for_reference(
        db, organization_id=scope.organization_id, wallet_id=wallet.id, amount_cents=amount_cents,
        actor_user_id=actor_user_id, note=f"{label} — {athlete.first_name}"[:500],
        idempotency_key=f"club-support:{row.id}:debit", reference={"reference_club_athlete_id": athlete.id},
        notification_title=f"O clube pagou {amount_cents / 100:.2f} € por {athlete.first_name}",
    )
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id, action="club.athlete_support",
        entity_type="club_athlete", entity_id=str(athlete.id),
        new_value={"category": category, "amount_cents": amount_cents, "note": note},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def list_for(db: AsyncSession, *, athlete_id: uuid.UUID) -> list[ClubAthleteSupport]:
    return list((await db.execute(
        select(ClubAthleteSupport).where(ClubAthleteSupport.athlete_id == athlete_id)
        .order_by(ClubAthleteSupport.paid_on.desc(), ClubAthleteSupport.created_at.desc())
    )).scalars())


async def money(db: AsyncSession, *, athlete: ClubAthlete) -> dict:
    """Il riquadro «soldi» della scheda: il saldo del wallet della famiglia,
    quanto il club ha pagato per l'atleta (per voce) e quanto ha investito."""
    from app.domains.club.people import INVESTMENT_SOURCE
    from app.domains.wallets import service as wallets_service
    from app.domains.wallets.models import WalletTransaction

    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=athlete.organization_id, user_id=athlete.guardian_user_id)
    rows = await list_for(db, athlete_id=athlete.id)
    by_category: dict[str, int] = {}
    for r in rows:
        by_category[r.category] = by_category.get(r.category, 0) + r.amount_cents
    invested = (await db.execute(
        select(func.coalesce(func.sum(WalletTransaction.amount_cents), 0)).where(
            WalletTransaction.reference_club_athlete_id == athlete.id, WalletTransaction.source == INVESTMENT_SOURCE,
        )
    )).scalar_one()
    return {
        "wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "support_total_cents": sum(r.amount_cents for r in rows),
        "support_by_category": by_category,
        "invested_cents": int(invested or 0),
        "supports": [support_dict(r) for r in rows[:20]],
    }
