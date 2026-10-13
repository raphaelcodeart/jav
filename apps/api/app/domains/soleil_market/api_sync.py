"""«Market 7» collegato all'API affiliati di SoleilDrop (13/10/2026).

Quattro cose, tutte attive solo se nelle impostazioni c'è la chiave API;
senza chiave il negozio resta quello di prima (Excel a mano, ordini inseriti
nel portale):

1. **Catalogo** -- `GET /catalog?all=1` ogni 3 ore, trasformato nelle stesse
   righe dell'Excel (`feed._apply`): prezzi, JavCash dal guadagno, prodotti
   nuovi spenti, referenze sparite non più comprabili. Una sola fonte di
   regole per i due ingressi.
2. **Invio ordini** -- `POST /orders` con `external_ref` = «JAV-<numero>».
   SoleilDrop non crea mai due ordini con lo stesso riferimento (risponde
   `duplicate`), quindi rimandare dopo un timeout è sicuro: è l'opposto di
   AliExpress, dove una risposta persa la deve guardare una persona.
   Pagamento dal wallet prepagato: con credito insufficiente l'ordine resta
   in attesa da loro (202) e parte da solo alla ricarica.
3. **Stato e tracking** -- dai webhook firmati e, come riserva, da
   `GET /orders?since=` ogni 30 minuti. Spedito/consegnato avvisano il
   cliente una volta sola, come quando lo segna l'amministratore.
4. **Prova del collegamento** -- `GET /me` e `GET /wallet`.

**Nessun prezzo nostro a SoleilDrop.** L'API accetta facoltativi
`sell_price`/`total_paid`; non li mandiamo, come l'email ai marchi non li
mandava: quanto paga il cliente è un fatto nostro.
"""

import hashlib
import hmac
import logging
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.notifications import service as notifications_service
from app.domains.soleil_market import client, feed, service
from app.domains.soleil_market.models import (
    SoleilMarketOrder,
    SoleilMarketProduct,
    SoleilMarketSettings,
    SoleilMarketWebhookEvent,
)

logger = logging.getLogger(__name__)

#: Gli stati di `fulfillment_status` che dicono «è da SoleilDrop». NOT_SENT e
#: SENT sono quelli di prima (SENT = inoltrato, a mano o via API).
WAITING_WALLET = "WAITING_WALLET"   # 202: aspetta la ricarica del wallet
WAITING_SOLEIL = "WAITING_SOLEIL"   # fermo da loro (contratto, dati da rivedere)
RETRY = "RETRY"                     # errore temporaneo: lo riprova il job
ERROR = "ERROR"                     # lo deve guardare una persona
SUPPLIER_CANCELLED = "CANCELLED"
#: Stati in cui un ordine non si rimanda più.
FINAL = ("SHIPPED", "DELIVERED", SUPPLIER_CANCELLED)
#: Stati SoleilDrop di un ordine fermo da loro.
PENDING_CODES = ("waiting_wallet", "contract_not_accepted", "needs_review")
WEBHOOK_EVENTS = ("order.status_changed", "order.shipped", "test.ping")


def connected(settings: SoleilMarketSettings) -> bool:
    return bool(settings.api_key)


def _cents(value: object) -> int | None:
    """Un importo dell'API (euro, 2 decimali) in centesimi."""
    if value is None or value == "":
        return None
    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal(1)))
    except (InvalidOperation, ValueError):
        return None


# --- Prova del collegamento ------------------------------------------------------------------------


async def check_connection(db: AsyncSession, *, settings: SoleilMarketSettings) -> dict:
    """GET /me e GET /wallet: dice a quale negozio SoleilDrop appartiene la
    chiave e quanto credito c'è. L'esito resta sulle impostazioni."""
    try:
        who = await client.me(settings.api_key)
        money = await client.wallet(settings.api_key)
    except client.SoleilApiError as exc:
        settings.last_api_check_at = utcnow()
        settings.last_api_error = str(exc)[:500]
        await db.commit()
        raise service.SoleilMarketValidationError(str(exc)) from exc
    eshop = who.get("eshop") or {}
    settings.eshop_name = (str(eshop.get("name") or eshop.get("code") or "") or None)
    if settings.eshop_name:
        settings.eshop_name = settings.eshop_name[:160]
    settings.wallet_balance_cents = _cents(money.get("balance"))
    settings.last_api_check_at = utcnow()
    settings.last_api_error = None
    await db.commit()
    return {
        "eshop_name": settings.eshop_name, "eshop_code": eshop.get("code"),
        "wallet_balance_cents": settings.wallet_balance_cents,
    }


