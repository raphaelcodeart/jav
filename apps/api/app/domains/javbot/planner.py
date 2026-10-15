"""Il "cervello" di JAVBOT: per ora deterministico, domani un modello.

Oggi una risposta nasce così: `intents.detect` riconosce che cosa chiede
l'utente (parole chiave in pt/it/en), il pianificatore chiama uno o più
strumenti di `tools.py` e scrive la risposta con le frasi di `texts.py`.
Tre percorsi hanno una piccola memoria (`JavbotConversation.state`): il
judogi (per chi → altezza → proposta → conferma), "come carico la ricevuta"
(che cosa hai pagato → passi) e il messaggio alla segreteria (testo →
conferma).

**Come sostituirlo con un modello vero (Claude)**, senza toccare gli
strumenti:

1. al modello si danno `REGISTRY.specs(audience="private")` come tools, un
   prompt di sistema con le regole (lingua dell'utente, mai importi propri,
   per scrivere si propone un compito e si aspetta il "sì") e gli ultimi
   messaggi della conversazione;
2. ogni `tool_use` del modello si esegue con `REGISTRY.call(nome, ctx, args)`
   — gli stessi permessi e lo stesso club di oggi, perché li applicano gli
   strumenti, non il pianificatore;
3. per un'azione che scrive il modello chiama `propose_task` (da esporre
   come strumento: crea il `JavbotTask` PENDING e restituisce l'id); la
   conferma resta `execute_task`, cioè un bottone o un "sì" dell'utente,
   mai il modello da solo;
4. la risposta finale del modello diventa `Reply.text`; i bottoni
   (`Reply.actions`) restano quelli definiti qui (`nav`, `open_pay`,
   `confirm`), che il modello può scegliere per nome.

`Planner.reply` è l'unico punto da cambiare: service.py, router e
interfaccia non se ne accorgono.
"""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import update

from app.core.db import utcnow
from app.domains.javbot import intents, texts
from app.domains.javbot.models import TASK_TTL_MINUTES, JavbotConversation, JavbotTask
from app.domains.javbot.texts import euro, say
from app.domains.javbot.tools import (
    FAMILY,
    INSTRUCT,
    MANAGE,
    REGISTRY,
    ToolContext,
    ToolDenied,
    first_name_in,
)


@dataclass
class Reply:
    text: str
    actions: list[dict] = field(default_factory=list)
    quick_replies: list[str] = field(default_factory=list)
    #: La memoria corta dopo questa risposta: {} chiude ogni percorso.
    state: dict = field(default_factory=dict)
    intent: str | None = None


# --- I bottoni che l'interfaccia sa mostrare ------------------------------------------------------
#
# `navigate.target` è un nome di sezione, non una rotta: la dashboard lo
# traduce nella scheda giusta per l'area in cui si trova l'utente.


def nav(lang: str, target: str, label_key: str) -> dict:
    return {"type": "navigate", "target": target, "label": say(lang, label_key)}


def open_pay(lang: str, kind: str) -> dict:
    """Apre "Carica un pagamento": `fees` direttamente sulle quote, `choose`
    sulla scelta quote / ordine dello Shop."""
    return {"type": "open_pay", "kind": kind, "label": say(lang, "act.pay")}


def confirm(task_id: uuid.UUID, label: str) -> dict:
    return {"type": "confirm_task", "task_id": str(task_id), "label": label}


def cancel(task_id: uuid.UUID, lang: str) -> dict:
    return {"type": "cancel_task", "task_id": str(task_id), "label": say(lang, "act.cancel")}


def link(href: str, label: str) -> dict:
    return {"type": "link", "href": href, "label": label}


def copy(value: str, label: str) -> dict:
    return {"type": "copy", "value": value, "label": label}


ORDER_WORDS = ("ordine", "order", "encomenda", "shop", "loja", "negozio", "judogi", "materiale", "material")
FEES_WORDS = (
    "quote", "quota", "quotas", "fees", "fee", "mensilita", "mensalidade", "mensalidades", "club", "clube",
    "iscrizione", "inscricao", "enrolment",
)
PROBLEM_WORDS = (
    "non funziona", "non va", "non riesco", "errore", "problema", "nao funciona", "nao consigo", "erro",
    "doesn't work", "does not work", "can't", "cannot", "error", "problem", "fails",
)
STAFF_WORDS = ("scadut*", "chi", "quem", "who", "caducad*", "expired", "atleti", "atletas", "athletes", "club", "clube")


