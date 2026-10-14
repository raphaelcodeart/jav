"""JAVBOT sul sito pubblico: guida chi non è ancora cliente.

Senza login, senza memoria e senza cookie: ogni domanda arriva con la sua
lingua e, se la pagina è quella di un club, con lo slug del club; la
risposta si costruisce da capo. Le risposte rapide portano con sé il
contesto ("Orari Judo Clube de Lagos"), così una conversazione regge anche
senza stato.

**Non vede i dati di nessuno.** Chiama solo gli strumenti con
`audience="public"` (tools.py), che leggono le stesse funzioni del sito
(`club/site.py`): club pubblicati, orari dai corsi, contatti della pagina,
eventi, gruppi per età. I prezzi solo se il club ha acceso "mostra i
prezzi sul sito" (`club_sites.show_prices`): allora la scheda è completa
(piani, scadenza, quote annuali, sconti), altrimenti gruppi ed età sì, i
soldi li dice il club. I corsi JAV nelle scuole dicono sempre la loro
mensilità (regola di JAV, kinds.py). Quote, pagamenti, atleti: per quelli si
entra nella propria area.
"""

from app.domains.club import site as site_service
from app.domains.club.service import ClubNotFoundError
from app.domains.javbot import intents, texts
from app.domains.javbot.intents import PUBLIC_INTENTS, normalize
from app.domains.javbot.planner import Reply, link
from app.domains.javbot.texts import euro, say
from app.domains.javbot.tools import REGISTRY, ToolContext


async def _tool(ctx: ToolContext, name: str, args: dict | None = None) -> dict:
    return await REGISTRY.call(name, ctx, args, audience="public")


def _match_club(text: str, clubs: list[dict]) -> dict | None:
    """Il club nominato nel messaggio: per slug, per nome o per città."""
    norm = normalize(text)
    for club in clubs:
        if club["slug"] in norm or normalize(club["name"]) in norm:
            return club
    for club in clubs:
        if club.get("city") and intents.mentions(text, club["city"]):
            return club
    return None


def _club_qr(lang: str, key: str, clubs: list[dict]) -> list[str]:
    return [f"{say(lang, key)} {c['name']}" for c in clubs[:6]]


def _suggestions(lang: str) -> list[str]:
    return [say(lang, k) for k in (
        "pub.qr.about", "pub.qr.clubs", "pub.qr.courses", "pub.qr.schedule", "pub.qr.signup", "pub.qr.events",
    )]


async def answer(ctx: ToolContext, text: str, *, club_slug: str | None = None) -> Reply:
    lang = ctx.lang
    intent, _score = intents.detect(text, lang=lang, catalog=PUBLIC_INTENTS)
    clubs = (await _tool(ctx, "public_clubs"))["clubs"]
    club = _match_club(text, clubs)
    if club is None and club_slug:
        club = next((c for c in clubs if c["slug"] == club_slug), None)
    if club is None and len(clubs) == 1 and intent in ("schedule", "prices", "groups", "discounts", "signup", "contacts"):
        club = clubs[0]

    if intent is None and club is not None:
        return await _club_card(ctx, club)
    if intent == "greet" or not text.strip():
        # Il messaggio vuoto è l'apertura della chat: il saluto.
        return Reply(say(lang, "pub.greet"), quick_replies=_suggestions(lang), intent="greet")
    if intent == "help":
        return Reply(say(lang, "pub.help"), quick_replies=_suggestions(lang), intent="help")
    if intent == "thanks":
        return Reply(say(lang, "thanks"), quick_replies=_suggestions(lang), intent=intent)
    if intent == "about":
        return Reply(say(lang, "pub.about"), actions=[link("/clubes", say(lang, "pub.act.clubs"))],
                     quick_replies=_suggestions(lang), intent=intent)
    if intent == "benefits":
        return Reply(say(lang, "pub.benefits"), actions=[link("/clubes", say(lang, "pub.act.clubs"))],
                     quick_replies=[say(lang, "pub.qr.clubs"), say(lang, "pub.qr.signup")], intent=intent)
    if intent == "clubs":
        return _clubs(lang, clubs)
    if intent == "events":
        return await _events(ctx)
    if intent == "courses":
        return await _courses(ctx)

    if intent in ("schedule", "prices", "groups", "discounts", "signup", "contacts"):
        if club is None:
            if not clubs:
                return Reply(say(lang, "pub.clubsNone"), quick_replies=_suggestions(lang), intent=intent)
            key = {"schedule": "pub.qr.schedule", "prices": "pub.qr.prices", "groups": "pub.qr.groups",
                   "discounts": "pub.qr.discounts", "signup": "pub.qr.signup", "contacts": "pub.qr.clubs"}[intent]
            lead = say(lang, "pub.signupGeneric") if intent == "signup" else (
                say(lang, "pub.contactsGeneric") if intent == "contacts" else say(lang, "pub.whichClub"))
            return Reply(lead, quick_replies=_club_qr(lang, key, clubs), intent=intent)
        try:
            info = await _tool(ctx, "public_club_info", {"slug": club["slug"]})
        except ClubNotFoundError:
            return _clubs(lang, clubs)
        if intent == "schedule":
            return _schedule(lang, info)
        if intent in ("prices", "groups"):
            # "Quanto custa?" e "que idades?" hanno la stessa risposta: i
            # gruppi sono la tabella dei prezzi, e viceversa.
            return _prices(lang, info, intent=intent)
        if intent == "discounts":
            return _discounts(lang, info)
        if intent == "signup":
            return Reply(say(lang, "pub.signup", club=info["name"]),
                         actions=[link(info["signup_path"], say(lang, "pub.act.signup", club=info["name"])),
                                  link(f"/clubes/{info['slug']}", say(lang, "pub.act.club", club=info["name"]))],
                         quick_replies=[f"{say(lang, 'pub.qr.schedule')} {info['name']}",
                                        f"{say(lang, 'pub.qr.prices')} {info['name']}"], intent=intent)
        return _contacts(lang, info)

    return Reply(say(lang, "pub.fallback"), quick_replies=_suggestions(lang))


