"""Shop Jav Partner (CJ Dropshipping): pricing, settings, import, the
checkout shared with the other shops, sending orders to CJ and following
them. CJ itself is replaced by a fake at client.call, the one door every
CJ request goes through."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.db import utcnow
from app.core.security import hash_otp_code, hash_password
from app.domains.accounting import details as accounting_details
from app.domains.accounting import service as accounting_service
from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.cj_dropshipping import client as cj_client
from app.domains.cj_dropshipping import pricing
from app.domains.cj_dropshipping import service as cj_service
from app.domains.cj_dropshipping.models import CjOrder, CjSettings, CjVariant
from app.domains.notifications.models import Notification
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.carts import service as carts_service
from app.domains.wallets import service as wallet_service

def _con_iva(merce_cents: int, aliquota: int = 22) -> int:
    """Il totale che il cliente paga sulla merce: dalla Session 78 l'IVA si
    aggiunge al prezzo esposto invece di essere contenuta."""
    from app.domains.marketplaces import rules

    return merce_cents + rules.vat_added_cents(net_cents=merce_cents, percentage=aliquota)


OTP = "111222"
ADDRESS = {
    "recipient_name": "Mario Rossi", "recipient_phone": "3331234567", "address_line1": "Via Roma 1",
    "address_line2": None, "city": "Milano", "province": "MI", "postal_code": "20100",
}


class FakeCj:
    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []
        self.fail_create: str | None = None
        self.fail_pay: str | None = None
        self.lookup_error: str | None = None
        self.timeout_after_create = False
        self.autopay_on_create = False  # what CJ does with sandbox orders
        self.balance = 0.0
        self.orders_created = 0
        self.freight_options = [
            {"logisticName": "CJPacket Ordinary", "logisticPrice": 6.10, "totalPostageFee": 7.81, "logisticAging": "4-8"},
            {"logisticName": "Slow Post", "logisticPrice": 9.50, "totalPostageFee": 9.50, "logisticAging": "20-30"},
            # Cheapest base price, most expensive in reality: must not be chosen.
            {"logisticName": "Trap Express", "logisticPrice": 5.00, "totalPostageFee": 12.00, "logisticAging": "3-5"},
        ]
        self.remote_orders: dict[str, dict] = {}

    async def __call__(self, db, settings, method, path, *, params=None, body=None):
        self.calls.append((path, body))
        if path == "/product/query":
            return {
                "pid": "P1", "productSku": "SKU1", "productNameEn": "Wireless Earbuds",
                "description": "<p>Great <b>sound</b></p><script>alert(1)</script><ul><li>Bluetooth 5.3</li></ul>",
                "categoryName": "Electronics", "bigImage": "https://img/1.jpg", "productImageSet": ["https://img/2.jpg"],
                "variants": [
                    {"vid": "V1", "variantSku": "SKU1-B", "variantKey": "Black", "variantSellPrice": "10.00",
                     "variantWeight": "120", "inventories": None},
                    {"vid": "V2", "variantSku": "SKU1-W", "variantKey": "White", "variantSellPrice": "11.00",
                     "variantWeight": "130", "inventories": None},
                ],
            }
        if path == "/product/stock/getInventoryByPid":
            return {
                "inventories": [{"countryCode": "CN", "totalInventoryNum": 500}],
                "variantInventories": [
                    {"vid": "V1", "inventory": [{"countryCode": "CN", "totalInventory": 500}]},
                    {"vid": "V2", "inventory": [{"countryCode": "CN", "totalInventory": 0}]},
                ],
            }
        if path == "/logistic/freightCalculate":
            return self.freight_options
        if path == "/shopping/order/getOrderDetail":
            if self.lookup_error:
                raise cj_client.CjApiError(self.lookup_error)  # e.g. timeout: code None
            item = self._find(params["orderId"])
            if item is None:
                raise cj_client.CjApiError("CJ: order not found", code=1600300)
            return dict(item)
        if path == "/shopping/order/createOrderV2":
            if self.fail_create:
                raise cj_client.CjApiError(self.fail_create, code=1600100)
            self.orders_created += 1
            n = self.orders_created
            status = "UNSHIPPED" if self.autopay_on_create else "UNPAID"
            item = {
                "orderId": f"26091711{n:04d}", "cjOrderCode": f"SD{n:04d}", "orderNum": body["orderNumber"],
                "orderStatus": status, "orderAmount": 17.81, "productAmount": 10.00, "postageAmount": 7.81,
            }
            self.remote_orders[body["orderNumber"]] = item
            if self.timeout_after_create:
                self.timeout_after_create = False
                raise cj_client.CjApiError("CJ non risponde (ReadTimeout). Riprova tra poco.")
            return {
                "orderId": item["cjOrderCode"], "orderNumber": body["orderNumber"], "shipmentOrderId": f"CJ{n}",
                "orderStatus": "", "orderAmount": 17.81, "productAmount": 10.00, "postageAmount": 7.81,
                "cjPayUrl": None if self.autopay_on_create else f"https://pay.cj.example/{n}",
            }
        if path == "/shopping/pay/payBalance":
            if self.fail_pay:
                message, self.fail_pay = self.fail_pay, None
                raise cj_client.CjApiError(message)
            item = self._find(body["orderId"])
            if item is None or item["orderStatus"] != "UNPAID":
                raise cj_client.CjApiError("CJ: pay order fail, order status is not unpaid.", code=1603001)
            if self.balance < item["orderAmount"]:
                raise cj_client.CjApiError("CJ: Insufficient balance", code=1603001)
            self.balance = round(self.balance - item["orderAmount"], 2)
            item["orderStatus"] = "UNSHIPPED"
            return None
        if path == "/shopping/order/getOrderDetailBatch":
            return [dict(i) for i in (self._find(x) for x in body["orderIds"]) if i is not None]
        if path == "/shopping/pay/getBalance":
            return {"amount": self.balance}
        raise AssertionError(f"unexpected CJ call {path}")

    def _find(self, ref):
        for item in self.remote_orders.values():
            if ref in (item["orderId"], item["cjOrderCode"], item["orderNum"]):
                return item
        return None

    def count(self, path):
        return sum(1 for p, _ in self.calls if p == path)

    def calls_to_orders(self):
        return sum(1 for p, _ in self.calls if p.startswith("/shopping/"))


@pytest.fixture
def fake_cj(monkeypatch):
    fake = FakeCj()
    cache: dict = {}

    async def cache_get(key):
        return cache.get(key)

    async def cache_set(key, value, seconds):
        cache[key] = value

    monkeypatch.setattr(cj_client, "call", fake)
    monkeypatch.setattr(cj_service, "_cache_get", cache_get)
    monkeypatch.setattr(cj_service, "_cache_set", cache_set)
    return fake


async def _user(db, organization_id, role_code="CUSTOMER"):
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


async def _shop(db, organization_id, admin, bank_transfer_discount_percentage=None, credit_percentage=50, **settings_updates):
    from app.domains.marketplaces import rules

    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456")
    )
    if bank_transfer_discount_percentage is not None:
        await rules.update_config(
            db, organization_id=organization_id, labels=None,
            bank_transfer_discount_percentage=bank_transfer_discount_percentage,
        )
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    await cj_service.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={
            "api_key": "CJ123@api@secret-abcd", "enabled": True, "markup_percentage": 40, "auto_forward": False,
            **settings_updates,
        },
    )
    product = await cj_service.import_product(
        db, row=row, actor_user_id=admin.id, pid="P1", name="Auricolari wireless", description=None,
        credit_discount_percentage=credit_percentage, markup_percentage=None, vids=None, activate=True,
    )
    variants = (await db.execute(select(CjVariant).where(CjVariant.product_id == product.id))).scalars().all()
    return row, product, {v.cj_vid: v for v in variants}


async def _otp(db, user_id):
    db.add(OtpCode(
        user_id=user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code_hash=hash_otp_code(OTP),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    await db.commit()


def _settings(**kw):
    base = {"usd_eur_rate": Decimal("0.92"), "markup_percentage": 40, "markup_fixed_cents": 0,
            "price_rounding": "90", "shipping_mode": "CUSTOMER_PAYS"}
    base.update(kw)
    return CjSettings(**base)


def test_price_is_cost_converted_marked_up_and_rounded_up():
    # 10 USD x 0.92 = 9.20 EUR, +40% = 12.88 -> 12.90
    assert pricing.sale_price_cents(cost_usd="10", settings=_settings()) == 1290
    assert pricing.sale_price_cents(cost_usd="10", settings=_settings(price_rounding="99")) == 1299
    assert pricing.sale_price_cents(cost_usd="10", settings=_settings(price_rounding="NONE")) == 1288
    # 12.91 must never be rounded down to 12.90: goes to 13.90
    assert pricing._round_up(1291, "90") == 1390
    # Shipping included: 7.81 USD -> 7.19 EUR more, 20.07 -> 20.90; checkout shipping is then 0.
    included = _settings(shipping_mode="INCLUDED")
    assert pricing.sale_price_cents(cost_usd="10", settings=included, shipping_estimate_usd="7.81") == 2090
    assert pricing.shipping_price_cents(shipping_usd="7.81", settings=included) == 0
    assert pricing.shipping_price_cents(shipping_usd="7.81", settings=_settings()) == 719


def test_cj_description_becomes_plain_text():
    text = cj_service.html_to_text("<p>Great <b>sound</b></p><ul><li>Bluetooth</li></ul>&amp; more")
    assert "<" not in text
    assert "Great sound" in text and "• Bluetooth" in text and "& more" in text


@pytest.mark.asyncio
async def test_new_shop_starts_with_a_100_percent_markup(db, organization_id):
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    assert row.markup_percentage == 100  # pay 10, sell at 20 (before rounding)
    assert pricing.sale_price_cents(cost_usd="10", settings=row) == 1890  # 9.20 x 2 = 18.40 -> 18.90


@pytest.mark.asyncio
async def test_api_key_is_never_returned_and_changing_it_drops_the_tokens(db, organization_id):
    admin = await _user(db, organization_id, "ADMIN")
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.update_settings(db, row=row, updates={"enabled": True}, actor_user_id=admin.id)
    await cj_service.update_settings(db, row=row, updates={"api_key": "CJ1@api@secret-wxyz"}, actor_user_id=admin.id)
    row.access_token = "tok"
    await db.commit()
    read = cj_service.settings_read_dict(row)
    assert read["api_key_configured"] is True
    assert read["api_key_hint"] == "…wxyz"
    assert "secret" not in str(read)
    await cj_service.update_settings(db, row=row, updates={"api_key": "CJ1@api@other-1111"}, actor_user_id=admin.id)
    assert row.access_token is None


@pytest.mark.asyncio
async def test_import_saves_variants_with_our_price_and_blocks_duplicates(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    row, product, variants = await _shop(db, organization_id, admin)
    assert product.origin_country == "CN"
    assert product.shipping_days == "4-8"  # the cheapest option
    assert "<" not in product.description
    assert "alert" not in product.description  # script contents dropped, not turned into text
    assert variants["V1"].price_cents == 1290
    assert variants["V1"].inventory == 500
    assert variants["V2"].inventory == 0

    card = await cj_service.product_customer_dict(db, product, settings=row)
    assert card["min_price_cents"] == 1290
    assert [v["in_stock"] for v in card["variants"]] == [True, False]

    with pytest.raises(cj_service.CjValidationError):
        await cj_service.import_product(
            db, row=row, actor_user_id=admin.id, pid="P1", name="x", description=None,
            credit_discount_percentage=None, markup_percentage=None, vids=None, activate=True,
        )

    # A new markup re-prices every variant from the stored cost.
    await cj_service.update_settings(db, row=row, updates={"markup_percentage": 100}, actor_user_id=admin.id)
    await db.refresh(variants["V1"])
    assert variants["V1"].price_cents == 1890  # 9.20 x 2 = 18.40 -> 18.90


@pytest.mark.asyncio
async def test_product_cj_cannot_ship_is_not_importable(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    fake_cj.freight_options = []
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    await cj_service.update_settings(db, row=row, updates={"api_key": "k"}, actor_user_id=admin.id)
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.import_product(
            db, row=row, actor_user_id=admin.id, pid="P1", name="x", description=None,
            credit_discount_percentage=None, markup_percentage=None, vids=None, activate=True,
        )


@pytest.mark.asyncio
async def test_checkout_with_javcash_and_shipping_like_every_shop(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await cj_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id, quantity=2
    )
    assert quote["items_cents"] == 2580
    assert quote["shipping_cents"] == 719
    assert quote["amount_cents"] == _con_iva(2580) + 719
    # Session 77: il tetto e' il 50% del **valore della merce**, spedizione
    # esclusa -- i JavCash scontano il prodotto, non il corriere. Prima la
    # spedizione entrava nella base, e il tetto era piu' alto.
    assert quote["max_creditable_cents"] == round(quote["items_cents"] * 50 / 100)

    with pytest.raises(cj_service.CjValidationError):  # out of stock variant
        await cj_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V2"].id, quantity=1
        )
    with pytest.raises(cj_service.InvalidOtpError):
        await cj_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
            quantity=2, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
            actor_user_id=customer.id, otp_code="000000", note=None,
        )

    await _otp(db, customer.id)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=2, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.amount_cents == quote["amount_cents"]
    assert order.logistic_name == "CJPacket Ordinary"
    assert order.city == "Milano" and order.country_code == "IT"
    assert order.fulfillment_status == "NOT_SENT"
    txn = await db.get(wallet_service.WalletTransaction, order.credit_debit_transaction_id)
    assert txn.reference_cj_order_id == order.id
    assert (await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=customer.id
    )).balance_cents == 0

    # Not paid yet: cannot go to CJ.
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)

    await cj_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert order.status == "PAID"

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    # Paid by bank transfer: 5% off the 22.99 residual (114.95 -> 115).
    assert euro_rows and euro_rows[0]["amount_cents"] == cj_service.amount_due_cents(order)
    wallet_rows = [m for m in movements if m["kind"] == "WALLET" and m["order_id"] == order.id]
    assert wallet_rows and wallet_rows[0]["product_name"] == "Auricolari wireless"

    detail = await accounting_details._order_detail(
        db, organization_id=organization_id, entity_id=order.id, owner_user_id=customer.id
    )
    assert detail["subtitle"].endswith("Marketplace 1")
    assert "CJ" not in detail["subtitle"] and "Partner" not in detail["subtitle"]
    assert not any(f and f["label"] == "Ordine CJ" for f in detail["facts"])


@pytest.mark.asyncio
async def test_cancel_gives_the_javcash_back(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=500, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _otp(db, customer.id)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=500, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    await cj_service.cancel_order(
        db, organization_id=organization_id, order_id=order.id, reason="ripensamento", actor_user_id=admin.id
    )
    assert order.status == "CANCELLED"
    assert (await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=customer.id
    )).balance_cents == 500


async def _paid_order(db, organization_id, fake_cj, admin=None, customer=None):
    admin = admin or await _user(db, organization_id, "ADMIN")
    customer = customer or await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    await cj_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    return admin, customer, order


async def _staff_notes(db, type_):
    return (await db.execute(select(Notification).where(Notification.type == type_))).scalars().all()


def test_shipping_is_chosen_and_charged_on_what_cj_really_bills():
    options = FakeCj().freight_options
    assert cj_service._cheapest(options)["logisticName"] == "CJPacket Ordinary"  # 7.81, not the 5.00 base price
    assert cj_service.postage_usd({"logisticPrice": 9.39, "totalPostageFee": 12.89}) == Decimal("12.89")
    assert cj_service.postage_usd({"logisticPrice": 9.39}) == Decimal("9.39")


@pytest.mark.asyncio
async def test_scenario1_balance_covers_it_created_and_paid_automatically(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    assert order.cj_payment_status == "NOT_REQUIRED"
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.fulfillment_status == "PROCESSING"
    assert order.cj_payment_status == "PAID" and order.cj_paid_at is not None
    assert order.cj_order_code == "SD0001"
    assert order.cj_amount_usd == Decimal("17.81")
    body = next(b for p, b in fake_cj.calls if p == "/shopping/order/createOrderV2")
    assert body["payType"] == 1 and body["orderNumber"] == f"JAV-{order.id}"
    assert body["isSandbox"] == 1 and body["logisticName"] == "CJPacket Ordinary" and body["iossType"] == 3
    assert fake_cj.count("/shopping/pay/payBalance") == 1
    assert fake_cj.balance == 82.19
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "PREPARING"
    assert "cj_payment_status" not in read and "fulfillment_status" not in read and "cj_pay_url" not in read
    summary = await cj_service.cash_requirement(db, organization_id=organization_id, refresh_balance=False)
    assert summary["orders_to_pay"] == 0 and summary["required_usd"] == 0


@pytest.mark.asyncio
async def test_scenario1b_sandbox_order_paid_by_cj_at_creation_is_not_paid_again(db, organization_id, fake_cj):
    fake_cj.autopay_on_create = True
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.cj_payment_status == "PAID" and order.fulfillment_status == "PROCESSING"
    assert fake_cj.count("/shopping/pay/payBalance") == 0 and fake_cj.count("/shopping/pay/getBalance") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("balance", [0.0, 10.0])
async def test_scenario2_3_balance_zero_or_short_order_waits_for_payment(db, organization_id, fake_cj, balance):
    fake_cj.balance = balance
    _admin, customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.cj_order_id and order.fulfillment_status == "SENT"
    assert order.cj_payment_status == "PAYMENT_REQUIRED"
    assert order.last_error_kind == "INSUFFICIENT_BALANCE" and order.next_retry_at is not None
    assert order.cj_pay_url == "https://pay.cj.example/1"
    assert fake_cj.count("/shopping/pay/payBalance") == 0  # never tried with a balance that cannot cover it
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "RECEIVED"
    admin_read = await cj_service.order_read_dict(db, order, admin=True)
    assert admin_read["cj_payment_status"] == "PAYMENT_REQUIRED" and admin_read["cj_pay_url"]
    alerts = await _staff_notes(db, "CJ_PAYMENT_REQUIRED")
    assert len(alerts) >= 1 and "17.81" in alerts[0].title
    assert f"{balance:.2f}" in alerts[0].body
    # Nothing is said to the customer about it.
    customer_notes = (await db.execute(select(Notification).where(Notification.recipient_user_id == customer.id))).scalars().all()
    assert all("CJ" not in n.title and "saldo" not in (n.body or "").lower() for n in customer_notes)
    # Asking again: same CJ order, no second alert.
    before = len(await _staff_notes(db, "CJ_PAYMENT_REQUIRED"))
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 1
    assert len(await _staff_notes(db, "CJ_PAYMENT_REQUIRED")) == before
    summary = await cj_service.cash_requirement(db, organization_id=organization_id, refresh_balance=True)
    assert summary["orders_to_pay"] == 1 and summary["required_usd"] == 17.81
    assert summary["balance_usd"] == balance and summary["shortfall_usd"] == round(17.81 - balance, 2)


@pytest.mark.asyncio
async def test_scenario4_create_times_out_but_cj_created_it_no_duplicate(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    fake_cj.timeout_after_create = True
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.fulfillment_status == "ERROR" and order.last_error_kind == "TEMPORARY"
    assert order.next_retry_at is not None and order.cj_order_id is None
    # A lookup that itself fails must not lead to creating blindly.
    fake_cj.lookup_error = "CJ non risponde (ReadTimeout). Riprova tra poco."
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 1 and order.fulfillment_status == "ERROR"
    fake_cj.lookup_error = None
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 1  # picked up by our order number
    assert order.cj_order_code == "SD0001" and order.cj_payment_status == "PAID"
    assert order.attempt_count == 3


@pytest.mark.asyncio
async def test_scenario5_payment_fails_temporarily_and_is_recovered(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    fake_cj.fail_pay = "CJ non risponde (ConnectTimeout). Riprova tra poco."
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.fulfillment_status == "SENT" and order.cj_payment_status == "FAILED"
    assert order.last_error_kind == "TEMPORARY" and order.next_retry_at is not None
    assert (await cj_service.order_read_dict(db, order, admin=False))["delivery_status"] == "RECEIVED"
    # The retry job picks it up when its time comes.
    order.next_retry_at = utcnow() - timedelta(minutes=1)
    await db.commit()
    await cj_service.update_settings(
        db, row=await cj_service.get_settings_row(db, organization_id=organization_id),
        updates={"auto_forward": True}, actor_user_id=None,
    )
    assert await cj_service.retry_due_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.cj_payment_status == "PAID" and order.fulfillment_status == "PROCESSING"
    assert fake_cj.count("/shopping/order/createOrderV2") == 1 and fake_cj.count("/shopping/pay/payBalance") == 2


@pytest.mark.asyncio
async def test_scenario6_admin_pays_on_cj_page_and_sync_detects_it(db, organization_id, fake_cj):
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.cj_payment_status == "PAYMENT_REQUIRED"
    fake_cj.remote_orders[f"JAV-{order.id}"]["orderStatus"] = "UNSHIPPED"  # paid by card on CJ's page
    assert await cj_service.sync_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.cj_payment_status == "PAID" and order.fulfillment_status == "PROCESSING"
    assert (await cj_service.order_read_dict(db, order, admin=False))["delivery_status"] == "PREPARING"
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    fake_cj.balance = 100.0
    assert await cj_service.retry_due_orders(db, organization_id=organization_id) == 0
    assert fake_cj.count("/shopping/pay/payBalance") == 0 and fake_cj.balance == 100.0


@pytest.mark.asyncio
async def test_scenario6b_balance_topped_up_is_spent_once_oldest_first(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin, auto_forward=True)
    orders = []
    for _ in range(2):
        order = await cj_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
            quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
            actor_user_id=customer.id, otp_code=None, note=None,
        )
        order.status, order.paid_at = "PAID", utcnow()
        await db.commit()
        orders.append(await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None))
    assert [o.cj_payment_status for o in orders] == ["PAYMENT_REQUIRED", "PAYMENT_REQUIRED"]
    summary = await cj_service.cash_requirement(db, organization_id=organization_id, refresh_balance=True)
    assert summary["required_usd"] == 35.62 and summary["shortfall_usd"] == 35.62
    fake_cj.balance = 20.0  # enough for one
    for o in orders:
        o.next_retry_at = utcnow() - timedelta(minutes=1)
    await db.commit()
    assert await cj_service.retry_due_orders(db, organization_id=organization_id) == 1
    for o in orders:
        await db.refresh(o)
    assert [o.cj_payment_status for o in orders] == ["PAID", "PAYMENT_REQUIRED"]
    assert fake_cj.count("/shopping/pay/payBalance") == 1 and fake_cj.balance == 2.19


@pytest.mark.asyncio
async def test_scenario7_tracking_reaches_the_customer(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    _admin, customer, order = await _paid_order(db, organization_id, fake_cj)
    await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    remote = fake_cj.remote_orders[f"JAV-{order.id}"]
    remote.update({"orderStatus": "SHIPPED", "trackNumber": "LP123IT", "trackingProvider": "PostNL"})
    assert await cj_service.sync_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.fulfillment_status == "SHIPPED" and order.tracking_number == "LP123IT" and order.shipped_at
    notes = (
        await db.execute(
            select(Notification).where(Notification.recipient_user_id == customer.id, Notification.type == "ORDER_SHIPPED")
        )
    ).scalars().all()
    assert len(notes) == 1
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "SHIPPED" and read["tracking_url"].endswith("LP123IT")
    assert await cj_service.sync_orders(db, organization_id=organization_id) == 0  # nobody told twice


@pytest.mark.asyncio
async def test_scenario8_two_processes_one_order_handled_once(db, organization_id, fake_cj):
    fake_cj.balance = 100.0
    _admin, _customer, order = await _paid_order(db, organization_id, fake_cj)
    # Another process holds the order right now.
    order.fulfillment_status = "SENDING"
    order.last_attempt_at = utcnow()
    await db.commit()
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.calls_to_orders() == 0
    # That process died after CJ created the order: taken over after 10 minutes, no duplicate.
    fake_cj.remote_orders[f"JAV-{order.id}"] = {
        "orderId": "999", "cjOrderCode": "SD0999", "orderNum": f"JAV-{order.id}", "orderStatus": "UNPAID",
        "orderAmount": 17.81,
    }
    order.last_attempt_at = utcnow() - timedelta(minutes=15)
    await db.commit()
    order = await cj_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert fake_cj.count("/shopping/order/createOrderV2") == 0
    assert order.cj_order_code == "SD0999" and order.cj_payment_status == "PAID"


def test_error_classification():
    assert cj_service.classify_error(cj_client.CjApiError("CJ non risponde (ReadTimeout).")) == "TEMPORARY"
    assert cj_service.classify_error(cj_client.CjApiError("CJ: Insufficient balance", code=1603001)) == "INSUFFICIENT_BALANCE"
    assert cj_service.classify_error(cj_client.CjApiError("CJ: token invalid", code=1600001)) == "AUTHENTICATION"
    assert cj_service.classify_error(cj_client.CjApiError("CJ: Param error", code=1600100)) == "VALIDATION"


@pytest.mark.asyncio
async def test_orders_of_a_switched_off_shop_cannot_be_placed(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin)
    await cj_service.update_settings(db, row=row, updates={"enabled": False}, actor_user_id=admin.id)
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id, quantity=1
        )
    assert (await db.execute(select(CjOrder))).first() is None


@pytest.mark.asyncio
async def test_real_sized_cj_tokens_are_stored(db, organization_id, monkeypatch):
    """CJ's JWT tokens are longer than 500 characters: the first real login
    failed on a VARCHAR(500) (migration 0045)."""
    long_token = "API@CJ1@CJ:" + "x" * 900

    async def raw_call(method, path, **kwargs):
        if path == "/authentication/getAccessToken":
            return {"code": 200, "data": {
                "accessToken": long_token, "refreshToken": long_token, "openId": 51143,
                "accessTokenExpiryDate": "2027-03-16T02:28:23+08:00", "refreshTokenExpiryDate": "2027-03-16T02:28:23+08:00",
            }}
        return {"code": 200, "data": {"amount": 12.5}}

    monkeypatch.setattr(cj_client, "_raw_call", raw_call)
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    row.api_key = "CJ1@api@key"
    await db.commit()
    read = await cj_service.test_connection(db, row=row)
    assert read["connected"] is True
    assert read["last_balance_usd"] == 12.5
    await db.refresh(row)
    assert row.access_token == long_token and row.open_id == "51143"


def test_stock_comes_from_the_inventory_endpoint_and_picks_the_nearest_warehouse():
    """Live CJ: the product detail has inventories=null, stock only in
    getInventoryByPid. Ships from the warehouse covering most variants,
    the nearest on a tie."""
    detail = {"variants": [{"vid": "A", "inventories": None}, {"vid": "B", "inventories": None}]}
    inventory = {"variantInventories": [
        {"vid": "A", "inventory": [{"countryCode": "CN", "totalInventory": 40000}, {"countryCode": "DE", "totalInventory": 12}]},
        {"vid": "B", "inventory": [{"countryCode": "CN", "totalInventory": 7}]},
    ]}
    stock = cj_service._stock_by_variant(detail, inventory)
    assert stock["A"] == {"CN": 40000, "DE": 12}
    # B is only in China: shipping from Germany would make B look sold out.
    assert cj_service._choose_origin(stock, inventory) == "CN"
    both_in_de = {"A": {"CN": 5, "DE": 3}, "B": {"CN": 5, "DE": 9}}
    assert cj_service._choose_origin(both_in_de, None) == "DE"
    assert cj_service._choose_origin(cj_service._stock_by_variant(detail, None), None) == "CN"



# --- Paying by bank transfer costs 5% less (never a card surcharge) ---------------------------------


def test_bank_transfer_gives_no_discount_whatever_the_percentage():
    # Session 86: no discount for paying by bank transfer, even if a caller
    # (or an old stored setting) still passes a percentage in.
    assert pricing.bank_transfer_discount_cents(residual_cents=2000, percentage=5) == 0
    assert pricing.bank_transfer_discount_cents(residual_cents=250, percentage=5) == 0
    assert pricing.bank_transfer_discount_cents(residual_cents=2000, percentage=10) == 0
    assert pricing.bank_transfer_discount_cents(residual_cents=0, percentage=5) == 0
    assert pricing.bank_transfer_discount_cents(residual_cents=2000, percentage=0) == 0


async def _card_ready(db, organization_id, monkeypatch):
    import stripe

    from app.domains.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "stripe_secret_key": "sk_test_fake", "stripe_publishable_key": "pk_test_fake"}
    await db.commit()
    created = []

    class _Session:
        def __init__(self, n):
            self.id = f"cs_cj_{n}_{uuid.uuid4().hex[:6]}"
            self.url = f"https://stripe.example/{self.id}"

    monkeypatch.setattr(
        stripe.checkout.Session, "create", staticmethod(lambda **p: created.append(p) or _Session(len(created)))
    )
    return created


@pytest.mark.asyncio
async def test_bank_transfer_costs_the_same_as_card_even_with_an_old_percentage_stored(
    db, organization_id, fake_cj, monkeypatch
):
    """Session 86: no discount for paying by bank transfer -- the residual
    after JavCash is due whole, whatever an old setting still says."""
    from app.domains.organizations.models import Organization
    from app.domains.payments import service as payments_service

    created = await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1299, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await cj_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id, quantity=2
    )
    assert quote["amount_cents"] == _con_iva(2580) + 719
    assert quote["bank_transfer_discount_percentage"] == 0
    assert quote["bank_transfer_amount_cents"] == quote["amount_cents"]

    await _otp(db, customer.id)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=2, address=ADDRESS, credit_applied_cents=quote["max_creditable_cents"], payment_method="CARD",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    # Session 77: il tetto e' il 50% della merce, spedizione esclusa -- 12,90
    # sui 25,80 di prodotti, non sui 32,99 dell'ordine.
    assert order.credit_applied_cents == 1290
    residuo = quote["amount_cents"] - 1290
    # Card pays exactly the price shown: no surcharge, ever.
    assert order.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(order) == residuo
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == residuo
    assert "description" not in created[-1]["line_items"][0]["price_data"]["product_data"]

    # Switching to bank transfer takes nothing off (Session 86), even with a
    # percentage stored before then in the organization settings.
    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "marketplace_bank_transfer_discount_percentage": 5}
    await db.commit()
    await cj_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert order.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(order) == residuo
    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["bank_transfer_discount_cents"] == 0 and read["amount_due_cents"] == residuo

    # Back to card (a Stripe checkout): the same amount.
    url = await payments_service.create_checkout_session_for_cj_order(
        db, organization_id=organization_id, order=order, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    assert url.startswith("https://stripe.example/")
    await db.refresh(order)
    assert order.payment_method == "CARD" and order.bank_transfer_discount_cents == 0
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == residuo

    await cj_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    assert euro_rows and euro_rows[0]["amount_cents"] == residuo


@pytest.mark.asyncio
async def test_card_has_no_discount_and_zero_percent_switches_it_off(db, organization_id, fake_cj, monkeypatch):
    await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin, bank_transfer_discount_percentage=0)
    bank = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert bank.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(bank) == bank.amount_cents

    from app.domains.marketplaces import rules

    await rules.update_config(db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=5)
    card = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="CARD",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert card.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(card) == card.amount_cents


@pytest.mark.asyncio
async def test_a_new_product_starts_at_30_percent_javcash_and_never_100(db, organization_id, fake_cj):
    """Session 68: Marketplace products are never bought entirely with
    JavCash; they enter at 30%, the administrator may raise it below 100."""
    admin = await _user(db, organization_id, "ADMIN")
    row = await cj_service.get_settings_row(db, organization_id=organization_id)
    await cj_service.update_settings(
        db, row=row, actor_user_id=admin.id, updates={"api_key": "CJ123@api@secret-abcd", "auto_forward": False}
    )
    product = await cj_service.import_product(
        db, row=row, actor_user_id=admin.id, pid="P1", name="Auricolari", description=None,
        credit_discount_percentage=None, markup_percentage=None, vids=None, activate=True,
    )
    assert product.credit_discount_percentage == 30
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.update_product(
            db, row=row, product=product, updates={"credit_discount_percentage": 100}, actor_user_id=admin.id
        )
    product = await cj_service.update_product(
        db, row=row, product=product, updates={"credit_discount_percentage": 80}, actor_user_id=admin.id
    )
    assert product.credit_discount_percentage == 80


# --- L'IVA e' compresa nel prezzo, mai aggiunta (Session 74) -----------------------------------------


def test_vat_included_is_the_tax_contained_in_the_price_rounded_half_up():
    """The price shown is the final one, so the VAT is taken *out* of it --
    gross x pct / (100 + pct) -- never added on top."""
    from app.domains.marketplaces import rules

    assert rules.vat_included_cents(gross_cents=1220, percentage=22) == 220
    assert rules.vat_included_cents(gross_cents=1815, percentage=22) == 327  # 18,15 -> 3,27
    # Exactly half a cent goes up, the way an invoice rounds: at 20%, 0,03
    # contains 0,005 -> 0,01 and 0,09 contains 0,015 -> 0,02.
    assert rules.vat_included_cents(gross_cents=3, percentage=20) == 1
    assert rules.vat_included_cents(gross_cents=9, percentage=20) == 2
    assert rules.vat_included_cents(gross_cents=0, percentage=22) == 0
    assert rules.vat_included_cents(gross_cents=1220, percentage=0) == 0


@pytest.mark.asyncio
async def test_vat_is_frozen_with_the_discount_and_the_margin_is_net_of_it(
    db, organization_id, fake_cj, monkeypatch
):
    """Session 74: 22% by default, contained in the price; the bonifico
    discount lowers the base, the JavCash spent does not, and what we
    compare to the CJ cost is the base, never the gross.
    (Session 78: VAT added on top; Session 86: no bonifico discount at all.)"""
    from app.domains.marketplaces import rules
    from app.domains.payments import service as payments_service

    await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await _otp(db, customer.id)

    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=2, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    # Session 86: niente sconto bonifico, si paga tutto il residuo dopo i JavCash.
    assert order.bank_transfer_discount_cents == 0
    assert cj_service.amount_due_cents(order) == order.amount_cents - order.credit_applied_cents
    assert order.vat_percentage == 22
    assert order.vat_amount_cents == 568  # 3184 x 22 / 122 = 574,16
    # The 10,00 of JavCash did not shrink the base: it is a way of paying,
    # not a discount. On the 21,84 really transferred the VAT would be 3,94.
    assert order.vat_amount_cents != rules.vat_included_cents(
        gross_cents=cj_service.amount_due_cents(order), percentage=22
    )

    # Carta: niente sconto, quindi base piena e IVA piu' alta -- ma il
    # prezzo resta lo stesso, non si aggiunge nulla.
    await cj_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="CARD"
    )
    assert order.bank_transfer_discount_cents == 0
    assert order.vat_amount_cents == 568  # 25,80 di merce al 22%
    assert cj_service.amount_due_cents(order) == (
        order.amount_cents - order.credit_applied_cents - order.bank_transfer_discount_cents
    )

    read = await cj_service.order_read_dict(db, order, admin=False)
    assert read["vat_percentage"] == 22 and read["vat_amount_cents"] == 568
    admin_read = await cj_service.order_read_dict(db, order, admin=True)
    # Il margine si misura sull'imponibile: l'IVA non e' mai stata nostra.
    assert admin_read["estimated_margin_cents"] == (
        cj_service.taxable_base_cents(order) - admin_read["cj_cost_cents"]
    )

    # Un giro di Stripe ricongela tutto insieme allo sconto.
    await cj_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert order.vat_amount_cents == 568
    await payments_service.create_checkout_session_for_cj_order(
        db, organization_id=organization_id, order=order, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    await db.refresh(order)
    assert order.bank_transfer_discount_cents == 0 and order.vat_amount_cents == 568


@pytest.mark.asyncio
async def test_vat_rate_is_a_setting_and_zero_switches_it_off(db, organization_id, fake_cj):
    from app.domains.marketplaces import rules

    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)

    config = await rules.get_config(db, organization_id=organization_id)
    assert config["vat_percentage"] == 22

    # Sopra il massimo si taglia, non si rifiuta: come lo sconto bonifico.
    config = await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None, vat_percentage=99
    )
    assert config["vat_percentage"] == rules.MAX_VAT_PERCENTAGE

    await rules.update_config(
        db, organization_id=organization_id, labels=None, bank_transfer_discount_percentage=None, vat_percentage=0
    )
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert order.vat_percentage == 0 and order.vat_amount_cents == 0
    admin_read = await cj_service.order_read_dict(db, order, admin=True)
    # Senza IVA il margine torna quello di prima: imponibile = prezzo scontato.
    assert admin_read["estimated_margin_cents"] == (
        order.amount_cents - order.bank_transfer_discount_cents - admin_read["cj_cost_cents"]
    )


async def _two_cj_in_stock(db, variants):
    """Il catalogo finto tiene una variante esaurita; per il carrello ne
    servono due comprabili."""
    due = list(variants.values())[:2]
    for v in due:
        v.inventory = 25
        v.active = True
    await db.commit()
    return due


# --- Il carrello su CJ (Session 77) ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_cj_cart_charges_one_shipping_for_the_whole_order(db, organization_id, fake_cj):
    """CJ quota il carrello intero in una chiamata: la spedizione che il
    cliente paga e' quella della spedizione unica, non la somma di due
    quotazioni separate -- che sarebbe piu' alta e falsa."""
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    due = await _two_cj_in_stock(db, variants)
    if len(due) < 2:
        pytest.skip("il catalogo finto ha una variante sola")

    for v in due:
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="cj",
            variant_id=v.id, quantity=1,
        )
    summary = await carts_service.summary(db, organization_id=organization_id, customer_user_id=customer.id)
    sezione = summary["sections"][0]
    assert sezione["shop"] == "cj"
    assert len(sezione["items"]) == 2
    # Una spedizione sola per l'ordine.
    assert sezione["amount_cents"] == _con_iva(sezione["items_cents"]) + sezione["shipping_cents"]
    # Il tetto JavCash e' la somma delle righe, spedizione esclusa.
    assert sezione["max_creditable_cents"] == sum(
        i["max_creditable_cents"] for i in sezione["items"]
    )


