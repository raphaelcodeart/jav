"""I fornitori dello Shop e l'email che raccoglie i loro ordini.

Cosa si protegge qui: chi è il fornitore di un prodotto (il suo, oppure
quello della categoria) e che resti congelato sull'ordine; che la coda
«Fornitori da avvisare» raccolga gli ordini di più clienti per lo stesso
fornitore; che la lettera dica tutto quello che serve e niente prezzi; e
soprattutto che un'email partita segni le righe, una non partita non segni
niente, e che nessuna strada -- coda, pulsante sull'ordine, invio
automatico -- mandi due volte la stessa merce.
"""

import pytest
from sqlalchemy import func, select

from app.core.email import EmailNotConfiguredError
from app.domains.jav_market import service as market
from app.domains.jav_market.models import JavMarketOrderItem, JavMarketSupplierDispatch
from app.domains.shop_categories import service as categories
from tests.test_jav_market import ADDRESS, _paid_order, _shop, _user, _variants


async def _producer(db, organization_id, admin, name, email):
    return await market.create_producer(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": name, "description": "", "email": email, "website_url": None, "logo_url": None,
                 "vat_number": None, "phone": None, "address": None},
    )


async def _product(db, organization_id, admin, name, *, producer_id=None, price_cents=1500):
    return await market.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": name, "credit_discount_percentage": 0, "producer_id": producer_id,
                 "variants": [{"label": "Unica", "price_cents": price_cents}]},
    )


async def _category(db, organization_id, admin, name, *, position=0, producer_id=None, products=()):
    category = await categories.create_category(
        db, organization_id=organization_id, shop="jav_market", name=name, position=position,
        producer_id=producer_id, actor_user_id=admin.id,
    )
    for product in products:
        current = await categories.category_ids_for_product(
            db, organization_id=organization_id, shop="jav_market", product_id=product.id
        )
        await categories.replace_assignments(
            db, organization_id=organization_id, shop="jav_market", product_id=product.id,
            category_ids=[*current, category.id], actor_user_id=admin.id,
        )
    return category


