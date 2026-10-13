"""Marketplace 6 — «Marketplace VAITTO» (Session 88).

Prima i test di `test_kappa_market.py` rifatti sul clone, per fissare che
si comporta come l'originale; poi quelli del rifornimento dal feed di Vaitto:
prodotti nuovi spenti, prezzo costo × ricarico, marche e categorie in
italiano, un import che aggiorna solo ciò che decide Vaitto, un feed
troncato che non spegne il catalogo, e le righe d'ordine con SKU ed EAN per
inserire l'ordine su vaitto.com.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.carts import service as carts_service
from app.domains.vaitto_market import service as market
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
        # I test ereditati da Market Kappa verificano la modalità «IVA aggiunta»;
        # quella «IVA inclusa» (prezzo del marchio) ha i suoi test più sotto.
        updates={"enabled": True, "shipping_flat_cents": shipping_flat_cents, "shipping_days": "3-5",
                 "prices_include_vat": False},
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

    with pytest.raises(market.VaittoMarketValidationError):
        await market.create_product(
            db, organization_id=organization_id, actor_user_id=admin.id,
            payload={"name": "Senza varianti", "variants": []},
        )
    # E due schede della stessa azienda non si creano.
    with pytest.raises(market.VaittoMarketValidationError):
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
    with pytest.raises(market.VaittoMarketValidationError):
        await market.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variante.id, quantity=1,
        )


@pytest.mark.asyncio
async def test_the_quote_shows_final_prices_and_charges_one_shipping(db, organization_id):
    """Session 89: con i prezzi dal ricarico (IVA esclusa) il cliente vede e
    paga comunque il prezzo finale, IVA dentro; spedizione una volta per
    ordine, tetto JavCash somma delle righe."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _p, pane, miele = await _shop(db, organization_id, admin)
    mezzo_kg = (await _variants(db, pane))[0]
    vasetto = (await _variants(db, miele))[0]

    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id,
        lines=[(mezzo_kg.id, 2), (vasetto.id, 1)],
    )
    # 4,50 € e 9,00 € netti diventano 5,49 € e 10,98 € IVA inclusa.
    assert [i["unit_price_cents"] for i in quote["items"]] == [549, 1098]
    merce = 549 * 2 + 1098
    assert quote["items_cents"] == merce
    assert quote["vat_mode"] == "INCLUDED"
    assert quote["vat_cents"] == rules.vat_included_cents(gross_cents=merce, percentage=22)
    # Una spedizione sola, non una per riga.
    assert quote["shipping_cents"] == 490
    assert quote["amount_cents"] == merce + 490
    # Il tetto JavCash è la somma delle righe, spedizione esclusa.
    assert quote["max_creditable_cents"] == round(1098 * 25 / 100) + round(1098 * 25 / 100)
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
            db, organization_id=organization_id, customer_user_id=customer.id, shop="vaitto_market",
            variant_id=variante.id, quantity=quantita,
        )
    riepilogo = await carts_service.summary(
        db, organization_id=organization_id, customer_user_id=customer.id
    )
    sezione = riepilogo["sections"][0]
    assert sezione["shop"] == "vaitto_market" and len(sezione["items"]) == 2

    _cart, lines = await carts_service.checkout_lines(
        db, customer_user_id=customer.id, shop="vaitto_market"
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
    assert order.vat_mode == "INCLUDED"

    # Rinominare l'azienda non tocca l'ordine.
    await market.update_producer(
        db, organization_id=organization_id, producer_id=producer.id, payload={"name": "Caseificio Bianchi"},
    )
    items = await market.order_items(db, order)
    assert all(i.producer_name == "Caseificio Rossi" for i in items)

    await carts_service.clear(db, customer_user_id=customer.id, shop="vaitto_market")
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
    assert order.vat_amount_cents == rules.vat_included_cents(gross_cents=order.items_cents, percentage=22)
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
    with pytest.raises(market.VaittoMarketValidationError):
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
    with pytest.raises(market.VaittoMarketValidationError):
        await market.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variante.id, quantity=1,
        )
    with pytest.raises(carts_service.CartValidationError):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="vaitto_market",
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
    with pytest.raises(market.VaittoMarketValidationError):
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

    with pytest.raises(market.VaittoMarketValidationError):
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


