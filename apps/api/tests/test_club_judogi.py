"""I judogi del club (club/judogi.py): il conto del calcolatore vecchio
(listino + personalizzazione − permuta al 50%), la taglia scelta fra quelle
che esistono, la regola del nome sotto i 13 anni, chi ordina (titolare,
atleta maggiorenne) e chi desidera soltanto (atleta minorenne, con la
notifica al titolare), la quota EQUIPMENT una sola volta, l'annullamento e
la lista dei desideri dello Shop."""

from datetime import date

from sqlalchemy import select

from app.domains.club import athlete_access, judogi
from app.domains.club.models import Club, ClubFee
from app.domains.club.operations_models import ClubEquipmentOrder, ClubWishlistItem
from app.domains.notifications.models import Notification
from app.domains.rbac.models import Role
from tests.test_club_area_extras import _client
from tests.test_club_fees import _athlete, _plans, _user

TODAY = date.today()


def _born(years: int) -> date:
    return date(TODAY.year - years, 1, 1)


async def _club(db, scope) -> Club:
    club = await db.get(Club, scope.club_id)
    await judogi.seed_prices(db, club=club)
    await db.commit()
    return club


async def test_quote_matches_the_old_calculator(db, scope):
    club = await _club(db, scope)
    # Tochi Gi azul da treino, 140 cm: 42 € + 35 € = 77 € (ordine #3 del vecchio).
    q = await judogi.quote(db, club=club, choice={"kimono_type": "TRAINING", "color": "BLUE", "brand": "Tochi Gi"},
                           height_cm=137)
    assert (q["size_cm"], q["base_price_cents"], q["total_cents"]) == (140, 4200, 7700)
    # Permuta: un Tochi Gi rosa 120 restituito vale 39 €, metà sconto.
    q = await judogi.quote(db, club=club, choice={
        "kimono_type": "TRAINING", "color": "BLUE", "brand": "Tochi Gi", "size_cm": 140,
        "trade_in": {"kimono_type": "TRAINING", "color": "PINK", "brand": "Tochi Gi", "size_cm": 120},
    })
    assert q["trade_in_discount_cents"] == 1950 and q["total_cents"] == 7700 - 1950
    # 95 cm: il vecchio diceva «nessuna marca»; qui il 100. Oltre il 200, il 200.
    assert (await judogi.quote(db, club=club, choice={"kimono_type": "TRAINING", "color": "WHITE", "brand": "NKL"},
                               height_cm=95))["size_cm"] == 100
    assert (await judogi.quote(db, club=club, choice={"kimono_type": "TRAINING", "color": "WHITE", "brand": "NKL"},
                               height_cm=210))["size_cm"] == 200
    # I refusi del listino vecchio sono corretti (13 → 23 €).
    assert (await judogi.quote(db, club=club, choice={"kimono_type": "TRAINING", "color": "WHITE", "brand": "NKL",
                                                      "size_cm": 100}))["base_price_cents"] == 2300
    # Il rosa di Tochi Gi arriva al 170: per 180 cm resta il 170.
    q = await judogi.quote(db, club=club, choice={"kimono_type": "TRAINING", "color": "PINK", "brand": "Tochi Gi"},
                           height_cm=180)
    assert q["size_cm"] == 170
    # Personalizzazione e permuta sono del club.
    admin = await _user(db, scope, "admin")
    await judogi.update_settings(db, club=club, actor_user_id=admin.id,
                                 data={"customization_cents": 2000, "trade_in_percent": 40})
    q = await judogi.quote(db, club=club, choice={
        "kimono_type": "TRAINING", "color": "BLUE", "brand": "Tochi Gi", "size_cm": 140,
        "trade_in": {"kimono_type": "TRAINING", "color": "PINK", "brand": "Tochi Gi", "size_cm": 120},
    })
    assert q["total_cents"] == 4200 + 2000 - 1560
    tree = judogi.price_tree(await judogi.price_rows(db, club_id=club.id), height_cm=137)
    training = next(t for t in tree if t["code"] == "TRAINING")
    tochi = next(b for c in training["colors"] if c["code"] == "BLUE" for b in c["brands"] if b["name"] == "Tochi Gi")
    assert tochi["suggested_size_cm"] == 140 and tochi["suggested_price_cents"] == 4200
    # Il listino si carica una volta sola.
    assert await judogi.seed_prices(db, club=club) == 0


