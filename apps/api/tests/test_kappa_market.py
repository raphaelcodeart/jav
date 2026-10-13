"""Marketplace 5 — «Market Kappa» (Session 87).

Clone di «Fai la Spesa con Jav», con tabelle sue: questi test sono quelli
di `test_jav_market.py` rifatti sul nuovo dominio, per fissare che il clone
si comporta come l'originale -- catalogo scritto a mano, marchio congelato
sull'ordine, spedizione a importo fisso, carrello, JavCash e IVA come
negli altri negozi -- senza toccarne le tabelle.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.carts import service as carts_service
from app.domains.kappa_market import service as market
from app.domains.marketplaces import rules
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service
from app.core.security import hash_otp_code, hash_password

OTP = "424242"
ADDRESS = {
    "recipient_name": "Mario Rossi", "recipient_phone": "333 1234567", "address_line1": "Via Roma 1",
    "address_line2": None, "city": "Milano", "province": "MI", "postal_code": "20100",
}


async def _user(db, organization_id, role_code="CUSTOMER"):
    from sqlalchemy import select

    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("x"),
    )
    db.add(user)
    await db.flush()
    role = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if role is None:
        role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
        db.add(role)
        await db.flush()
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


async def _otp(db, user_id):
    db.add(OtpCode(
        user_id=user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code_hash=hash_otp_code(OTP),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    await db.commit()


async def _shop(db, organization_id, admin, *, shipping_flat_cents=490, credit_percentage=25):
    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456"),
    )
    row = await market.get_settings_row(db, organization_id=organization_id)
    await market.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={"enabled": True, "shipping_flat_cents": shipping_flat_cents, "shipping_days": "3-5"},
    )
    producer = await market.create_producer(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Caseificio Rossi", "description": "Formaggi di malga dal 1952",
                 "website_url": "https://caseificiorossi.it", "vat_number": "IT01234567890",
                 "email": None, "phone": None, "address": None, "logo_url": None},
    )
    pane = await market.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Pane di segale", "description": "Cotto a legna",
                 "credit_discount_percentage": credit_percentage, "unit_cost_cents": 200,
                 "producer_id": producer.id,
                 "variants": [{"label": "500 g", "price_cents": 450, "inventory": 20},
                              {"label": "1 kg", "price_cents": 800, "inventory": 10}]},
    )
    miele = await market.create_product(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Miele di acacia", "description": "Vasetto da 500 g",
                 "credit_discount_percentage": credit_percentage, "unit_cost_cents": 400,
                 "producer_id": producer.id,
                 "variants": [{"label": "Unica", "price_cents": 900, "inventory": 15}]},
    )
    return row, producer, pane, miele


async def _variants(db, product):
    return await market._variants(db, product.id)


@pytest.mark.asyncio
async def test_the_admin_builds_the_catalogue_by_hand(db, organization_id):
    """Non c'è un fornitore: prodotti e varianti li scrive l'amministratore,
    e un prodotto senza varianti non deve poter nascere."""
    admin = await _user(db, organization_id, "ADMIN")
    _row, producer, pane, _miele = await _shop(db, organization_id, admin)

    letto = await market.product_read_dict(db, pane, admin=True)
    assert letto["name"] == "Pane di segale"
    assert [v["label"] for v in letto["variants"]] == ["500 g", "1 kg"]
    assert letto["producer"]["name"] == "Caseificio Rossi"
    # Al cliente il produttore si mostra, ma non la sua partita IVA.
    pubblico = await market.product_read_dict(db, pane, admin=False)
    assert pubblico["producer"]["name"] == "Caseificio Rossi"
    assert "vat_number" not in pubblico["producer"]

    with pytest.raises(market.KappaMarketValidationError):
        await market.create_product(
            db, organization_id=organization_id, actor_user_id=admin.id,
            payload={"name": "Senza varianti", "variants": []},
        )
    # E due schede della stessa azienda non si creano.
    with pytest.raises(market.KappaMarketValidationError):
        await market.create_producer(
            db, organization_id=organization_id, actor_user_id=admin.id, payload={"name": producer.name},
        )


@pytest.mark.asyncio
async def test_the_shop_is_empty_while_it_is_switched_off(db, organization_id):
    """Un negozio spento non mostra niente e non vende niente: la scheda
    sparisce da sola dallo Shop."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _p, pane, _m = await _shop(db, organization_id, admin)
    assert len(await market.customer_products(db, organization_id=organization_id)) == 2

    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": False})
    assert await market.customer_products(db, organization_id=organization_id) == []
    variante = (await _variants(db, pane))[0]
    with pytest.raises(market.KappaMarketValidationError):
        await market.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variante.id, quantity=1,
        )