# --- Il feed di Vaitto (Session 88) --------------------------------------------------------------

from sqlalchemy import select as _select  # noqa: E402

from app.domains.shop_categories.models import ShopCategory, ShopCategoryProduct  # noqa: E402
from app.domains.vaitto_market import feed as vaitto_feed  # noqa: E402
from app.domains.vaitto_market.models import SHOP, VaittoMarketProduct, VaittoMarketVariant  # noqa: E402

HEADER = (
    "product_id,variant_id,brand,product_name,slug,description,description_html,category,tags,sku,size,colour,"
    "retail_price,compare_at_price,wholesale_price,markup_pct,currency,stock_qty,dropship_available,image_url,"
    "image_url_2,weight_grams,requires_shipping,taxable,vaitto_product_url,parent_sku,product_type,subcategory,"
    "google_product_category,barcode,mpn,gender,age_group,condition,season,composition,availability,moq,"
    "lead_time,additional_image_urls,supplier_code,feed_generated_at"
)


def _row(pid, vid, *, brand="Herno", name="Piumino lungo", sku=None, size="M", colour="Black", cost="100.00",
         compare="450.00", stock=3, availability="in stock", sub="Down Jackets", barcode="8050000000001",
         retail="140.00"):
    values = [
        pid, vid, brand, name, "slug", '"Caldo, leggero"', "", "Clothing", "", sku or f"SKU-{vid}", size, colour,
        retail, compare, cost, "40", "EUR", str(stock), "true", f"https://vaitto.com/img/{pid}.jpg",
        "", "1500", "true", "true", f"https://vaitto.com/catalog/{pid}", "", "variation", sub, "", barcode, "",
        "Women", "adult", "new", "", "", availability, "1", "", "", "", "2026-09-29T00:00:00Z",
    ]
    return ",".join(values)


def _csv(*rows) -> bytes:
    return ("\ufeff" + HEADER + "\n" + "\n".join(rows) + "\n").encode("utf-8")


async def _vaitto_shop(db, organization_id, admin, *, markup=0):
    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456"),
    )
    row = await market.get_settings_row(db, organization_id=organization_id)
    await market.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"enabled": True, "markup_percentage": markup},
    )
    return row


@pytest.mark.asyncio
async def test_the_price_is_the_vaitto_suggested_one_plus_our_markup():
    """Session 88: si vende al prezzo suggerito da Vaitto; il nostro ricarico,
    di norma 0, si aggiunge sopra, al centesimo, senza arrotondamenti."""
    assert market.sale_price_cents(18113, 0) == 18113   # esattamente il suggerito
    assert market.sale_price_cents(18113, 10) == 19925  # 199,243 -> 199,25
    # Una variante senza suggerito (import vecchio) lo ricava dal costo + 40%,
    # mai dal costo da solo.
    senza = VaittoMarketVariant(cost_cents=10000, suggested_price_cents=None)
    assert market.price_base_cents(senza) == 14000