def _clubs(lang: str, clubs: list[dict]) -> Reply:
    if not clubs:
        return Reply(say(lang, "pub.clubsNone"), quick_replies=_suggestions(lang), intent="clubs")
    lines = [say(lang, "pub.clubsIntro")]
    lines += [say(lang, "pub.clubLine", name=c["name"], city=f", {c['city']}" if c.get("city") else "") for c in clubs]
    return Reply("\n".join(lines),
                 actions=[link(f"/clubes/{c['slug']}", say(lang, "pub.act.club", club=c["name"])) for c in clubs[:4]],
                 quick_replies=_club_qr(lang, "pub.qr.schedule", clubs), intent="clubs")


async def _club_card(ctx: ToolContext, club: dict) -> Reply:
    lang = ctx.lang
    lines = [f"{club['name']}{', ' + club['city'] if club.get('city') else ''}"]
    if club.get("tagline"):
        lines.append(club["tagline"])
    return Reply("\n".join(lines),
                 actions=[link(f"/clubes/{club['slug']}", say(lang, "pub.act.club", club=club["name"])),
                          link(f"/c/{club['slug']}", say(lang, "pub.act.signup", club=club["name"]))],
                 quick_replies=[f"{say(lang, k)} {club['name']}" for k in ("pub.qr.schedule", "pub.qr.prices", "pub.qr.signup")],
                 intent="clubs")


def _slot_text(lang: str, slot: dict) -> str:
    return f"{slot['starts_at']}–{slot['ends_at']} {slot['course']}{texts.ages(lang, slot['min_age'], slot['max_age'])}"


def _schedule_lines(lang: str, info: dict) -> list[str]:
    return [
        say(lang, "pub.scheduleDay", day=texts.WEEKDAYS[texts.lang_of(lang)][day["weekday"]],
            slots="; ".join(_slot_text(lang, s) for s in day["slots"]))
        for day in info["schedule"]
    ]


def _schedule(lang: str, info: dict) -> Reply:
    actions = [link(f"/clubes/{info['slug']}", say(lang, "pub.act.club", club=info["name"])),
               link(info["signup_path"], say(lang, "pub.act.signup", club=info["name"]))]
    if not info["schedule"]:
        return Reply(say(lang, "pub.scheduleNone", club=info["name"]), actions=actions, intent="schedule")
    lines = [say(lang, "pub.scheduleIntro", club=info["name"]), *_schedule_lines(lang, info)]
    return Reply("\n".join(lines), actions=actions,
                 quick_replies=[f"{say(lang, 'pub.qr.prices')} {info['name']}", f"{say(lang, 'pub.qr.signup')} {info['name']}"],
                 intent="schedule")


def _plan_schedule(lang: str, plan: dict, schedule: list[dict]) -> str:
    """Gli allenamenti di un gruppo: i turni dei corsi la cui fascia d'età
    tocca quella del piano (site.plan_slots, la stessa regola della pagina
    del club); il nome del corso solo se i corsi sono più d'uno."""
    found = site_service.plan_slots(plan["min_age"], plan["max_age"], schedule)
    if not found:
        return ""
    named = len({slot["course"] for _, slot in found}) > 1
    days = texts.WEEKDAYS[texts.lang_of(lang)]
    return say(lang, "pub.groupSchedule", slots="; ".join(
        f"{days[weekday]} {slot['starts_at']}–{slot['ends_at']}" + (f" ({slot['course']})" if named else "")
        for weekday, slot in found
    ))