async def _world(db, organization_id):
    """Due fornitori con email: il caseificio (sui suoi prodotti) e chi fa
    gli integratori (sulla categoria), più un prodotto senza nessuno."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, caseificio, pane, miele = await _shop(db, organization_id, admin)
    await market.update_producer(
        db, organization_id=organization_id, producer_id=caseificio.id, payload={"email": "ordini@caseificio.it"}
    )
    integratori = await _producer(db, organization_id, admin, "Integratori Spa", "ordini@integratori.it")
    proteine = await _product(db, organization_id, admin, "Proteine whey")
    await _category(db, organization_id, admin, "Integratori", producer_id=integratori.id, products=[proteine])
    cintura = await _product(db, organization_id, admin, "Cintura bianca")
    return {
        "admin": admin, "customer": customer, "settings": row, "caseificio": caseificio,
        "integratori": integratori, "pane": pane, "miele": miele, "proteine": proteine, "cintura": cintura,
    }


async def _variant(db, product, index=0):
    return (await _variants(db, product))[index]


async def _queue_for(db, organization_id, producer):
    queue = await market.supplier_queue(db, organization_id=organization_id)
    return next((s for s in queue["suppliers"] if s["producer"]["id"] == producer.id), None)


# --- Chi è il fornitore ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_product_supplier_wins_otherwise_the_first_category_with_one(db, organization_id):
    w = await _world(db, organization_id)
    admin = w["admin"]
    altro = await _product(db, organization_id, admin, "Barretta")
    # Tre categorie: la prima per posizione non ha fornitore, conta la seconda.
    await _category(db, organization_id, admin, "Novità", position=0, products=[altro])
    await _category(db, organization_id, admin, "Snack", position=1, producer_id=w["integratori"].id, products=[altro])
    await _category(db, organization_id, admin, "Formaggi", position=2, producer_id=w["caseificio"].id, products=[altro])

    resolved = await market.resolve_suppliers(db, organization_id=organization_id, products=[altro])
    assert resolved[altro.id].producer.id == w["integratori"].id
    assert resolved[altro.id].source == "CATEGORY" and resolved[altro.id].category_name == "Snack"

    # Il fornitore scritto sul prodotto vince sulla categoria...
    await market.update_product(
        db, organization_id=organization_id, product_id=altro.id, payload={"producer_id": w["caseificio"].id}
    )
    letto = await market.product_read_dict(db, altro, admin=True)
    assert letto["supplier"]["name"] == "Caseificio Rossi" and letto["supplier_source"] == "PRODUCT"
    # ...e toglierlo lo fa tornare a quello della categoria.
    await market.update_product(db, organization_id=organization_id, product_id=altro.id, payload={"producer_id": None})
    letto = await market.product_read_dict(db, altro, admin=True)
    assert letto["supplier"]["name"] == "Integratori Spa" and letto["supplier_category_name"] == "Snack"

    elenco = {p["name"]: p for p in await market.admin_products_read(db, organization_id=organization_id)}
    assert elenco["Cintura bianca"]["supplier"] is None
    assert elenco["Proteine whey"]["supplier_source"] == "CATEGORY"
    assert len(elenco["Barretta"]["category_ids"]) == 3


@pytest.mark.asyncio
async def test_only_shop_categories_can_have_a_supplier(db, organization_id):
    w = await _world(db, organization_id)
    with pytest.raises(categories.ShopCategoryValidationError):
        await categories.create_category(
            db, organization_id=organization_id, shop="internal", name="Casa",
            producer_id=w["caseificio"].id, actor_user_id=w["admin"].id,
        )


@pytest.mark.asyncio
async def test_the_order_freezes_the_supplier_resolved_at_creation(db, organization_id):
    w = await _world(db, organization_id)
    order = await _paid_order(
        db, organization_id, w["admin"], w["customer"], lines=[((await _variant(db, w["proteine"])).id, 1)]
    )
    [item] = await market.order_items(db, order)
    assert item.producer_id == w["integratori"].id and item.producer_name == "Integratori Spa"

    # Il prodotto cambia fornitore: l'ordine già fatto no.
    await market.update_product(
        db, organization_id=organization_id, product_id=w["proteine"].id, payload={"producer_id": w["caseificio"].id}
    )
    await db.refresh(item)
    assert item.producer_id == w["integratori"].id
    assert (await _queue_for(db, organization_id, w["integratori"]))["order_count"] == 1


# --- La coda e la lettera ----------------------------------------------------------------------------


async def _three_orders(db, organization_id, w):
    """Due ordini con merce del caseificio, uno misto con una riga senza
    fornitore, e uno non pagato che non deve comparire da nessuna parte."""
    mezzo_kg = await _variant(db, w["pane"])
    vasetto = await _variant(db, w["miele"])
    a = await _paid_order(db, organization_id, w["admin"], w["customer"], lines=[(mezzo_kg.id, 2), (vasetto.id, 1)])
    b = await _paid_order(
        db, organization_id, w["admin"], w["customer"],
        lines=[(mezzo_kg.id, 1), ((await _variant(db, w["proteine"])).id, 3), ((await _variant(db, w["cintura"])).id, 1)],
    )
    await market.create_order(
        db, organization_id=organization_id, customer_user_id=w["customer"].id, lines=[(vasetto.id, 5)],
        address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=w["customer"].id, otp_code=None, note=None,
    )
    return a, b


@pytest.mark.asyncio
async def test_the_queue_gathers_each_suppliers_lines_across_orders(db, organization_id):
    w = await _world(db, organization_id)
    a, b = await _three_orders(db, organization_id, w)

    queue = await market.supplier_queue(db, organization_id=organization_id)
    assert [s["producer"]["name"] for s in queue["suppliers"]] == ["Caseificio Rossi", "Integratori Spa"]
    caseificio = queue["suppliers"][0]
    assert caseificio["order_count"] == 2 and caseificio["piece_count"] == 4
    assert [o["order_code"] for o in caseificio["orders"]] == [market.order_code(a), market.order_code(b)]
    integratori = queue["suppliers"][1]
    assert integratori["order_count"] == 1 and integratori["piece_count"] == 3
    # La cintura non ha fornitore: non si perde, sta nell'elenco a parte.
    assert [(u["product_name"], u["order_code"]) for u in queue["unassigned"]] == [
        ("Cintura bianca", market.order_code(b))
    ]


@pytest.mark.asyncio
async def test_the_draft_is_a_complete_letter_without_prices(db, organization_id):
    w = await _world(db, organization_id)
    await market.update_settings(
        db, row=w["settings"], actor_user_id=w["admin"].id,
        updates={"supplier_email_from": "info@judoartevida.com",
                 "supplier_email_signature": "Grazie,\nJudo Arte e Vida"},
    )
    a, b = await _three_orders(db, organization_id, w)

    draft = await market.supplier_draft(db, organization_id=organization_id, producer_id=w["caseificio"].id)
    assert draft["to_email"] == "ordini@caseificio.it"
    assert draft["from_email"] == "info@judoartevida.com"
    assert draft["subject"] == "2 nuovi ordini da preparare"
    assert draft["order_codes"] == [market.order_code(a), market.order_code(b)]
    assert len(draft["item_ids"]) == 3
    body = draft["body_text"]
    assert body.startswith("Buongiorno Caseificio Rossi,")
    assert f"ORDINE #{market.order_code(a)} del " in body and f"ORDINE #{market.order_code(b)} del " in body
    assert "- 2 × Pane di segale – 500 g" in body and "- 1 × Miele di acacia\n" in body
    assert "Mario Rossi" in body and "Via Roma 1" in body and "20100 Milano (MI)" in body
    assert "Telefono: 333 1234567" in body and "Note del cliente: Citofonare Rossi" in body
    assert "tracking" in body and body.endswith("Grazie,\nJudo Arte e Vida")
    # Solo la sua merce, e mai il prezzo pagato dal cliente.
    assert "Proteine" not in body and "Cintura" not in body
    assert "€" not in body and "4,50" not in body and "9,00" not in body


# --- L'invio -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sending_marks_the_lines_and_the_orders_that_are_complete(db, organization_id, monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(market, "send_html_email", lambda **kw: sent.append(kw))
    w = await _world(db, organization_id)
    await market.update_settings(
        db, row=w["settings"], actor_user_id=w["admin"].id, updates={"supplier_email_from": "info@judoartevida.com"}
    )
    a, b = await _three_orders(db, organization_id, w)
    draft = await market.supplier_draft(db, organization_id=organization_id, producer_id=w["caseificio"].id)

    dispatch = await market.send_supplier_dispatch(
        db, organization_id=organization_id, producer_id=w["caseificio"].id, to_email="magazzino@caseificio.it",
        subject="Ordini di ottobre", body_text=draft["body_text"] + "\n\nP.S. corretto a mano <b>",
        item_ids=draft["item_ids"], actor_user_id=w["admin"].id,
    )
    [email] = sent
    # Parte da info@, la risposta torna lì e una copia resta nella casella.
    assert email["to"] == "magazzino@caseificio.it" and email["subject"] == "Ordini di ottobre"
    assert email["from_address"] == email["reply_to"] == email["bcc"] == "info@judoartevida.com"
    assert email["text_body"].endswith("P.S. corretto a mano <b>")
    assert "corretto a mano &lt;b&gt;" in email["html_body"]

    items = (await db.execute(select(JavMarketOrderItem).where(JavMarketOrderItem.id.in_(draft["item_ids"])))).scalars().all()
    assert {i.supplier_dispatch_id for i in items} == {dispatch.id}
    await db.refresh(a)
    await db.refresh(b)
    # L'ordine A era tutto del caseificio: è mandato. B aspetta ancora gli integratori.
    assert a.fulfillment_status == "SENT" and a.forwarded_by_user_id == w["admin"].id
    assert b.fulfillment_status == "NOT_SENT"
    assert await _queue_for(db, organization_id, w["caseificio"]) is None
    assert (await _queue_for(db, organization_id, w["integratori"]))["order_count"] == 1

    [storico] = await market.list_supplier_dispatches(db, organization_id=organization_id)
    assert storico["producer_name"] == "Caseificio Rossi" and storico["source"] == "QUEUE"
    assert storico["order_count"] == 2 and storico["item_count"] == 3 and storico["piece_count"] == 4
    assert storico["subject"] == "Ordini di ottobre"

    # Mandati anche gli integratori, B è completo (la cintura senza
    # fornitore non lo trattiene: non c'è nessuno a cui mandarla).
    altra = await market.supplier_draft(db, organization_id=organization_id, producer_id=w["integratori"].id)
    await market.send_supplier_dispatch(
        db, organization_id=organization_id, producer_id=w["integratori"].id, to_email=altra["to_email"],
        subject=altra["subject"], body_text=altra["body_text"], item_ids=altra["item_ids"],
        actor_user_id=w["admin"].id,
    )
    await db.refresh(b)
    assert b.fulfillment_status == "SENT"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [EmailNotConfiguredError("smtp_host is empty"), TimeoutError("smtp")])
async def test_an_email_that_does_not_leave_marks_nothing(db, organization_id, monkeypatch, failure):
    def fails(**_kw):
        raise failure

    monkeypatch.setattr(market, "send_html_email", fails)
    w = await _world(db, organization_id)
    a, _b = await _three_orders(db, organization_id, w)
    draft = await market.supplier_draft(db, organization_id=organization_id, producer_id=w["caseificio"].id)

    with pytest.raises(market.JavMarketValidationError) as err:
        await market.send_supplier_dispatch(
            db, organization_id=organization_id, producer_id=w["caseificio"].id, to_email=draft["to_email"],
            subject=draft["subject"], body_text=draft["body_text"], item_ids=draft["item_ids"],
            actor_user_id=w["admin"].id,
        )
    assert "Nessun ordine è stato segnato" in str(err.value)
    if isinstance(failure, EmailNotConfiguredError):
        assert "non è ancora configurato" in str(err.value)

    assert (await db.execute(select(func.count()).select_from(JavMarketSupplierDispatch))).scalar_one() == 0
    await db.refresh(a)
    assert a.fulfillment_status == "NOT_SENT"
    assert (await _queue_for(db, organization_id, w["caseificio"]))["order_count"] == 2


@pytest.mark.asyncio
async def test_the_same_lines_are_never_sent_twice(db, organization_id, monkeypatch):
    """Il doppio clic, o due amministratori sulla stessa coda: il secondo
    invio trova le righe già segnate e si ferma prima dell'email."""
    sent: list[dict] = []
    monkeypatch.setattr(market, "send_html_email", lambda **kw: sent.append(kw))
    w = await _world(db, organization_id)
    await _three_orders(db, organization_id, w)
    integratori_id = w["integratori"].id
    draft = await market.supplier_draft(db, organization_id=organization_id, producer_id=w["caseificio"].id)
    invio = {
        "organization_id": organization_id, "producer_id": w["caseificio"].id, "to_email": draft["to_email"],
        "subject": draft["subject"], "body_text": draft["body_text"], "item_ids": draft["item_ids"],
        "actor_user_id": w["admin"].id,
    }
    await market.send_supplier_dispatch(db, **invio)
    with pytest.raises(market.JavMarketConflictError):
        await market.send_supplier_dispatch(db, **invio)
    assert len(sent) == 1

    # Né si possono far passare righe di un altro fornitore sotto questo.
    # (Gli id si leggono da `invio`: il rifiuto fa rollback e scade gli oggetti.)
    altra = await market.supplier_draft(db, organization_id=organization_id, producer_id=integratori_id)
    with pytest.raises(market.JavMarketConflictError):
        await market.send_supplier_dispatch(db, **{**invio, "item_ids": altra["item_ids"]})
    assert len(sent) == 1
    # E a coda vuota la bozza dice che non c'è niente, invece di una lettera vuota.
    with pytest.raises(market.JavMarketConflictError):
        await market.supplier_draft(db, organization_id=organization_id, producer_id=invio["producer_id"])


