"""La Loja del club (club/loja.py, docs/club-portal.md «La Loja del club»).

Le promesse: per chi è un articolo (il modello dell'altro sesso non si
vede; l'alta competizione si vede chiusa; il FIJ e il rosa si vedono e non
si comprano) vale all'ordine, non solo a schermo; l'alta competizione la
segnano segreteria e treinador solo nei piani che la permettono; il
carrello diventa un ordine per riga, ognuno con la sua quota, tutti o
nessuno; la scorta scende e torna con l'annullamento; il judogi resta un
ordine di judogi e finisce nell'armadio dell'atleta, da cui esce quello
restituito con la permuta; lo shop di un club non si compra più dallo Shop.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.domains.club import judogi, loja
from app.domains.club.models import Club, ClubCompetition, ClubCompetitionEntry, ClubFee, ClubPlan
from app.domains.club.operations_models import ClubCartItem, ClubEquipmentOrder
from app.domains.club.service import ClubValidationError
from app.domains.jav_market.models import JavMarketProduct, JavMarketVariant
from tests.test_club_area_extras import _client
from tests.test_club_fees import _athlete, _plans, _user

TODAY = date.today()


def _born(years: int) -> date:
    return date(TODAY.year - years, 1, 1)


async def _setup(db, scope):
    club = await db.get(Club, scope.club_id)
    await judogi.seed_prices(db, club=club)
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    maria = await _athlete(db, scope, parent, birth_date=_born(12), first_name="Maria", sex="F", today=TODAY)
    joao = await _athlete(db, scope, parent, birth_date=_born(16), first_name="João", sex="M", today=TODAY)
    maria.height_cm, joao.height_cm = 138, 172
    await db.commit()
    return club, admin, parent, maria, joao


async def _product(db, scope, admin, name, *, sex="ALL", hc=False, kit=False, needs_name=False, variants=None):
    product = JavMarketProduct(organization_id=scope.organization_id, club_id=scope.club_id, name=name,
                               description="", images=[], created_by_user_id=admin.id, audience_sex=sex,
                               high_competition_only=hc, club_kit=kit, needs_name=needs_name)
    db.add(product)
    await db.flush()
    out = []
    for label, cents, height, stock in variants or [("Unica", 1500, None, None)]:
        v = JavMarketVariant(product_id=product.id, label=label, price_cents=cents, max_height_cm=height,
                             inventory=stock)
        db.add(v)
        out.append(v)
    await db.commit()
    return product, out


async def test_who_can_buy_what(db, scope):
    club, admin, parent, maria, joao = await _setup(db, scope)
    shirt_f, _ = await _product(db, scope, admin, "T-shirt", sex="F", kit=True,
                                variants=[("10 anos", 1500, 140, None), ("12 anos", 1500, 152, None)])
    shirt_m, _ = await _product(db, scope, admin, "T-shirt", sex="M", kit=True, variants=[("M", 1500, 175, None)])
    elite, (elite_v,) = await _product(db, scope, admin, "Casaco da seleção", hc=True)

    view = await loja.shop(db, scope=scope, club=club, user_id=parent.id, athlete_id=maria.id, today=TODAY)
    names = {(p["name"], p["audience_sex"]): p for p in view["products"]}
    # La t-shirt dei ragazzi non c'è; il casaco della selezione sì, chiuso.
    assert ("T-shirt", "M") not in names and names[("Casaco da seleção", "ALL")]["lock"] == "HIGH_COMPETITION"
    # La taglia suggerita arriva all'altezza (138 → «10 anos»).
    tee = names[("T-shirt", "F")]
    assert next(v["label"] for v in tee["variants"] if v["id"] == tee["suggested_variant_id"]) == "10 anos"
    locks = {(j["kimono_type"], j["color"]): j["lock"] for j in view["judogis"]}
    assert locks[("FIJ_APPROVED", "WHITE")] == "HIGH_COMPETITION" and locks[("TRAINING", "PINK")] is None
    assert [k["state"] for k in view["kit"]] == ["MISSING", "MISSING"]

    view = await loja.shop(db, scope=scope, club=club, user_id=parent.id, athlete_id=joao.id, today=TODAY)
    locks = {(j["kimono_type"], j["color"]): j["lock"] for j in view["judogis"]}
    assert locks[("TRAINING", "PINK")] == "GIRLS_ONLY" and locks[("TRAINING", "WHITE_PINK_STRIPES")] == "GIRLS_ONLY"

    # Le regole valgono all'ordine, non solo a schermo.
    with pytest.raises(ClubValidationError, match="ragazze"):
        await loja.add_to_cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY, data={
            "athlete_id": joao.id, "kind": "JUDOGI",
            "judogi": {"kimono_type": "TRAINING", "color": "PINK", "brand": "Tochi Gi", "kimono_name": "João"}})
    with pytest.raises(ClubValidationError, match="alta competizione"):
        await loja.buy_now(db, scope=scope, club=club, user_id=parent.id, today=TODAY,
                           data={"athlete_id": joao.id, "kind": "PRODUCT", "variant_id": elite_v.id})
    with pytest.raises(ClubValidationError, match="non è per questo atleta"):
        await loja.place_product_order(db, scope=scope, athlete=joao, actor_user_id=parent.id,
                                       variant_id=(await db.execute(select(JavMarketVariant.id).where(
                                           JavMarketVariant.product_id == shirt_f.id))).scalars().first(),
                                       quantity=1, name=None, today=TODAY)
    await db.rollback()
    for obj in (joao, admin, parent, club, elite_v):
        await db.refresh(obj)

    # L'alta competizione: solo in un piano che la permette.
    with pytest.raises(ClubValidationError, match="Grupo 3"):
        await loja.set_high_competition(db, scope=scope, athlete=joao, actor_user_id=admin.id, value=True)
    plan = await db.get(ClubPlan, joao.plan_id)
    plan.allows_high_competition = True
    await db.commit()
    await loja.set_high_competition(db, scope=scope, athlete=joao, actor_user_id=admin.id, value=True)
    assert await loja.is_high_competition(db, joao)
    result = await loja.buy_now(db, scope=scope, club=club, user_id=parent.id, today=TODAY,
                                data={"athlete_id": joao.id, "kind": "PRODUCT", "variant_id": elite_v.id})
    assert result["orders"][0]["kind"] == "PRODUCT" and len(result["fee_ids"]) == 1
    # Cambiato di piano, il segno resta ma non vale più.
    plan.allows_high_competition = False
    await db.commit()
    assert not await loja.is_high_competition(db, joao)


async def test_cart_makes_one_order_per_line(db, scope):
    club, admin, parent, maria, joao = await _setup(db, scope)
    bag, (bag_v,) = await _product(db, scope, admin, "Saco com o nome", needs_name=True,
                                   variants=[("Unica", 3000, None, 2)])
    owned = await loja.add_owned_judogi(db, scope=scope, athlete=maria, actor_user_id=admin.id, today=TODAY, data={
        "kimono_type": "TRAINING", "color": "WHITE", "brand": "Tochi Gi", "size_cm": 120})
    assert owned.origin == "MANUAL" and owned.fee_id is None

    await loja.add_to_cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY, data={
        "athlete_id": maria.id, "kind": "JUDOGI", "judogi": {
            "kimono_type": "TRAINING", "color": "WHITE", "brand": "Matsuru", "kimono_name": "Maria",
            "trade_in": {"owned_order_id": str(owned.id)}}})
    with pytest.raises(ClubValidationError, match="nome"):
        await loja.add_to_cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY,
                               data={"athlete_id": joao.id, "kind": "PRODUCT", "variant_id": bag_v.id})
    with pytest.raises(ClubValidationError, match="restano 2"):
        await loja.add_to_cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY, data={
            "athlete_id": joao.id, "kind": "PRODUCT", "variant_id": bag_v.id, "quantity": 3, "name": "João"})
    await loja.add_to_cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY, data={
        "athlete_id": joao.id, "kind": "PRODUCT", "variant_id": bag_v.id, "quantity": 2, "name": "João Silva"})

    cart = await loja.cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY)
    judogi_line = next(i for i in cart["items"] if i["kind"] == "JUDOGI")
    # Matsuru bianco 140 = 31 € + 35 € − metà del Tochi Gi 120 restituito (25 €).
    assert judogi_line["price_cents"] == 3100 + 3500 - 1250
    assert cart["total_cents"] == judogi_line["price_cents"] + 6000 and cart["can_checkout"]

    result = await loja.checkout(db, scope=scope, club=club, user_id=parent.id, item_ids=None, today=TODAY)
    assert sorted(o["kind"] for o in result["orders"]) == ["JUDOGI", "PRODUCT"] and len(result["fee_ids"]) == 2
    assert (await db.execute(select(ClubCartItem))).first() is None
    fees = list((await db.execute(select(ClubFee).where(ClubFee.id.in_(result["fee_ids"])))).scalars())
    assert sorted(f.amount_cents for f in fees) == sorted([judogi_line["price_cents"], 6000])
    assert all(f.kind == "EQUIPMENT" and f.status == "DUE" for f in fees)
    await db.refresh(bag_v)
    assert bag_v.inventory == 0

    # La segreteria consegna il judogi: il Tochi Gi restituito esce dall'armadio.
    new_id = next(o["id"] for o in result["orders"] if o["kind"] == "JUDOGI")
    bag_order = next(o["id"] for o in result["orders"] if o["kind"] == "PRODUCT")
    for status in ("IN_PREPARATION", "DELIVERED"):
        await judogi.update_order(db, scope=scope, order_id=new_id, actor_user_id=admin.id,
                                  data={"status": status}, today=TODAY)
    await db.refresh(owned)
    assert owned.retired_reason == "TRADED_IN"
    wardrobe = (await loja.wardrobe(db, athletes=[maria]))[maria.id]
    assert [(w["brand"], w["status"]) for w in wardrobe] == [("Matsuru", "DELIVERED")]
    # Annullato il saco, la scorta torna.
    await judogi.update_order(db, scope=scope, order_id=bag_order, actor_user_id=admin.id,
                              data={"status": "CANCELLED"}, today=TODAY)
    await db.refresh(bag_v)
    assert bag_v.inventory == 2
    # Gli ordini dei prodotti stanno con quelli dei judogi; l'armadio a mano no.
    rows = await judogi.admin_orders(db, scope=scope)
    assert {r["kind"] for r in rows} == {"JUDOGI", "PRODUCT"} and all(r["origin"] == "ORDER" for r in rows)
    assert "Saco com o nome" in judogi.orders_csv(rows)


async def test_checkout_is_all_or_nothing(db, scope):
    club, admin, parent, maria, joao = await _setup(db, scope)
    _tee, (tee_v,) = await _product(db, scope, admin, "T-shirt", variants=[("S", 1500, None, 1)])
    await loja.add_to_cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY,
                           data={"athlete_id": maria.id, "kind": "PRODUCT", "variant_id": tee_v.id})
    await loja.add_to_cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY,
                           data={"athlete_id": joao.id, "kind": "PRODUCT", "variant_id": tee_v.id})
    cart = await loja.cart(db, scope=scope, club=club, user_id=parent.id, today=TODAY)
    assert cart["can_checkout"]  # una a testa: la scorta di 1 basta per ognuna, non per tutte e due
    with pytest.raises(ClubValidationError):
        await loja.checkout(db, scope=scope, club=club, user_id=parent.id, item_ids=None, today=TODAY)
    await db.rollback()
    await db.refresh(parent)
    assert (await db.execute(select(ClubEquipmentOrder))).first() is None
    assert len(list((await db.execute(select(ClubCartItem))).scalars())) == 2


async def test_wardrobe_for_the_next_competition(db, scope):
    club, admin, parent, maria, joao = await _setup(db, scope)
    await loja.add_owned_judogi(db, scope=scope, athlete=joao, actor_user_id=admin.id, today=TODAY, data={
        "kimono_type": "TRAINING", "color": "WHITE", "brand": "NKL", "size_cm": 170})
    await loja.add_owned_judogi(db, scope=scope, athlete=joao, actor_user_id=admin.id, today=TODAY, data={
        "kimono_type": "TRAINING", "color": "BLUE", "brand": "NKL", "size_cm": 160})
    comp = ClubCompetition(organization_id=scope.organization_id, club_id=scope.club_id, name="Taça do Algarve",
                           starts_on=TODAY + timedelta(days=8), ends_on=TODAY + timedelta(days=8),
                           registration_deadline=TODAY + timedelta(days=3), created_by_user_id=admin.id)
    db.add(comp)
    await db.flush()
    db.add(ClubCompetitionEntry(organization_id=scope.organization_id, club_id=scope.club_id, competition_id=comp.id,
                                athlete_id=joao.id, registered_by_user_id=admin.id))
    await db.commit()
    board = await loja.staff_judogis(db, scope=scope, user_id=admin.id, manager=True, competition_id=comp.id,
                                     today=TODAY)
    assert [c["name"] for c in board["competitions"]] == ["Taça do Algarve"]
    (row,) = board["rows"]
    # L'azul 160 è piccolo per 172 cm, ma c'è: il bianco 170 pure (piccolo). Niente manca.
    assert row["first_name"] == "João" and row["blue"]["small"] and row["missing"] == []
    everyone = await loja.staff_judogis(db, scope=scope, user_id=admin.id, manager=True, competition_id=None,
                                        today=TODAY)
    maria_row = next(r for r in everyone["rows"] if r["first_name"] == "Maria")
    assert maria_row["missing"] == ["WHITE", "BLUE"]
    retired = await loja.retire_judogi(db, scope=scope, user_id=admin.id, manager=True,
                                       order_id=row["blue"]["id"], reason="OUTGROWN", today=TODAY)
    assert retired.retired_on == TODAY


async def test_club_products_leave_the_shop_checkout(db, scope, monkeypatch):
    from app.domains.jav_market import service as shop

    club, admin, parent, maria, joao = await _setup(db, scope)
    _tee, (tee_v,) = await _product(db, scope, admin, "T-shirt")
    with pytest.raises(shop.JavMarketValidationError, match="Loja del club"):
        await shop.create_order(
            db, organization_id=scope.organization_id, customer_user_id=parent.id, actor_user_id=parent.id,
            address={"recipient_name": "Ana", "address_line1": "Rua 1", "city": "Lagos", "province": "FA",
                     "postal_code": "8600"},
            credit_applied_cents=0, payment_method="BANK_TRANSFER", otp_code=None, note=None, variant_id=tee_v.id,
        )
    await db.rollback()
    for obj in (parent, maria, tee_v):
        await db.refresh(obj)

    # E dalla Loja, via HTTP: carrello, ordine, le quote nella risposta.
    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.family", "club.athlete"})
    try:
        async with client:
            r = await client.post("/club/loja/cart", json={"athlete_id": str(maria.id), "kind": "PRODUCT",
                                                          "variant_id": str(tee_v.id)})
            assert r.status_code == 201, r.text
            assert r.json()["count"] == 1
            done = await client.post("/club/loja/checkout", json={})
            assert done.status_code == 201, done.text
            assert len(done.json()["fee_ids"]) == 1
            orders = (await client.get("/club/judogi/orders")).json()
            assert [o["kind"] for o in orders] == ["PRODUCT"]
            view = (await client.get(f"/club/loja/athletes/{maria.id}")).json()
            assert view["athlete"]["first_name"] == "Maria"
    finally:
        app.dependency_overrides.clear()
