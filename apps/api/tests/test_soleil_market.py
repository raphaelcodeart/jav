"""«Market 7» — «Marketplace SOLEIL» (Session 90), clone di Shop Beauty.

Prima i test di `test_symphonya_market.py` rifatti sul clone, per fissare che
si comporta come l'originale; poi quelli del rifornimento dall'Excel di
SoleilDrop: prodotti nuovi spenti, prezzo = prezzo di vendita ivato del file,
marche e categorie, un import che aggiorna solo ciò che decide SoleilDrop, un
file troncato che non spegne il catalogo, e le righe d'ordine con codice ed
EAN per inserire l'ordine nel portale SoleilDrop.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.carts import service as carts_service
from app.domains.soleil_market import service as market
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

    with pytest.raises(market.SoleilMarketValidationError):
        await market.create_product(
            db, organization_id=organization_id, actor_user_id=admin.id,
            payload={"name": "Senza varianti", "variants": []},
        )
    # E due schede della stessa azienda non si creano.
    with pytest.raises(market.SoleilMarketValidationError):
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
    with pytest.raises(market.SoleilMarketValidationError):
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
            db, organization_id=organization_id, customer_user_id=customer.id, shop="soleil_market",
            variant_id=variante.id, quantity=quantita,
        )
    riepilogo = await carts_service.summary(
        db, organization_id=organization_id, customer_user_id=customer.id
    )
    sezione = riepilogo["sections"][0]
    assert sezione["shop"] == "soleil_market" and len(sezione["items"]) == 2

    _cart, lines = await carts_service.checkout_lines(
        db, customer_user_id=customer.id, shop="soleil_market"
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

    await carts_service.clear(db, customer_user_id=customer.id, shop="soleil_market")
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
    with pytest.raises(market.SoleilMarketValidationError):
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
    with pytest.raises(market.SoleilMarketValidationError):
        await market.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id,
            variant_id=variante.id, quantity=1,
        )
    with pytest.raises(carts_service.CartValidationError):
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="soleil_market",
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
    with pytest.raises(market.SoleilMarketValidationError):
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

    with pytest.raises(market.SoleilMarketValidationError):
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


# --- L'Excel di SoleilDrop (Session 90) --------------------------------------------------------------

from sqlalchemy import select as _select  # noqa: E402

from app.domains.shop_categories.models import ShopCategory  # noqa: E402
from app.domains.soleil_market import feed as soleil_feed  # noqa: E402
from app.domains.soleil_market.models import SHOP, SoleilMarketProduct, SoleilMarketVariant  # noqa: E402

COLUMNS = [
    "Codice", "Nome", "Marca", "EAN", "Categoria", "Prezzo Soleil", "Prezzo vendita (imponibile)", "IVA %",
    "Prezzo vendita (ivato)", "Peso kg", "Unità", "Pubblicato", "Disponibile", "Descrizione breve",
    "Descrizione", "Meta title", "Meta description", "Immagini",
]


def _item(code, *, brand="Lancôme", name="La Vie Est Belle, Eau de Parfum, 50 ml", cost=14.18, gross=40.0,
          available="Sì", category="Profumi > Donna", unit="PZ", ean="3605532612768", description="Un profumo."):
    """Una riga come la scrive l'export «Excel generico» del portale SoleilDrop."""
    return {
        "Codice": code, "Nome": name, "Marca": brand, "EAN": ean, "Categoria": category,
        "Prezzo Soleil": cost, "Prezzo vendita (imponibile)": round(gross / 1.22, 2) if gross else 0,
        "IVA %": 22, "Prezzo vendita (ivato)": gross, "Peso kg": 0.3, "Unità": unit, "Pubblicato": "Sì",
        "Disponibile": available, "Descrizione breve": "", "Descrizione": description, "Meta title": "",
        "Meta description": "", "Immagini": f"https://img.soleildrop.com/{code}-1.jpg, https://img.soleildrop.com/{code}-2.jpg",
    }


