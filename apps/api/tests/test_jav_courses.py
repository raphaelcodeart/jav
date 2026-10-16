"""I corsi JAV nelle scuole (club/kinds.py, club/jav_courses.py,
docs/club-portal.md "Cursos JAV").

Le promesse: nell'unità dei corsi niente cinture, gare e ranking, si paga
solo la mensilità e la piattaforma non prende commissione; ogni mensilità va
al corso dell'atleta (con il treinador e la percentuale di quel momento) e
non cambia più; il treinador prende la sua parte di ciò che è entrato dal
suo corso, JAV il resto; una famiglia passa a un club solo senza debiti, e
dopo il passaggio i due mondi non si toccano; e sul sito pubblico ci sono i
corsi pubblicati, mai le persone che li frequentano.
"""

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.domains.club import accounting, jav_courses, kinds
from app.domains.club import clubs as clubs_service
from app.domains.club import competitions as competitions_service
from app.domains.club import courses as courses_service
from app.domains.club import service as club_service
from app.domains.club import site as site_service
from app.domains.club.models import (
    ClubAthlete,
    ClubBeltGrade,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubCourse,
    ClubCourseAthlete,
    ClubCourseSlot,
    ClubFee,
)
from app.domains.club.scope import ClubScope
from app.domains.club.site_models import ClubAthletePublicProfile, ClubSite
from app.domains.javbot import public as public_bot
from app.domains.javbot.texts import euro, say
from app.domains.javbot.tools import ToolContext
from tests.test_club_fees import _athlete, _fees, _plans, _user

TODAY = date(2026, 10, 14)
OCTOBER = accounting.Period(key="2026-10", kind="month", start=date(2026, 10, 1), end=date(2026, 11, 1))


async def _unit(db, organization_id) -> tuple[ClubScope, object]:
    # Lo staff della piattaforma non è di nessun club.
    actor = await _user(db, ClubScope(organization_id=organization_id, club_id=None), "superadmin")
    unit = await clubs_service.ensure_courses_unit(db, organization_id=organization_id, actor_user_id=actor.id)
    return ClubScope(organization_id=organization_id, club_id=unit.id), actor


async def _course(db, scope, actor, *, name, coach=None, published=True, pct=None, venue="Escola EB1 da Luz"):
    data = {"name": name, "min_age": 4, "max_age": 10, "venue_name": venue, "venue_city": "Lagos",
            "public_description": "Judo a brincar", "published": published}
    if coach is not None:
        data["instructor_user_id"] = coach.id
    if pct is not None:
        data["coach_share_pct"] = pct
    course = await courses_service.create_course(db, scope=scope, actor_user_id=actor.id, data=data)
    await courses_service.add_slot(
        db, scope=scope, course_id=course.id, actor_user_id=actor.id, weekday=2,
        starts_at=time(17, 30), ends_at=time(18, 30), room=None,
    )
    return course


async def _pay(db, fee: ClubFee, on: datetime) -> None:
    fee.status = "PAID"
    fee.paid_at = on
    await db.commit()


async def test_the_unit_is_one_and_born_with_its_rules(db, organization_id):
    scope, actor = await _unit(db, organization_id)
    again = await clubs_service.ensure_courses_unit(db, organization_id=organization_id, actor_user_id=actor.id)
    assert again.id == scope.club_id  # una sola per organizzazione
    plans = await club_service.list_plans(db, scope=scope)
    assert [(p.monthly_fee_cents, p.enrollment_fee_cents) for p in plans] == [(2500, 0)]
    pricing = await club_service.club_pricing(db, club_id=scope.club_id)
    assert pricing["family_discount_cents"] == 0 and pricing["tier_discount_pct"]["A"] == 0
    assert pricing["parent_member_fee_cents"] == 0
    # Gli sconti si possono attivare; la quota socio no: è una regola del tipo.
    await clubs_service.update_club_pricing(db, scope=scope, actor_user_id=actor.id, changes={
        "family_discount_cents": 300, "parent_member_fee_cents": 6000,
    })
    pricing = await club_service.club_pricing(db, club_id=scope.club_id)
    assert pricing["family_discount_cents"] == 300 and pricing["parent_member_fee_cents"] == 0
    with pytest.raises(club_service.ClubValidationError):
        await club_service.update_plan(db, scope=scope, plan_id=plans[0].id, actor_user_id=actor.id,
                                       changes={"enrollment_fee_cents": 1000})