def _fee_lines(lang: str, info: dict) -> list[str]:
    """Quote annuali e sconti del club, solo quelli accesi: un importo a
    zero non è "gratis", è una cosa che il club non fa, e non si nomina."""
    fees = info["fees"] or {}
    lines: list[str] = []
    other: list[str] = []
    if fees.get("parent_member_fee_cents"):
        other.append(say(lang, "pub.feeParent", age=fees["minor_age"], amount=euro(fees["parent_member_fee_cents"], lang)))
    if fees.get("parent_member_fee_cents") or any(p["enrollment_fee_cents"] for p in info["plans"]):
        other.append(say(lang, "pub.feeProrata"))
        if fees.get("enrollment_includes"):
            other.append(say(lang, "pub.feeIncludes", text=fees["enrollment_includes"]))
    if other:
        lines += [say(lang, "pub.feesIntro"), *other]
    discounts = _discount_lines(lang, fees)
    if discounts:
        lines += [say(lang, "pub.discountsIntro"), *discounts]
    return lines


def _discount_lines(lang: str, fees: dict) -> list[str]:
    """Gli sconti accesi, con gli importi e con che cosa fare per averli."""
    lines: list[str] = []
    tiers = fees.get("tier_discount_pct") or {}
    if tiers:
        lines.append(say(lang, "pub.discountTier", tiers=", ".join(f"{t} −{p}%" for t, p in tiers.items())))
        if tiers.get("A"):
            lines.append(say(lang, "pub.discountAdapted", pct=tiers["A"]))
    if fees.get("family_discount_cents"):
        lines.append(say(lang, "pub.discountFamily", n=fees["family_min_athletes"],
                         amount=euro(fees["family_discount_cents"], lang)))
    if fees.get("referral_credit_cents"):
        lines.append(say(lang, "pub.discountReferral", amount=euro(fees["referral_credit_cents"], lang)))
    return lines


def _discounts(lang: str, info: dict) -> Reply:
    """"Come ho uno sconto?": gli sconti che il club fa davvero e che cosa
    fare per averli. Gli importi con "mostra i prezzi", altrimenti solo i
    nomi e i contatti del club."""
    name = info["name"]
    actions = [link(info["signup_path"], say(lang, "pub.act.signup", club=name)),
               link(f"/clubes/{info['slug']}", say(lang, "pub.act.club", club=name))]
    quick = [f"{say(lang, 'pub.qr.prices')} {name}", f"{say(lang, 'pub.qr.signup')} {name}"]
    enabled = [k for k in ("tier", "adapted", "family", "referral") if info["discounts"].get(k)]
    if not enabled:
        lines = [say(lang, "pub.discountsNone", club=name), *_contact_lines(lang, info)]
    elif info["show_prices"]:
        lines = [say(lang, "pub.discountsHow", club=name), *_discount_lines(lang, info["fees"] or {})]
    else:
        names = ", ".join(say(lang, f"pub.dname.{k}") for k in enabled)
        lines = [say(lang, "pub.discountsHidden", club=name, names=names), *_contact_lines(lang, info)]
    return Reply("\n".join(lines), actions=actions, quick_replies=quick, intent="discounts")


def _prices(lang: str, info: dict, *, intent: str = "prices") -> Reply:
    """La scheda di un club: i gruppi (piani attivi) con età, allenamenti e,
    se il club mostra i prezzi, mensilità, iscrizione, scadenza, mesi, le
    altre quote e gli sconti. Tutto da ciò che il club ha configurato
    (tools.py::public_club_info): niente si inventa, niente si calcola."""
    name = info["name"]
    actions = [link(info["signup_path"], say(lang, "pub.act.signup", club=name)),
               link(f"/clubes/{info['slug']}", say(lang, "pub.act.club", club=name))]
    quick = [f"{say(lang, 'pub.qr.schedule')} {name}", f"{say(lang, 'pub.qr.signup')} {name}"]
    if not info["plans"]:
        # Meglio dirlo che lasciar credere che il club nasconda qualcosa:
        # chi chiede trova i contatti e, se c'è, l'orario.
        lines = [say(lang, "pub.groupsNone", club=name)]
        lines += _contact_lines(lang, info) or [say(lang, "secretary.noContacts")]
        if info["schedule"]:
            lines += [say(lang, "pub.scheduleIntro", club=name), *_schedule_lines(lang, info)]
        return Reply("\n".join(lines), actions=actions, quick_replies=quick[1:], intent=intent)
    show = info["show_prices"]
    lines = [say(lang, "pub.pricesIntro" if show else "pub.groupsIntro", club=name)]
    for plan in info["plans"]:
        ages = texts.ages(lang, plan["min_age"], plan["max_age"])
        if show:
            enrollment = say(lang, "pub.priceEnrollment", amount=euro(plan["enrollment_fee_cents"], lang)) \
                if plan["enrollment_fee_cents"] else ""
            lines.append(say(lang, "pub.priceLine", name=plan["name"], ages=ages,
                             monthly=euro(plan["monthly_fee_cents"], lang), enrollment=enrollment))
            lines.append(say(lang, "pub.priceDue", day=plan["due_day"],
                             months=texts.billing_months(lang, plan["billing_months"])))
            if plan.get("description"):
                lines.append(say(lang, "pub.planNote", text=plan["description"].strip()))
        else:
            lines.append(say(lang, "pub.groupLine", name=plan["name"], ages=ages))
        training = _plan_schedule(lang, plan, info["schedule"])
        if training:
            lines.append(training)
    if show:
        lines += _fee_lines(lang, info)
    else:
        lines.append(say(lang, "pub.pricesHidden", club=name))
        lines += _contact_lines(lang, info)
    return Reply("\n".join(lines), actions=actions, quick_replies=quick, intent=intent)