def _xlsx(*items) -> bytes:
    import io

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Catalogo"
    sheet.append(COLUMNS)
    for item in items:
        sheet.append([item.get(c) for c in COLUMNS])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def _soleil_shop(db, organization_id, admin, *, markup=0):
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
async def test_the_price_is_the_soleil_suggested_one_plus_our_markup():
    """Si vende al prezzo di vendita del file SoleilDrop; il nostro ricarico,
    di norma 0, si aggiunge sopra, al centesimo, senza arrotondamenti."""
    assert market.sale_price_cents(18113, 0) == 18113   # esattamente il suggerito
    assert market.sale_price_cents(18113, 10) == 19925  # 199,243 -> 199,25
    # Una variante senza suggerito (import vecchio) lo ricava dal costo + 40%,
    # mai dal costo da solo.
    senza = SoleilMarketVariant(cost_cents=10000, suggested_price_cents=None)
    assert market.price_base_cents(senza) == 14000


@pytest.mark.asyncio
async def test_the_catalogue_arrives_switched_off_at_the_selling_price_with_vat_inside(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    await _soleil_shop(db, organization_id, admin)
    summary = await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_xlsx(
            _item("SD-71"),
            _item("SD-72", brand="", name="Crema mani", cost=10.0, gross=0, category="Corpo", ean="8001"),
            _item("SD-73", unit="CT", ean="8002"),
        ),
    )
    assert (summary["created"], summary["updated"]) == (3, 0)
    by_id = {
        p.soleil_product_id: p for p in (await db.execute(
            _select(SoleilMarketProduct).where(SoleilMarketProduct.organization_id == organization_id)
        )).scalars().all()
    }
    assert all(p.status == "INACTIVE" for p in by_id.values())
    [profumo] = await market._variants(db, by_id["SD-71"].id)
    # Prezzo al cliente = prezzo di vendita ivato del file; il Prezzo Soleil è il costo.
    assert (profumo.price_cents, profumo.cost_cents) == (4000, 1418)
    assert (profumo.sku, profumo.barcode, profumo.label) == ("SD-71", "3605532612768", "Unica")
    assert profumo.inventory is None and market.variant_sellable(profumo)
    assert by_id["SD-71"].images == [
        "https://img.soleildrop.com/SD-71-1.jpg", "https://img.soleildrop.com/SD-71-2.jpg",
    ]
    assert by_id["SD-71"].description == "Un profumo."
    assert (by_id["SD-71"].category_name, by_id["SD-71"].subcategory) == ("Profumi", "Donna")
    # Senza prezzo di vendita: costo + 40% + IVA (10,00 -> 17,08).
    [crema] = await market._variants(db, by_id["SD-72"].id)
    assert crema.price_cents == 1708 and by_id["SD-72"].producer_id is None
    # Venduto a cartone: si dice nell'etichetta.
    [cartone] = await market._variants(db, by_id["SD-73"].id)
    assert cartone.label == "CT"
    card = await market.product_read_dict(db, by_id["SD-71"], admin=True)
    assert card["producer"]["name"] == "Lancôme"
    names = {c.name for c in (await db.execute(
        _select(ShopCategory).where(ShopCategory.organization_id == organization_id, ShopCategory.shop == SHOP)
    )).scalars().all()}
    assert {"Profumi", "Corpo"} <= names
    row = await market.get_settings_row(db, organization_id=organization_id)
    assert row.prices_include_vat is True and "3 referenze" in row.last_import_summary
    assert await market.customer_products(db, organization_id=organization_id) == []


@pytest.mark.asyncio
async def test_javcash_follows_the_users_formula_and_loss_makers_are_hidden(db, organization_id):
    """La formula di Vaitto e Symphonya: guadagno = prezzo senza IVA − costo così
    com'è; JavCash = metà del guadagno in % del prezzo IVA inclusa.
    40,00 ÷ 1,22 = 32,79 − 14,18 = 18,61, metà 9,30 = 23,3% di 40 → 23%.
    8,00 ÷ 1,22 = 6,56 − 7,00 = −0,44: in perdita, non si vende."""
    admin = await _user(db, organization_id, "ADMIN")
    await _soleil_shop(db, organization_id, admin)
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_xlsx(_item("1"), _item("2", name="Smalto", cost=7.0, gross=8.0, ean="1")),
    )
    products = {
        p.soleil_product_id: p for p in (await db.execute(
            _select(SoleilMarketProduct).where(SoleilMarketProduct.organization_id == organization_id)
        )).scalars().all()
    }
    assert products["1"].credit_discount_percentage == 23
    [smalto] = await market._variants(db, products["2"].id)
    assert smalto.below_cost is True
    await soleil_feed.bulk_set_status(
        db, organization_id=organization_id, status="ACTIVE", producer_id=products["1"].producer_id,
    )
    assert [c["name"] for c in await market.customer_products(db, organization_id=organization_id)] == [
        "La Vie Est Belle, Eau de Parfum, 50 ml"
    ]