async def test_no_belts_no_competitions_no_ranking(db, organization_id):
    scope, actor = await _unit(db, organization_id)
    coach = await _user(db, scope, "treinador")
    course = await _course(db, scope, actor, name="Judo EB1", coach=coach)
    parent = await _user(db, scope)
    child = await _athlete(db, scope, parent, birth_date=date(2019, 5, 5), course_id=course.id, today=TODAY)

    belts = (await db.execute(select(ClubBeltGrade).where(ClubBeltGrade.athlete_id == child.id))).scalars().all()
    assert belts == []  # nessuna cintura di partenza
    with pytest.raises(club_service.ClubValidationError, match="cinture"):
        await club_service.award_belt(db, athlete=child, grade="YELLOW", awarded_on=TODAY, actor_user_id=coach.id)
    with pytest.raises(club_service.ClubValidationError, match="cinture"):
        await _athlete(db, scope, parent, birth_date=date(2018, 5, 5), belt="YELLOW", first_name="Ana", sex="F")
    with pytest.raises(club_service.ClubValidationError, match="gare"):
        await competitions_service.create_competition(db, scope=scope, actor_user_id=actor.id, data={
            "name": "Torneio", "starts_on": date(2026, 11, 7), "registration_deadline": date(2026, 11, 1),
        })
    # Anche con una gara messa a mano nel database, il ranking resta vuoto.
    comp = ClubCompetition(**scope.columns(), name="Torneio", starts_on=date(2026, 10, 1), ends_on=date(2026, 10, 1),
                           registration_deadline=date(2026, 10, 1), level="CLUB", fee_cents=0, status="DONE",
                           requires_agonistic_certificate=False)
    db.add(comp)
    await db.flush()
    db.add(ClubCompetitionEntry(**scope.columns(), competition_id=comp.id, athlete_id=child.id,
                                registered_by_user_id=actor.id, placement=1))
    await db.commit()
    assert await competitions_service.ranking(db, scope=scope, season=2026) == []

    # Iscrizione 0 e quota socio 0: solo la mensilità, attribuita al corso.
    fees = await _fees(db, child.id)
    assert [(f.kind, f.amount_cents) for f in fees] == [("MONTHLY", 2500)]
    membership = (await db.execute(select(ClubFee).where(ClubFee.guardian_user_id == parent.id))).scalars().all()
    assert membership == []


async def test_the_fee_goes_to_the_course_and_stays_there(db, organization_id):
    scope, actor = await _unit(db, organization_id)
    coach_a = await _user(db, scope, "treinador-a")
    coach_b = await _user(db, scope, "treinador-b")
    luz = await _course(db, scope, actor, name="Judo Luz", coach=coach_a)
    mar = await _course(db, scope, actor, name="Judo Mar", coach=coach_b, pct=Decimal(40), venue="Escola do Mar")
    assert luz.coach_share_pct == Decimal(50)  # il default dei corsi JAV
    parent = await _user(db, scope)
    child = await _athlete(db, scope, parent, birth_date=date(2018, 3, 3), course_id=luz.id, today=TODAY)
    october = (await _fees(db, child.id, period="2026-10"))[0]
    assert (october.course_id, october.coach_user_id, october.coach_share_pct) == (luz.id, coach_a.id, Decimal(50))

    # Cambia corso e il corso cambia percentuale: ottobre non si muove,
    # novembre va al corso nuovo.
    await courses_service.unenrol(db, course=luz, athlete=child, actor_user_id=actor.id)
    await courses_service.enrol(db, course=mar, athlete=child, actor_user_id=actor.id)
    await courses_service.update_course(db, scope=scope, course_id=luz.id, actor_user_id=actor.id,
                                        changes={"coach_share_pct": Decimal(70)})
    await club_service.generate_monthly_fees(db, scope=scope, period="2026-11")
    await db.refresh(october)
    assert (october.course_id, october.coach_share_pct) == (luz.id, Decimal(50))
    november = (await _fees(db, child.id, period="2026-11"))[0]
    assert (november.course_id, november.coach_user_id, november.coach_share_pct) == (mar.id, coach_b.id, Decimal(40))

    # Chi va a due corsi paga una mensilità sola, al primo corso a cui si è iscritto.
    twin = await _athlete(db, scope, parent, birth_date=date(2018, 3, 3), first_name="Rui", course_id=mar.id, today=TODAY)
    await courses_service.enrol(db, course=luz, athlete=twin, actor_user_id=actor.id)
    await club_service.generate_monthly_fees(db, scope=scope, period="2026-12")
    december = await _fees(db, twin.id, period="2026-12")
    assert len(december) == 1 and december[0].course_id == mar.id

    # Un atleta aggiunto senza corso: la quota è senza corso finché non si
    # iscrive, poi va al suo primo corso (solo se ancora da pagare).
    loose = await _athlete(db, scope, parent, birth_date=date(2017, 1, 1), first_name="Eva", sex="F", today=TODAY)
    orphan = (await _fees(db, loose.id, period="2026-10"))[0]
    assert orphan.course_id is None
    assert [f.id for f in await club_service.list_fees(db, scope=scope, course="none")] == [orphan.id]
    await courses_service.enrol(db, course=luz, athlete=loose, actor_user_id=actor.id)
    await db.refresh(orphan)
    assert (orphan.course_id, orphan.coach_share_pct) == (luz.id, Decimal(70))


