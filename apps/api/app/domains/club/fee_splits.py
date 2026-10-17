"""Pagamento parziale e mese esente. Specifica: docs/club-portal.md,
"Pagamento parziale e mese esente".

**Pagamento parziale.** La famiglia porta 20 € di una mensilità da 35 €: la
quota si **divide** in due righe, come le rate (installment_no) ma decise
al momento. La quota originale resta PAID con l'importo davvero pagato (e
tutto ciò che è congelato: listino, sconti, taxa de falta, corso); il resto
nasce DUE con lo stesso tipo e la stessa scadenza, il periodo della quota
più `/rN` ("2026-10/r1") e `split_from_fee_id` che punta alla quota da cui
nasce, con il motivo (`split_reason`). Così ogni conto che già esiste torna
da solo: l'incasso è la parte pagata, nel mese in cui è entrata; il resto è
un debito come gli altri (quadro del mese, area della famiglia, scadute,
avvisi, debiti per anzianità) e si paga con una prova o in segreteria. La
parte pagata ha la sua ricevuta (staff_record_payment), come ogni
pagamento.

Annullare: «Annulla pagamento parziale» (o il rifiuto della ricevuta, o la
riapertura) rimette la quota da pagare e le **riassorbe** il resto, se è
ancora intero e da pagare (`merge_remainder`): la quota torna una riga sola,
con l'importo di prima.

**Mese esente** («Isenta este mês»). L'atleta quel mese non deve la
mensilità (assente, infortunato): la quota diventa WAIVED con
`waive_kind = EXEMPT` e il motivo. Fuori dall'emesso, dai debiti, dagli
incassi e dagli avvisi come un condono, ma non è un «mancato incasso» (la
contabilità lo conta a parte, `exempt_cents`). Se la mensilità di quel mese
non è ancora emessa (un mese futuro) la si emette qui, con le regole del
job, e si esenta subito: il vincolo UNIQUE impedisce al job di ricrearla.
Si annulla con un tocco: un mese futuro torna a non avere la quota (la
emetterà il job, con i prezzi di allora), uno già arrivato torna da pagare.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.club import kinds, seasons
from app.domains.club import service as club_service
from app.domains.club.models import ClubAthlete, ClubFee, ClubPaymentProof, ClubPaymentProofFee
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError

#: Il segno del resto nel periodo: "2026-10/r1", "2026/2/r1".
REMAINDER_MARK = "/r"
REMAINDER_SUFFIX = " · resto"


def base_period(period: str) -> str:
    """Il periodo della quota da cui nasce un resto ("2026-10/r2" → "2026-10")."""
    return period.split(REMAINDER_MARK, 1)[0]


def _clean_reason(reason: str | None, *, what: str) -> str:
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ClubValidationError(f"Scrivi {what}.")
    return reason[:500]


# --- Le parti di una mensilità --------------------------------------------------------------------


def group_state(parts: list[ClubFee], *, today: date) -> str:
    """Lo stato di una mensilità fatta di una o più parti (la quota e i suoi
    resti): PARTIAL se qualcosa è pagato e qualcosa no."""
    due = [p for p in parts if p.status == "DUE"]
    paid = [p for p in parts if p.status == "PAID"]
    if due:
        if paid:
            return "PARTIAL"
        return "OVERDUE" if min(p.due_date for p in due) < today else "DUE"
    if paid:
        return "PAID"
    root = next((p for p in parts if p.split_from_fee_id is None), parts[0])
    return "MONTH_EXEMPT" if root.waive_kind == "EXEMPT" else "WAIVED"


def group_numbers(parts: list[ClubFee]) -> dict:
    return {
        "paid_cents": sum(p.amount_cents for p in parts if p.status == "PAID"),
        "due_cents": sum(p.amount_cents for p in parts if p.status == "DUE"),
    }


def group_main(parts: list[ClubFee]) -> ClubFee:
    """La parte da mostrare (e da pagare): il primo resto da pagare, se c'è;
    altrimenti la quota originale."""
    due = sorted((p for p in parts if p.status == "DUE"), key=lambda p: (p.period, p.created_at))
    if due:
        return due[0]
    return next((p for p in parts if p.split_from_fee_id is None), parts[0])


def order_parts(parts: list[ClubFee]) -> list[ClubFee]:
    """La quota originale, poi i resti nell'ordine in cui sono nati."""
    return sorted(parts, key=lambda p: (p.split_from_fee_id is not None, p.period, p.created_at))