@pytest.mark.asyncio
async def test_a_new_import_updates_what_soleil_decides_and_keeps_what_we_decided(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    await _soleil_shop(db, organization_id, admin)
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_xlsx(_item("1")),
    )
    product = (await db.execute(
        _select(SoleilMarketProduct).where(SoleilMarketProduct.soleil_product_id == "1")
    )).scalar_one()
    await market.update_product(
        db, organization_id=organization_id, product_id=product.id,
        payload={"name": "La Vie Est Belle 50 ml", "status": "ACTIVE"},
    )
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_xlsx(_item("1", cost=15.0, gross=42.0)),
    )
    await db.refresh(product)
    [variant] = await market._variants(db, product.id)
    assert (product.name, product.status) == ("La Vie Est Belle 50 ml", "ACTIVE")
    assert (variant.cost_cents, variant.price_cents, variant.inventory) == (1500, 4200, None)
    # Non più disponibile da SoleilDrop: resta, ma non si compra.
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_xlsx(_item("1", available="No")),
    )
    await db.refresh(variant)
    assert variant.inventory == 0 and not market.variant_sellable(variant)
    # Sparito dal catalogo: non comprabile, non cancellato.
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_xlsx(_item("9", ean="9")),
    )
    await db.refresh(product)
    await db.refresh(variant)
    assert product.missing_from_feed and not market.variant_sellable(variant)


@pytest.mark.asyncio
async def test_a_truncated_catalogue_does_not_switch_the_shop_off(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    await _soleil_shop(db, organization_id, admin)
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_xlsx(*[_item(str(i), ean=str(i)) for i in range(30)]),
    )
    summary = await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_xlsx(_item("0", ean="0")),
    )
    assert summary["truncated"] and "ATTENZIONE" in summary["text"]


@pytest.mark.asyncio
async def test_a_file_that_is_not_the_soleil_catalogue_is_refused(db, organization_id):
    with pytest.raises(soleil_feed.SoleilFeedError, match="Prezzo Soleil"):
        soleil_feed.parse_feed(b"nome,prezzo\nMaglia,10\n")
    with pytest.raises(soleil_feed.SoleilFeedError, match="nessuna referenza"):
        soleil_feed.parse_feed(_xlsx())
    with pytest.raises(soleil_feed.SoleilFeedError, match="non si apre"):
        soleil_feed.parse_feed(b"PK\x03\x04 rotto")


def test_the_same_export_saved_as_csv_is_read_too():
    """L'Excel salvato come CSV (Excel italiano: punto e virgola, virgola
    decimale) dà le stesse referenze."""
    csv_text = (
        ";".join(COLUMNS) + "\n"
        + "SD-1;Crema;Nivea;4005808;Corpo;3,50;6,56;22;8,00;0,2;PZ;Sì;Sì;;Idratante;;;https://img.soleildrop.com/1.jpg\n"
    )
    groups = soleil_feed.parse_feed(csv_text.encode("utf-8-sig"))
    [row] = groups["SD-1"]
    assert (soleil_feed._cents(row["wholesale_price"]), row["suggested_cents"], row["brand"]) == (350, 800, "Nivea")


@pytest.mark.asyncio
async def test_the_quote_has_vat_inside_and_the_order_carries_the_ean(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row = await _soleil_shop(db, organization_id, admin)
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"shipping_flat_cents": 690})
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id, content=_xlsx(_item("1")),
    )
    product = (await db.execute(
        _select(SoleilMarketProduct).where(SoleilMarketProduct.soleil_product_id == "1")
    )).scalar_one()
    await market.update_product(db, organization_id=organization_id, product_id=product.id, payload={"status": "ACTIVE"})
    [variant] = await market._variants(db, product.id)
    quote = await market.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variant.id, quantity=2,
    )
    assert quote["vat_mode"] == "INCLUDED" and quote["amount_cents"] == 2 * 4000 + 690
    assert quote["vat_cents"] == rules.vat_included_cents(gross_cents=8000, percentage=22)
    order = await market.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variant.id, quantity=1,
        address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    line = (await market.order_read_dict(db, order, admin=True))["items"][0]
    assert (line["supplier_sku"], line["barcode"]) == ("1", "3605532612768")


