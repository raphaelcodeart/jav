"""«Market 7» collegato all'API affiliati di SoleilDrop (13/10/2026).

SoleilDrop qui è un server finto (httpx.MockTransport) che risponde come la
documentazione v1 dell'08/10/2026: nessuna chiamata esce davvero. Si fissa:

- il catalogo dall'API entra con le stesse regole dell'Excel (prodotti nuovi
  spenti, prezzo IVA inclusa dal prezzo di vendita senza IVA, solo a pezzi);
- l'ordine pagato parte con external_ref «JAV-<numero>», solo codici e
  quantità -- nessun prezzo nostro -- e rimandarlo non crea doppioni;
- credito insufficiente, errori da guardare e errori da riprovare finiscono
  in stati diversi;
- il webhook vale solo con la firma giusta, una volta per consegna, e avvisa
  il cliente quando l'ordine parte;
- chiave e segreto non tornano mai indietro.
"""

import hashlib
import hmac
import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.domains.notifications.models import Notification
from app.domains.soleil_market import api_sync, client
from app.domains.soleil_market import service as market
from app.domains.soleil_market.models import SoleilMarketProduct, SoleilMarketVariant
from tests.test_soleil_market import ADDRESS, _user

API_KEY = "sdk_" + "a1" * 16
SECRET = "whsec_test_123456"


def _item(code, *, cost, sell, available=True, piece=True, brand="NASTRO AZZURRO", category="Bevande > Birre"):
    return {
        "id": f"177{code}", "code": code, "ean": f"800{code}", "name": f"Articolo {code}", "brand": brand,
        "vat_rate": 22, "weight_kg": 1.0, "images": [f"https://img.example/{code}.jpg"],
        "published": True, "available": available, "cost_price": cost, "sell_price": sell,
        "units": {"piece": piece, "box": False, "layer": False, "pallet": False},
        "category": category, "category_id": "12",
        "texts": {"it": {"description_short": "breve", "description": f"Descrizione {code}"}},
        "updated_at": "2026-10-10T10:00:00Z",
    }


class FakeSoleil:
    """Il server SoleilDrop finto: catalogo, ordini (idempotenti per
    external_ref, come quello vero), elenco ordini, wallet."""

    def __init__(self):
        self.items = [_item("133", cost=10.00, sell=15.00), _item("200", cost=3.00, sell=None)]
        self.all_ids = None
        self.orders: dict[str, dict] = {}
        self.posts: list[dict] = []
        self.next_post: tuple[int, dict] | None = None
        self.balance = 300.00

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        path = request.url.path.removeprefix("/api/affiliate/v1")
        if path == "/me":
            return httpx.Response(200, json={"ok": True, "eshop": {"id": 1, "code": "ESHOP-004", "name": "Jav"}})
        if path == "/wallet":
            return httpx.Response(200, json={"ok": True, "currency": "EUR", "balance": self.balance, "movements": []})
        if path == "/catalog":
            assert request.url.params.get("all") == "1"
            ids = self.all_ids if self.all_ids is not None else [i["id"] for i in self.items]
            return httpx.Response(200, json={"ok": True, "count": len(self.items), "all_ids": ids, "items": self.items})
        if path == "/orders" and request.method == "POST":
            body = json.loads(request.content)
            self.posts.append(body)
            if self.next_post is not None:
                status, answer = self.next_post
                self.next_post = None
                return httpx.Response(status, json=answer)
            ref = body["external_ref"]
            if ref in self.orders:
                return httpx.Response(200, json={"ok": True, "duplicate": True, "order": self.orders[ref]})
            order = {
                "number": f"AF004-2026-{len(self.orders) + 1:04d}", "external_ref": ref, "source": "api",
                "status": {"code": "in_attesa", "label": "In attesa di Conferma", "shipped": False,
                           "cancelled": False, "delivered": False},
                "totals": {"wallet_charged": 19.42}, "tracking": {"number": None},
                "carrier": {"id": "3", "name": "SDA Express Courier"},
            }
            self.orders[ref] = order
            return httpx.Response(201, json={"ok": True, "duplicate": False, "order": order,
                                             "wallet": {"charged": 19.42, "balance_after": 280.58}})
        if path == "/orders" and request.method == "GET":
            return httpx.Response(200, json={"ok": True, "orders": list(self.orders.values())})
        return httpx.Response(404, json={"ok": False, "error": "not_found", "message": "Non trovato"})


