"""Lo script della tabella prezzi ufficiale (scripts/load_official_prices.py):
senza `--apply` non scrive niente; con `--apply` carica tutto; rilanciato
non cambia più nulla. E il bot del sito poi dice esattamente quella tabella.
"""

from datetime import date, time

from sqlalchemy import select

from app.domains.club import pricing as pricing_rules
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubCourse, ClubCourseSlot
from app.domains.club.site_models import ClubSite
from app.domains.javbot import public as public_bot
from app.domains.javbot.tools import ToolContext
from scripts import load_official_prices as script


async def test_the_official_table_loads_once_and_the_bot_tells_it(db, scope):
    club = await db.get(Club, scope.club_id)
    club.slug = "judo-clube-de-lagos"
    db.add(ClubSite(**scope.columns(), city="Lagos", gallery=[], coaches=[], published=True))
    await db.commit()

    planned = await script.load(db, club.slug, apply=False, show_prices=True)
    assert planned and await club_service.list_plans(db, scope=scope) == []

    done = await script.load(db, club.slug, apply=True, show_prices=True)
    assert done == planned
    assert await script.load(db, club.slug, apply=True, show_prices=True) == []

    plans = await club_service.list_plans(db, scope=scope, only_active=True)
    assert [(p.name, p.min_age, p.max_age, p.monthly_fee_cents, p.enrollment_fee_cents, p.due_day) for p in plans] == [
        ("Grupo 1 · Iniciação", 2, 7, 3500, 12000, 15),
        ("Grupo 2 · Formação", 8, 12, 6000, 12000, 15),
        ("Grupo 3 · Competição, Manutenção e Veteranos", 13, None, 8500, 12000, 15),
    ]
    await db.refresh(club)
    pricing = pricing_rules.get_pricing(club)
    assert pricing["tier_discount_pct"] == {"A": 25, "B": 20, "C": 15, "D": 10}
    assert (pricing["family_discount_cents"], pricing["referral_credit_cents"], pricing["parent_member_fee_cents"]) == (
        500, 500, 6000)
    slots = (await db.execute(
        select(ClubCourse.name, ClubCourseSlot.weekday, ClubCourseSlot.starts_at)
        .join(ClubCourseSlot, ClubCourseSlot.course_id == ClubCourse.id).where(ClubCourse.club_id == club.id)
    )).all()
    assert len(slots) == 9 and ("Grupo 1 · Iniciação", 0, time(18, 30)) in slots

    ctx = ToolContext(db=db, user_id=None, organization_id=None, scope=None, permissions=frozenset(), lang="pt",
                      today=date(2026, 10, 14))
    reply = await public_bot.answer(ctx, "quanto custa a mensalidade em Lagos")
    for expected in ("Grupo 1 · Iniciação (2–7 anos): 35,00 € por mês, inscrição anual 120,00 €",
                     "Paga-se até ao dia 15 de cada mês", "12,50 € por aula", "Treinos: Segunda 18:30–19:30",
                     "Escalão: A −25%, B −20%, C −15%, D −10%", "Inscrição na FPJ e seguro desportivo"):
        assert expected in reply.text, expected