@pytest.mark.asyncio
async def test_the_customer_gets_the_catalogue_a_page_at_a_time(db, organization_id):
    """Come Shop Beauty: con ~31.000 prodotti la vetrina intera pesava 63 MB. Il
    cliente riceve una pagina per volta, con ricerca e categoria filtrate sul
    server, e nessun prodotto ripetuto o saltato tra una pagina e l'altra."""
    admin = await _user(db, organization_id, "ADMIN")
    await _soleil_shop(db, organization_id, admin)
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_xlsx(
            *[_item(str(i), name=f"Profumo {i}", ean=str(1000 + i)) for i in range(5)],
            _item("9", brand="", name="Crema mani 100% naturale", cost=10.0, gross=0, category="Corpo > Mani",
                  ean="9"),
        ),
    )
    first = await market.customer_products_page(db, organization_id=organization_id)
    assert (first["items"], first["shop_total"]) == ([], 0)  # tutto spento all'import
    for category in ("Profumi", "Corpo"):
        await soleil_feed.bulk_set_status(
            db, organization_id=organization_id, status="ACTIVE", category_name=category,
        )

    seen = []
    for offset in (0, 2, 4):
        page = await market.customer_products_page(db, organization_id=organization_id, offset=offset, limit=2)
        assert (page["total"], page["shop_total"]) == (6, 6)
        seen += [c["name"] for c in page["items"]]
    assert sorted(seen) == sorted([f"Profumo {i}" for i in range(5)] + ["Crema mani 100% naturale"])

    found = await market.customer_products_page(db, organization_id=organization_id, search="crema")
    assert ([c["name"] for c in found["items"]], found["total"], found["shop_total"]) == (
        ["Crema mani 100% naturale"], 1, 6,
    )
    # Il «%» del cliente è un carattere, non un jolly del database.
    assert (await market.customer_products_page(db, organization_id=organization_id, search="0%"))["total"] == 1
    assert (await market.customer_products_page(db, organization_id=organization_id, search="%"))["total"] == 1

    corpo = (await db.execute(_select(ShopCategory).where(
        ShopCategory.organization_id == organization_id, ShopCategory.shop == SHOP, ShopCategory.name == "Corpo",
    ))).scalar_one()
    by_category = await market.customer_products_page(db, organization_id=organization_id, category_id=corpo.id)
    assert [c["name"] for c in by_category["items"]] == ["Crema mani 100% naturale"]
    assert corpo.id in by_category["category_ids"]


@pytest.mark.asyncio
async def test_pages_fill_up_past_hidden_products_and_never_repeat_one(db, organization_id):
    """marketplaces/paging.py, comune a tutti i Marketplace: un prodotto
    acceso che non dà scheda (esaurito, non spedibile) non lascia pagine a
    metà, e `next_offset` riprende esattamente dopo l'ultimo letto."""
    from app.domains.marketplaces import paging

    admin = await _user(db, organization_id, "ADMIN")
    await _soleil_shop(db, organization_id, admin)
    await soleil_feed.import_feed(
        db, organization_id=organization_id, actor_user_id=admin.id,
        content=_xlsx(*[_item(str(i), name=f"Profumo {i}", ean=str(2000 + i)) for i in range(7)]),
    )
    await soleil_feed.bulk_set_status(
        db, organization_id=organization_id, status="ACTIVE", category_name="Profumi",
    )
    hidden = {"Profumo 1", "Profumo 2", "Profumo 5"}

    async def cards(products):
        return [None if p.name in hidden else {"name": p.name} for p in products]

    seen, offset, pages = [], 0, 0
    while offset is not None:
        page = await paging.customer_page(
            db, model=SoleilMarketProduct, shop=SHOP, organization_id=organization_id,
            build_cards=cards, offset=offset, limit=2,
        )
        assert len(page["items"]) == 2 or page["next_offset"] is None
        seen += [c["name"] for c in page["items"]]
        offset, pages = page["next_offset"], pages + 1
    assert sorted(seen) == ["Profumo 0", "Profumo 3", "Profumo 4", "Profumo 6"]
    assert pages == 2
