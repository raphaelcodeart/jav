"""Il modello linguistico di JAVBOT e degli articoli, e il conto dei token.

**La regola è spendere poco.** Il modello non cerca dati e non fa conti:
quelli li trovano il codice (gli strumenti, le azioni in actions.py, il
RAG in rag.py) e il database. Il modello serve a due cose sole — capire
una frase che le regole non capiscono, e scrivere una risposta naturale con
i dati già trovati — e ogni chiamata è piccola: un modello piccolo
(`OPENAI_MODEL`), poco storico, pochi passaggi, un tetto di token in uscita.

Ogni risposta, anche quelle senza modello, lascia una riga in
`javbot_usage` (route, token): è da lì che la console mostra quante
risposte sono costate zero e quanto è costato il resto. Oltre il tetto
giornaliero di tutta la piattaforma (`JAVBOT_DAILY_TOKEN_BUDGET`) il
modello si spegne fino a domani e JAVBOT risponde con regole e documenti.

Fornitore: OpenAI (Chat Completions, via httpx: niente SDK in più
nell'immagine). Se manca la chiave OpenAI ma c'è quella di Anthropic,
l'assistente con gli strumenti resta quello di assistant.py.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow

logger = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
#: Una risposta in chat: meglio le regole subito che un utente che aspetta.
TIMEOUT_SECONDS = 30.0


class LlmUnavailable(Exception):
    """Niente chiave, tetto raggiunto o API che non risponde: chi chiama
    risponde senza modello."""


@dataclass
class LlmResult:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    #: Il messaggio dell'assistente da rimettere nello storico (con i tool_calls).
    message: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    model: str = ""


@dataclass
class Spend:
    """I token di una risposta, che può fare più chiamate."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    model: str | None = None

    def add(self, result: LlmResult) -> None:
        self.calls += 1
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.cached_tokens += result.cached_tokens
        self.model = result.model


def provider() -> str | None:
    settings = get_settings()
    if settings.openai_api_key:
        return "openai"
    if settings.anthropic_api_key:
        return "anthropic"
    return None


def enabled() -> bool:
    return bool(get_settings().openai_api_key)


def _is_reasoning(model: str) -> bool:
    # I modelli che ragionano non accettano la temperatura e spendono token
    # di ragionamento: con loro si chiede lo sforzo minimo.
    return model.startswith(("o1", "o3", "o4", "gpt-5", "gpt-6"))


async def budget_left(db: AsyncSession) -> bool:
    """Il tetto di token di oggi, per tutta la piattaforma."""
    from app.domains.javbot.models import JavbotUsage

    cap = get_settings().javbot_daily_token_budget
    if cap <= 0:
        return True
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    spent = (await db.execute(select(
        func.coalesce(func.sum(JavbotUsage.input_tokens + JavbotUsage.output_tokens), 0),
    ).where(JavbotUsage.created_at >= since))).scalar_one()
    return int(spent) < cap