async def test_coach_takes_his_share_jav_keeps_the_rest_and_no_platform_fee(db, organization_id):
    scope, actor = await _unit(db, organization_id)
    coach = await _user(db, scope, "treinador")
    course = await _course(db, scope, actor, name="Judo Luz", coach=coach)
    parent = await _user(db, scope)
    kids = [
        await _athlete(db, scope, parent, birth_date=date(2018, 1, 1), first_name=n, course_id=course.id, today=TODAY)
        for n in ("Ana", "Rui", "Eva")
    ]
    october = [(await _fees(db, k.id, period="2026-10"))[0] for k in kids]
    await _pay(db, october[0], datetime(2026, 10, 12, tzinfo=UTC))
    await _pay(db, october[1], datetime(2026, 10, 13, tzinfo=UTC))

    summary = await accounting.club_summary(db, scope=scope, period=OCTOBER, today=TODAY)
    t = summary["totals"]
    assert t["income_cents"] == 5000
    assert t["coach_share_cents"] == 2500 and t["kept_cents"] == 2500
    assert t["platform_fee_cents"] == 0 and summary["platform_fee_pct"] == 0
    assert t["result_cents"] == 2500  # nessuna spesa: è la parte di JAV
    assert summary["forecast"]["result_cents"] == 2500 + 1250  # più la metà della quota ancora da pagare

    with pytest.raises(club_service.ClubValidationError):
        await accounting.set_platform_fee(db, organization_id=organization_id, club_id=scope.club_id,
                                          pct=Decimal(10), actor_user_id=actor.id, today=TODAY)

    report = await jav_courses.courses_report(db, scope=scope, period=OCTOBER, today=TODAY)
    [row] = report["courses"]
    assert (row["income_cents"], row["coach_share_cents"], row["jav_share_cents"]) == (5000, 2500, 2500)
    assert (row["athletes"], row["pending_cents"], row["debt_cents"]) == (3, 2500, 2500)

    earnings = await jav_courses.coach_earnings(db, scope=scope, user_id=coach.id, year=2026)
    by_month = {r["month"]: r for r in earnings["rows"]}
    assert by_month["2026-10"]["earned_cents"] == 2500 and by_month["2026-10"]["pending_earning_cents"] == 1250
    other = await _user(db, scope, "altro")
    assert (await jav_courses.coach_earnings(db, scope=scope, user_id=other.id, year=2026))["rows"] == []

    # La piattaforma: i corsi fuori dai club, con la loro riga nel contatore.
    platform = await accounting.platform_summary(db, organization_id=organization_id, year=2026, today=TODAY)
    assert all(c["id"] != scope.club_id for c in platform["clubs"])
    assert platform["courses_unit"]["id"] == scope.club_id
    assert platform["earnings"]["courses_month_cents"] == 2500
    assert platform["earnings"]["month_cents"] == 0