# --- Pagamento parziale ---------------------------------------------------------------------------


async def _next_remainder_period(db: AsyncSession, *, fee: ClubFee) -> str:
    root = base_period(fee.period)
    stmt = select(func.count()).where(
        ClubFee.club_id == fee.club_id, ClubFee.kind == fee.kind, ClubFee.period.like(f"{root}{REMAINDER_MARK}%"),
    )
    stmt = stmt.where(ClubFee.athlete_id == fee.athlete_id) if fee.athlete_id is not None else stmt.where(
        ClubFee.guardian_user_id == fee.guardian_user_id
    )
    return f"{root}{REMAINDER_MARK}{(await db.execute(stmt)).scalar_one() + 1}"


async def record_partial_payment(
    db: AsyncSession, *, scope: ClubScope, actor_user_id: uuid.UUID, fee_id: uuid.UUID, amount_cents: int,
    reason: str, method: str, note: str | None = None, cash_received_by_user_id: uuid.UUID | None = None,
    cash_received_by_name: str | None = None, file_bytes: bytes | None = None, content_type: str | None = None,
    original_filename: str | None = None,
) -> tuple[ClubPaymentProof, ClubFee]:
    """La segreteria incassa una parte di una quota: la ricevuta della parte
    pagata e il resto, che resta da pagare. Restituisce (ricevuta, resto)."""
    reason = _clean_reason(reason, what="perché non è stata pagata tutta (es. «Paga il resto a fine mese»)")
    # Prima i controlli di staff_record_payment, così un errore non lascia
    # niente a metà da annullare.
    if method not in ("BANK_TRANSFER", "MBWAY", "CASH", "CARD"):
        raise ClubValidationError("Scegli come è stata pagata: bonifico, MB Way, contanti o carta.")
    if method == "CASH":
        await club_service._cash_receiver(db, scope=scope, user_id=cash_received_by_user_id, name=cash_received_by_name)
    fee = (
        await db.execute(select(ClubFee).where(ClubFee.id == fee_id, ClubFee.club_id == scope.club_id).with_for_update())
    ).scalar_one_or_none()
    if fee is None:
        raise ClubNotFoundError("Quota non trovata.")
    if fee.status != "DUE":
        raise ClubValidationError("Questa quota non è da pagare: aggiorna la pagina.")
    if not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ClubValidationError("Scrivi quanto è stato pagato.")
    if amount_cents >= fee.amount_cents:
        raise ClubValidationError("Per l'importo intero usa «Segna pagato»: il parziale è meno del totale.")
    rest = fee.amount_cents - amount_cents
    remainder = ClubFee(
        organization_id=fee.organization_id, club_id=fee.club_id, athlete_id=fee.athlete_id,
        guardian_user_id=fee.guardian_user_id, kind=fee.kind,
        period=await _next_remainder_period(db, fee=fee),
        installment_no=fee.installment_no, installments_total=fee.installments_total,
        description=(fee.description.removesuffix(REMAINDER_SUFFIX)[: 200 - len(REMAINDER_SUFFIX)] + REMAINDER_SUFFIX),
        # Il resto è solo denaro da incassare: listino, sconti e taxa de
        # falta restano sulla quota originale, che li ha congelati.
        amount_cents=rest, gross_amount_cents=None, discount_cents=0, due_date=fee.due_date, status="DUE",
        competition_id=fee.competition_id, course_id=fee.course_id, coach_user_id=fee.coach_user_id,
        coach_share_pct=fee.coach_share_pct, split_from_fee_id=fee.id, split_reason=reason,
    )
    db.add(remainder)
    fee.amount_cents = amount_cents
    await db.flush()
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.fee_partial_payment", entity_type="club_fee", entity_id=str(fee.id), reason=reason,
        new_value={"paid_cents": amount_cents, "remainder_cents": rest, "remainder_fee_id": str(remainder.id),
                   "method": method},
    )
    try:
        # La ricevuta della parte pagata: la stessa strada di «Segna pagato»,
        # che committa tutto insieme (quota pagata, resto, ricevuta).
        proof = await club_service.staff_record_payment(
            db, scope=scope, actor_user_id=actor_user_id, fee_ids=[fee.id], method=method,
            file_bytes=file_bytes, content_type=content_type, original_filename=original_filename,
            note=note or f"Pagamento parziale: {reason}", cash_received_by_user_id=cash_received_by_user_id,
            cash_received_by_name=cash_received_by_name,
        )
    except club_service.ClubError:
        await db.rollback()
        raise
    await db.refresh(remainder)
    return proof, remainder