@pytest.fixture
def soleil():
    fake = FakeSoleil()
    client.TRANSPORT = httpx.MockTransport(fake)
    yield fake
    client.TRANSPORT = None


async def _connected_shop(db, organization_id, admin, **updates):
    from app.domains.organizations import service as organizations_service
    from app.domains.organizations.schemas import OrganizationSettingsUpdate

    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456"),
    )
    row = await market.get_settings_row(db, organization_id=organization_id)
    return await market.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={"enabled": True, "shipping_flat_cents": 490, "api_key": API_KEY, "webhook_secret": SECRET,
                 **updates},
    )


async def _active_variant(db, organization_id, code):
    product = (await db.execute(
        select(SoleilMarketProduct).where(
            SoleilMarketProduct.organization_id == organization_id, SoleilMarketProduct.soleil_product_id == code,
        )
    )).scalar_one()
    product.status = "ACTIVE"
    await db.commit()
    return (await db.execute(select(SoleilMarketVariant).where(SoleilMarketVariant.product_id == product.id))).scalar_one()


async def _paid_order(db, organization_id, admin, customer, variant, quantity=2):
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=[(variant.id, quantity)],
        address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note="Citofonare Rossi",
    )
    await market.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    await db.refresh(order)
    return order


def _signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    return raw, "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_key_and_secret_are_written_never_read(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    row = await _connected_shop(db, organization_id, admin)
    letto = market.settings_read_dict(row)
    assert letto["api_configured"] and letto["webhook_configured"]
    assert API_KEY not in json.dumps(letto, default=str) and SECRET not in json.dumps(letto, default=str)
    assert letto["api_key_hint"] == "…" + API_KEY[-4:]
    assert letto["webhook_url"].endswith(f"/api/soleil-market/webhook/{organization_id}")
    with pytest.raises(market.SoleilMarketValidationError):
        await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"api_key": "chiave-sbagliata"})


@pytest.mark.asyncio
async def test_the_connection_check_reads_shop_and_wallet(db, organization_id, soleil):
    admin = await _user(db, organization_id, "ADMIN")
    row = await _connected_shop(db, organization_id, admin)
    esito = await api_sync.check_connection(db, settings=row)
    assert esito == {"eshop_name": "Jav", "eshop_code": "ESHOP-004", "wallet_balance_cents": 30000}


@pytest.mark.asyncio
async def test_the_api_catalogue_enters_with_the_excel_rules(db, organization_id, soleil):
    admin = await _user(db, organization_id, "ADMIN")
    await _connected_shop(db, organization_id, admin)
    soleil.items.append(_item("300", cost=5.00, sell=8.00, piece=False))
    summary = await api_sync.import_catalog(db, organization_id=organization_id)
    assert summary["created"] == 3

    products = {
        p.soleil_product_id: p for p in (await db.execute(
            select(SoleilMarketProduct).where(SoleilMarketProduct.organization_id == organization_id)
        )).scalars()
    }
    assert all(p.status == "INACTIVE" for p in products.values())
    variant = (await db.execute(
        select(SoleilMarketVariant).where(SoleilMarketVariant.product_id == products["133"].id)
    )).scalar_one()
    # 15,00 senza IVA -> 18,30 IVA inclusa; il costo resta 10,00.
    assert variant.suggested_price_cents == 1830 and variant.price_cents == 1830
    assert variant.cost_cents == 1000 and variant.sku == "133" and variant.barcode == "800133"
    # Senza prezzo di vendita: costo + 40% + IVA, come per l'Excel.
    senza = (await db.execute(
        select(SoleilMarketVariant).where(SoleilMarketVariant.product_id == products["200"].id)
    )).scalar_one()
    assert senza.suggested_price_cents == (300 * 140 * 122 + 5000) // 10000
    # Non ordinabile a pezzi: non si vende.
    a_cartoni = (await db.execute(
        select(SoleilMarketVariant).where(SoleilMarketVariant.product_id == products["300"].id)
    )).scalar_one()
    assert a_cartoni.available_in_store is False

    # Una risposta con meno referenze di quante ne elenca non spegne nulla.
    soleil.all_ids = [i["id"] for i in soleil.items]
    soleil.items = soleil.items[:1]
    await api_sync.import_catalog(db, organization_id=organization_id)
    await db.refresh(products["200"])
    assert products["200"].missing_from_feed is False