async def test_order_wish_and_permissions(db, scope, monkeypatch):
    for code in ("ATHLETE", "CUSTOMER"):
        db.add(Role(organization_id=scope.organization_id, code=code, name=code.title()))
    await db.commit()
    await _club(db, scope)
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=_born(10), first_name="Afonso", today=TODAY)
    await athlete_access.set_login(db, athlete=kid, actor_user_id=parent.id, username="afonso.j", email=None,
                                   password="segreto1")
    big = await _athlete(db, scope, parent, birth_date=_born(20), first_name="Rita", sex="F", today=TODAY)
    await athlete_access.set_login(db, athlete=big, actor_user_id=parent.id, username="rita.j", email=None,
                                   password="segreto1")
    await db.refresh(kid)
    await db.refresh(big)
    from app.domains.users.models import User

    choice = {"kimono_type": "TRAINING", "color": "BLUE", "brand": "Tochi Gi", "size_cm": 140}

    # Il ragazzo (10 anni) vede e desidera, non compra.
    app, client = await _client(db, monkeypatch, user=await db.get(User, kid.user_id), scope=scope,
                                granted={"club.athlete"})
    try:
        async with client:
            mine = (await client.get("/club/judogi/athletes")).json()
            assert [(a["mode"], a["kimono_name"], a["single_name_only"]) for a in mine] == [("WISH", "Afonso", True)]
            assert (await client.get("/club/judogi/catalog")).json()["customization_cents"] == 3500
            no = await client.post("/club/judogi/orders", json={**choice, "athlete_id": str(kid.id),
                                                                 "kimono_name": "Afonso"})
            assert no.status_code == 400
            wish = await client.post("/club/wishlist", json={"athlete_id": str(kid.id), "kind": "JUDOGI",
                                                             "judogi": {**choice, "kimono_name": "Afonso"}})
            assert wish.status_code == 201, wish.text
            wish_id = wish.json()["id"]
            # Un secondo judogi sostituisce il primo.
            again = await client.post("/club/wishlist", json={"athlete_id": str(kid.id), "kind": "JUDOGI",
                                                              "judogi": {**choice, "size_cm": 150}})
            assert again.json()["id"] == wish_id
            assert (await client.patch(f"/club/wishlist/{wish_id}", json={"status": "DISMISSED"})).status_code == 400
    finally:
        app.dependency_overrides.clear()
    notes = list((await db.execute(select(Notification).where(
        Notification.recipient_user_id == parent.id, Notification.type == "CLUB_WISHLIST_ADDED",
    ))).scalars())
    assert len(notes) == 2 and "Afonso" in notes[0].title

    # Il titolare vede il desiderio e ne fa l'ordine (ricalcolato).
    app, client = await _client(db, monkeypatch, user=parent, scope=scope, granted={"club.family", "club.athlete"})
    try:
        async with client:
            wishes = (await client.get("/club/wishlist")).json()
            assert len(wishes) == 1 and wishes[0]["can_decide"] and wishes[0]["judogi"]["quote"]["size_cm"] == 150
            bad = await client.post("/club/judogi/orders", json={**choice, "athlete_id": str(kid.id),
                                                                  "kimono_name": "Afonso Silva"})
            assert bad.status_code == 400 and "13 anni" in bad.json()["detail"]
            ok = await client.post("/club/judogi/orders", json={**choice, "athlete_id": str(kid.id),
                                                                 "kimono_name": "Afonso", "wish_id": wish_id})
            assert ok.status_code == 201, ok.text
            order = ok.json()
            assert order["price_cents"] == 7700 and order["status"] == "PENDING"
            twice = await client.post("/club/judogi/orders", json={**choice, "athlete_id": str(kid.id),
                                                                    "kimono_name": "Afonso"})
            assert twice.status_code == 400
            assert (await client.get("/club/wishlist")).json()[0]["status"] == "ORDERED"
            assert [o["id"] for o in (await client.get("/club/judogi/orders")).json()] == [order["id"]]
    finally:
        app.dependency_overrides.clear()
    fees = list((await db.execute(select(ClubFee).where(ClubFee.athlete_id == kid.id,
                                                         ClubFee.kind == "EQUIPMENT"))).scalars())
    assert [(f.amount_cents, f.period, f.status) for f in fees] == [(7700, order["id"], "DUE")]

    # La figlia maggiorenne con il suo accesso ordina per sé, e il nome intero va bene.
    app, client = await _client(db, monkeypatch, user=await db.get(User, big.user_id), scope=scope,
                                granted={"club.athlete"})
    try:
        async with client:
            mine = (await client.get("/club/judogi/athletes")).json()
            assert [(a["mode"], a["single_name_only"], a["high_competition"]) for a in mine] == [("BUY", False, False)]
            # Il FIJ è dell'alta competizione (club/loja.py): prima no...
            fij = {"kimono_type": "FIJ_APPROVED", "color": "WHITE", "brand": "Mizuno", "height_cm": 168,
                   "athlete_id": str(big.id), "kimono_name": "Rita Jesus"}
            no = await client.post("/club/judogi/orders", json=fij)
            assert no.status_code == 400 and "alta competizione" in no.json()["detail"]
            # ...poi la segreteria apre il suo piano e la segna.
            from app.domains.club import loja
            from app.domains.club.models import ClubPlan

            (await db.get(ClubPlan, big.plan_id)).allows_high_competition = True
            await loja.set_high_competition(db, scope=scope, athlete=big, actor_user_id=admin.id, value=True)
            ok = await client.post("/club/judogi/orders", json={
                "kimono_type": "FIJ_APPROVED", "color": "WHITE", "brand": "Mizuno", "height_cm": 168,
                "athlete_id": str(big.id), "kimono_name": "Rita Jesus",
            })
            assert ok.status_code == 201, ok.text
            assert (ok.json()["size_cm"], ok.json()["price_cents"]) == (170, 18000 + 3500)
            # Il fratello non è suo.
            other = await client.post("/club/judogi/orders", json={**choice, "athlete_id": str(kid.id),
                                                                    "kimono_name": "Afonso"})
            assert other.status_code == 404
    finally:
        app.dependency_overrides.clear()

    # La segreteria: elenco, CSV per il fornitore, annullamento (la quota non pagata sparisce).
    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted={"club.manage"})
    try:
        async with client:
            rows = (await client.get("/club/admin/judogi/orders", params={"q": "afonso"})).json()
            assert [r["id"] for r in rows] == [order["id"]]
            csv = (await client.get("/club/admin/judogi/orders.csv")).text
            assert "Afonso" in csv and "Rita Jesus" in csv
            r = await client.patch(f"/club/admin/judogi/orders/{order['id']}", json={"status": "CANCELLED"})
            assert r.status_code == 200 and r.json()["status"] == "CANCELLED" and r.json()["fee_id"] is None
            again = await client.patch(f"/club/admin/judogi/orders/{order['id']}", json={"status": "PENDING"})
            assert again.status_code == 400
            prices = (await client.get("/club/admin/judogi/prices")).json()
            assert len(prices) == len(judogi.base_catalog())
            p = await client.post("/club/admin/judogi/prices", json={
                "kimono_type": "TRAINING", "color": "BLUE", "brand": "Tochi Gi", "size_cm": 140, "price_cents": 4500,
            })
            assert p.json()["price_cents"] == 4500
            assert len((await client.get("/club/admin/judogi/prices")).json()) == len(prices)
    finally:
        app.dependency_overrides.clear()
    assert (await db.execute(select(ClubFee).where(ClubFee.athlete_id == kid.id,
                                                    ClubFee.kind == "EQUIPMENT"))).first() is None
    cancelled = await db.get(ClubEquipmentOrder, order["id"])
    assert cancelled.status == "CANCELLED"
    # Dopo l'annullamento lo stesso judogi si può ordinare di nuovo.
    club = await db.get(Club, scope.club_id)
    again = await judogi.create_order(db, scope=scope, club=club, athlete=kid, actor_user_id=parent.id,
                                      data={**choice, "kimono_name": "Afonso"}, today=TODAY)
    assert again.price_cents == 4500 + 3500