async def merge_remainder(db: AsyncSession, *, fee: ClubFee) -> bool:
    """Una quota tornata da pagare riassorbe il suo resto, se il resto è
    ancora intero: da pagare, senza resti suoi e senza prove collegate (anche
    rifiutate: la loro storia resta). Non committa. True se l'ha fatto."""
    if fee.status != "DUE":
        return False
    child = (
        await db.execute(select(ClubFee).where(ClubFee.split_from_fee_id == fee.id).with_for_update())
    ).scalars().all()
    if len(child) != 1 or child[0].status != "DUE":
        return False
    rest = child[0]
    grandchild = (await db.execute(select(ClubFee.id).where(ClubFee.split_from_fee_id == rest.id).limit(1))).first()
    linked = (
        await db.execute(select(ClubPaymentProofFee.id).where(ClubPaymentProofFee.fee_id == rest.id).limit(1))
    ).first()
    if grandchild is not None or linked is not None:
        return False
    fee.amount_cents += rest.amount_cents
    await db.delete(rest)
    await db.flush()
    return True


async def undo_partial_payment(
    db: AsyncSession, *, scope: ClubScope, fee_id: uuid.UUID, actor_user_id: uuid.UUID,
) -> ClubFee:
    """«Annulla pagamento parziale»: la ricevuta della parte pagata si
    annulla (senza avvisare la famiglia come per un rifiuto: è la segreteria
    che corregge se stessa), la quota torna da pagare e riassorbe il resto."""
    from app.domains.club import referrals

    fee = await club_service._get_fee(db, scope=scope, fee_id=fee_id)
    rest = (
        await db.execute(select(ClubFee).where(ClubFee.split_from_fee_id == fee.id))
    ).scalars().all()
    if fee.status != "PAID" or len(rest) != 1:
        raise ClubValidationError("Questa quota non ha un pagamento parziale da annullare.")
    if rest[0].status != "DUE":
        raise ClubValidationError("Il resto è già stato pagato o condonato: annulla prima quello.")
    proof = await db.get(ClubPaymentProof, fee.paid_via_proof_id) if fee.paid_via_proof_id else None
    if proof is not None:
        others = (
            await db.execute(
                select(func.count()).where(ClubPaymentProofFee.proof_id == proof.id, ClubPaymentProofFee.fee_id != fee.id)
            )
        ).scalar_one()
        if others or proof.credit_cents:
            raise ClubValidationError("La ricevuta copre anche altre quote: rifiutala da «Comprovativos».")
        proof.status = "REJECTED"
        proof.reviewed_by_user_id = actor_user_id
        proof.reviewed_at = utcnow()
        proof.rejection_reason = "Pagamento parziale annullato dalla segreteria"
    fee.status = "DUE"
    club_service._clear_payment(fee)
    if not await merge_remainder(db, fee=fee):
        raise ClubValidationError(
            "Il resto ha già una prova di pagamento collegata: condonalo o incassalo invece di annullare."
        )
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.fee_partial_payment_undone", entity_type="club_fee", entity_id=str(fee.id),
        new_value={"amount_cents": fee.amount_cents, "proof_id": str(proof.id) if proof else None},
    )
    await db.commit()
    await db.refresh(fee)
    await referrals.on_fee_unpaid(db, fee=fee, actor_user_id=actor_user_id)
    return fee


# --- Mese esente ----------------------------------------------------------------------------------


async def _issue_monthly(db: AsyncSession, *, athlete: ClubAthlete, year: int, month: int) -> None:
    """La mensilità di quel mese con le regole del job del 1°
    (service.generate_monthly_fees), senza toccare il piano dell'atleta."""
    scope = ClubScope(organization_id=athlete.organization_id, club_id=athlete.club_id)
    plans = {p.id: p for p in await club_service.list_plans(db, scope=scope)}
    plan = plans.get(athlete.plan_id) if athlete.plan_id else None
    if not athlete.plan_locked:
        plan = club_service.pick_plan(
            [p for p in plans.values() if p.active], age=seasons.federal_age(athlete.birth_date, year)
        ) or plan
    if plan is None:
        return
    sizes = await club_service.family_sizes(db, club_id=athlete.club_id)
    course = None
    if (await kinds.club_rules(db, club_id=athlete.club_id)).coach_paid_by_share:
        course = (await club_service.primary_courses(db, athlete_ids=[athlete.id])).get(athlete.id)
    await club_service.ensure_monthly_fee(
        db, athlete=athlete, plan=plan, year=year, month=month,
        pricing=await club_service.club_pricing(db, club_id=athlete.club_id),
        family_size=sizes.get(athlete.guardian_user_id, 1), course=course,
    )