@pytest.mark.asyncio
async def test_the_feed_creates_products_switched_off_with_brand_and_italian_category(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    await _vaitto_shop(db, organization_id, admin)
    summary = await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1", size="S"), _row("p1", "v2", size="M", barcode=""),
                     _row("p2", "v3", brand="Unknown", sub="Sneakers", colour="")),
    )
    assert (summary["created"], summary["updated"]) == (2, 0)
    products = (await db.execute(
        _select(VaittoMarketProduct).where(VaittoMarketProduct.organization_id == organization_id)
    )).scalars().all()
    by_id = {p.vaitto_product_id: p for p in products}
    assert all(p.status == "INACTIVE" for p in products)
    herno = by_id["p1"]
    variants = await market._variants(db, herno.id)
    assert [v.label for v in variants] == ["Taglia S · Nero", "Taglia M · Nero"]
    # Il prezzo è il suggerito da Vaitto (140,00), il costo (100,00) resta
    # all'amministratore.
    assert variants[0].price_cents == 14000 and variants[0].cost_cents == 10000
    assert variants[0].suggested_price_cents == 14000
    assert variants[0].barcode == "8050000000001" and variants[1].barcode is None
    card = await market.product_read_dict(db, herno, admin=True)
    assert card["producer"]["name"] == "Herno"
    assert by_id["p2"].producer_id is None  # «Unknown» non diventa una marca
    names = {c.name for c in (await db.execute(
        _select(ShopCategory).where(ShopCategory.organization_id == organization_id, ShopCategory.shop == SHOP)
    )).scalars().all()}
    assert {"Piumini", "Sneakers"} <= names
    # Spento: il cliente non vede niente finché qualcuno non lo accende.
    assert await market.customer_products(db, organization_id=organization_id) == []


@pytest.mark.asyncio
async def test_a_new_feed_updates_what_vaitto_decides_and_keeps_what_we_decided(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    await _vaitto_shop(db, organization_id, admin)
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1"), _row("p1", "v2", size="L")),
    )
    product = (await db.execute(
        _select(VaittoMarketProduct).where(VaittoMarketProduct.vaitto_product_id == "p1")
    )).scalar_one()
    v1, v2 = await market._variants(db, product.id)
    # Le nostre scelte: nome, stato, un prezzo scritto a mano.
    await market.update_product(
        db, organization_id=organization_id, product_id=product.id,
        payload={"name": "Piumino Herno donna", "status": "ACTIVE"},
    )
    await market.update_variant(db, organization_id=organization_id, variant_id=v2.id, payload={"price_cents": 19900})

    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1", cost="120.00", retail="168.00", stock=7),
                     _row("p1", "v2", size="L", cost="120.00", retail="168.00")),
    )
    await db.refresh(product)
    await db.refresh(v1)
    await db.refresh(v2)
    assert (product.name, product.status) == ("Piumino Herno donna", "ACTIVE")
    assert (v1.cost_cents, v1.inventory, v1.price_cents) == (12000, 7, 16800)
    assert v2.price_locked and v2.price_cents == 19900

    # v2 sparisce dal feed, poi l'intero prodotto: non comprabili, non cancellati.
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_csv(_row("p1", "v1")),
    )
    await db.refresh(v2)
    assert v2.available_in_store is False and not market.variant_sellable(v2)
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_csv(_row("p9", "v9")),
    )
    await db.refresh(product)
    await db.refresh(v1)
    assert product.missing_from_feed and v1.available_in_store is False


@pytest.mark.asyncio
async def test_a_truncated_feed_does_not_switch_the_catalogue_off(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    await _vaitto_shop(db, organization_id, admin)
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(*[_row(f"p{i}", f"v{i}") for i in range(30)]),
    )
    summary = await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_csv(_row("p0", "v0")),
    )
    assert summary["truncated"] and "ATTENZIONE" in summary["text"]
    kept = (await db.execute(
        _select(VaittoMarketVariant).join(VaittoMarketProduct).where(VaittoMarketProduct.vaitto_product_id == "p5")
    )).scalar_one()
    assert kept.available_in_store is True


@pytest.mark.asyncio
async def test_a_file_in_another_format_is_refused_before_anything_changes(db, organization_id):
    with pytest.raises(vaitto_feed.VaittoFeedError, match="formato"):
        vaitto_feed.parse_feed(b"nome,prezzo\nMaglia,10\n")