async def test_product_wish_closes_with_the_shop_order(db, scope):
    from app.domains.jav_market.models import JavMarketProduct, JavMarketVariant

    await _club(db, scope)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=_born(9), first_name="Tiago", today=TODAY)
    product = JavMarketProduct(organization_id=scope.organization_id, name="Cinto de treino", description="",
                               images=[], created_by_user_id=parent.id)
    db.add(product)
    await db.flush()
    variant = JavMarketVariant(product_id=product.id, label="Unica", price_cents=1200)
    db.add(variant)
    await db.commit()
    club = await db.get(Club, scope.club_id)
    first = await judogi.add_wish(db, scope=scope, club=club, athlete=kid, actor_user_id=parent.id,
                                  data={"kind": "PRODUCT", "product_id": product.id, "variant_id": variant.id})
    same = await judogi.add_wish(db, scope=scope, club=club, athlete=kid, actor_user_id=parent.id,
                                 data={"kind": "PRODUCT", "product_id": product.id})
    assert first.id == same.id
    # Il titolare che aggiunge da sé non riceve la notifica.
    assert (await db.execute(select(Notification).where(Notification.recipient_user_id == parent.id))).first() is None
    from app.domains.jav_market.models import JavMarketOrder

    order = JavMarketOrder(organization_id=scope.organization_id, customer_user_id=parent.id, athlete_id=kid.id,
                           created_by_user_id=parent.id, items_cents=1200, shipping_cents=0, amount_cents=1200,
                           status="AWAITING_PAYMENT", payment_method="BANK_TRANSFER", recipient_name="X",
                           address_line1="Rua", city="Lagos", province="FA", postal_code="8600")
    db.add(order)
    await db.flush()
    order_id = order.id
    await judogi.mark_products_ordered(db, athlete_id=kid.id, product_ids={product.id}, order_id=order_id,
                                       actor_user_id=parent.id)
    await db.commit()
    wish = await db.get(ClubWishlistItem, first.id)
    assert wish.status == "ORDERED" and wish.jav_market_order_id == order_id