async def test_moving_a_family_to_a_club(db, organization_id):
    unit, actor = await _unit(db, organization_id)
    club = await clubs_service.create_club(db, organization_id=organization_id, actor_user_id=actor.id,
                                           name="Judo Clube de Lagos", slug="lagos-move")
    club_scope = ClubScope(organization_id=organization_id, club_id=club[0].id)
    await _plans(db, club_scope, actor)
    coach = await _user(db, unit, "treinador")
    course = await _course(db, unit, actor, name="Judo Luz", coach=coach)
    parent = await _user(db, unit)
    child = await _athlete(db, unit, parent, birth_date=date(2018, 3, 3), course_id=course.id, today=TODAY)
    october = (await _fees(db, child.id, period="2026-10"))[0]

    with pytest.raises(club_service.ClubValidationError, match="da pagare"):
        await jav_courses.move_family_to_club(db, scope=unit, guardian_user_id=parent.id,
                                              target_club_id=club_scope.club_id, actor_user_id=actor.id, today=TODAY)
    # L'unità non è un club in cui portare qualcuno, e un altro club non è dei corsi.
    with pytest.raises(club_service.ClubNotFoundError):
        await jav_courses.move_family_to_club(db, scope=unit, guardian_user_id=parent.id,
                                              target_club_id=unit.club_id, actor_user_id=actor.id, today=TODAY)
    with pytest.raises(club_service.ClubValidationError):
        await jav_courses.move_family_to_club(db, scope=club_scope, guardian_user_id=parent.id,
                                              target_club_id=club_scope.club_id, actor_user_id=actor.id, today=TODAY)

    await _pay(db, october, datetime(2026, 10, 10, tzinfo=UTC))
    result = await jav_courses.move_family_to_club(db, scope=unit, guardian_user_id=parent.id,
                                                   target_club_id=club_scope.club_id, actor_user_id=actor.id, today=TODAY)
    assert result["athletes"] == 1
    await db.refresh(child)
    await db.refresh(parent)
    assert child.club_id == parent.club_id == club_scope.club_id
    assert child.plan_id is not None and child.joined_on == TODAY
    assert (await club_service.current_belts(db, athlete_ids=[child.id]))[child.id] == "WHITE"
    enrolments = (await db.execute(select(ClubCourseAthlete).where(ClubCourseAthlete.athlete_id == child.id))).all()
    assert enrolments == []

    # La storia resta ai corsi; nel club, iscrizione a pro rata e mensilità dal mese prossimo.
    await db.refresh(october)
    assert october.club_id == unit.club_id and october.course_id == course.id
    in_club = await club_service.list_fees(db, scope=club_scope, athlete_ids=[child.id])
    assert {(f.kind, f.period) for f in in_club} >= {("ENROLLMENT", "2026"), ("MONTHLY", "2026-11")}
    assert all(f.course_id is None for f in in_club)
    assert ("MONTHLY", "2026-10") not in {(f.kind, f.period) for f in in_club}
    enrollment = next(f for f in in_club if f.kind == "ENROLLMENT")
    assert enrollment.amount_cents == round(2500 * 3 / 12)  # ottobre–dicembre

    # Isolamento: l'unità non vede più l'atleta, il club non vede le quote dei corsi.
    with pytest.raises(club_service.ClubNotFoundError):
        await club_service.get_athlete(db, scope=unit, athlete_id=child.id)
    assert await club_service.list_fees(db, scope=club_scope, course=course.id) == []
    report = await jav_courses.courses_report(db, scope=unit, period=OCTOBER, today=TODAY)
    assert report["courses"][0]["income_cents"] == 2500 and report["courses"][0]["athletes"] == 0
    # Ora è un atleta del club: le cinture ci sono.
    await club_service.award_belt(db, athlete=child, grade="YELLOW", awarded_on=TODAY, actor_user_id=actor.id)