@pytest.mark.asyncio
async def test_switching_on_a_whole_brand_and_the_order_carries_sku_and_ean(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    await _vaitto_shop(db, organization_id, admin)
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1", sku="HER-1-M"), _row("p2", "v2", brand="Dsquared2")),
    )
    herno = (await db.execute(
        _select(VaittoMarketProduct).where(VaittoMarketProduct.vaitto_product_id == "p1")
    )).scalar_one()
    with pytest.raises(market.VaittoMarketValidationError):
        await vaitto_feed.bulk_set_status(db, organization_id=organization_id, status="ACTIVE")
    assert await vaitto_feed.bulk_set_status(
        db, organization_id=organization_id, status="ACTIVE", producer_id=herno.producer_id,
    ) == 1
    cards = await market.customer_products(db, organization_id=organization_id)
    assert [c["name"] for c in cards] == ["Piumino lungo"] and cards[0]["compare_at_cents"] == 45000

    variant = (await market._variants(db, herno.id))[0]
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variant.id, quantity=1,
        address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    admin_view = await market.order_read_dict(db, order, admin=True)
    line = admin_view["items"][0]
    assert (line["supplier_sku"], line["barcode"]) == ("HER-1-M", "8050000000001")
    assert line["supplier_url"] == "https://vaitto.com/catalog/p1"
    customer_view = await market.order_read_dict(db, order, admin=False)
    assert "supplier_sku" not in customer_view["items"][0]


@pytest.mark.asyncio
async def test_the_shop_javcash_percentage_applies_to_all_but_the_hand_picked_ones(db, organization_id):
    """Session 88: la percentuale JavCash si imposta una volta per tutto il
    negozio; un prodotto cambiato a mano resta com'è finché non lo si
    riporta a quella del negozio."""
    admin = await _user(db, organization_id, "ADMIN")
    row = await _vaitto_shop(db, organization_id, admin)
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"credit_percentage": 25})
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1"), _row("p2", "v2"), _row("p3", "v3")),
    )
    by_id = {p.vaitto_product_id: p for p in (await db.execute(
        _select(VaittoMarketProduct).where(VaittoMarketProduct.organization_id == organization_id)
    )).scalars().all()}
    assert {p.credit_discount_percentage for p in by_id.values()} == {25}  # i nuovi nascono con quella del negozio

    # p2 personalizzato a mano; salvare p3 senza cambiarla non lo personalizza.
    await market.update_product(
        db, organization_id=organization_id, product_id=by_id["p2"].id, payload={"credit_discount_percentage": 50},
    )
    await market.update_product(
        db, organization_id=organization_id, product_id=by_id["p3"].id,
        payload={"name": "Nuovo nome", "credit_discount_percentage": 25},
    )
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"credit_percentage": 20})
    for p in by_id.values():
        await db.refresh(p)
    assert (by_id["p1"].credit_discount_percentage, by_id["p2"].credit_discount_percentage,
            by_id["p3"].credit_discount_percentage) == (20, 50, 20)
    assert by_id["p2"].credit_locked and not by_id["p3"].credit_locked

    # «Usa quella del negozio»
    await market.update_product(
        db, organization_id=organization_id, product_id=by_id["p2"].id, payload={"credit_locked": False},
    )
    await db.refresh(by_id["p2"])
    assert (by_id["p2"].credit_discount_percentage, by_id["p2"].credit_locked) == (20, False)
    with pytest.raises(Exception):
        await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"credit_percentage": 100})


