"""L'API affiliati di SoleilDrop (v1, 08/10/2026), come la usa questa app.

Docs: https://www.soleildrop.com/api-affiliati.html

- **Autenticazione**: `Authorization: Bearer sdk_…`, la chiave generata
  nell'area SoleilDrop. Non finisce mai in un URL, quindi nemmeno nei log.
- **Risposte**: sempre JSON con `ok`; quando `ok` è falso ci sono `error`
  (codice) e `message` (in italiano, già leggibile dall'amministratore).
- **Limite**: 120 chiamate al minuto per chiave. Le usiamo in poche decine
  l'ora (catalogo ogni 3 ore, ordini uno per acquisto, controllo stati ogni
  30 minuti), quindi niente coda: un 429 diventa un errore «riprova», come un
  5xx.

Le chiamate restituiscono il corpo JSON; chi sbaglia riceve SoleilApiError
con stato HTTP e codice SoleilDrop, perché chi chiama deve distinguere «non
riprovare» (422: prodotto sconosciuto, indirizzo incompleto…) da «riprova»
(409 busy/price_changed, 429, 5xx, rete).
"""

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.soleildrop.com/api/affiliate/v1"
TIMEOUT_SECONDS = 30
#: Il catalogo intero sta in una risposta sola: più tempo.
CATALOG_TIMEOUT_SECONDS = 180


class SoleilApiError(Exception):
    """`status` è l'HTTP (None = la rete), `code` il codice SoleilDrop."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None, body: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.body = body or {}

    @property
    def retryable(self) -> bool:
        """Vale la pena riprovare da soli? Rete, 409 (busy, price_changed),
        429 e 5xx sì; il resto lo deve guardare una persona."""
        return self.status is None or self.status in (409, 429) or self.status >= 500


class SoleilNotConfiguredError(SoleilApiError):
    pass


def _headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        raise SoleilNotConfiguredError("La chiave API di SoleilDrop non è impostata.")
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _parse(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise SoleilApiError(
            f"SoleilDrop ha risposto in modo inatteso (HTTP {response.status_code}).", status=response.status_code
        )
    if response.status_code >= 400 or body.get("ok") is False:
        code = body.get("error")
        message = body.get("message") or code or f"HTTP {response.status_code}"
        raise SoleilApiError(f"SoleilDrop: {message}", status=response.status_code, code=code, body=body)
    return body


async def _request(
    method: str, path: str, *, api_key: str | None, params: dict | None = None, json: dict | None = None,
    timeout: float = TIMEOUT_SECONDS, transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[int, dict]:
    headers = _headers(api_key)
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=timeout, transport=transport) as http:
            response = await http.request(method, path, params=params, json=json, headers=headers)
    except httpx.HTTPError as exc:
        raise SoleilApiError(f"SoleilDrop non raggiungibile: {exc.__class__.__name__}.") from exc
    return response.status_code, _parse(response)


#: I test sostituiscono il trasporto HTTP qui, senza toccare la rete.
TRANSPORT: httpx.AsyncBaseTransport | None = None


async def me(api_key: str | None) -> dict:
    return (await _request("GET", "/me", api_key=api_key, transport=TRANSPORT))[1]


async def wallet(api_key: str | None) -> dict:
    return (await _request("GET", "/wallet", api_key=api_key, params={"limit": 1}, transport=TRANSPORT))[1]


async def catalog(api_key: str | None) -> dict:
    """Tutte le referenze assegnate al negozio, anche quelle non ancora
    pubblicate nell'area SoleilDrop (`all=1`): come l'export Excel «Tutte
    quelle in elenco», le importiamo tutte e spente."""
    return (await _request(
        "GET", "/catalog", api_key=api_key, params={"all": 1}, timeout=CATALOG_TIMEOUT_SECONDS, transport=TRANSPORT,
    ))[1]


async def create_order(api_key: str | None, payload: dict) -> tuple[int, dict]:
    """201 = partito e pagato dal wallet; 202 = in attesa di credito; 200 con
    `duplicate` = già partito con questo external_ref (nessun nuovo addebito)."""
    return await _request("POST", "/orders", api_key=api_key, json=payload, transport=TRANSPORT)


async def get_order(api_key: str | None, ref: str) -> dict:
    """Un ordine per numero SoleilDrop o per external_ref."""
    return (await _request("GET", f"/orders/{ref}", api_key=api_key, transport=TRANSPORT))[1]


async def list_orders(api_key: str | None, *, since: str | None = None, limit: int = 200) -> dict:
    params: dict = {"limit": limit}
    if since:
        params["since"] = since
    return (await _request("GET", "/orders", api_key=api_key, params=params, transport=TRANSPORT))[1]