# --- Catalogo ---------------------------------------------------------------------------------------


def _row(item: dict) -> tuple[str, dict] | None:
    """Una referenza dell'API nella forma di una riga dell'Excel
    (`feed._row`), così `_apply` non sa da dove arriva.

    La chiave è il **codice** SoleilDrop, come nell'Excel (colonna «Codice»):
    i due ingressi aggiornano gli stessi prodotti, e l'ordine si manda con
    quel codice. Il prezzo di vendita dell'API è senza IVA: lo portiamo IVA
    inclusa con l'aliquota della referenza, come la colonna «Prezzo vendita
    (ivato)». Si vende solo al pezzo: una referenza che non si può ordinare
    a pezzi resta non comprabile."""
    key = str(item.get("code") or item.get("id") or "").strip()[:64]
    if not key:
        return None
    cost = _cents(item.get("cost_price"))
    vat_rate = item.get("vat_rate")
    try:
        vat = Decimal(str(vat_rate)) if vat_rate is not None else Decimal(22)
    except InvalidOperation:
        vat = Decimal(22)
    net = _cents(item.get("sell_price"))
    gross = int((Decimal(net) * (100 + vat) / 100).quantize(Decimal(1))) if net else None
    units = item.get("units") or {}
    by_piece = units.get("piece", True) is not False
    path = [p.strip() for p in str(item.get("category") or "").split(">") if p.strip()]
    texts = (item.get("texts") or {}).get("it") or {}
    return key, {
        "product_id": key,
        "variant_id": key,
        "brand": str(item.get("brand") or "").strip(),
        "product_name": str(item.get("name") or "").strip(),
        "description": str(texts.get("description") or texts.get("description_short") or "").strip(),
        "sku": key,
        "barcode": str(item.get("ean") or "").strip(),
        "wholesale_price": f"{cost / 100:.2f}" if cost else "",
        "rrp": f"{gross / 100:.2f}" if gross else "",
        "suggested_cents": gross or feed._fallback_price(cost),
        "available": bool(item.get("available")) and by_piece,
        "category": path[0] if path else "",
        "subcategory": path[-1] if len(path) > 1 else "",
        "presentation": "",
        "images": [str(u).strip() for u in (item.get("images") or []) if str(u).strip().startswith("https://")],
    }


async def import_catalog(db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None = None) -> dict:
    """Il catalogo dall'API, applicato con le regole dell'Excel. Errori e
    riepilogo restano sulle impostazioni, che il pannello mostra."""
    settings = await service.get_settings_row(db, organization_id=organization_id)
    try:
        body = await client.catalog(settings.api_key)
        groups: dict[str, list[dict]] = {}
        for item in body.get("items") or []:
            parsed = _row(item) if isinstance(item, dict) else None
            if parsed and parsed[0] not in groups:
                groups[parsed[0]] = [parsed[1]]
        listed = len(body.get("all_ids") or [])
        # Se l'API elenca più referenze di quante ne ha mandate (una risposta
        # a pagine, non documentata), non si spegne niente: chi manca
        # potrebbe esserci ancora.
        complete = listed <= len(body.get("items") or [])
        if not groups:
            summary = {
                "products_in_feed": 0, "created": 0, "updated": 0, "skipped": 0, "gone": 0, "truncated": False,
                "text": "Il catalogo SoleilDrop non ha ancora referenze assegnate al negozio.",
            }
        else:
            summary = await feed._apply(
                db, settings=settings, groups=groups,
                actor_user_id=actor_user_id or await feed._system_actor(db, organization_id),
                allow_gone=complete, source="catalogo API SoleilDrop",
            )
    except (client.SoleilApiError, feed.SoleilFeedError) as exc:
        await db.rollback()
        settings = await service.get_settings_row(db, organization_id=organization_id)
        settings.last_import_at = utcnow()
        settings.last_import_error = str(exc)[:500]
        await db.commit()
        raise feed.SoleilFeedError(str(exc)) from exc
    settings = await service.get_settings_row(db, organization_id=organization_id)
    settings.last_import_at = utcnow()
    settings.last_import_error = None
    settings.last_import_summary = summary["text"][:500]
    await db.commit()
    return summary


# --- Invio ordini ------------------------------------------------------------------------------------