@pytest.mark.asyncio
async def test_the_quote_adds_vat_and_charges_one_shipping(db, organization_id):
    """Le stesse regole degli altri Marketplace: IVA aggiunta sulla merce,
    spedizione una volta per ordine, tetto JavCash somma delle righe."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, miele = await _shop(db, organization_id, admin)
    mezzo_kg = (await _variants(db, pane))[0]
    vasetto = (await _variants(db, miele))[0]

    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(mezzo_kg.id, 2), (vasetto.id, 1)],
    )
    merce = 450 * 2 + 900
    assert quote["items_cents"] == merce
    assert quote["vat_cents"] == rules.vat_added_cents(net_cents=merce, percentage=22)
    # Una spedizione sola, non una per riga.
    assert quote["shipping_cents"] == 490
    assert quote["amount_cents"] == merce + quote["vat_cents"] + 490
    # Il tetto JavCash è la somma delle righe, spedizione e IVA escluse.
    assert quote["max_creditable_cents"] == round(900 * 25 / 100) + round(900 * 25 / 100)
    assert quote["max_creditable_cents"] == sum(i["max_creditable_cents"] for i in quote["items"])


@pytest.mark.asyncio
async def test_the_cart_becomes_one_order_that_remembers_the_producer(db, organization_id):
    """L'ordine congela il nome dell'azienda come congela quello del
    prodotto: rinominarla non deve cambiare cosa dice un ordine passato."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, producer, pane, miele = await _shop(db, organization_id, admin)
    mezzo_kg = (await _variants(db, pane))[0]
    vasetto = (await _variants(db, miele))[0]

    for variante, quantita in ((mezzo_kg, 2), (vasetto, 1)):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="kappa_market",
            variant_id=variante.id, quantity=quantita,
        )
    riepilogo = await carts_service.summary(
        db, organization_id=organization_id, customer_user_id=customer.id
    )
    sezione = riepilogo["sections"][0]
    assert sezione["shop"] == "kappa_market" and len(sezione["items"]) == 2

    _cart, lines = await carts_service.checkout_lines(
        db, customer_user_id=customer.id, shop="kappa_market"
    )
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    items = await market.order_items(db, order)
    assert len(items) == 2
    assert all(i.producer_name == "Caseificio Rossi" for i in items)
    assert order.number and market.order_code(order) == str(order.number)
    assert order.vat_mode == "ADDED"

    # Rinominare l'azienda non tocca l'ordine.
    await market.update_producer(
        db, organization_id=organization_id, producer_id=producer.id, payload={"name": "Caseificio Bianchi"},
    )
    items = await market.order_items(db, order)
    assert all(i.producer_name == "Caseificio Rossi" for i in items)

    await carts_service.clear(db, customer_user_id=customer.id, shop="kappa_market")
    vuoto = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    assert vuoto["sections"] == []


@pytest.mark.asyncio
async def test_javcash_is_spent_with_a_code_and_never_covers_it_all(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, _m = await _shop(db, organization_id, admin, credit_percentage=99)
    variante = (await _variants(db, pane))[1]  # 1 kg, 8,00
    wallet = await wallet_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=customer.id
    )
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=10000,
        type_="ADMIN_CREDIT", actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id, quantity=1
    )
    # Mai l'intero ordine, qualunque percentuale.
    assert quote["max_creditable_cents"] < quote["amount_cents"]

    with pytest.raises(market.InvalidOtpError):
        await market.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
            quantity=1, address=ADDRESS, credit_applied_cents=quote["max_creditable_cents"],
            payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code="000000", note=None,
        )
    await _otp(db, customer.id)
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
        quantity=1, address=ADDRESS, credit_applied_cents=quote["max_creditable_cents"],
        payment_method="BANK_TRANSFER", actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    assert order.credit_applied_cents == quote["max_creditable_cents"]
    # I JavCash non abbassano l'IVA: sono un modo di pagare.
    assert order.vat_amount_cents == rules.vat_added_cents(net_cents=order.items_cents, percentage=22)
    # Session 86: nessuno sconto bonifico, si paga tutto il residuo dopo i JavCash.
    residuo = order.amount_cents - order.credit_applied_cents
    assert order.bank_transfer_discount_cents == 0
    assert market.amount_due_cents(order) == residuo