@pytest.mark.asyncio
async def test_a_paid_order_goes_to_soleil_once_with_codes_and_no_prices(db, organization_id, soleil):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    await _connected_shop(db, organization_id, admin)
    await api_sync.import_catalog(db, organization_id=organization_id)
    variant = await _active_variant(db, organization_id, "133")
    order = await _paid_order(db, organization_id, admin, customer, variant)
    # Invio automatico spento: il pagamento da solo non manda niente.
    assert soleil.posts == [] and order.fulfillment_status == "NOT_SENT"

    order = await market.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    inviato = soleil.posts[0]
    assert inviato["external_ref"] == f"JAV-{order.number}"
    assert inviato["items"] == [{"code": "133", "qty": 2, "unit": "piece"}]
    assert inviato["recipient"]["name"] == "Mario Rossi" and inviato["recipient"]["zip"] == "20100"
    assert inviato["notes"] == "Citofonare Rossi"
    assert not {"total_paid", "shipping_paid", "total_tax", "sell_price"} & set(json.dumps(inviato).split('"'))
    assert order.fulfillment_status == "SENT"
    assert order.soleil_order_number == "AF004-2026-0001"
    assert order.soleil_wallet_charged_cents == 1942

    # Rimandarlo (doppio clic, job di riprova) non crea un secondo ordine.
    order = await market.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert len(soleil.orders) == 1 and order.soleil_order_number == "AF004-2026-0001"


@pytest.mark.asyncio
async def test_auto_forward_sends_it_when_paid(db, organization_id, soleil):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    await _connected_shop(db, organization_id, admin, auto_forward=True)
    await api_sync.import_catalog(db, organization_id=organization_id)
    variant = await _active_variant(db, organization_id, "133")
    order = await _paid_order(db, organization_id, admin, customer, variant)
    assert len(soleil.posts) == 1 and order.fulfillment_status == "SENT"


@pytest.mark.asyncio
async def test_no_credit_waits_and_errors_are_told_apart(db, organization_id, soleil):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    await _connected_shop(db, organization_id, admin)
    await api_sync.import_catalog(db, organization_id=organization_id)
    variant = await _active_variant(db, organization_id, "133")

    # 202: credito insufficiente -> in attesa, e lo staff lo sa.
    attesa = await _paid_order(db, organization_id, admin, customer, variant)
    soleil.next_post = (202, {
        "ok": True, "status": "waiting_wallet", "message": "Ordine ricevuto ma in attesa di credito.",
        "order": {"number": None, "external_ref": f"JAV-{attesa.number}", "pending": True,
                  "status": {"code": "waiting_wallet", "label": "In attesa di credito wallet"}},
        "wallet": {"balance": 12.0, "requested": 19.42},
    })
    attesa = await market.forward_order(db, organization_id=organization_id, order_id=attesa.id, actor_user_id=admin.id)
    assert attesa.fulfillment_status == "WAITING_WALLET" and attesa.soleil_order_number is None
    avvisi = (await db.execute(
        select(Notification).where(Notification.entity_id == str(attesa.id),
                                   Notification.type == "SOLEIL_MARKET_ORDER_FORWARD_ISSUE")
    )).scalars().all()
    assert avvisi and "ricarica il wallet" in avvisi[0].title

    # 422: da guardare, nessuna riprova automatica.
    rifiutato = await _paid_order(db, organization_id, admin, customer, variant, quantity=1)
    soleil.next_post = (422, {"ok": False, "error": "invalid_address", "message": "Manca il CAP"})
    with pytest.raises(market.SoleilMarketValidationError, match="Manca il CAP"):
        await market.forward_order(db, organization_id=organization_id, order_id=rifiutato.id, actor_user_id=admin.id)
    await db.refresh(rifiutato)
    assert rifiutato.fulfillment_status == "ERROR"

    # 503: temporaneo -> lo riprova il job, e la seconda volta parte.
    temporaneo = await _paid_order(db, organization_id, admin, customer, variant, quantity=3)
    soleil.next_post = (503, {"ok": False, "error": "server_error", "message": "Riprovare"})
    with pytest.raises(market.SoleilMarketValidationError):
        await market.forward_order(db, organization_id=organization_id, order_id=temporaneo.id, actor_user_id=admin.id)
    await db.refresh(temporaneo)
    assert temporaneo.fulfillment_status == "RETRY"
    from datetime import timedelta

    temporaneo.paid_at = temporaneo.paid_at - timedelta(minutes=10)
    await db.commit()
    assert await api_sync.retry_orders(db, organization_id=organization_id) == 1
    await db.refresh(temporaneo)
    assert temporaneo.fulfillment_status == "SENT"