async def _payload(db: AsyncSession, order: SoleilMarketOrder) -> dict:
    items = []
    for item in await service.order_items(db, order):
        code = item.supplier_sku
        if not code:
            product = await db.get(SoleilMarketProduct, item.product_id)
            code = product.soleil_product_id if product else None
        if not code:
            raise service.SoleilMarketValidationError(
                f"«{item.product_name}» non ha un codice SoleilDrop: non si può inviare via API."
            )
        items.append({"code": code, "qty": item.quantity, "unit": "piece"})
    address = order.address_line1 + (f", {order.address_line2}" if order.address_line2 else "")
    payload = {
        "external_ref": service.order_number(order),
        "recipient": {
            "name": order.recipient_name, "address": address, "zip": order.postal_code, "city": order.city,
            "province": order.province, "country": order.country_code or "IT",
            "phone": order.recipient_phone or "",
        },
        "items": items,
    }
    if order.note:
        payload["notes"] = order.note[:500]
    return payload


async def _alert(db: AsyncSession, order: SoleilMarketOrder, *, title: str, body: str) -> None:
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="SOLEIL_MARKET_ORDER_FORWARD_ISSUE", entity_type="soleil_market_order", entity_id=order.id,
        title=title[:255], body=body[:1000],
    )


async def forward_via_api(
    db: AsyncSession, *, settings: SoleilMarketSettings, order: SoleilMarketOrder, actor_user_id: uuid.UUID | None,
) -> SoleilMarketOrder:
    """Manda l'ordine pagato a SoleilDrop. Si può chiamare quante volte si
    vuole (pulsante, automatismo, job di riprova): lo stesso external_ref non
    crea mai un secondo ordine né un secondo addebito."""
    if order.status != "PAID":
        raise service.SoleilMarketValidationError("Si invia a SoleilDrop solo un ordine già pagato dal cliente.")
    if order.fulfillment_status in FINAL:
        raise service.SoleilMarketValidationError("L'ordine è già spedito o chiuso su SoleilDrop.")
    payload = await _payload(db, order)
    code = service.order_code(order)
    try:
        http_status, body = await client.create_order(settings.api_key, payload)
    except client.SoleilApiError as exc:
        order.forward_error = str(exc)[:500]
        if exc.code == "contract_not_accepted":
            order.fulfillment_status = WAITING_SOLEIL
            await _alert(
                db, order, title=f"Ordine #{code}: accetta il contratto SoleilDrop",
                body="SoleilDrop tiene l'ordine in attesa finché non accetti il nuovo Contratto di affiliazione "
                     "nella tua area SoleilDrop. Dopo, l'ordine riparte da solo.",
            )
        elif exc.retryable:
            order.fulfillment_status = RETRY
        else:
            order.fulfillment_status = ERROR
            await _alert(db, order, title=f"Ordine #{code}: SoleilDrop non l'ha accettato", body=str(exc))
        await audit_service.record(
            db, organization_id=order.organization_id, actor_user_id=actor_user_id,
            action="soleil_market.order_forward_failed", entity_type="soleil_market_order", entity_id=str(order.id),
            new_value={"http": exc.status, "code": exc.code, "error": str(exc)[:300]},
        )
        await db.commit()
        await db.refresh(order)
        raise service.SoleilMarketValidationError(str(exc)) from exc

    remote = body.get("order") or {}
    charged = _cents((body.get("wallet") or {}).get("charged"))
    if charged is not None:
        order.soleil_wallet_charged_cents = charged
    if (body.get("wallet") or {}).get("balance_after") is not None:
        settings.wallet_balance_cents = _cents(body["wallet"]["balance_after"])
    order.forwarded_at = order.forwarded_at or utcnow()
    order.forwarded_by_user_id = actor_user_id
    order.forward_error = None
    if http_status == 202 or body.get("status") == "waiting_wallet":
        order.fulfillment_status = WAITING_WALLET
        order.forward_error = (body.get("message") or "In attesa di credito sul wallet SoleilDrop.")[:500]
        await _alert(
            db, order, title=f"Ordine #{code}: ricarica il wallet SoleilDrop",
            body=order.forward_error + " L'ordine parte da solo appena ricarichi (Contabilità → Wallet).",
        )
    else:
        order.fulfillment_status = "SENT"
    changes = _apply_remote(order, remote)
    await audit_service.record(
        db, organization_id=order.organization_id, actor_user_id=actor_user_id,
        action="soleil_market.order_forwarded", entity_type="soleil_market_order", entity_id=str(order.id),
        new_value={
            "via": "api", "http": http_status, "duplicate": bool(body.get("duplicate")),
            "soleil_order_number": order.soleil_order_number, "wallet_charged_cents": charged,
        },
    )
    await db.commit()
    await db.refresh(order)
    await _notify(db, order, changes)
    return order