@pytest.mark.asyncio
async def test_the_admin_ships_it_and_the_customer_is_told(db, organization_id):
    """Qui non c'è un fornitore a cui inoltrare: paga il cliente, e poi
    l'amministratore spedisce e segna il tracking."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, _m = await _shop(db, organization_id, admin)
    variante = (await _variants(db, pane))[0]
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    # Non si spedisce un ordine non pagato.
    with pytest.raises(market.KappaMarketValidationError):
        await market.mark_shipped(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id,
            tracking_number="X1", tracking_url=None, tracking_company=None,
        )
    await market.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    await db.refresh(order)
    assert order.status == "PAID" and market.delivery_status(order) == "RECEIVED"

    await market.mark_shipped(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id,
        tracking_number="RR123456789IT", tracking_url=None, tracking_company="Poste",
    )
    await db.refresh(order)
    assert market.delivery_status(order) == "SHIPPED" and order.tracking_number == "RR123456789IT"

    await market.mark_delivered(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    await db.refresh(order)
    assert market.delivery_status(order) == "DELIVERED"


@pytest.mark.asyncio
async def test_a_sold_out_variant_cannot_be_bought_or_put_in_the_cart(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, _m = await _shop(db, organization_id, admin)
    variante = (await _variants(db, pane))[0]
    await market.update_variant(
        db, organization_id=organization_id, variant_id=variante.id, payload={"inventory": 0}
    )
    with pytest.raises(market.KappaMarketValidationError):
        await market.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variante.id, quantity=1,
        )
    with pytest.raises(carts_service.CartValidationError):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="kappa_market",
            variant_id=variante.id, quantity=1,
        )


# --- L'ordine che parte verso l'azienda (Session 80) -----------------------------------------------


async def _paid_order(db, organization_id, admin, customer, *, lines):
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note="Citofonare Rossi",
    )
    await market.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    await db.refresh(order)
    return order


@pytest.mark.asyncio
async def test_the_order_is_emailed_to_each_producer_with_only_its_own_lines(
    db, organization_id, monkeypatch
):
    """Un ordine può contenere prodotti di aziende diverse: ciascuna riceve
    solo le sue righe, più l'indirizzo di consegna."""
    inviate: list[dict] = []
    monkeypatch.setattr(market, "send_html_email_best_effort", lambda **kw: inviate.append(kw) or True)

    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, primo, pane, miele = await _shop(db, organization_id, admin)
    await market.update_producer(
        db, organization_id=organization_id, producer_id=primo.id, payload={"email": "ordini@caseificio.it"}
    )
    secondo = await market.create_producer(
        db, organization_id=organization_id, actor_user_id=admin.id,
        payload={"name": "Apicoltura Verdi", "description": "", "email": "ciao@apicolturaverdi.it",
                 "website_url": None, "logo_url": None, "vat_number": None, "phone": None, "address": None},
    )
    await market.update_product(
        db, organization_id=organization_id, product_id=miele.id, payload={"producer_id": secondo.id}
    )

    mezzo_kg = (await _variants(db, pane))[0]
    vasetto = (await _variants(db, miele))[0]
    order = await _paid_order(
        db, organization_id, admin, customer, lines=[(mezzo_kg.id, 2), (vasetto.id, 1)]
    )
    inviate.clear()  # via le email al cliente: qui interessano quelle alle aziende

    await market.forward_order(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    ai_fornitori = {m["to"]: m for m in inviate}
    assert set(ai_fornitori) == {"ordini@caseificio.it", "ciao@apicolturaverdi.it"}

    caseificio = ai_fornitori["ordini@caseificio.it"]["html_body"]
    apicoltura = ai_fornitori["ciao@apicolturaverdi.it"]["html_body"]
    # Ciascuna vede la sua merce e non quella dell'altra.
    assert "Pane di segale" in caseificio and "Miele" not in caseificio
    assert "Miele di acacia" in apicoltura and "Pane" not in apicoltura
    # E tutte e due sanno dove consegnare, con la nota del cliente.
    for corpo in (caseificio, apicoltura):
        assert "Via Roma 1" in corpo and "20100" in corpo and "Mario Rossi" in corpo
        assert "Citofonare Rossi" in corpo
        # Mai il prezzo che il cliente ha pagato: sarebbe mostrare il ricarico.
        assert "4,50" not in corpo and "9,00" not in corpo

    await db.refresh(order)
    assert order.fulfillment_status == "SENT" and order.forwarded_at is not None
    assert order.forward_error is None


@pytest.mark.asyncio
async def test_an_order_is_never_forwarded_before_it_is_paid(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, producer, pane, _m = await _shop(db, organization_id, admin)
    await market.update_producer(
        db, organization_id=organization_id, producer_id=producer.id, payload={"email": "ordini@caseificio.it"}
    )
    variante = (await _variants(db, pane))[0]
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variante.id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    with pytest.raises(market.KappaMarketValidationError):
        await market.forward_order(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )


@pytest.mark.asyncio
async def test_a_company_without_an_email_is_reported_and_not_silently_skipped(
    db, organization_id, monkeypatch
):
    """Un'azienda senza email vuol dire merce che nessuno sta preparando:
    va detto, non ignorato."""
    inviate: list[dict] = []
    monkeypatch.setattr(market, "send_html_email_best_effort", lambda **kw: inviate.append(kw) or True)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _producer, pane, _m = await _shop(db, organization_id, admin)  # nessuna email in scheda
    variante = (await _variants(db, pane))[0]
    order = await _paid_order(db, organization_id, admin, customer, lines=[(variante.id, 1)])

    with pytest.raises(market.KappaMarketValidationError):
        await market.forward_order(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )
    await db.refresh(order)
    assert order.fulfillment_status == "NOT_SENT"
    assert "non ha un'email" in (order.forward_error or "")


@pytest.mark.asyncio
async def test_auto_forward_sends_it_the_moment_the_payment_is_confirmed(
    db, organization_id, monkeypatch
):
    """Con l'automatismo acceso l'ordine parte da solo; spento, aspetta il
    pulsante. Nasce spento."""
    inviate: list[dict] = []
    monkeypatch.setattr(market, "send_html_email_best_effort", lambda **kw: inviate.append(kw) or True)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, producer, pane, _m = await _shop(db, organization_id, admin)
    assert row.auto_forward is False, "l'automatismo deve nascere spento"
    await market.update_producer(
        db, organization_id=organization_id, producer_id=producer.id, payload={"email": "ordini@caseificio.it"}
    )
    variante = (await _variants(db, pane))[0]

    # Spento: il pagamento non manda niente all'azienda.
    order = await _paid_order(db, organization_id, admin, customer, lines=[(variante.id, 1)])
    assert not [m for m in inviate if m["to"] == "ordini@caseificio.it"]
    await db.refresh(order)
    assert order.fulfillment_status == "NOT_SENT"

    # Acceso: parte da solo.
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"auto_forward": True})
    inviate.clear()
    altro = await _paid_order(db, organization_id, admin, customer, lines=[(variante.id, 1)])
    assert [m for m in inviate if m["to"] == "ordini@caseificio.it"]
    await db.refresh(altro)
    assert altro.fulfillment_status == "SENT"


@pytest.mark.asyncio
async def test_the_admin_deletes_a_product_never_ordered_but_not_one_already_ordered(db, organization_id):
    """Session 89: «Elimina» toglie davvero un prodotto mai venduto (con le sue
    varianti); uno già ordinato resta, perché gli ordini lo citano."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _producer, pane, miele = await _shop(db, organization_id, admin)
    [variante, *_] = await _variants(db, miele)
    await _paid_order(db, organization_id, admin, customer, lines=[(variante.id, 1)])

    await market.delete_product(db, organization_id=organization_id, product_id=pane.id, actor_user_id=admin.id)
    remaining = {p.id for p in await market.list_products(db, organization_id=organization_id)}
    assert pane.id not in remaining and miele.id in remaining
    assert await market._variants(db, pane.id) == []

    with pytest.raises(market.KappaMarketValidationError):
        await market.delete_product(db, organization_id=organization_id, product_id=miele.id, actor_user_id=admin.id)
    with pytest.raises(market.KappaMarketNotFoundError):
        await market.delete_product(db, organization_id=organization_id, product_id=pane.id, actor_user_id=admin.id)