async def _public_world(db, organization_id):
    """Un'unità dei corsi con un corso pubblicato e uno no, un atleta con
    consenso e pubblicazione forzati a mano (per provare che il sito non li
    guarda nemmeno) e un risultato in gara; accanto, un club ufficiale."""
    unit, actor = await _unit(db, organization_id)
    db.add(ClubSite(**unit.columns(), published=True, gallery=[], coaches=[], tagline="Judo nas escolas",
                    contact_email="cursos@jav.example"))
    coach = await _user(db, unit, "treinador")
    shown = await _course(db, unit, actor, name="Judo Luz", coach=coach)
    shown.public_coach_name = "Mestre Rui"
    hidden = await _course(db, unit, actor, name="Judo Segreto", published=False, venue="Escola Escondida")
    parent = await _user(db, unit)
    kid = await _athlete(db, unit, parent, birth_date=date(2018, 3, 3), first_name="Tiago", last_name="Escolar",
                         course_id=shown.id, today=TODAY)
    # La scheda d'ufficio c'è già: la famiglia aggiunge la foto.
    profile = (await db.execute(select(ClubAthletePublicProfile).where(ClubAthletePublicProfile.athlete_id == kid.id))).scalar_one()
    profile.show_photo = True
    comp = ClubCompetition(**unit.columns(), name="Torneio Interno", starts_on=date(2026, 10, 1),
                           ends_on=date(2026, 10, 1), registration_deadline=date(2026, 10, 1), level="CLUB",
                           fee_cents=0, status="DONE", requires_agonistic_certificate=False)
    db.add(comp)
    await db.flush()
    db.add(ClubCompetitionEntry(**unit.columns(), competition_id=comp.id, athlete_id=kid.id,
                                registered_by_user_id=actor.id, placement=1))
    await db.commit()
    return unit, actor, shown, hidden, kid, comp, parent


async def test_the_public_site_shows_courses_never_people(db, organization_id):
    unit, actor, shown, hidden, kid, comp, parent = await _public_world(db, organization_id)
    unit_club = await clubs_service.get_club(db, organization_id=organization_id, club_id=unit.club_id)

    data = await site_service.public_courses(db)
    assert [c["id"] for c in data["courses"]] == [shown.id]
    card = data["courses"][0]
    assert card["signup_path"] == f"/c/{unit_club.slug}?curso={shown.id}"
    assert card["coach_name"] == "Mestre Rui" and card["slots"][0]["starts_at"] == "17:30"
    assert data["unit"]["tagline"] == "Judo nas escolas"

    # L'unità non è un club del sito, e i suoi atleti non esistono, nemmeno
    # con consenso e pubblicazione.
    home = await site_service.portal_home(db, today=TODAY)
    assert home["clubs"] == [] and home["top_ranking"] == [] and home["latest_medals"] == []
    assert home["upcoming_events"] == []
    assert await site_service.list_public_clubs(db) == []
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.club_page(db, slug=unit_club.slug, today=TODAY)
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.judoka_profile(db, athlete_id=kid.id, today=TODAY)
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.event_detail(db, event_id=comp.id, today=TODAY)
    assert (await site_service.public_ranking(db, season=2026, today=TODAY))["rows"] == []
    assert await site_service.list_events(db, today=TODAY) == []
    with pytest.raises(club_service.ClubValidationError):
        await site_service.set_athlete_published(db, scope=unit, athlete_id=kid.id, published=True, actor_user_id=actor.id)

    # Le API vere e il bot: nessun nome, nessun dato di persona.
    from app.core.db import get_db
    from app.main import app

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    bodies = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
            for path in ("/public-site/courses", "/public-site/home", "/public-site/clubs", "/public-site/ranking",
                         "/public-site/events", "/public-site/events?when=past"):
                res = await client.get(path)
                assert res.status_code == 200, (path, res.text)
                bodies.append(json.dumps(res.json()))
            for path in (f"/public-site/judoka/{kid.id}", f"/public-site/events/{comp.id}",
                         f"/public-site/clubs/{unit_club.slug}"):
                assert (await client.get(path)).status_code == 404, path
    finally:
        app.dependency_overrides.clear()
    ctx = ToolContext(db=db, user_id=None, organization_id=None, scope=None, permissions=frozenset(), lang="pt",
                      today=TODAY)
    for question in ("Há cursos nas escolas?", "ranking", "Tiago", "Próximos eventos", "Que clubes há?"):
        reply = await public_bot.answer(ctx, question)
        bodies.append(json.dumps({"t": reply.text, "a": reply.actions, "q": reply.quick_replies}, default=str))
    courses_reply = await public_bot.answer(ctx, "Há cursos nas escolas?")
    assert "Judo Luz" in courses_reply.text and "Judo Segreto" not in courses_reply.text
    # Il prezzo dei corsi è una regola di JAV: si dice sempre, dal piano dell'unità.
    assert say("pt", "pub.coursesFee", amount=euro(2500, "pt")) in courses_reply.text
    everything = "\n".join(bodies)
    for secret in ("Tiago", "Escolar", "2018-03-03", parent.email, str(kid.id), "Judo Segreto", "Escondida",
                   "Torneio Interno", str(parent.id)):
        assert secret not in everything, secret


