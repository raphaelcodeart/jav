"""I corsi esterni (domains/extcourses): un sistema a parte dai club.

Le promesse: l'iscrizione dal sito crea l'account del genitore e mette ogni
bambino nel gruppo della sua età; un'email che ha già un account (anche di
un club) si iscrive da dentro e l'anagrafica si riscrive, è del corso; la
mensilità nasce una volta per mese; la prova la segna pagata e il rifiuto la
riporta da pagare; un genitore non paga né vede i figli di un altro; la
scuola vede contatti e pagamenti, il treinador no; il treinador segna le
presenze (non nel futuro); i conti dividono le mensilità pagate tra il
treinador (50%) e JudoArteVida.
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.domains.extcourses import service
from app.domains.extcourses.models import ExtFee, ExtParticipant
from tests.test_club_fees import _user

TODAY = date.today()
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


async def _course(db, scope, admin):
    course = await service.save_course(db, organization_id=scope.organization_id, actor_user_id=admin.id, data={
        "name": "Torraltinha", "school_name": "Externato da Torraltinha", "school_city": "Lagos",
        "monthly_fee_cents": 2500, "billing_months": list(range(1, 13)), "due_day": 10,
        "starts_on": TODAY - timedelta(days=30), "ends_on": TODAY + timedelta(days=300), "published": True,
    })
    await service.save_group(db, course=course, data={"name": "Grupo 1", "max_age": 6, "weekday": 0,
                                                       "starts_at": time(15, 30), "ends_at": time(16)})
    await service.save_group(db, course=course, data={"name": "Grupo 2", "min_age": 7, "weekday": 0,
                                                       "starts_at": time(16), "ends_at": time(16, 30)})
    return course


def _child(name, years):
    return {"first_name": name, "last_name": "Silva", "birth_date": date(TODAY.year - years, 1, 1)}


async def test_signup_fees_proofs_and_accounts(db, scope):
    admin = await _user(db, scope, "superadmin")
    coach = await _user(db, scope, "marco")
    course = await _course(db, scope, admin)
    await service.add_staff(db, course=course, actor_user_id=admin.id, email=coach.email, role="COACH", share_pct=None)
    _row, _link = await service.add_staff(db, course=course, actor_user_id=admin.id, email="secretaria@torraltinha.pt",
                                          role="SCHOOL", share_pct=None)

    parent = await service.public_signup(db, course=course, email="mae@example.pt", password="segreta123",
                                         guardian_name="Ana Silva", guardian_phone="+351 912 000 000",
                                         children=[_child("Rita", 5), _child("Tomás", 8)], today=TODAY)
    kids = {p.first_name: p for p in (await db.execute(select(ExtParticipant))).scalars()}
    groups = {g.id: g.name for g in (await service.groups_of(db, [course.id]))[course.id]}
    assert groups[kids["Rita"].group_id] == "Grupo 1" and groups[kids["Tomás"].group_id] == "Grupo 2"
    fam = await service.family(db, user_id=parent.id, today=TODAY)
    assert fam["due_cents"] == 5000 and len(fam["children"]) == 2
    # Il lavoro mensile non fa doppioni.
    assert await service.issue_month(db, today=TODAY) == 0

    with pytest.raises(service.ExtAccountExists):
        await service.public_signup(db, course=course, email="MAE@example.pt", password="segreta123",
                                    guardian_name="Ana Silva", guardian_phone=None, children=[_child("Rui", 6)], today=TODAY)

    # Una famiglia di un club si iscrive da dentro: anagrafica nuova, del corso.
    club_parent = await _user(db, scope, "pai-clube")
    await service.enroll(db, course=course, parent=club_parent, children=[_child("Rui", 9)], guardian_name="Pai Clube",
                         guardian_phone=None, today=TODAY)
    rui = (await db.execute(select(ExtParticipant).where(ExtParticipant.first_name == "Rui"))).scalar_one()
    rui_fee = (await db.execute(select(ExtFee).where(ExtFee.participant_id == rui.id))).scalar_one()

    # Un genitore non paga le mensilità di un altro.
    with pytest.raises(service.ExtValidation):
        await service.upload_proof(db, user_id=parent.id, fee_ids=[rui_fee.id], method="BANK_TRANSFER",
                                   file=(PDF, "application/pdf", "x.pdf"), note=None)
    fee_ids = [f["id"] for f in fam["due_fees"]]
    proof = await service.upload_proof(db, user_id=parent.id, fee_ids=fee_ids, method="BANK_TRANSFER",
                                       file=(PDF, "application/pdf", "comprovativo.pdf"), note=None)
    assert proof.amount_cents == 5000
    assert (await service.family(db, user_id=parent.id, today=TODAY))["due_cents"] == 0

    # La scuola vede contatti e pagamenti; il treinador no.
    school_view = await service.roster(db, course=course, roles={"SCHOOL"}, today=TODAY)
    row = next(r for r in school_view["participants"] if r["first_name"] == "Rita")
    assert row["guardian_phone"] == "+351 912 000 000" and "fees" in row and school_view["proofs"]
    coach_view = await service.roster(db, course=course, roles={"COACH"}, today=TODAY)
    assert "fees" not in coach_view["participants"][0] and "proofs" not in coach_view

    # Il rifiuto riporta le mensilità da pagare.
    await service.reject_proof(db, course=course, proof_id=proof.id, actor_user_id=admin.id, reason="Valor errado")
    assert (await service.family(db, user_id=parent.id, today=TODAY))["due_cents"] == 5000
    await service.set_fee_paid(db, course=course, fee_id=fee_ids[0], actor_user_id=admin.id, method="CASH")

    acc = await service.accounts(db, organization_id=scope.organization_id, year=TODAY.year)
    assert acc["total"] == {"income_cents": 2500, "coach_cents": 1250, "jav_cents": 1250}
    mine = await service.accounts(db, organization_id=scope.organization_id, year=TODAY.year, coach_user_id=coach.id)
    assert mine["total"]["coach_cents"] == 1250


async def test_staff_access_and_attendance(db, scope):
    admin = await _user(db, scope, "superadmin")
    coach = await _user(db, scope, "treinador")
    stranger = await _user(db, scope, "estranho")
    course = await _course(db, scope, admin)
    await service.add_staff(db, course=course, actor_user_id=admin.id, email=coach.email, role="COACH", share_pct=None)
    parent = await service.public_signup(db, course=course, email="pai@example.pt", password="segreta123",
                                         guardian_name="Pai Costa", guardian_phone=None, children=[_child("Nur", 7)],
                                         today=TODAY)
    nur = (await db.execute(select(ExtParticipant).where(ExtParticipant.parent_user_id == parent.id))).scalar_one()
    with pytest.raises(service.ExtNotFound):
        await service.staff_course(db, user_id=stranger.id, course_id=course.id, admin=False)
    _c, roles = await service.staff_course(db, user_id=coach.id, course_id=course.id, admin=False)
    assert roles == {"COACH"}
    monday = TODAY - timedelta(days=TODAY.weekday())
    await service.mark_attendance(db, course=course, on=monday, marks={nur.id: True}, actor_user_id=coach.id, today=TODAY)
    day = await service.attendance_day(db, course=course, on=monday)
    assert [p["present"] for g in day["groups"] for p in g["participants"]] == [True]
    with pytest.raises(service.ExtValidation):
        await service.mark_attendance(db, course=course, on=TODAY + timedelta(days=7), marks={nur.id: True},
                                      actor_user_id=coach.id, today=TODAY)
    state = await service.clock(db, course=course, user_id=coach.id, action="in")
    assert state["open"] is not None
    state = await service.clock(db, course=course, user_id=coach.id, action="out")
    assert state["open"] is None and state["sessions"][0]["minutes"] == 0
    await service.post_notice(db, course=course, author_user_id=coach.id, title="Segunda sem aula", body="Feriado escolar.")
    assert (await service.family(db, user_id=parent.id, today=TODAY))["notices"][0]["title"] == "Segunda sem aula"