@pytest.mark.asyncio
async def test_javcash_from_margin_follows_the_users_formula(db, organization_id):
    """Session 89, formula dell'utente: guadagno = prezzo al cliente senza IVA
    − prezzo a noi (preso così com'è, niente spedizione); metà del guadagno in
    percentuale del prezzo IVA inclusa è la parte pagabile in JavCash; una
    variante che non copre il costo non si vende."""
    admin = await _user(db, organization_id, "ADMIN")
    row = await _vaitto_shop(db, organization_id, admin)
    await market.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"credit_mode": "MARGIN", "credit_margin_share": 50},
    )
    assert row.prices_include_vat
    # La giacca Moose Knuckles vera: costo 129,38, prezzo del marchio 450.
    giacca = VaittoMarketVariant(cost_cents=12938, price_cents=45000)
    assert market.our_total_cost_cents(giacca, row, 22) == 12938
    assert market.variant_gain_cents(giacca, row, 22) == 36885 - 12938   # 450 / 1,22 − 129,38
    assert market.margin_credit_percentage([giacca], settings=row, vat_percentage=22) == 26
    # Al prezzo dal ricarico (258,76 senza IVA, 315,69 con): 129,38 di
    # guadagno, metà 64,69 = 20,5% di 315,69 → 20%.
    row.prices_include_vat = False
    ricarico = VaittoMarketVariant(cost_cents=12938, price_cents=25876)
    assert market.variant_gain_cents(ricarico, row, 22) == 12938
    assert market.margin_credit_percentage([ricarico], settings=row, vat_percentage=22) == 20
    row.prices_include_vat = True

    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(
            _row("p1", "v1", cost="129.38", retail="181.13") + ",450.00,rrp,450.00",
            _row("p2", "v2", cost="300.00", retail="420.00") + ",350.00,rrp,350.00",
        ).replace(b"feed_generated_at", b"feed_generated_at,rrp,price_basis,your_price"),
    )
    by_id = {p.vaitto_product_id: p for p in (await db.execute(
        _select(VaittoMarketProduct).where(VaittoMarketProduct.organization_id == organization_id)
    )).scalars().all()}
    v1 = (await market._variants(db, by_id["p1"].id))[0]
    v2 = (await market._variants(db, by_id["p2"].id))[0]
    # Si legge your_price (il prezzo del marchio), non retail_price.
    assert v1.price_cents == 45000 and v1.compare_at_cents == 45000
    assert by_id["p1"].credit_discount_percentage == 26
    # 350 / 1,22 = 286,89 < 300: in perdita, non si vende.
    assert v2.below_cost and not market.variant_sellable(v2)
    assert by_id["p2"].credit_discount_percentage == 0


@pytest.mark.asyncio
async def test_with_the_brand_price_the_vat_is_inside_not_added(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row = await _vaitto_shop(db, organization_id, admin)
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"shipping_flat_cents": 500})
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1", cost="129.38", retail="181.13") + ",450.00,rrp,450.00").replace(
            b"feed_generated_at", b"feed_generated_at,rrp,price_basis,your_price"
        ),
    )
    product = (await db.execute(
        _select(VaittoMarketProduct).where(VaittoMarketProduct.vaitto_product_id == "p1")
    )).scalar_one()
    await market.update_product(db, organization_id=organization_id, product_id=product.id, payload={"status": "ACTIVE"})
    variant = (await market._variants(db, product.id))[0]
    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variant.id, quantity=1,
    )
    # Il cliente paga 450 + 5 di spedizione, non 450 + 22%: l'IVA è dentro.
    assert quote["amount_cents"] == 45000 + 500
    assert quote["vat_cents"] == rules.vat_included_cents(gross_cents=45000, percentage=22)
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variant.id, quantity=1,
        address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    assert order.vat_mode == "INCLUDED" and order.amount_cents == 45500


@pytest.mark.asyncio
async def test_the_feed_says_whether_its_prices_include_vat(db, organization_id):
    """price_basis «markup» = prezzi senza IVA (si aggiunge), «rrp» = prezzo del
    marchio con l'IVA dentro (si scorpora): lo decide il feed, non la casella."""
    admin = await _user(db, organization_id, "ADMIN")
    row = await _vaitto_shop(db, organization_id, admin)
    header = (b"feed_generated_at", b"feed_generated_at,rrp,price_basis,your_price")
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1", cost="129.38", retail="181.13") + ",450.00,markup,181.13").replace(*header),
    )
    await db.refresh(row)
    assert row.prices_include_vat is False
    variant = (await db.execute(_select(VaittoMarketVariant))).scalars().first()
    assert not variant.below_cost  # 181,13 senza IVA copre 129,38 + 5
    await vaitto_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_csv(_row("p1", "v1", cost="129.38", retail="181.13") + ",450.00,rrp,450.00").replace(*header),
    )
    await db.refresh(row)
    await db.refresh(variant)
    assert row.prices_include_vat is True and variant.price_cents == 45000