# --- Stato e tracking --------------------------------------------------------------------------------


def _apply_remote(order: SoleilMarketOrder, remote: dict) -> set[str]:
    """Copia sull'ordine quello che SoleilDrop dice di lui. Restituisce i
    passaggi nuovi («shipped», «delivered», «cancelled») perché chi chiama
    avvisi il cliente o lo staff **dopo** il commit, una volta sola. Non fa
    commit. Non tocca il pagamento del cliente: un ordine annullato da
    SoleilDrop va rimborsato da una persona, non da qui."""
    changes: set[str] = set()
    if not remote:
        return changes
    number = remote.get("number")
    if number:
        order.soleil_order_number = str(number)[:64]
    state = remote.get("status") or {}
    if isinstance(state, dict):
        if state.get("code"):
            order.soleil_status_code = str(state["code"])[:64]
        if state.get("label"):
            order.soleil_status_label = str(state["label"])[:128]
    elif state:
        order.soleil_status_code = str(state)[:64]
    totals = remote.get("totals") or {}
    if totals.get("wallet_charged") is not None:
        order.soleil_wallet_charged_cents = _cents(totals["wallet_charged"])
    tracking = remote.get("tracking") or {}
    carrier = remote.get("carrier") or {}
    if tracking.get("number"):
        order.tracking_number = str(tracking["number"])[:128]
    if carrier.get("name"):
        order.tracking_company = str(carrier["name"])[:128]
    order.soleil_synced_at = utcnow()

    flags = state if isinstance(state, dict) else {}
    if order.status != "PAID" or order.fulfillment_status == SUPPLIER_CANCELLED:
        return changes
    if flags.get("cancelled"):
        order.fulfillment_status = SUPPLIER_CANCELLED
        changes.add("cancelled")
        return changes
    # Un ordine che aspettava (credito, contratto) e ora ha un numero è partito.
    if number and order.fulfillment_status in (WAITING_WALLET, WAITING_SOLEIL, RETRY, ERROR, "NOT_SENT"):
        if order.soleil_status_code not in PENDING_CODES:
            order.fulfillment_status = "SENT"
            order.forward_error = None
    if (flags.get("delivered") or tracking.get("delivered_at")) and not order.delivered_at:
        if not order.shipped_at:
            order.shipped_at = utcnow()
        order.fulfillment_status = "DELIVERED"
        order.delivered_at = utcnow()
        changes.add("delivered")
    elif (flags.get("shipped") or tracking.get("shipped_at")) and not order.shipped_at:
        order.fulfillment_status = "SHIPPED"
        order.shipped_at = utcnow()
        changes.add("shipped")
    return changes


async def _notify(db: AsyncSession, order: SoleilMarketOrder, changes: set[str]) -> None:
    """Dopo il commit delle modifiche: email al cliente e campanella. Le
    notifiche in-app non si salvano da sole (notify_user non fa commit),
    per questo il commit in fondo."""
    if not changes:
        return
    if "shipped" in changes:
        await service._notify_customer_shipping(db, order=order, delivered=False)
    if "delivered" in changes:
        await service._notify_customer_shipping(db, order=order, delivered=True)
    if "cancelled" in changes:
        await _alert(
            db, order, title=f"Ordine #{service.order_code(order)} annullato da SoleilDrop",
            body=(order.soleil_status_label or "Annullato")
            + ". Il cliente ha già pagato: va contattato e rimborsato a mano.",
        )
    await db.commit()


async def _find_order(db: AsyncSession, organization_id: uuid.UUID, remote: dict) -> SoleilMarketOrder | None:
    ref = str(remote.get("external_ref") or "")
    if ref.startswith("JAV-") and ref[5:].isdigit():
        found = await db.execute(
            select(SoleilMarketOrder).where(
                SoleilMarketOrder.organization_id == organization_id, SoleilMarketOrder.number == int(ref[5:])
            )
        )
        order = found.scalar_one_or_none()
        if order is not None:
            return order
    number = remote.get("number")
    if number:
        found = await db.execute(
            select(SoleilMarketOrder).where(
                SoleilMarketOrder.organization_id == organization_id,
                SoleilMarketOrder.soleil_order_number == str(number),
            )
        )
        return found.scalar_one_or_none()
    return None