async def _monthly_parts(db: AsyncSession, *, athlete_id: uuid.UUID, period: str) -> list[ClubFee]:
    return list(
        (
            await db.execute(
                select(ClubFee).where(
                    ClubFee.athlete_id == athlete_id, ClubFee.kind == "MONTHLY",
                    (ClubFee.period == period) | ClubFee.period.like(f"{period}{REMAINDER_MARK}%"),
                ).with_for_update()
            )
        ).scalars()
    )


async def exempt_month(
    db: AsyncSession, *, scope: ClubScope, athlete_id: uuid.UUID, period: str, reason: str,
    actor_user_id: uuid.UUID,
) -> ClubFee:
    """«Isenta este mês»: la mensilità di quel mese non si paga."""
    reason = _clean_reason(reason, what="perché questo mese non paga (es. «Assente tutto il mese»)")
    try:
        year, month = seasons.parse_period(period)
    except ValueError as exc:
        raise ClubValidationError("Il mese deve essere nel formato AAAA-MM.") from exc
    period = f"{year:04d}-{month:02d}"
    athlete = await club_service.get_athlete(db, scope=scope, athlete_id=athlete_id)
    parts = await _monthly_parts(db, athlete_id=athlete.id, period=period)
    if not parts:
        await _issue_monthly(db, athlete=athlete, year=year, month=month)
        parts = await _monthly_parts(db, athlete_id=athlete.id, period=period)
    if not parts:
        raise ClubValidationError(
            f"{athlete.first_name} non ha una mensilità in {seasons.month_label(year, month)}: non c'è niente da esentare."
        )
    if len(parts) > 1:
        raise ClubValidationError("Questa mensilità è stata pagata in parte: annulla prima il pagamento parziale.")
    fee = parts[0]
    if fee.status == "PAID":
        raise ClubValidationError("Questa mensilità è già pagata: annulla prima il pagamento.")
    if fee.status == "WAIVED":
        raise ClubValidationError("Questa mensilità è già esente o condonata.")
    fee.status = "WAIVED"
    fee.waive_kind = "EXEMPT"
    fee.waived_by_user_id = actor_user_id
    fee.waived_at = utcnow()
    fee.waive_reason = reason
    await audit_service.record(
        db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
        action="club.fee_month_exempt", entity_type="club_fee", entity_id=str(fee.id), reason=reason,
        new_value={"athlete_id": str(athlete.id), "period": period, "amount_cents": fee.amount_cents},
    )
    await db.commit()
    await db.refresh(fee)
    return fee


async def undo_exempt_month(
    db: AsyncSession, *, scope: ClubScope, fee_id: uuid.UUID, actor_user_id: uuid.UUID, today: date,
) -> ClubFee | None:
    """Annulla «Isenta este mês». Un mese non ancora arrivato torna senza
    quota (None): la emetterà il job, con i prezzi e il gruppo di allora."""
    fee = await club_service._get_fee(db, scope=scope, fee_id=fee_id)
    if fee.status != "WAIVED" or fee.waive_kind != "EXEMPT":
        raise ClubValidationError("Questa mensilità non è esente.")
    linked = (await db.execute(select(ClubPaymentProofFee.id).where(ClubPaymentProofFee.fee_id == fee.id).limit(1))).first()
    if fee.kind == "MONTHLY" and fee.period > seasons.period_of(today) and linked is None:
        await audit_service.record(
            db, organization_id=scope.organization_id, actor_user_id=actor_user_id,
            action="club.fee_month_exempt_undone", entity_type="club_fee", entity_id=str(fee.id),
            new_value={"deleted": True, "period": fee.period},
        )
        await db.delete(fee)
        await db.commit()
        return None
    return await club_service.reopen_fee(db, scope=scope, fee_id=fee.id, actor_user_id=actor_user_id)
