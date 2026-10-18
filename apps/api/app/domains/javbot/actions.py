"""Le azioni di JAVBOT come un segretario: capite dal codice, confermate
dall'utente, eseguite nel database.

- **Iscrivere un atleta a una gara** (famiglia): "iscrivimi alla gara di
  Lisbona del 28 ottobre", "inscreve o Marco no torneio de Faro". Si
  riconoscono il verbo, la gara (data, città, parole del nome, tra quelle
  con le iscrizioni aperte) e l'atleta (nome, "me", o l'unico della
  famiglia); si controlla che possa iscriversi (competitions.eligibility);
  nasce un compito COMPETITION_ENTRY da confermare. Eseguito, la quota
  della gara c'è già e la risposta porta al pagamento.
- **Segnare le presenze** (treinador e segreteria): "segna presenti Marco,
  Ariel e Nur il 17 ottobre". Si riconoscono la data (anche "ieri",
  "ontem") e i nomi tra gli atleti che chi scrive vede, con la loro turma
  di quel giorno; nasce un compito STAFF_ATTENDANCE con l'elenco da
  confermare.

**Il modello solo quando serve**: se il verbo c'è ma il codice non capisce
quale gara o quali nomi, una chiamata piccola (`llm.chat_json`, poche
centinaia di token) sceglie tra le opzioni vere, già trovate nel
database; poi decide di nuovo il codice. Il modello non esegue mai niente:
esegue la conferma (planner.execute_task).
"""

import re
import uuid
from datetime import date, timedelta

from app.domains.javbot import llm
from app.domains.javbot.intents import normalize
from app.domains.javbot.planner import Reply, cancel, confirm
from app.domains.javbot.texts import day, euro, say
from app.domains.javbot.tools import FAMILY, INSTRUCT, ToolContext, ToolDenied

SIGNUP_VERBS = re.compile(
    r"\b(iscriv\w*|inscrev\w*|inscreva\w*|registra\w*|regista\w*|sign\s+(me\s+|him\s+|her\s+)?up|enrol\w*|enroll\w*)\b"
)
ATTENDANCE_VERBS = re.compile(r"\b(segn\w*|marc\w*|regist\w*|mark\w*|metti|poni|put)\b")
ATTENDANCE_WORDS = re.compile(r"\b(presen\w*|attendance|assiduidade)\b")
MONTHS = {
    # it / pt / en, normalizzati
    "gennaio": 1, "janeiro": 1, "january": 1, "febbraio": 2, "fevereiro": 2, "february": 2, "marzo": 3,
    "marco": 3, "march": 3, "aprile": 4, "abril": 4, "april": 4, "maggio": 5, "maio": 5, "may": 5,
    "giugno": 6, "junho": 6, "june": 6, "luglio": 7, "julho": 7, "july": 7, "agosto": 8, "august": 8,
    "settembre": 9, "setembro": 9, "september": 9, "ottobre": 10, "outubro": 10, "october": 10,
    "novembre": 11, "novembro": 11, "november": 11, "dicembre": 12, "dezembro": 12, "december": 12,
}
SELF_WORDS = {"me", "mim", "io", "eu", "myself", "mi", "iscrivimi", "inscreve-me", "inscrevame"}
#: Parole che non sono nomi di persona, anche se maiuscole a inizio frase.
NOT_NAMES = {"segna", "marca", "presenze", "presencas", "presente", "presentes", "di", "de", "e", "and", "il", "o",
             "a", "the", "of", "oggi", "hoje", "ieri", "ontem", "today", "yesterday", "per", "para", "alla", "na", "no"}


# --- Le date ---------------------------------------------------------------------------------------