class Planner:
    """Una risposta per un messaggio, nella lingua di `ctx.lang`."""

    def __init__(self, ctx: ToolContext, conversation: JavbotConversation):
        self.ctx = ctx
        self.conversation = conversation
        self.lang = ctx.lang

    # --- Accesso agli strumenti -------------------------------------------------------------------

    async def tool(self, name: str, args: dict | None = None) -> dict:
        return await REGISTRY.call(name, self.ctx, args)

    def can(self, permission: str) -> bool:
        return self.ctx.scope is not None and permission in self.ctx.permissions

    async def new_task(self, kind: str, payload: dict) -> JavbotTask:
        task = JavbotTask(
            organization_id=self.ctx.organization_id, conversation_id=self.conversation.id,
            user_id=self.ctx.user_id, club_id=self.ctx.scope.club_id if self.ctx.scope else None,
            kind=kind, payload=payload, status="PENDING",
        )
        self.ctx.db.add(task)
        await self.ctx.db.flush()
        return task

    def suggestions(self) -> list[str]:
        if self.can(FAMILY):
            keys = ("qr.overview", "qr.fees", "qr.paid", "qr.upload", "qr.judogi", "qr.secretary")
        elif self.can(MANAGE):
            keys = ("qr.staffUnpaid", "qr.lessons", "qr.staffCerts")
        elif self.can(INSTRUCT):
            keys = ("qr.lessons",)
        else:
            keys = ("qr.judogi", "qr.wallet")
        return [say(self.lang, k) for k in keys]

    # --- Saluto -----------------------------------------------------------------------------------

    async def greeting(self) -> Reply:
        from app.domains.club.models import Club

        if self.can(FAMILY):
            club = await self.ctx.db.get(Club, self.ctx.scope.club_id)
            text = say(self.lang, "greet", club=club.name if club else "Jav")
        elif self.can(MANAGE) or self.can(INSTRUCT):
            text = say(self.lang, "greetStaff")
        else:
            text = say(self.lang, "greetNoClub")
        return Reply(text, quick_replies=self.suggestions(), intent="greet")

    # --- Un messaggio -----------------------------------------------------------------------------

    async def reply(self, text: str) -> Reply:
        state = dict(self.conversation.state or {})
        intent, score = intents.detect(text, lang=self.lang)

        pending = state.get("pending_task")
        if pending:
            if intents.is_yes(text):
                return await execute_task(self.ctx, uuid.UUID(pending))
            if intents.is_no(text):
                return await cancel_task(self.ctx, uuid.UUID(pending))
            # Qualunque altra cosa: la proposta resta valida sul suo bottone,
            # ma un "sì" detto più avanti non deve confermarla per sbaglio.
            state.pop("pending_task", None)

        try:
            flow = state.get("flow")
            if flow:
                continued = await self.continue_flow(flow, text, state, intent, score)
                if continued is not None:
                    return continued
            if intent is None:
                if flow:
                    return self.reask(state)
                return await self.from_knowledge(text)
            # Una sola parola chiave ("treino" in "posso trazer comida para o
            # treino?") è un indizio debole: se i documenti rispondono
            # davvero alla domanda intera, rispondono loro.
            if score <= 1 and not flow:
                quoted = await self.from_knowledge(text, strict=True)
                if quoted is not None:
                    return quoted
            return await self.dispatch(intent, text, score)
        except ToolDenied as denied:
            return Reply(say(self.lang, denied.reason), quick_replies=self.suggestions(), intent=intent)

    async def from_knowledge(self, text: str, *, strict: bool = False) -> Reply | None:
        """Una domanda che nessuna intenzione riconosce: prima di dire "non
        ho capito" si cerca nei PDF della base comune e del club
        (knowledge.py), e si mostrano gli estratti con il documento e la
        pagina. Senza modello non si riassume né si interpreta: si cita.
        Con `strict` niente ripiego: None se i documenti non rispondono."""
        from app.domains.javbot import knowledge

        organization_id = self.ctx.scope.organization_id if self.ctx.scope else self.ctx.organization_id
        found = await knowledge.passages(
            self.ctx.db, organization_id=organization_id,
            club_id=self.ctx.scope.club_id if self.ctx.scope else None, query=text, strict=strict,
        ) if organization_id else []
        if not found:
            return None if strict else Reply(say(self.lang, "fallback"), quick_replies=self.suggestions())
        parts = [say(self.lang, "kb.found")]
        for hit in found:
            parts.append(f"«{hit['excerpt']}»\n" + say(self.lang, "kb.source", title=hit["document"], page=hit["page"]))
        parts.append(say(self.lang, "kb.more"))
        return Reply("\n\n".join(parts), quick_replies=self.suggestions(), intent="knowledge")

    def reask(self, state: dict) -> Reply:
        question = state.get("question") or say(self.lang, "fallback")
        return Reply(say(self.lang, "reask", question=question), quick_replies=state.get("qr", []), state=state)

    async def continue_flow(self, flow: str, text: str, state: dict, intent: str | None, score: int) -> Reply | None:
        """Prima di cercare un argomento nuovo, prova a leggere il messaggio
        come risposta alla domanda in sospeso. None = non è una risposta."""
        if flow == "judogi":
            step = state.get("step")
            if step == "athlete":
                names = [a["first_name"] for a in state.get("athletes", [])]
                if first_name_in(text, names):
                    return await self.judogi(text, state)
            if step == "height" and intents.extract_height_cm(text) is not None:
                return await self.judogi(text, state)
            return None
        if flow == "upload":
            if intents.mentions(text, *PROBLEM_WORDS):
                return self.upload_problems()
            if intents.mentions(text, *ORDER_WORDS):
                return await self.upload_order()
            if intents.mentions(text, *FEES_WORDS):
                return await self.upload_fees()
            return None
        if flow == "secretary":
            if intent not in (None, "secretary") and score >= 3:
                return None
            return await self.secretary_message(text)
        return None

    async def dispatch(self, intent: str, text: str, score: int) -> Reply:
        lang = self.lang
        if intent == "greet":
            reply = await self.greeting()
            return reply
        if intent == "help":
            return Reply(say(lang, "help"), quick_replies=self.suggestions(), intent=intent)
        if intent == "thanks":
            return Reply(say(lang, "thanks"), quick_replies=self.suggestions(), intent=intent)
        if intent == "fees_due":
            if not self.can(FAMILY) and self.can(MANAGE):
                return await self.staff_unpaid()
            return await self.fees()
        if intent == "staff_unpaid":
            # "Estou em dívida?" detto da un genitore: parla di sé, non del club.
            if self.can(FAMILY) and not self.can(MANAGE):
                return await self.fees()
            return await self.staff_unpaid()
        if intent == "payments_made":
            return await self.payments()
        if intent == "overview":
            return await (self.overview() if self.can(FAMILY) else self.profile(text))
        if intent == "my_profile":
            return await self.profile(text)
        if intent == "belts":
            return await self.belts(text)
        if intent == "attendance_stats":
            return await self.attendance(text)
        if intent == "ranking":
            return await self.ranking(text)
        if intent == "upload_proof":
            if intents.mentions(text, *ORDER_WORDS):
                return await self.upload_order()
            if intents.mentions(text, *FEES_WORDS):
                return await self.upload_fees()
            question = say(lang, "upload.ask")
            qr = [say(lang, "qr.kindFees"), say(lang, "qr.kindOrder")]
            return Reply(question, quick_replies=qr, intent=intent,
                         state={"flow": "upload", "question": question, "qr": qr})
        if intent == "judogi":
            return await self.judogi(text, {})
        if intent == "shop":
            return Reply(say(lang, "shop.text"), actions=[nav(lang, "shop", "act.shop")],
                         quick_replies=[say(lang, "qr.judogi")], intent=intent)
        if intent == "certificates":
            staff_view = self.can(MANAGE) and (not self.can(FAMILY) or intents.mentions(text, *STAFF_WORDS))
            return await (self.staff_certificates() if staff_view else self.certificates())
        if intent == "competitions":
            return await self.competitions()
        if intent in ("lessons_today", "mark_attendance"):
            if self.can(FAMILY):
                return await self.lessons()
            return await self.staff_lessons()
        if intent == "invite":
            return await self.invite()
        if intent == "wallet":
            data = await self.tool("wallet_balance")
            return Reply(say(lang, "wallet.text", amount=euro(data["balance_cents"], lang)),
                         actions=[nav(lang, "wallet", "act.wallet")], quick_replies=self.suggestions(), intent=intent)
        if intent == "secretary":
            return await self.secretary()
        return await self.from_knowledge(text)

    # --- Quote e ricevute -------------------------------------------------------------------------

    async def fees(self) -> Reply:
        lang = self.lang
        data = await self.tool("family_dues")
        if not data["fees"]:
            return Reply(say(lang, "fees.none"), quick_replies=self.suggestions(), intent="fees_due")
        if data["overdue_cents"]:
            lines = [say(lang, "fees.totalOverdue", total=euro(data["due_cents"], lang), overdue=euro(data["overdue_cents"], lang))]
        else:
            lines = [say(lang, "fees.total", total=euro(data["due_cents"], lang))]
        for row in data["by_athlete"]:
            count = say(lang, "fees.countOne") if row["count"] == 1 else say(lang, "fees.countMany", n=row["count"])
            if row["overdue"]:
                count += (say(lang, "fees.overdueOne") if row["overdue"] == 1
                          else say(lang, "fees.overdueSuffix", n=row["overdue"]))
            lines.append(say(lang, "fees.line", name=row["first_name"] or say(lang, "fees.family"),
                             amount=euro(row["cents"], lang), count=count))
        lines.append(say(lang, "fees.next", date=texts.day(data["next_due_date"], lang)))
        bank = data["bank"]
        lines.append("")
        if bank["iban"]:
            lines.append(say(lang, "fees.bank", holder=bank["holder"] or data["club_name"] or "", iban=bank["iban"]))
            if bank["instructions"]:
                lines.append(bank["instructions"])
        else:
            lines.append(say(lang, "fees.noBank"))
        lines.append("")
        lines.append(say(lang, "fees.howTo"))
        return Reply("\n".join(lines), actions=[open_pay(lang, "fees"), nav(lang, "club", "act.club")],
                     quick_replies=[say(lang, "qr.upload"), say(lang, "qr.wallet")], intent="fees_due")

    async def upload_fees(self) -> Reply:
        lang = self.lang
        data = await self.tool("family_dues")
        after = {"flow": "upload", "question": say(lang, "upload.ask"), "qr": [say(lang, "qr.problems")]}
        if not data["fees"]:
            return Reply(say(lang, "upload.feesNothing"), quick_replies=[say(lang, "qr.kindOrder")],
                         state=after, intent="upload_proof")
        text = say(lang, "upload.feesSteps", n=len(data["fees"]), amount=euro(data["due_cents"], lang))
        return Reply(text, actions=[open_pay(lang, "fees")], quick_replies=[say(lang, "qr.problems")],
                     state=after, intent="upload_proof")

    async def upload_order(self) -> Reply:
        lang = self.lang
        data = await self.tool("shop_orders_awaiting_payment")
        after = {"flow": "upload", "question": say(lang, "upload.ask"), "qr": [say(lang, "qr.problems")]}
        if not data["orders"]:
            return Reply(say(lang, "upload.orderNothing"), actions=[nav(lang, "orders", "act.orders")],
                         quick_replies=[say(lang, "qr.kindFees")], state=after, intent="upload_proof")
        items = ", ".join(
            say(lang, "upload.orderItemProof" if o["proof_uploaded"] else "upload.orderItem",
                number=o["number"], amount=euro(o["amount_due_cents"], lang))
            for o in data["orders"]
        )
        return Reply(say(lang, "upload.orderSteps", list=items), actions=[open_pay(lang, "choose")],
                     quick_replies=[say(lang, "qr.problems")], state=after, intent="upload_proof")

    def upload_problems(self) -> Reply:
        from app.domains.javbot.tools import PROOF_MAX_MB

        lang = self.lang
        actions = [open_pay(lang, "choose")] if self.can(FAMILY) else [nav(self.lang, "orders", "act.orders")]
        return Reply(say(lang, "upload.problems", mb=PROOF_MAX_MB), actions=actions,
                     quick_replies=[say(lang, "qr.secretary")], intent="upload_proof")

    # --- I miei conti, i miei dati, il percorso --------------------------------------------------

    def personal_suggestions(self) -> list[str]:
        return [say(self.lang, k) for k in ("qr.paid", "qr.fees", "qr.myData", "qr.belts", "qr.attendance")]

    def owed_line(self, totals: dict) -> str:
        lang = self.lang
        if not totals["due_cents"]:
            return say(lang, "paid.allClear")
        if totals["overdue_cents"]:
            return say(lang, "paid.dueOverdue", due=euro(totals["due_cents"], lang),
                       overdue=euro(totals["overdue_cents"], lang))
        return say(lang, "paid.due", due=euro(totals["due_cents"], lang))

    def fee_label(self, row: dict) -> str:
        lang = self.lang
        label = say(lang, f"feeKind.{row['kind']}")
        if row["kind"] == "MONTHLY" and row["period"] and len(row["period"]) == 7:
            label = f"{label} {texts.month_label(row['period'])}"
        elif row["kind"] == "COMPETITION" and row["description"]:
            label = f"{label} {row['description']}"
        if row["first_name"]:
            label = say(lang, "paid.of", label=label, name=row["first_name"])
        return label

    async def payments(self) -> Reply:
        lang = self.lang
        data = await self.tool("family_payments")
        totals = data["totals"]
        lines = []
        if not data["paid_count"]:
            lines.append(say(lang, "paid.nothing"))
        else:
            lines.append(say(lang, "paid.total", year=data["year"], amount=euro(totals["paid_year_cents"], lang),
                             all=euro(totals["paid_all_time_cents"], lang)))
            for person in data["people"]:
                if person["paid_year_cents"]:
                    lines.append(say(lang, "paid.person", name=person["first_name"] or say(lang, "fees.family"),
                                     amount=euro(person["paid_year_cents"], lang)))
            lines.append("")
            lines.append(say(lang, "paid.recent"))
            for row in data["recent"]:
                lines.append(say(lang, "paid.line", date=texts.day(row["paid_on"], lang), label=self.fee_label(row),
                                 amount=euro(row["amount_cents"], lang)))
            if data["paid_count"] > len(data["recent"]):
                lines.append(say(lang, "paid.more", n=data["paid_count"] - len(data["recent"])))
        if data["shop"]["year_cents"]:
            lines.append(say(lang, "paid.shop", amount=euro(data["shop"]["year_cents"], lang),
                             n=data["shop"]["orders_year"]))
        if totals["savings_year_cents"]:
            lines.append(say(lang, "paid.savings", amount=euro(totals["savings_year_cents"], lang)))
        lines.append("")
        lines.append(self.owed_line(totals))
        if data["wallet_balance_cents"]:
            lines.append(say(lang, "paid.wallet", amount=euro(data["wallet_balance_cents"], lang)))
        actions = [nav(lang, "accounts", "act.accounts")]
        if totals["due_cents"]:
            actions.insert(0, open_pay(lang, "fees"))
        return Reply("\n".join(lines), actions=actions, quick_replies=self.personal_suggestions(),
                     intent="payments_made")

    def only_named(self, rows: list[dict], text: str) -> list[dict]:
        """"Che cintura ha Luca?": solo Luca. Nessun nome: tutta la famiglia."""
        name = first_name_in(text, [r["first_name"] for r in rows])
        return [r for r in rows if r["first_name"] == name] if name else rows

    def certificate_text(self, status: str, expires_on) -> str:
        return say(self.lang, f"cert.{status}", date=texts.day(expires_on, self.lang))

    async def profile(self, text: str) -> Reply:
        lang = self.lang
        data = await self.tool("my_profile")
        name = " ".join(p for p in (data["first_name"], data["last_name"]) if p)
        lines = [say(lang, "profile.intro")]
        for key, value in (("name", name), ("email", data["email"]), ("phone", data["phone"]),
                           ("fiscal", data["fiscal_code"])):
            if value:
                lines.append(say(lang, f"profile.{key}", v=value))
        if data["address"]:
            a = data["address"]
            place = " ".join(p for p in (a["postal_code"], a["city"]) if p)
            province = f" ({a['province']})" if a["province"] else ""
            lines.append(say(lang, "profile.address", v=f"{a['street']}, {place}{province}"))
        for athlete in self.only_named(data["athletes"], text):
            lines.append("")
            who = say(lang, "profile.you") if athlete["is_self"] else f"{athlete['first_name']} {athlete['last_name']}"
            lines.append(say(lang, "profile.athlete", name=who, birth=texts.day(athlete["birth_date"], lang),
                             age=athlete["age"]))
            if athlete["plan_name"]:
                lines.append(say(lang, "profile.plan", plan=athlete["plan_name"],
                                 fee=euro(athlete["monthly_fee_cents"], lang)))
            if athlete["federation_number"]:
                expires = (say(lang, "profile.until", date=texts.day(athlete["federation_expires_on"], lang))
                           if athlete["federation_expires_on"] else "")
                lines.append(say(lang, "profile.federation", n=athlete["federation_number"], until=expires))
            if athlete["fiscal_code"]:
                lines.append(say(lang, "profile.fiscal", v=athlete["fiscal_code"]))
            if athlete["weight_kg"] is not None:
                lines.append(say(lang, "profile.weight", kg=f"{athlete['weight_kg']:g}"))
            lines.append(say(lang, "profile.joined", date=texts.day(athlete["joined_on"], lang)))
            lines.append(f"• {self.certificate_text(athlete['certificate'], athlete['certificate_expires_on'])}")
            if athlete["status"] != "ACTIVE":
                lines.append(say(lang, "profile.suspended"))
        lines.append("")
        lines.append(say(lang, "profile.fix"))
        return Reply("\n".join(lines), actions=[nav(lang, "settings", "act.myData")],
                     quick_replies=self.personal_suggestions(), intent="my_profile")

    def belt_text(self, code: str) -> str:
        if code.startswith("BLACK_"):
            return say(self.lang, "beltName.BLACK", n=code.split("_")[1])
        return say(self.lang, f"beltName.{code}")

    async def belts(self, text: str) -> Reply:
        lang = self.lang
        data = await self.tool("family_progress")
        if not data["has_belts"]:
            return Reply(say(lang, "belts.notInCourses"), quick_replies=self.personal_suggestions(), intent="belts")
        rows = self.only_named(data["athletes"], text)
        if not rows:
            return Reply(say(lang, "progress.none"), quick_replies=self.suggestions(), intent="belts")
        lines = [say(lang, "belts.intro")]
        for row in rows:
            since = say(lang, "belts.since", date=texts.day(row["belt_since"], lang)) if row["belt_since"] else ""
            lines.append(say(lang, "belts.line", name=row["first_name"], belt=self.belt_text(row["belt"] or "WHITE"),
                             since=since))
        lines.append("")
        lines.append(say(lang, "belts.how"))
        return Reply("\n".join(lines), actions=[nav(lang, "club", "act.club")],
                     quick_replies=self.personal_suggestions(), intent="belts")

    async def attendance(self, text: str) -> Reply:
        lang = self.lang
        data = await self.tool("family_progress")
        rows = self.only_named(data["athletes"], text)
        if not rows:
            return Reply(say(lang, "progress.none"), quick_replies=self.suggestions(), intent="attendance_stats")
        lines = [say(lang, "attendance.intro")]
        for row in rows:
            lines.append(say(lang, "attendance.line", name=row["first_name"], month=row["attendances_month"],
                             season=row["attendances_season"], label=data["season_label"], all=row["attendances"]))
        return Reply("\n".join(lines), actions=[nav(lang, "club", "act.club")],
                     quick_replies=self.personal_suggestions(), intent="attendance_stats")

    async def ranking(self, text: str) -> Reply:
        lang = self.lang
        data = await self.tool("family_progress")
        rows = self.only_named(data["athletes"], text)
        if not rows:
            return Reply(say(lang, "progress.none"), quick_replies=self.suggestions(), intent="ranking")
        lines = []
        for row in rows:
            if data["has_competitions"]:
                m = row["medals"]
                lines.append(say(lang, "ranking.line", name=row["first_name"], points=row["ranking_points"],
                                 label=data["season_label"], gold=m["gold"], silver=m["silver"], bronze=m["bronze"],
                                 level=row["level"], n=row["achievements_earned"]))
                comp = row["next_competition"]
                if comp:
                    lines.append(say(lang, "ranking.next", name=comp["name"], date=texts.day(comp["starts_on"], lang)))
            else:
                lines.append(say(lang, "ranking.levelOnly", name=row["first_name"], level=row["level"],
                                 n=row["achievements_earned"]))
        actions = [nav(lang, "competitions", "act.competitions")] if data["has_competitions"] else []
        return Reply("\n".join(lines), actions=actions, quick_replies=self.personal_suggestions(), intent="ranking")

    async def overview(self) -> Reply:
        """"Che cosa sai di me?": chi sei, ogni atleta in una riga, i conti."""
        lang = self.lang
        me = await self.tool("my_profile")
        progress = {r["first_name"]: r for r in (await self.tool("family_progress"))["athletes"]}
        money = await self.tool("family_payments")
        name = me["first_name"] or ""
        lines = [say(lang, "overview.intro", name=f" {name}" if name else "", club=me["club_name"] or "Jav")]
        for athlete in me["athletes"]:
            row = progress.get(athlete["first_name"], {})
            parts = [say(lang, "overview.age", n=athlete["age"])]
            if athlete["plan_name"]:
                parts.append(athlete["plan_name"])
            if row.get("belt"):
                parts.append(say(lang, "overview.belt", belt=self.belt_text(row["belt"])))
            parts.append(self.certificate_text(athlete["certificate"], athlete["certificate_expires_on"]))
            parts.append(say(lang, "overview.month", n=row.get("attendances_month", 0)))
            who = say(lang, "profile.you") if athlete["is_self"] else athlete["first_name"]
            lines.append(f"• {who}: {', '.join(parts)}")
        totals = money["totals"]
        lines.append("")
        lines.append(say(lang, "overview.paid", year=money["year"], amount=euro(totals["paid_year_cents"], lang)))
        lines.append(self.owed_line(totals))
        if money["wallet_balance_cents"]:
            lines.append(say(lang, "paid.wallet", amount=euro(money["wallet_balance_cents"], lang)))
        lines.append("")
        lines.append(say(lang, "overview.more"))
        return Reply("\n".join(lines), actions=[nav(lang, "accounts", "act.accounts")],
                     quick_replies=self.personal_suggestions(), intent="overview")

    # --- Judogi -----------------------------------------------------------------------------------

    async def judogi(self, text: str, state: dict) -> Reply:
        """Per chi → altezza → taglia e prezzo → conferma. Ogni passo si
        salta se il messaggio porta già la risposta ("judogi per Luca, 145")."""
        lang = self.lang
        athletes = state.get("athletes")
        if athletes is None:
            athletes = []
            if self.can(FAMILY):
                data = await self.tool("family_athletes")
                athletes = [{"id": str(a["id"]), "first_name": a["first_name"], "is_self": a["is_self"]}
                            for a in data["athletes"]]
        st: dict = {"flow": "judogi", "athletes": athletes}
        for key in ("athlete_id", "athlete_name", "is_self"):
            if key in state:
                st[key] = state[key]

        if "athlete_id" not in st:
            chosen = None
            if len(athletes) == 1:
                chosen = athletes[0]
            elif len(athletes) > 1:
                name = first_name_in(text, [a["first_name"] for a in athletes])
                chosen = next((a for a in athletes if a["first_name"] == name), None)
                if chosen is None:
                    question = say(lang, "judogi.whichAthlete")
                    qr = [a["first_name"] for a in athletes]
                    return Reply(question, quick_replies=qr, intent="judogi",
                                 state={**st, "step": "athlete", "question": question, "qr": qr})
            st["athlete_id"] = chosen["id"] if chosen else None
            st["athlete_name"] = chosen["first_name"] if chosen else None
            st["is_self"] = bool(chosen["is_self"]) if chosen else True

        height = intents.extract_height_cm(text)
        if height is None:
            question = (say(lang, "judogi.askHeightSelf") if st["is_self"]
                        else say(lang, "judogi.askHeight", name=st["athlete_name"]))
            return Reply(question, intent="judogi", state={**st, "step": "height", "question": question})
        return await self.judogi_offer(st, height)

    async def judogi_offer(self, st: dict, height: int) -> Reply:
        lang = self.lang
        data = await self.tool("find_judogi", {"height_cm": height})
        number = say(lang, "judogi.number", n=data["size_number"]) if data["size_number"] else ""
        lines = [say(lang, "judogi.size", height=height, size=data["size_cm"], number=number)]
        if data.get("shop_closed"):
            lines.append(say(lang, "judogi.shopClosed"))
            return Reply("\n\n".join(lines), quick_replies=self.suggestions(), intent="judogi")

        if not data["found"]:
            lines.append(say(lang, "judogi.notFound", size=data["size_cm"]) if data.get("judogi_products")
                         else say(lang, "judogi.none"))
            if self.ctx.scope is None:
                return Reply("\n\n".join(lines), actions=[nav(lang, "shop", "act.shop")], intent="judogi")
            for_part = say(lang, "judogi.for", name=st["athlete_name"]) if st.get("athlete_name") and not st.get("is_self") else ""
            message = say(lang, "judogi.notifyText", size=data["size_cm"], **{"for": for_part})
            task = await self.new_task("CLUB_MESSAGE", {"text": message})
            lines.append(say(lang, "judogi.offerNotify", size=data["size_cm"]))
            return Reply("\n\n".join(lines), actions=[confirm(task.id, say(lang, "act.notify")), cancel(task.id, lang)],
                         quick_replies=[say(lang, "qr.yes"), say(lang, "qr.no")],
                         state={"pending_task": str(task.id)}, intent="judogi")

        quote = data["quote"]
        if not quote["bank_transfer_available"]:
            lines.append(say(lang, "judogi.noTransfer"))
            return Reply("\n\n".join(lines), quick_replies=self.suggestions(), intent="judogi")
        found_key = "judogi.found" if data["exact"] else "judogi.foundBigger"
        lines.append(say(lang, found_key, product=data["product_name"], label=data["variant_label"], size=data["size_cm"]))
        price_key = "judogi.priceFreeShipping" if quote["shipping_cents"] == 0 else "judogi.price"
        price = [say(lang, price_key, items=euro(quote["items_cents"], lang), vat=euro(quote["vat_cents"], lang),
                     shipping=euro(quote["shipping_cents"], lang), total=euro(quote["amount_cents"], lang))]
        if quote["bank_transfer_discount_percentage"] > 0:
            price.append(say(lang, "judogi.transfer", amount=euro(quote["bank_transfer_amount_cents"], lang),
                             pct=quote["bank_transfer_discount_percentage"]))
        lines.append(" ".join(price))
        if quote["min_order_missing_cents"] > 0:
            lines.append(say(lang, "judogi.minOrder"))
            return Reply("\n\n".join(lines), actions=[nav(lang, "shop", "act.shop")], intent="judogi")

        address = await self.tool("delivery_address")
        if not address["complete"]:
            lines.append(say(lang, "judogi.addressMissing"))
            return Reply("\n\n".join(lines), actions=[nav(lang, "settings", "act.settings")],
                         quick_replies=[say(lang, "qr.judogi")], intent="judogi")
        a = address["address"]
        lines.append(say(lang, "judogi.shipTo", name=a["recipient_name"], line1=a["address_line1"],
                         postal=a["postal_code"], city=a["city"], province=a["province"]))
        lines.append(say(lang, "judogi.confirm"))
        task = await self.new_task("SHOP_ORDER", {
            "variant_id": str(data["variant_id"]), "athlete_id": st.get("athlete_id"), "address": a,
            "product_name": data["product_name"], "variant_label": data["variant_label"],
            "height_cm": height, "size_cm": data["size_cm"], "athlete_name": st.get("athlete_name"),
            # Solo per il riepilogo: l'ordine ricalcola tutto (jav_market.create_order).
            "shown_amount_cents": quote["amount_cents"],
        })
        return Reply("\n\n".join(lines),
                     actions=[confirm(task.id, say(lang, "act.confirmOrder")), cancel(task.id, lang)],
                     quick_replies=[say(lang, "qr.yes"), say(lang, "qr.no")],
                     state={"pending_task": str(task.id)}, intent="judogi")

    # --- Certificati, gare, lezioni, inviti -------------------------------------------------------

    async def certificates(self) -> Reply:
        lang = self.lang
        data = await self.tool("family_certificates")
        if not data["athletes"]:
            return Reply(say(lang, "certs.none"), quick_replies=self.suggestions(), intent="certificates")
        lines = [say(lang, f"certs.{a['status']}", name=a["first_name"], date=texts.day(a["expires_on"], lang))
                 for a in data["athletes"]]
        if all(a["status"] == "VALID" for a in data["athletes"]):
            lines.insert(0, say(lang, "certs.allOk"))
        else:
            lines.append("")
            lines.append(say(lang, "certs.howTo"))
        return Reply("\n".join(lines), actions=[nav(lang, "club", "act.club")], quick_replies=self.suggestions(),
                     intent="certificates")

    async def competitions(self) -> Reply:
        from app.domains.club import kinds

        lang = self.lang
        # Nei corsi JAV non ci sono gare né ranking (club/kinds.py): niente
        # da proporre, si dice perché e dove si fanno.
        if self.ctx.scope is not None and not (
            await kinds.club_rules(self.ctx.db, club_id=self.ctx.scope.club_id)
        ).has_competitions:
            return Reply(say(lang, "competitions.notInCourses"), quick_replies=self.suggestions(), intent="competitions")
        data = await self.tool("open_competitions")
        if not data["competitions"]:
            return Reply(say(lang, "competitions.none"), quick_replies=self.suggestions(), intent="competitions")
        lines = [say(lang, "competitions.intro")]
        for c in data["competitions"]:
            lines.append(say(lang, "competitions.line", name=c["name"], date=texts.day(c["starts_on"], lang),
                             location=f", {c['location']}" if c["location"] else "",
                             deadline=texts.day(c["registration_deadline"], lang)))
            lines.append(say(lang, "competitions.eligible", names=", ".join(c["eligible"])) if c["eligible"]
                         else say(lang, "competitions.nobody"))
        if data["more"]:
            lines.append(say(lang, "competitions.more", n=data["more"]))
        return Reply("\n".join(lines), actions=[nav(lang, "competitions", "act.competitions")],
                     quick_replies=self.suggestions(), intent="competitions")

    async def lessons(self) -> Reply:
        lang = self.lang
        data = await self.tool("family_lessons_today")
        if not data["lessons"]:
            return Reply(say(lang, "lessons.none"), quick_replies=self.suggestions(), intent="lessons_today")
        lines = [say(lang, "lessons.intro")]
        actions = []
        for lesson in data["lessons"]:
            lines.append(say(lang, "lessons.line", name=lesson["first_name"], course=lesson["course_name"],
                             start=lesson["starts_at"], end=lesson["ends_at"],
                             status=say(lang, "lessons.present") if lesson["present"] else ""))
            if not lesson["present"] and len(actions) < 4:
                task = await self.new_task("MARK_ATTENDANCE", {
                    "athlete_id": str(lesson["athlete_id"]), "course_id": str(lesson["course_id"]),
                    "athlete_name": lesson["first_name"], "course_name": lesson["course_name"],
                })
                actions.append(confirm(task.id, say(lang, "act.mark", name=lesson["first_name"])))
        if actions:
            lines.append("")
            lines.append(say(lang, "lessons.markHint"))
        return Reply("\n".join(lines), actions=actions, quick_replies=self.suggestions(), intent="lessons_today")

    async def invite(self) -> Reply:
        from app.core.config import get_settings

        lang = self.lang
        data = await self.tool("invite_link")
        url = f"{get_settings().public_app_base_url.rstrip('/')}{data['path']}"
        text = say(lang, "invite.text", url=url, credit=euro(data["credit_per_month_cents"], lang),
                   n=data["invited_count"], earned=euro(data["earned_cents"], lang))
        return Reply(text, actions=[copy(url, say(lang, "act.invite"))], quick_replies=self.suggestions(), intent="invite")

    async def secretary(self) -> Reply:
        lang = self.lang
        data = await self.tool("club_contacts")
        lines = []
        details = [say(lang, f"secretary.{k}", v=data[k]) for k in ("email", "phone", "address") if data.get(k)]
        if details:
            lines.append(say(lang, "secretary.contacts", club=data["club_name"] or ""))
            lines.extend(details)
        else:
            lines.append(say(lang, "secretary.noContacts"))
        question = say(lang, "secretary.ask")
        lines.append("")
        lines.append(question)
        return Reply("\n".join(lines), intent="secretary", state={"flow": "secretary", "question": question})

    async def secretary_message(self, text: str) -> Reply:
        lang = self.lang
        message = text.strip()
        if len(message.split()) < 2:
            question = say(lang, "secretary.tooShort")
            return Reply(question, state={"flow": "secretary", "question": question}, intent="secretary")
        if self.ctx.scope is None:
            raise ToolDenied("denied.noClub")
        task = await self.new_task("CLUB_MESSAGE", {"text": message[:1000]})
        return Reply(say(lang, "secretary.confirm", text=message[:1000]),
                     actions=[confirm(task.id, say(lang, "act.send")), cancel(task.id, lang)],
                     quick_replies=[say(lang, "qr.yes"), say(lang, "qr.no")],
                     state={"pending_task": str(task.id)}, intent="secretary")

    # --- Segreteria e istruttori ------------------------------------------------------------------

    async def staff_unpaid(self) -> Reply:
        lang = self.lang
        data = await self.tool("staff_unpaid_month")
        month = texts.month_label(data["period"])
        if not data["rows"]:
            return Reply(say(lang, "staffUnpaid.none", month=month), quick_replies=self.suggestions(), intent="staff_unpaid")
        lines = [say(lang, "staffUnpaid.intro", month=month, n=len(data["rows"]), total=euro(data["total_cents"], lang))]
        for row in data["rows"][:15]:
            lines.append(say(lang, "staffUnpaid.line", name=row["name"], amount=euro(row["amount_cents"], lang),
                             overdue=say(lang, "staffUnpaid.overdue") if row["overdue"] else ""))
        if len(data["rows"]) > 15:
            lines.append(say(lang, "staffUnpaid.more", n=len(data["rows"]) - 15))
        return Reply("\n".join(lines), quick_replies=self.suggestions(), intent="staff_unpaid")

    async def staff_lessons(self) -> Reply:
        lang = self.lang
        data = await self.tool("staff_lessons_today")
        if not data["lessons"]:
            return Reply(say(lang, "staffLessons.none"), quick_replies=self.suggestions(), intent="lessons_today")
        lines = [say(lang, "staffLessons.intro")]
        for lesson in data["lessons"]:
            lines.append(say(lang, "staffLessons.line", start=lesson["starts_at"], end=lesson["ends_at"],
                             course=lesson["course_name"], present=lesson["present"], enrolled=lesson["enrolled"],
                             now=say(lang, "staffLessons.now") if lesson["current"] else ""))
        return Reply("\n".join(lines), quick_replies=self.suggestions(), intent="lessons_today")

    async def staff_certificates(self) -> Reply:
        lang = self.lang
        data = await self.tool("staff_certificate_issues")
        lines = [
            say(lang, f"staffCerts.{status}", n=len(data[status]), names=", ".join(data[status][:20]))
            for status in ("EXPIRED", "MISSING", "EXPIRING") if data[status]
        ]
        if not lines:
            lines = [say(lang, "staffCerts.none")]
        return Reply("\n\n".join(lines), quick_replies=self.suggestions(), intent="certificates")