def _contact_lines(lang: str, info: dict) -> list[str]:
    c = info["contacts"]
    return [say(lang, f"secretary.{k}", v=c[k]) for k in ("email", "phone", "address") if c.get(k)]


def _contacts(lang: str, info: dict) -> Reply:
    details = _contact_lines(lang, info)
    text = "\n".join([say(lang, "secretary.contacts", club=info["name"]), *details]) if details \
        else say(lang, "secretary.noContacts")
    return Reply(text, actions=[link(f"/clubes/{info['slug']}", say(lang, "pub.act.club", club=info["name"]))],
                 intent="contacts")


async def _events(ctx: ToolContext) -> Reply:
    lang = ctx.lang
    events = (await _tool(ctx, "public_events"))["events"]
    if not events:
        return Reply(say(lang, "pub.eventsNone"), quick_replies=_suggestions(lang), intent="events")
    lines = [say(lang, "pub.eventsIntro")]
    lines += [say(lang, "pub.eventLine", name=e["name"], date=texts.day(e["starts_on"], lang),
                  location=f", {e['location']}" if e["location"] else "", club=e["club"]) for e in events]
    return Reply("\n".join(lines), actions=[link("/eventos", say(lang, "pub.act.events"))],
                 quick_replies=_suggestions(lang), intent="events")


async def _courses(ctx: ToolContext) -> Reply:
    """I corsi JAV nelle scuole: dove, quando, per che età, e dove ci si
    iscrive. Solo i corsi pubblicati, mai chi li frequenta."""
    lang = ctx.lang
    data = await _tool(ctx, "public_courses")
    courses = data["courses"]
    if not courses:
        return Reply(say(lang, "pub.coursesNone"), actions=[link("/clubes", say(lang, "pub.act.clubs"))],
                     quick_replies=_suggestions(lang), intent="courses")
    lines = [say(lang, "pub.coursesIntro")]
    for c in courses:
        venue = ", ".join(x for x in (c["venue_name"], c["venue_city"]) if x) or c["name"]
        slots = "; ".join(
            f"{texts.WEEKDAYS[texts.lang_of(lang)][s['weekday']]} {s['starts_at']}–{s['ends_at']}" for s in c["slots"]
        ) or "—"
        lines.append(say(lang, "pub.courseLine", name=c["name"], venue=venue,
                         ages=texts.ages(lang, c["min_age"], c["max_age"]), slots=slots))
    lines += _courses_fee_lines(lang, data["plans"])
    actions = [link("/cursos", say(lang, "pub.act.courses"))]
    actions += [link(c["signup_path"], say(lang, "pub.act.courseSignup", course=c["name"])) for c in courses[:3]]
    return Reply("\n".join(lines), actions=actions, quick_replies=_suggestions(lang), intent="courses")


def _courses_fee_lines(lang: str, plans: list[dict]) -> list[str]:
    """La mensilità dei corsi dai piani dell'unità (di regola uno, 25 €):
    una riga se è la stessa per tutti, altrimenti una per piano. Senza
    piani non si dice nessun importo."""
    fees = {p["monthly_fee_cents"] for p in plans}
    if len(fees) == 1:
        return [say(lang, "pub.coursesFee", amount=euro(fees.pop(), lang))]
    if not fees:
        return []
    return [say(lang, "pub.coursesFees")] + [
        say(lang, "pub.priceLine", name=p["name"], ages=texts.ages(lang, p["min_age"], p["max_age"]),
            monthly=euro(p["monthly_fee_cents"], lang), enrollment="")
        for p in plans
    ]