def parse_date(text: str, today: date) -> date | None:
    """Una data scritta come la scrive una persona: "17 ottobre 2026",
    "17/10", "ieri", "ontem". None se non c'è."""
    norm = normalize(text)
    if re.search(r"\b(oggi|hoje|today)\b", norm):
        return today
    if re.search(r"\b(ieri|ontem|yesterday)\b", norm):
        return today - timedelta(days=1)
    if re.search(r"\b(l altro ieri|anteontem)\b", norm):
        return today - timedelta(days=2)
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", norm)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = (int(y) + 2000 if len(y) == 2 else int(y)) if y else today.year
        try:
            return date(year, mo, d)
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})\s*(?:de\s+|of\s+)?([a-z]+)(?:\s+(?:de\s+)?(\d{4}))?\b", norm)
    if m and m.group(2) in MONTHS:
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            return date(year, MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", normalize(text)) if len(w) >= 3}


# --- Iscrizione a una gara ------------------------------------------------------------------------


def wants_signup(text: str) -> bool:
    return bool(SIGNUP_VERBS.search(normalize(text)))


async def _signup_options(ctx: ToolContext):
    from app.domains.club import competitions as competitions_service
    from app.domains.club import service as club_service

    scope = ctx.require(FAMILY)
    comps = [c for c in await competitions_service.list_competitions(ctx.db, scope=scope, status="OPEN",
                                                                      from_date=ctx.today)
             if c.registration_deadline >= ctx.today]
    athletes = await club_service.list_family_athletes(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
    return comps, [a for a in athletes if a.status == "ACTIVE"]


def _score_competition(comp, text: str, when: date | None) -> int:
    score = 0
    if when is not None and comp.starts_on <= when <= comp.ends_on:
        score += 5
    words = _words(text)
    for w in _words(f"{comp.name} {comp.location or ''}"):
        if len(w) >= 4 and any(x.startswith(w[:5]) for x in words):
            score += 2
    return score


def _pick_athletes(athletes, text: str) -> list:
    norm_words = set(re.findall(r"[a-z0-9]+", normalize(text)))
    named = [a for a in athletes if normalize(a.first_name) in norm_words]
    if named:
        return named
    if norm_words & SELF_WORDS or "iscrivimi" in normalize(text):
        own = [a for a in athletes if a.is_self]
        if own:
            return own
    return athletes if len(athletes) == 1 else []


async def signup(ctx: ToolContext, conversation, text: str, spend: llm.Spend, new_task) -> Reply | None:
    """L'iscrizione a una gara chiesta in chat, fino alla proposta da
    confermare. None se la frase non è un'iscrizione."""
    from app.domains.club import competitions as competitions_service

    if not wants_signup(text) or FAMILY not in ctx.permissions or ctx.scope is None:
        return None
    lang = ctx.lang
    comps, athletes = await _signup_options(ctx)
    if not comps:
        return Reply(say(lang, "act.signup.noneOpen"), intent="competition_entry")
    if not athletes:
        return Reply(say(lang, "act.signup.noAthletes"), intent="competition_entry")
    when = parse_date(text, ctx.today)
    scored = sorted(((_score_competition(c, text, when), c) for c in comps), key=lambda x: -x[0])
    best = [c for s, c in scored if s == scored[0][0] and s > 0]
    chosen = athletes_chosen = None
    if len(best) == 1:
        chosen = best[0]
    athletes_chosen = _pick_athletes(athletes, text)
    if (chosen is None or not athletes_chosen) and llm.enabled():
        # Il codice non ha capito: il modello sceglie tra le opzioni vere.
        options = "\n".join(f"{i}: {c.name} — {c.starts_on:%d/%m/%Y}, {c.location or ''}" for i, c in enumerate(comps))
        names = ", ".join(a.first_name for a in athletes)
        try:
            out = await llm.chat_json(
                ctx.db,
                "Return JSON {\"competition\": index or null, \"athletes\": [first names]} choosing ONLY from the "
                "lists given. null if the message does not say.",
                f"Competitions:\n{options}\nAthletes: {names}\nMessage: {text}", spend=spend,
            )
        except llm.LlmUnavailable:
            out = {}
        idx = out.get("competition")
        if chosen is None and isinstance(idx, int) and 0 <= idx < len(comps):
            chosen = comps[idx]
        if not athletes_chosen and isinstance(out.get("athletes"), list):
            wanted = {normalize(str(n)) for n in out["athletes"]}
            athletes_chosen = [a for a in athletes if normalize(a.first_name) in wanted]
    if chosen is None:
        return Reply(say(lang, "act.signup.which"), cards=[_comp_card(ctx, c, athletes) for c in comps[:5]],
                     intent="competition_entry")
    if not athletes_chosen:
        return Reply(say(lang, "act.signup.who", name=chosen.name),
                     quick_replies=[say(lang, "act.signup.say", athlete=a.first_name, name=chosen.name)
                                    for a in athletes[:4]], intent="competition_entry")
    athlete = athletes_chosen[0]
    ok, reason = await competitions_service.eligibility(ctx.db, competition=chosen, athlete=athlete, today=ctx.today)
    if not ok:
        return Reply(say(lang, "act.signup.notEligible", athlete=athlete.first_name, name=chosen.name,
                         reason=reason or ""), intent="competition_entry")
    task = await new_task("COMPETITION_ENTRY", {
        "competition_id": str(chosen.id), "athlete_id": str(athlete.id), "athlete_name": athlete.first_name,
        "competition_name": chosen.name, "fee_cents": chosen.fee_cents, "starts_on": chosen.starts_on.isoformat(),
    })
    extra = [say(lang, "act.signup.alsoOthers", names=", ".join(a.first_name for a in athletes_chosen[1:]))] \
        if len(athletes_chosen) > 1 else []
    fee = say(lang, "act.signup.fee", amount=euro(chosen.fee_cents, lang)) if chosen.fee_cents else say(lang, "act.signup.free")
    text_out = "\n".join([say(lang, "act.signup.confirm", athlete=athlete.first_name, name=chosen.name,
                              date=day(chosen.starts_on, lang), location=f", {chosen.location}" if chosen.location else "",
                              deadline=day(chosen.registration_deadline, lang)), fee, *extra])
    return Reply(text_out, actions=[confirm(task.id, say(lang, "act.signup.button")), cancel(task.id, lang)],
                 quick_replies=[say(lang, "qr.yes"), say(lang, "qr.no")],
                 state={"pending_task": str(task.id)}, intent="competition_entry")


def _comp_card(ctx: ToolContext, comp, athletes) -> dict:
    lang = ctx.lang
    return {
        "type": "event", "competition_id": str(comp.id), "title": comp.name, "kind": comp.kind,
        "date": comp.starts_on.isoformat(), "end_date": comp.ends_on.isoformat(), "location": comp.location,
        "deadline": comp.registration_deadline.isoformat(), "fee_cents": comp.fee_cents,
        "has_regulation": bool(comp.regulation_storage_key),
        "actions": [{"type": "say", "label": say(lang, "act.signup.short", athlete=a.first_name),
                     "value": say(lang, "act.signup.say", athlete=a.first_name, name=comp.name)} for a in athletes[:3]],
    }


async def execute_signup(ctx: ToolContext, payload: dict) -> Reply:
    """La conferma: l'iscrizione vera, con la quota (competitions.register_entry)."""
    from app.domains.club import competitions as competitions_service
    from app.domains.club import service as club_service
    from app.domains.javbot.planner import nav, open_pay

    scope = ctx.require(FAMILY)
    athletes = await club_service.list_family_athletes(ctx.db, scope=scope, guardian_user_id=ctx.user_id)
    athlete = next((a for a in athletes if str(a.id) == payload["athlete_id"]), None)
    if athlete is None:
        raise ToolDenied("task.notFound")
    comp = await competitions_service.get_competition(ctx.db, scope=scope, competition_id=uuid.UUID(payload["competition_id"]))
    await competitions_service.register_entry(ctx.db, competition=comp, athlete=athlete, actor_user_id=ctx.user_id,
                                              category=None)
    lang = ctx.lang
    if comp.fee_cents:
        return Reply(say(lang, "act.signup.doneFee", athlete=athlete.first_name, name=comp.name,
                         amount=euro(comp.fee_cents, lang), deadline=day(comp.registration_deadline, lang)),
                     actions=[open_pay(lang, "fees"), nav(lang, "competitions", "act.competitions")],
                     intent="competition_entry")
    return Reply(say(lang, "act.signup.done", athlete=athlete.first_name, name=comp.name),
                 actions=[nav(lang, "competitions", "act.competitions")], intent="competition_entry")


# --- Le presenze del treinador --------------------------------------------------------------------


def wants_staff_attendance(text: str) -> bool:
    norm = normalize(text)
    return bool(ATTENDANCE_WORDS.search(norm) and ATTENDANCE_VERBS.search(norm))


async def _visible(ctx: ToolContext) -> list[dict]:
    from app.domains.club import coach

    scope = ctx.require_staff()
    return await coach.my_athletes(ctx.db, scope=scope, user_id=ctx.user_id, manager=ctx.staff_manager, today=ctx.today)


async def _lesson_courses(ctx: ToolContext, course_ids: set, on: date) -> dict:
    """Le turme (tra quelle date) che hanno una lezione in quel giorno."""
    from sqlalchemy import select

    from app.domains.club.models import ClubCourse, ClubCourseSlot

    if not course_ids:
        return {}
    rows = (await ctx.db.execute(
        select(ClubCourse.id, ClubCourse.name).join(ClubCourseSlot, ClubCourseSlot.course_id == ClubCourse.id)
        .where(ClubCourse.id.in_(course_ids), ClubCourseSlot.weekday == on.weekday()).distinct()
    )).all()
    return dict(rows)


def _match_names(athletes: list[dict], text: str) -> tuple[list[dict], list[str], dict[str, list[dict]]]:
    """(trovati, nomi non trovati, nomi ambigui → candidati)."""
    norm = normalize(text)
    tokens = re.findall(r"[a-z]+", norm)
    found, ambiguous = [], {}
    used = set()
    by_first: dict[str, list[dict]] = {}
    for a in athletes:
        by_first.setdefault(normalize(a["first_name"]), []).append(a)
    for i, tok in enumerate(tokens):
        if tok in NOT_NAMES or tok not in by_first or tok in used:
            continue
        used.add(tok)
        cands = by_first[tok]
        if len(cands) > 1 and i + 1 < len(tokens):
            narrowed = [a for a in cands if normalize(a["last_name"]).split()[0].startswith(tokens[i + 1][:4])]
            cands = narrowed or cands
        if len(cands) == 1:
            found.append(cands[0])
        else:
            ambiguous[tok] = cands
    # I nomi scritti con la maiuscola che non sono di nessuno: si dicono.
    capitalized = {normalize(w) for w in re.findall(r"\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b", text)}
    unknown = sorted(n for n in capitalized - set(by_first) - NOT_NAMES - set(MONTHS)
                     if not (ATTENDANCE_VERBS.match(n) or ATTENDANCE_WORDS.match(n) or n == "javbot"))
    return found, unknown, ambiguous


async def staff_attendance(ctx: ToolContext, conversation, text: str, spend: llm.Spend, new_task) -> Reply | None:
    if not wants_staff_attendance(text) or INSTRUCT not in ctx.permissions or (ctx.staff_scope or ctx.scope) is None:
        return None
    lang = ctx.lang
    on = parse_date(text, ctx.today) or ctx.today
    if on > ctx.today:
        return Reply(say(lang, "act.att.future"), intent="staff_attendance")
    athletes = await _visible(ctx)
    found, unknown, ambiguous = _match_names(athletes, text)
    if not found and not ambiguous and llm.enabled():
        names = ", ".join(f"{a['first_name']} {a['last_name']}" for a in athletes[:200])
        try:
            out = await llm.chat_json(ctx.db, "Return JSON {\"names\": [full names]} choosing ONLY from the list, "
                                              "the athletes the message wants to mark present.",
                                      f"Athletes: {names}\nMessage: {text}", spend=spend)
        except llm.LlmUnavailable:
            out = {}
        wanted = {normalize(str(n)) for n in out.get("names") or []}
        found = [a for a in athletes if normalize(f"{a['first_name']} {a['last_name']}") in wanted]
    if ambiguous:
        tok, cands = next(iter(ambiguous.items()))
        return Reply(say(lang, "act.att.ambiguous", name=tok.capitalize()),
                     quick_replies=[f"{text} ({a['first_name']} {a['last_name']})" for a in cands[:4]],
                     intent="staff_attendance")
    if not found:
        return Reply(say(lang, "act.att.noNames"), intent="staff_attendance")
    courses = await _lesson_courses(ctx, {c for a in found for c in a["course_ids"]}, on)
    rows, skipped = [], []
    for a in found:
        lesson = next((c for c in a["course_ids"] if c in courses), None)
        if lesson is None:
            skipped.append(a["first_name"])
            continue
        rows.append({"athlete_id": str(a["id"]), "course_id": str(lesson), "name": f"{a['first_name']} {a['last_name']}",
                     "course_name": courses[lesson]})
    if not rows:
        return Reply(say(lang, "act.att.noLesson", names=", ".join(skipped), date=day(on, lang)), intent="staff_attendance")
    task = await new_task("STAFF_ATTENDANCE", {"date": on.isoformat(), "rows": rows,
                                               "club_id": str((ctx.staff_scope or ctx.scope).club_id)})
    lines = [say(lang, "act.att.confirm", n=len(rows), date=day(on, lang))]
    lines += [f"- **{r['name']}** · {r['course_name']}" for r in rows]
    if skipped:
        lines.append(say(lang, "act.att.skipped", names=", ".join(skipped)))
    if unknown:
        lines.append(say(lang, "act.att.unknown", names=", ".join(n.capitalize() for n in unknown)))
    return Reply("\n".join(lines), actions=[confirm(task.id, say(lang, "act.att.button")), cancel(task.id, lang)],
                 quick_replies=[say(lang, "qr.yes"), say(lang, "qr.no")],
                 state={"pending_task": str(task.id)}, intent="staff_attendance")


async def execute_staff_attendance(ctx: ToolContext, payload: dict) -> Reply:
    """La conferma: ogni presenza con le regole della rotta dello staff (il
    treinador vede l'atleta e l'atleta è iscritto alla turma)."""
    from sqlalchemy import select

    from app.domains.club import coach
    from app.domains.club import courses as courses_service
    from app.domains.club.models import ClubCourseAthlete

    scope = ctx.require_staff()
    if payload.get("club_id") and payload["club_id"] != str(scope.club_id):
        raise ToolDenied("task.notFound")
    on = date.fromisoformat(payload["date"])
    done = []
    for row in payload["rows"]:
        athlete = await coach._athlete(ctx.db, scope=scope, user_id=ctx.user_id, manager=ctx.staff_manager,
                                       athlete_id=uuid.UUID(row["athlete_id"]))
        course = await courses_service.get_course(ctx.db, scope=scope, course_id=uuid.UUID(row["course_id"]))
        enrolled = (await ctx.db.execute(select(ClubCourseAthlete.id).where(
            ClubCourseAthlete.course_id == course.id, ClubCourseAthlete.athlete_id == athlete.id))).first()
        if enrolled is None:
            continue
        await courses_service.mark_attendance(ctx.db, course=course, athlete=athlete, on=on, present=True,
                                              actor_user_id=ctx.user_id)
        done.append(athlete.first_name)
    return Reply(say(ctx.lang, "act.att.done", n=len(done), names=", ".join(done), date=day(on, ctx.lang)),
                 intent="staff_attendance")


async def try_handle(ctx: ToolContext, conversation, text: str, spend: llm.Spend, new_task) -> Reply | None:
    """La prima porta di JAVBOT: un'azione capita? (Senza modello, se si può.)"""
    for handler in (staff_attendance, signup):
        reply = await handler(ctx, conversation, text, spend, new_task)
        if reply is not None:
            return reply
    return None
