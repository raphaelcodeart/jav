"""The AliExpress Dropshipping (DS) API, as this app uses it (Session 71).

One door, `call()`, which tests replace. Two shapes of request, both signed
the same way (this is Alibaba's "iop" gateway):

- **system calls** -- `/auth/token/create`, `/auth/token/refresh`: sent to
  https://api-sg.aliexpress.com/rest<path>, the path itself is part of what
  gets signed;
- **business calls** -- `aliexpress.ds.*`: sent to
  https://api-sg.aliexpress.com/sync with a `method` parameter, the path is
  NOT part of the signature, and the access token travels as `session`.

Signature: HMAC-SHA256 with the App Secret over the parameters sorted by
name and concatenated as name+value (prefixed by the path for system
calls), hex, uppercase. `timestamp` is milliseconds since the epoch.

The authorisation itself is the usual code -> token exchange; the token
lasts a limited time and is renewed here with the refresh token, a few
minutes before it expires (same approach as Shopify's client).

**On the shape of the answers.** The DS gateway wraps the useful part under
a name that changes with the method, and hands it over as a JSON string
about as often as as an object. Nothing here assumes one nesting: every
answer goes through `unwrap()`, which is tried against the shapes we have
actually seen documented, and what a call could not find is reported to the
administrator with the gateway's own words rather than silently becoming an
empty list. Where a field name is genuinely uncertain -- and it is, until
the seller account is authorised and we can read a real answer -- the
plausible spellings are all accepted and the comment says so.

Docs: https://openservice.aliexpress.com/doc/doc.htm
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from datetime import timedelta

import httpx

from app.core.config import get_settings
from app.core.db import utcnow
from app.domains.aliexpress_dropshipping.models import AliexpressSettings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://api-sg.aliexpress.com/oauth/authorize"
SYSTEM_GATEWAY = "https://api-sg.aliexpress.com/rest"
BUSINESS_GATEWAY = "https://api-sg.aliexpress.com/sync"
#: Registered in the AliExpress portal as the app's "Callback URL": the
#: dashboard serves it and proxies it here. It must not change.
CALLBACK_PATH = "/api/aliexpress/oauth/callback"
TIMEOUT_SECONDS = 30
#: The token is renewed this long before it expires.
TOKEN_RENEW_MARGIN = timedelta(minutes=10)


class AliexpressApiError(Exception):
    def __init__(self, message: str, kind: str = "FATAL"):
        super().__init__(message)
        #: TEMPORARY / AUTHENTICATION / VALIDATION / FATAL, see models.ERROR_KINDS
        self.kind = kind


#: Session 71 named this AliexpressError while the client lived in
#: imported_products; the name is kept as an alias so the old manual plugin,
#: which still borrows this same door, goes on catching what it always did.
AliexpressError = AliexpressApiError


class AliexpressNotConfiguredError(AliexpressApiError):
    def __init__(self, message: str = "AliExpress non è configurato: inserisci App Key e App Secret."):
        super().__init__(message, kind="AUTHENTICATION")


def callback_url() -> str:
    return get_settings().public_app_base_url.rstrip("/") + CALLBACK_PATH


def has_credentials(settings: AliexpressSettings) -> bool:
    return bool(settings.app_key and settings.app_secret)


def is_connected(settings: AliexpressSettings) -> bool:
    return bool(has_credentials(settings) and settings.access_token)


def sign(secret: str, params: dict[str, str], *, path: str | None = None) -> str:
    payload = "".join(f"{k}{params[k]}" for k in sorted(params))
    if path:
        payload = path + payload
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest().upper()


def authorize_url(*, app_key: str, state: str) -> str:
    query = urllib.parse.urlencode({
        "response_type": "code",
        "force_auth": "true",
        "client_id": app_key,
        "redirect_uri": callback_url(),
        "state": state,
    })
    return f"{AUTHORIZE_URL}?{query}"


_redis_client = None


def reset_redis() -> None:
    """I task Celery girano ogni job in un event loop nuovo (asyncio.run):
    un client creato in un loop precedente lì non si può riusare."""
    global _redis_client
    _redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as redis

        _redis_client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client


async def cache_get(key: str):
    try:
        raw = await _get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001 -- un buco in cache, mai un errore
        return None


async def cache_set(key: str, value, seconds: int) -> None:
    try:
        await _get_redis().set(key, json.dumps(value), ex=seconds)
    except Exception:  # noqa: BLE001 -- senza cache si richiede ad AliExpress
        logger.debug("AliExpress cache write skipped for %s", key)


async def _post(url: str, params: dict[str, str]) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
            response = await http.post(url, data=params, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise AliexpressApiError(
            f"AliExpress non risponde ({type(exc).__name__}). Riprova tra poco.", "TEMPORARY"
        ) from exc
    if response.status_code >= 500:
        raise AliexpressApiError(f"AliExpress occupato (HTTP {response.status_code}). Riprova tra poco.", "TEMPORARY")
    try:
        body = response.json()
    except ValueError:
        raise AliexpressApiError(
            f"AliExpress ha risposto in un formato inatteso (HTTP {response.status_code})."
        ) from None
    return body if isinstance(body, dict) else {"result": body}


def _raise_for_error(body: dict) -> None:
    """The gateway reports failures in the body, not in the HTTP status.

    Sometimes at the top level, sometimes wrapped in `error_response` -- the
    rate limit («ApiCallLimit», Session 88) arrives wrapped, and until then
    it passed as a successful answer without a product."""
    wrapped = body.get("error_response")
    if isinstance(wrapped, dict):
        body = {**wrapped, "message": wrapped.get("msg") or wrapped.get("message"),
                "sub_message": wrapped.get("sub_msg")}
    code = str(body.get("code") or body.get("error_code") or "0")
    if code in ("0", "", "None"):
        return
    message = body.get("message") or body.get("error_message") or body.get("error_description") or ""
    detail = body.get("sub_message") or body.get("sub_msg") or ""
    text = " -- ".join(part for part in (message, detail) if part) or f"codice {code}"
    kind = "FATAL"
    lowered = f"{code} {text}".lower()
    if "sign" in lowered or "token" in lowered or "appkey" in lowered or "app_key" in lowered:
        kind = "AUTHENTICATION"
    elif "limit" in lowered or "flow" in lowered or "busy" in lowered or "frequency" in lowered:
        kind = "TEMPORARY"
    raise AliexpressApiError(f"AliExpress: {text} (codice {code}).", kind)


async def _system_call(settings: AliexpressSettings, path: str, params: dict[str, str]) -> dict:
    payload = {
        **params,
        "app_key": settings.app_key,
        "sign_method": "sha256",
        "timestamp": str(int(time.time() * 1000)),
    }
    payload["sign"] = sign(settings.app_secret, payload, path=path)
    body = await _post(SYSTEM_GATEWAY + path, payload)
    _raise_for_error(body)
    return body


async def create_token(settings: AliexpressSettings, *, code: str) -> dict:
    """Exchanges the authorisation code. Fills the settings row (no commit)."""
    if not has_credentials(settings):
        raise AliexpressNotConfiguredError()
    body = await _system_call(settings, "/auth/token/create", {"code": code})
    return _store_token(settings, body)


async def refresh_token(settings: AliexpressSettings) -> dict:
    if not settings.refresh_token:
        raise AliexpressApiError("Autorizzazione AliExpress scaduta: ricollega l'account.", "AUTHENTICATION")
    body = await _system_call(settings, "/auth/token/refresh", {"refresh_token": settings.refresh_token})
    return _store_token(settings, body)


def _store_token(settings: AliexpressSettings, body: dict) -> dict:
    token = body.get("access_token")
    if not token:
        raise AliexpressApiError("AliExpress non ha rilasciato il token di accesso.", "AUTHENTICATION")
    settings.access_token = str(token)[:500]
    if body.get("refresh_token"):
        settings.refresh_token = str(body["refresh_token"])[:500]
    seconds = body.get("expires_in") or body.get("expire_time")
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = 0
    # Some answers give an absolute epoch (ms) instead of a duration.
    if seconds > 10_000_000:
        seconds = max(0, int(seconds / 1000 - time.time()))
    settings.token_expires_at = utcnow() + timedelta(seconds=seconds) if seconds else None
    label = body.get("user_nick") or body.get("seller_id") or body.get("account") or body.get("user_id")
    if label:
        settings.account_label = str(label)[:255]
    settings.last_connected_at = utcnow()
    return body


async def _valid_token(settings: AliexpressSettings) -> str:
    if not has_credentials(settings):
        raise AliexpressNotConfiguredError()
    if not settings.access_token:
        raise AliexpressApiError(
            "Account AliExpress non collegato: premi “Collega AliExpress” nelle impostazioni del Marketplace.",
            "AUTHENTICATION",
        )
    expires = settings.token_expires_at
    if expires is not None and expires - TOKEN_RENEW_MARGIN <= utcnow():
        await refresh_token(settings)
    return settings.access_token


#: Quante volte si riprova una chiamata respinta per troppa frequenza, e
#: quanto si aspetta: AliExpress dice «this ban will last 1 seconds».
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 1.5


async def call(settings: AliexpressSettings, method: str, params: dict[str, str] | None = None) -> dict:
    """One DS API call. Renews the token once if the gateway refuses it, and
    waits and retries when it is refused for calling too often (Session 88:
    the product sync also asks for shipping now, and a sync of 300 products
    ran into the limit on one in six)."""
    for wait in range(RATE_LIMIT_RETRIES + 1):
        try:
            return await _call_once(settings, method, params)
        except AliexpressApiError as exc:
            if wait < RATE_LIMIT_RETRIES and "ApiCallLimit" in str(exc):
                await asyncio.sleep(RATE_LIMIT_WAIT_SECONDS * (wait + 1))
                continue
            raise
    raise AliexpressApiError("AliExpress: chiamata non riuscita.", "TEMPORARY")


async def _call_once(settings: AliexpressSettings, method: str, params: dict[str, str] | None) -> dict:
    for attempt in (0, 1):
        token = await _valid_token(settings)
        payload = {
            **{k: v for k, v in (params or {}).items() if v is not None},
            "method": method,
            "app_key": settings.app_key,
            "session": token,
            "sign_method": "sha256",
            "timestamp": str(int(time.time() * 1000)),
        }
        payload["sign"] = sign(settings.app_secret, payload)
        body = await _post(BUSINESS_GATEWAY, payload)
        try:
            _raise_for_error(body)
        except AliexpressApiError as exc:
            if attempt == 0 and exc.kind == "AUTHENTICATION" and settings.refresh_token:
                await refresh_token(settings)
                continue
            raise
        return body
    raise AliexpressApiError("AliExpress: chiamata non riuscita.", "TEMPORARY")


def unwrap(body: dict, *keys: str) -> dict | list | None:
    """The DS answers nest the useful part under names that differ per
    method, and sometimes hand it over as a JSON string."""
    node: object = body
    for key in keys:
        if isinstance(node, str):
            try:
                node = json.loads(node)
            except ValueError:
                return None
        if not isinstance(node, dict):
            return None
        node = node.get(key)
        if node is None:
            return None
    if isinstance(node, str):
        try:
            node = json.loads(node)
        except ValueError:
            return node  # type: ignore[return-value]
    return node  # type: ignore[return-value]


def first(body: dict, *paths: tuple[str, ...]) -> dict | list | None:
    """The first of several plausible nestings that yields something.

    Written because the DS answers are documented in more than one shape
    (`aliexpress_ds_..._response.resp_result.result`, `.result`, `.data`),
    and a reader that knows only one of them reports "nessun risultato" for
    an answer that is in fact full of data."""
    for path in paths:
        found = unwrap(body, *path)
        if found not in (None, [], {}):
            return found
    return None


def items_of(node, *names: str) -> list:
    """A DS list, which arrives either as a plain list or as an object with
    one key holding it (`{"ae_item_sku_info_d_t_o": [...]}`, `{"number": [...]}`)."""
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        for name in names:
            inner = node.get(name)
            if isinstance(inner, list):
                return inner
            if isinstance(inner, dict):
                return [inner]
        # Only one key, and it holds the list: take it whatever it is called.
        values = list(node.values())
        if len(values) == 1 and isinstance(values[0], list):
            return values[0]
    return []


# --- Operazioni DS ------------------------------------------------------------------------------
#
# Every method below is one `call()`. The parameter names are the ones the DS
# documentation gives; those that could not be checked against a live answer
# are marked, and the readers in service.py accept more than one spelling.


async def category_get(settings: AliexpressSettings, *, language: str = "it") -> dict:
    """The cheap call used as connection test: the categories the account
    may sell. Proves the token and the DS permission at once."""
    return await call(settings, "aliexpress.ds.category.get", {"language": language})


async def text_search(
    settings: AliexpressSettings,
    *,
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    sort_by: str | None = None,
) -> dict:
    return await call(
        settings,
        "aliexpress.ds.text.search",
        {
            "keyWord": keyword,
            # `local` is the locale of the texts, `countryCode` the shipping
            # destination: both matter for the prices that come back.
            "local": f"{settings.target_language}_{settings.ship_to_country}",
            "countryCode": settings.ship_to_country,
            "currency": settings.target_currency,
            "pageSize": str(page_size),
            "pageIndex": str(page),
            "sortBy": sort_by,
        },
    )


async def product_get(settings: AliexpressSettings, *, product_id: str) -> dict:
    return await call(
        settings,
        "aliexpress.ds.product.get",
        {
            "product_id": str(product_id),
            "ship_to_country": settings.ship_to_country,
            "target_currency": settings.target_currency,
            "target_language": settings.target_language,
        },
    )


async def freight_query(
    settings: AliexpressSettings, *, product_id: str, sku_id: str | None, quantity: int
) -> dict:
    """Shipping cost and time to Italy for one product. The DS gateway wants
    this one as a JSON string under a single parameter."""
    query = {
        "productId": str(product_id),
        "selectedSkuId": str(sku_id) if sku_id else None,
        "quantity": str(quantity),
        "shipToCountry": settings.ship_to_country,
        "currency": settings.target_currency,
        "language": settings.target_language,
        "locale": f"{settings.target_language}_{settings.ship_to_country}",
    }
    return await call(
        settings,
        "aliexpress.ds.freight.query",
        {"queryDeliveryReq": json.dumps({k: v for k, v in query.items() if v is not None})},
    )


async def order_create(settings: AliexpressSettings, *, request: dict) -> dict:
    """Places the dropshipping order. `request` carries the logistics address
    and the product items, as service.py builds it."""
    return await call(
        settings,
        "aliexpress.ds.order.create",
        {"param_place_order_request4_open_api_d_t_o": json.dumps(request)},
    )


async def order_tracking(settings: AliexpressSettings, *, order_id: str) -> dict:
    """Tracking of one order. The DS method is the right one; the older
    logistics method is tried after it because more accounts are entitled to
    it, and between the two at least one usually answers."""
    try:
        return await call(
            settings,
            "aliexpress.ds.order.tracking.get",
            {
                "ae_order_id": str(order_id),
                "language": f"{settings.target_language}_{settings.ship_to_country.upper()}",
            },
        )
    except AliexpressApiError as exc:
        if exc.kind == "AUTHENTICATION":
            # A refused token is not a reason to try a second method: it
            # would only be refused again, and the administrator must know.
            raise
        logger.info("ds.order.tracking.get unavailable for order %s (%s): falling back", order_id, exc)
        return await call(
            settings,
            "aliexpress.logistics.ds.trackinginfo.query",
            {"out_ref": str(order_id), "origin": "ESCROW", "service_name": "all"},
        )