@pytest.mark.asyncio
async def test_the_webhook_needs_the_signature_and_tells_the_customer_once(db, organization_id, soleil):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    await _connected_shop(db, organization_id, admin)
    await api_sync.import_catalog(db, organization_id=organization_id)
    variant = await _active_variant(db, organization_id, "133")
    customer_id = customer.id
    order = await _paid_order(db, organization_id, admin, customer, variant)
    order = await market.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)

    event = {
        "event": "order.shipped", "delivery_id": "3", "attempt": 1,
        "order": {"number": order.soleil_order_number, "external_ref": f"JAV-{order.number}",
                  "status": {"code": "spedito", "label": "Spedito", "shipped": True, "delivered": False,
                             "cancelled": False},
                  "tracking": {"number": "123456789"}, "carrier": {"name": "SDA"}},
    }
    raw, signature = _signed(event)
    headers = {"x-soleil-event": "order.shipped", "x-soleil-delivery": "3", "x-soleil-signature": signature}

    # Dall'esterno, attraverso la rotta vera: nessun login, solo la firma.
    from app.core.db import get_db
    from app.main import app

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as http:
            sbagliata = await http.post(
                f"/soleil-market/webhook/{organization_id}", content=raw,
                headers={**headers, "x-soleil-signature": "sha256=" + "0" * 64},
            )
            assert sbagliata.status_code == 401
            giusta = await http.post(f"/soleil-market/webhook/{organization_id}", content=raw, headers=headers)
            assert giusta.status_code == 200 and giusta.json()["result"] == "ok"
            # La riprova di SoleilDrop con la stessa consegna non rifà niente.
            doppia = await http.post(f"/soleil-market/webhook/{organization_id}", content=raw, headers=headers)
            assert doppia.json()["result"] == "duplicate"
            ping_raw, ping_sig = _signed({"event": "test.ping", "delivery_id": "t1"})
            ping = await http.post(
                f"/soleil-market/webhook/{organization_id}", content=ping_raw,
                headers={"x-soleil-event": "test.ping", "x-soleil-delivery": "t1", "x-soleil-signature": ping_sig},
            )
            assert ping.status_code == 200
    finally:
        app.dependency_overrides.clear()

    await db.refresh(order)
    assert order.fulfillment_status == "SHIPPED" and order.shipped_at is not None
    assert order.tracking_number == "123456789" and order.tracking_company == "SDA"
    assert market.delivery_status(order) == "SHIPPED"
    campanelle = (await db.execute(
        select(Notification).where(Notification.recipient_user_id == customer_id, Notification.type == "ORDER_SHIPPED")
    )).scalars().all()
    assert len(campanelle) == 1


@pytest.mark.asyncio
async def test_the_poll_catches_what_a_lost_webhook_missed(db, organization_id, soleil):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    await _connected_shop(db, organization_id, admin)
    await api_sync.import_catalog(db, organization_id=organization_id)
    variant = await _active_variant(db, organization_id, "133")
    order = await _paid_order(db, organization_id, admin, customer, variant)
    order = await market.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)

    remote = soleil.orders[f"JAV-{order.number}"]
    remote["status"] = {"code": "consegnato", "label": "Consegnato", "shipped": True, "delivered": True}
    remote["tracking"] = {"number": "XYZ"}
    assert await api_sync.sync_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.fulfillment_status == "DELIVERED" and order.delivered_at and order.shipped_at
    assert order.soleil_status_label == "Consegnato"