@pytest.mark.asyncio
async def test_cj_cart_becomes_one_order_with_every_line(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    due = await _two_cj_in_stock(db, variants)
    if len(due) < 2:
        pytest.skip("il catalogo finto ha una variante sola")
    for v in due:
        await carts_service.add_item(
            db, organization_id=organization_id, customer_user_id=customer.id, shop="cj",
            variant_id=v.id, quantity=1,
        )
    _cart, lines = await carts_service.checkout_lines(db, customer_user_id=customer.id, shop="cj")
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, lines=lines, address=ADDRESS,
        credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=customer.id,
        otp_code=None, note=None,
    )
    items = await cj_service.order_items(db, order)
    assert len(items) == 2
    assert {i.variant_id for i in items} == {v.id for v in due}
    # Il corpo per CJ porta tutte le righe, non solo la prima.
    body = await cj_service._create_body(db, order)
    assert len(body["products"]) == 2
    # E l'ordine ha un numero leggibile.
    await db.refresh(order)
    assert order.number and cj_service.order_code(order) == str(order.number)


# --- Session 88: disponibilità quasi in tempo reale, come AliExpress -----------------------------


@pytest.mark.asyncio
async def test_the_checkout_rechecks_a_stale_cj_product_before_payment(db, organization_id, fake_cj, monkeypatch):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, product, variants = await _shop(db, organization_id, admin)
    product.last_synced_at = utcnow() - timedelta(hours=5)
    await db.commit()
    # Nel frattempo CJ ha tolto la variante nera dal catalogo.
    original = fake_cj.__call__

    async def without_black(db_, settings, method, path, *, params=None, body=None):
        answer = await original(db_, settings, method, path, params=params, body=body)
        if path == "/product/query":
            answer["variants"] = [v for v in answer["variants"] if v["vid"] != "V1"]
        return answer

    monkeypatch.setattr(cj_client, "call", without_black)
    with pytest.raises(cj_service.CjValidationError):
        await cj_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
            quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
            actor_user_id=customer.id, otp_code=None, note=None,
        )
    await db.refresh(variants["V1"])
    assert variants["V1"].available_on_cj is False


@pytest.mark.asyncio
async def test_a_silent_cj_does_not_block_the_checkout(db, organization_id, fake_cj, monkeypatch):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, product, variants = await _shop(db, organization_id, admin)
    product.last_synced_at = utcnow() - timedelta(hours=5)
    await db.commit()
    original = fake_cj.__call__

    async def busy(db_, settings, method, path, *, params=None, body=None):
        if path == "/product/query":
            raise cj_client.CjApiError("Too many requests")
        return await original(db_, settings, method, path, params=params, body=body)

    monkeypatch.setattr(cj_client, "call", busy)
    order = await cj_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["V1"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert order.status == "AWAITING_PAYMENT"


@pytest.mark.asyncio
async def test_a_broken_cj_sync_alerts_staff_once_a_day(db, organization_id, fake_cj):
    admin = await _user(db, organization_id, "ADMIN")
    for _ in range(3):
        await cj_service.alert_sync_failure(db, organization_id=organization_id, job="products", error="Errore tecnico")
    rows = (await db.execute(select(Notification).where(
        Notification.recipient_user_id == admin.id, Notification.type == cj_service.SYNC_FAILED_NOTIFICATION,
    ))).scalars().all()
    assert len(rows) == 1