# --- I compiti: si eseguono solo dopo un "sì" -----------------------------------------------------


async def execute_task(ctx: ToolContext, task_id: uuid.UUID) -> Reply:
    """Esegue un compito confermato, una volta sola.

    Il compito si "prende" con un UPDATE condizionato (`status = 'PENDING'`)
    nella stessa transazione di ciò che fa: la seconda conferma aspetta il
    lucchetto sulla riga, poi trova `DONE` e non esegue niente. Se
    l'esecuzione fallisce (prodotto esaurito, IBAN non configurato) il
    rollback riporta il compito a `PENDING`: si può riprovare."""
    from app.domains.club.service import ClubError
    from app.domains.jav_market.service import ERRORS as MARKET_ERRORS
    from app.domains.wallets.service import WalletError

    lang = ctx.lang
    db = ctx.db
    task = await db.get(JavbotTask, task_id)
    if task is None or task.user_id != ctx.user_id:
        return Reply(say(lang, "task.notFound"))
    if task.status == "DONE":
        return _already(task, lang)
    if task.status == "CANCELLED" or task.created_at < utcnow() - timedelta(minutes=TASK_TTL_MINUTES):
        if task.status == "PENDING":
            task.status = "CANCELLED"
            await db.commit()
        return Reply(say(lang, "task.expired"), quick_replies=[say(lang, "qr.judogi")] if task.kind == "SHOP_ORDER" else [])

    claimed = (
        await db.execute(
            update(JavbotTask)
            .where(JavbotTask.id == task_id, JavbotTask.status == "PENDING")
            .values(status="DONE", done_at=utcnow())
            .returning(JavbotTask.id)
        )
    ).first()
    if claimed is None:
        await db.refresh(task)
        return _already(task, lang)

    kind, payload = task.kind, dict(task.payload or {})
    try:
        if kind == "SHOP_ORDER":
            result = await REGISTRY.call("create_shop_order", ctx, payload, allow_writes=True)
            # create_order ha già fatto commit insieme alla presa del compito;
            # il riferimento all'ordine segue subito, UNIQUE.
            await db.execute(
                update(JavbotTask).where(JavbotTask.id == task_id)
                .values(result_ref=str(result["order_id"]), payload={**payload, "order_number": result["number"]})
            )
            await db.commit()
            return Reply(
                say(lang, "task.orderDone", number=result["number"], amount=euro(result["amount_due_cents"], lang)),
                actions=[open_pay(lang, "choose"), nav(lang, "orders", "act.orders")], intent="judogi",
            )
        if kind == "CLUB_MESSAGE":
            await REGISTRY.call("send_club_message", ctx, {**payload, "task_id": str(task_id)}, allow_writes=True)
            return Reply(say(lang, "task.messageDone"), intent="secretary")
        if kind == "MARK_ATTENDANCE":
            await REGISTRY.call("mark_attendance", ctx, payload, allow_writes=True)
            return Reply(say(lang, "task.attendanceDone", name=payload.get("athlete_name") or "",
                             course=payload.get("course_name") or ""), intent="mark_attendance")
        raise ToolDenied("task.notFound")
    except ToolDenied as denied:
        await db.rollback()
        reason = denied.reason
        return Reply(say(lang, reason) if reason in texts.T else reason)
    except (*MARKET_ERRORS, ClubError, WalletError) as exc:
        await db.rollback()
        return Reply(say(lang, "task.failed", reason=str(exc)), quick_replies=[say(lang, "qr.secretary")])


def _already(task: JavbotTask, lang: str) -> Reply:
    if task.kind == "SHOP_ORDER" and task.result_ref:
        return Reply(say(lang, "task.alreadyOrder", number=(task.payload or {}).get("order_number") or ""),
                     actions=[nav(lang, "orders", "act.orders")])
    return Reply(say(lang, "task.already"))


async def cancel_task(ctx: ToolContext, task_id: uuid.UUID) -> Reply:
    """Annulla una proposta ancora in attesa. Un compito già eseguito non
    si annulla da qui (un ordine si annulla dallo Shop)."""
    db = ctx.db
    result = await db.execute(
        update(JavbotTask)
        .where(JavbotTask.id == task_id, JavbotTask.user_id == ctx.user_id, JavbotTask.status == "PENDING")
        .values(status="CANCELLED", done_at=utcnow())
        .returning(JavbotTask.id)
    )
    if result.first() is None:
        task = await db.get(JavbotTask, task_id)
        if task is not None and task.user_id == ctx.user_id and task.status == "DONE":
            return _already(task, ctx.lang)
    await db.commit()
    return Reply(say(ctx.lang, "task.cancelled"))