@pytest.mark.asyncio
async def test_the_order_button_and_the_queue_never_send_the_same_lines(db, organization_id, monkeypatch):
    batch: list[dict] = []
    single: list[dict] = []
    monkeypatch.setattr(market, "send_html_email", lambda **kw: batch.append(kw))
    monkeypatch.setattr(market, "send_html_email_best_effort", lambda **kw: single.append(kw) or True)
    w = await _world(db, organization_id)
    mezzo_kg = await _variant(db, w["pane"])

    # Mandato dal pulsante sull'ordine: sparisce dalla coda.
    primo = await _paid_order(db, organization_id, w["admin"], w["customer"], lines=[(mezzo_kg.id, 1)])
    single.clear()
    await market.forward_order(db, organization_id=organization_id, order_id=primo.id, actor_user_id=w["admin"].id)
    assert [m["to"] for m in single] == ["ordini@caseificio.it"]
    assert "Pane di segale" in single[0]["text_body"] and "Via Roma 1" in single[0]["html_body"]
    assert await _queue_for(db, organization_id, w["caseificio"]) is None

    # Mandato dalla coda: il pulsante sull'ordine non lo rimanda.
    secondo = await _paid_order(db, organization_id, w["admin"], w["customer"], lines=[(mezzo_kg.id, 1)])
    draft = await market.supplier_draft(db, organization_id=organization_id, producer_id=w["caseificio"].id)
    assert draft["order_codes"] == [market.order_code(secondo)]
    await market.send_supplier_dispatch(
        db, organization_id=organization_id, producer_id=w["caseificio"].id, to_email=draft["to_email"],
        subject=draft["subject"], body_text=draft["body_text"], item_ids=draft["item_ids"],
        actor_user_id=w["admin"].id,
    )
    single.clear()
    with pytest.raises(market.JavMarketValidationError):
        await market.forward_order(db, organization_id=organization_id, order_id=secondo.id, actor_user_id=w["admin"].id)
    assert single == []

    # L'invio automatico al pagamento segna le righe allo stesso modo.
    await market.update_settings(db, row=w["settings"], actor_user_id=w["admin"].id, updates={"auto_forward": True})
    terzo = await _paid_order(db, organization_id, w["admin"], w["customer"], lines=[(mezzo_kg.id, 1)])
    assert await _queue_for(db, organization_id, w["caseificio"]) is None
    await db.refresh(terzo)
    assert terzo.fulfillment_status == "SENT"
    sources = [d["source"] for d in await market.list_supplier_dispatches(db, organization_id=organization_id)]
    assert sorted(sources) == ["AUTO", "ORDER", "QUEUE"]
    assert len(batch) == 1