async def test_after_the_move_the_public_rules_are_the_normal_ones(db, organization_id):
    unit, actor, _shown, _hidden, kid, _comp, parent = await _public_world(db, organization_id)
    for fee in await club_service.list_fees(db, scope=unit, athlete_ids=[kid.id]):
        await _pay(db, fee, datetime(2026, 10, 10, tzinfo=UTC))
    club, _ = await clubs_service.create_club(db, organization_id=organization_id, actor_user_id=actor.id,
                                              name="Judo Clube de Lagos", slug="lagos-public")
    club_scope = ClubScope(organization_id=organization_id, club_id=club.id)
    db.add(ClubSite(**club_scope.columns(), published=True, gallery=[], coaches=[]))
    await db.commit()
    await jav_courses.move_family_to_club(db, scope=unit, guardian_user_id=parent.id, target_club_id=club.id,
                                          actor_user_id=actor.id, today=TODAY)
    # Il consenso resta della famiglia, ma la pubblicazione la decide il club.
    with pytest.raises(club_service.ClubNotFoundError):
        await site_service.judoka_profile(db, athlete_id=kid.id, today=TODAY)
    await site_service.set_athlete_published(db, scope=club_scope, athlete_id=kid.id, published=True,
                                             actor_user_id=actor.id)
    profile = await site_service.judoka_profile(db, athlete_id=kid.id, today=TODAY)
    assert profile["display_name"] == "Tiago E."
    assert profile["club"]["slug"] == "lagos-public"


def test_kind_rules_are_in_one_place():
    courses = kinds.rules_for(kinds.JAV_COURSES)
    club = kinds.rules_for(kinds.CLUB)
    assert not courses.has_belts and not courses.has_competitions and not courses.in_rankings
    assert not courses.public_as_club and courses.default_platform_fee_pct == 0 and courses.coach_paid_by_share
    assert club.has_belts and club.in_rankings and club.default_platform_fee_pct == 10
    assert kinds.rules_for(None) == club


async def test_admin_lists_filter_by_course(db, organization_id):
    scope, actor = await _unit(db, organization_id)
    luz = await _course(db, scope, actor, name="Judo Luz")
    mar = await _course(db, scope, actor, name="Judo Mar")
    parent = await _user(db, scope)
    a = await _athlete(db, scope, parent, birth_date=date(2018, 1, 1), course_id=luz.id, today=TODAY)
    b = await _athlete(db, scope, parent, birth_date=date(2018, 1, 1), first_name="Rui", course_id=mar.id, today=TODAY)
    assert [x.id for x in await club_service.search_athletes(db, scope=scope, course_id=luz.id)] == [a.id]
    assert [f.athlete_id for f in await club_service.list_fees(db, scope=scope, course=mar.id)] == [b.id]
    # Un corso di un club ufficiale non ha percentuale né pagina pubblica.
    other = (await clubs_service.create_club(db, organization_id=organization_id, actor_user_id=actor.id,
                                             name="Clube Oficial", slug="oficial-x"))[0]
    official = await courses_service.create_course(
        db, scope=ClubScope(organization_id=organization_id, club_id=other.id), actor_user_id=actor.id,
        data={"name": "Infantis", "coach_share_pct": Decimal(50), "published": True, "venue_name": "Escola"},
    )
    assert official.coach_share_pct is None and official.published is False and official.venue_name is None
    assert (await db.get(ClubCourse, official.id)).club_id == other.id
    assert (await db.execute(select(ClubAthlete).where(ClubAthlete.club_id == other.id))).all() == []
    assert (await db.execute(select(ClubCourseSlot).where(ClubCourseSlot.course_id == official.id))).all() == []