async def chat(
    db: AsyncSession, messages: list[dict], *, tools: list[dict] | None = None, max_tokens: int = 400,
    json_mode: bool = False, temperature: float = 0.2,
) -> LlmResult:
    """Una chiamata al modello. `tools` nel formato OpenAI
    ({"type": "function", "function": {...}}). Solleva LlmUnavailable se il
    modello non c'è, il tetto è superato o l'API non risponde."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise LlmUnavailable("no key")
    if not await budget_left(db):
        raise LlmUnavailable("budget")
    model = settings.openai_model
    body: dict = {"model": model, "messages": messages, "max_completion_tokens": max_tokens}
    if _is_reasoning(model):
        body["reasoning_effort"] = "minimal" if model.startswith("gpt-5") else "low"
    else:
        body["temperature"] = temperature
    if tools:
        body["tools"] = tools
        body["parallel_tool_calls"] = True
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(OPENAI_URL, json=body,
                                         headers={"Authorization": f"Bearer {settings.openai_api_key}"})
        if response.status_code >= 400:
            logger.warning("javbot llm: OpenAI %s %s", response.status_code, response.text[:300])
            raise LlmUnavailable(f"http {response.status_code}")
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("javbot llm: OpenAI non raggiungibile: %s", exc)
        raise LlmUnavailable("network") from exc
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}
    calls = []
    for call in message.get("tool_calls") or []:
        try:
            args = json.loads(call.get("function", {}).get("arguments") or "{}")
        except ValueError:
            args = {}
        calls.append({"id": call.get("id"), "name": call.get("function", {}).get("name"), "args": args})
    return LlmResult(
        text=(message.get("content") or "").strip(), tool_calls=calls,
        message={k: v for k, v in message.items() if k in ("role", "content", "tool_calls")},
        input_tokens=int(usage.get("prompt_tokens") or 0), output_tokens=int(usage.get("completion_tokens") or 0),
        cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        model=data.get("model") or model,
    )


async def chat_json(db: AsyncSession, system: str, user: str, *, max_tokens: int = 200,
                    spend: Spend | None = None) -> dict:
    """Una domanda che vuole un JSON piccolo (capire i dettagli di un'azione)."""
    result = await chat(db, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                        max_tokens=max_tokens, json_mode=True, temperature=0)
    if spend is not None:
        spend.add(result)
    try:
        out = json.loads(result.text or "{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


async def record(
    db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None, user_id: uuid.UUID | None,
    route: str, spend: Spend | None = None, intent: str | None = None, ok: bool = True,
) -> None:
    """La riga del contatore. Non fa commit: va con la risposta."""
    from app.domains.javbot.models import JavbotUsage

    spend = spend or Spend()
    db.add(JavbotUsage(
        organization_id=organization_id, club_id=club_id, user_id=user_id, route=route,
        provider="openai" if spend.calls else None, model=spend.model, calls=spend.calls,
        input_tokens=spend.input_tokens, output_tokens=spend.output_tokens, cached_tokens=spend.cached_tokens,
        intent=(intent or "")[:40] or None, ok=ok,
    ))


async def usage_summary(db: AsyncSession, *, organization_id: uuid.UUID, days: int = 30,
                        club_id: uuid.UUID | None = None) -> dict:
    """Per la console: le risposte per strada (quante a costo zero) e i
    token per giorno negli ultimi `days` giorni."""
    from app.domains.javbot.models import JavbotUsage

    since = utcnow() - timedelta(days=days)
    base = select(JavbotUsage).where(JavbotUsage.organization_id == organization_id, JavbotUsage.created_at >= since)
    if club_id is not None:
        base = base.where(JavbotUsage.club_id == club_id)
    sub = base.subquery()
    routes = {route: {"answers": n, "input_tokens": int(i or 0), "output_tokens": int(o or 0)}
              for route, n, i, o in (await db.execute(
                  select(sub.c.route, func.count(), func.sum(sub.c.input_tokens), func.sum(sub.c.output_tokens))
                  .group_by(sub.c.route))).all()}
    day = func.date_trunc("day", sub.c.created_at)
    daily = [{"day": d.date(), "answers": n, "tokens": int(t or 0)}
             for d, n, t in (await db.execute(
                 select(day, func.count(), func.sum(sub.c.input_tokens + sub.c.output_tokens))
                 .group_by(day).order_by(day))).all()]
    total = sum(r["answers"] for r in routes.values())
    free = sum(r["answers"] for k, r in routes.items() if k in ("RULES", "ACTION", "CACHE"))
    intents = [{"intent": i, "answers": n} for i, n in (await db.execute(
        select(sub.c.intent, func.count()).where(sub.c.intent.is_not(None))
        .group_by(sub.c.intent).order_by(func.count().desc()).limit(10))).all()]
    return {
        "days": days, "answers": total, "free_answers": free,
        "free_share": round(free / total, 3) if total else None,
        "tokens": sum(r["input_tokens"] + r["output_tokens"] for r in routes.values()),
        "routes": routes, "daily": daily, "top_intents": intents,
        "model": get_settings().openai_model if enabled() else None,
        "budget_per_day": get_settings().javbot_daily_token_budget,
    }