async def sync_orders(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """La riserva dei webhook: gli ordini cambiati da poco. Ogni 30 minuti,
    con un margine di sovrapposizione: rileggere un ordine non costa niente,
    perderne uno sì."""
    settings = await service.get_settings_row(db, organization_id=organization_id)
    if not connected(settings):
        return 0
    since_at = (settings.last_order_sync_at or utcnow() - timedelta(days=7)) - timedelta(minutes=30)
    started = utcnow()
    body = await client.list_orders(settings.api_key, since=since_at.strftime("%Y-%m-%dT%H:%M:%SZ"))
    touched = 0
    # Da verificare dal vivo: la documentazione non dice il nome della lista
    # nella risposta di GET /orders; «orders» è il più probabile.
    for remote in body.get("orders") or body.get("items") or []:
        if not isinstance(remote, dict):
            continue
        order = await _find_order(db, organization_id, remote)
        if order is None:
            continue
        changes = _apply_remote(order, remote)
        await db.commit()
        await db.refresh(order)
        await _notify(db, order, changes)
        touched += 1
    settings = await service.get_settings_row(db, organization_id=organization_id)
    settings.last_order_sync_at = started
    await db.commit()
    return touched


async def retry_orders(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """Gli ordini pagati che devono ancora partire: errori temporanei sempre;
    quelli mai inviati solo con l'invio automatico acceso (altrimenti li
    manda l'amministratore). Quelli in attesa di credito o contratto no:
    li fa ripartire SoleilDrop da sé."""
    settings = await service.get_settings_row(db, organization_id=organization_id)
    if not connected(settings):
        return 0
    states = [RETRY] + (["NOT_SENT"] if settings.auto_forward else [])
    found = await db.execute(
        select(SoleilMarketOrder).where(
            SoleilMarketOrder.organization_id == organization_id,
            SoleilMarketOrder.status == "PAID",
            SoleilMarketOrder.fulfillment_status.in_(states),
            SoleilMarketOrder.paid_at < utcnow() - timedelta(minutes=5),
        ).limit(50)
    )
    sent = 0
    for order in found.scalars().all():
        try:
            await forward_via_api(db, settings=settings, order=order, actor_user_id=None)
            sent += 1
        except service.SoleilMarketError:
            logger.warning("SoleilDrop: nuovo invio dell'ordine %s non riuscito", order.id)
    return sent


# --- Webhook -----------------------------------------------------------------------------------------


class WebhookRejected(Exception):
    pass


def signature_ok(secret: str, raw_body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (header or "").strip())


async def handle_webhook(
    db: AsyncSession, *, organization_id: uuid.UUID, raw_body: bytes, headers: dict[str, str],
) -> str:
    """Un avviso di SoleilDrop. Firma verificata sui byte esatti ricevuti,
    doppioni scartati con `X-Soleil-Delivery`. Il lavoro è poco (aggiornare
    una riga, al più un'email) e sta nei 10 secondi che SoleilDrop concede."""
    import json

    found = await db.execute(
        select(SoleilMarketSettings).where(SoleilMarketSettings.organization_id == organization_id)
    )
    settings = found.scalar_one_or_none()
    if settings is None or not settings.webhook_secret:
        raise WebhookRejected("Webhook SoleilDrop non configurato.")
    if not signature_ok(settings.webhook_secret, raw_body, headers.get("x-soleil-signature", "")):
        raise WebhookRejected("Firma del webhook non valida.")
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise WebhookRejected("Corpo del webhook non leggibile.") from exc
    if not isinstance(event, dict):
        raise WebhookRejected("Corpo del webhook non leggibile.")

    name = str(headers.get("x-soleil-event") or event.get("event") or "")[:64]
    delivery = str(headers.get("x-soleil-delivery") or event.get("delivery_id") or "")[:128]
    remote = event.get("order") if isinstance(event.get("order"), dict) else {}
    settings.last_webhook_at = utcnow()
    if name == "test.ping" or not remote:
        await db.commit()
        return "ok"
    if not delivery:
        raise WebhookRejected("Manca X-Soleil-Delivery.")

    order = await _find_order(db, organization_id, remote)
    changes = _apply_remote(order, remote) if order is not None else set()
    # La riga della consegna nella stessa transazione delle modifiche: o
    # passano insieme, o la riprova di SoleilDrop le rifarà insieme.
    db.add(SoleilMarketWebhookEvent(
        organization_id=organization_id, delivery_id=delivery, event=name,
        soleil_order_number=str(remote.get("number") or "")[:64] or None,
        external_ref=str(remote.get("external_ref") or "")[:64] or None,
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "duplicate"
    if order is None:
        logger.info("Webhook SoleilDrop per un ordine che non è nostro: %s", remote.get("external_ref"))
        return "unknown_order"
    await db.refresh(order)
    await _notify(db, order, changes)
    return "ok"