@pytest.mark.asyncio
async def test_a_line_sold_without_supplier_joins_the_queue_once_one_is_assigned(db, organization_id, monkeypatch):
    """L'avviso «righe senza fornitore» chiede di assegnarlo al prodotto o
    alla categoria: farlo deve bastare, anche per un ordine già pagato."""
    monkeypatch.setattr(market, "send_html_email", lambda **kw: None)
    w = await _world(db, organization_id)
    order = await _paid_order(
        db, organization_id, w["admin"], w["customer"], lines=[((await _variant(db, w["cintura"])).id, 1)]
    )
    assert len((await market.supplier_queue(db, organization_id=organization_id))["unassigned"]) == 1

    await _category(db, organization_id, w["admin"], "Cinture", producer_id=w["integratori"].id, products=[w["cintura"]])
    queue = await market.supplier_queue(db, organization_id=organization_id)
    assert queue["unassigned"] == []
    assert (await _queue_for(db, organization_id, w["integratori"]))["orders"][0]["id"] == order.id

    draft = await market.supplier_draft(db, organization_id=organization_id, producer_id=w["integratori"].id)
    await market.send_supplier_dispatch(
        db, organization_id=organization_id, producer_id=w["integratori"].id, to_email=draft["to_email"],
        subject=draft["subject"], body_text=draft["body_text"], item_ids=draft["item_ids"],
        actor_user_id=w["admin"].id,
    )
    [item] = await market.order_items(db, order)
    assert item.producer_id == w["integratori"].id, "partita, la riga congela il fornitore"
