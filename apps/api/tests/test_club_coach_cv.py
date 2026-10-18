"""Il curriculum del treinador (club/coach_cv.py).

Le promesse: l'archivio è del proprietario e di nessun altro; il CV unisce
ciò che scrive il treinador e ciò che il gestionale sa già (club, cintura,
certificazioni); il Curriculum Sportivo ricostruisce dallo storico la
carriera da atleta e da treinador, distinte; gli eventi aggiunti a mano
restano dichiarazioni personali (mai gare, calendario o ranking del club) e
si vedono come tali; i due PDF si generano e si salvano.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.domains.club import coach_cv
from app.domains.club.models import ClubBeltGrade, ClubCompetition, ClubCompetitionEntry, ClubEventReport
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from tests.test_club_area_extras import _client
from tests.test_club_fees import _athlete, _user

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


async def _past_competition(db, scope, admin, name, days_ago, level="REGIONAL"):
    day = date.today() - timedelta(days=days_ago)
    comp = ClubCompetition(organization_id=scope.organization_id, club_id=scope.club_id, name=name, starts_on=day,
                           ends_on=day, registration_deadline=day, level=level, location="Lagos",
                           created_by_user_id=admin.id, status="DONE")
    db.add(comp)
    await db.flush()
    return comp


async def test_archive_is_private_and_feeds_the_cv(db, scope, monkeypatch):
    coach = await _user(db, scope, "treinador")
    other = await _user(db, scope, "altro")
    doc = await coach_cv.save_document(db, user=coach, file=(PDF, "application/pdf", "grau-1.pdf"), data={
        "title": "Treinador de Judo Grau I", "category": "COACH_DIPLOMA", "issuer": "Federação Portuguesa de Judo",
        "issued_on": date(2015, 6, 1), "expires_on": date.today() + timedelta(days=30)})
    first = await coach_cv.save_document(db, user=coach, file=None, data={
        "title": "Suporte Básico de Vida", "category": "FIRST_AID", "show_in_cv": False})
    assert doc.storage_key and coach_cv.document_dict(doc, today=date.today())["status"] == "EXPIRING"
    with pytest.raises(ClubNotFoundError):
        await coach_cv.get_document(db, user=other, document_id=doc.id)
    with pytest.raises(ClubValidationError, match="scadenza"):
        await coach_cv.save_document(db, user=coach, file=None, document=first,
                                     data={"issued_on": date(2020, 1, 1), "expires_on": date(2019, 1, 1)})
    with pytest.raises(ClubValidationError, match="PDF, JPG o PNG"):
        await coach_cv.save_document(db, user=coach, file=(b"MZ...", "application/x-msdownload", "x.exe"),
                                     data={"title": "Virus", "category": "OTHER"})
    await db.rollback()
    for obj in (coach, doc, first):
        await db.refresh(obj)

    app, client = await _client(db, monkeypatch, user=coach, scope=scope, granted={"club.instruct"})
    try:
        async with client:
            saved = await client.put("/club/staff/cv", json={
                "headline": "Treinador de Judo · Grau I", "summary": "Ensino crianças e competição.",
                "experiences": [{"role": "Treinador principal", "organization": "Judo Clube de Lagos", "start": "2016-09",
                                 "current": True}],
                "languages": [{"name": "Português", "level": "Nativo"}], "specializations": ["Judo Adaptado"],
            })
            assert saved.status_code == 200, saved.text
            body = saved.json()
            assert body["data"]["experiences"][0]["role"] == "Treinador principal"
            assert [d["title"] for d in body["documents"] if d["show_in_cv"]] == ["Treinador de Judo Grau I"]
            assert (await client.put("/club/staff/cv", json={"experiences": [{"role": "X", "start": "ieri"}]})).status_code == 422
            pdf = await client.get("/club/staff/cv/pdf", params={"kind": "CV"})
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            url = await client.get(f"/club/staff/cv/documents/{doc.id}/url")
            assert url.status_code == 200 and url.json()["filename"] == "grau-1.pdf"
            export = await client.post("/club/staff/cv/exports", json={"kind": "CV", "note": "Para a FPJ"})
            assert export.status_code == 201, export.text
            assert [e["note"] for e in (await client.get("/club/staff/cv/exports")).json()] == ["Para a FPJ"]
    finally:
        app.dependency_overrides.clear()
    await coach_cv.delete_document(db, user=coach, document_id=doc.id)
    assert [d.title for d in await coach_cv.list_documents(db, user=coach)] == ["Suporte Básico de Vida"]


async def test_sport_history_from_the_records_and_declared_events(db, scope):
    admin = await _user(db, scope, "admin")
    coach = await _user(db, scope, "atleta-treinador")
    me = await _athlete(db, scope, coach, birth_date=date(1990, 1, 1), first_name="Matias", is_self=True)
    regional = await _past_competition(db, scope, admin, "Regional de Faro", 400)
    national = await _past_competition(db, scope, admin, "Nacional de Seniores", 200, level="NATIONAL")
    db.add(ClubCompetitionEntry(organization_id=scope.organization_id, club_id=scope.club_id, competition_id=regional.id,
                                athlete_id=me.id, registered_by_user_id=admin.id, placement=1, category="-81 kg"))
    db.add(ClubCompetitionEntry(organization_id=scope.organization_id, club_id=scope.club_id, competition_id=national.id,
                                athlete_id=me.id, registered_by_user_id=admin.id, placement=3))
    db.add(ClubBeltGrade(organization_id=scope.organization_id, club_id=scope.club_id, athlete_id=me.id,
                         grade="BLACK_2", awarded_on=date(2018, 5, 5)))
    coached = await _past_competition(db, scope, admin, "Torneio Infantil", 30, level="CLUB")
    db.add(ClubEventReport(organization_id=scope.organization_id, club_id=scope.club_id, competition_id=coached.id,
                           author_user_id=coach.id, title="Relatório"))
    await db.commit()
    before = (await db.execute(select(func.count()).select_from(ClubCompetition))).scalar_one()

    await coach_cv.save_event(db, user=coach, data={
        "title": "Campeonato Europeu de Juniores", "event_type": "COMPETITION", "role": "ATHLETE",
        "starts_on": date(2008, 9, 1), "level": "EUROPEAN_CHAMPIONSHIP", "placement": 5, "location": "Varsóvia"})
    await coach_cv.save_event(db, user=coach, data={
        "title": "Estágio Nacional de Treinadores", "event_type": "STAGE", "role": "COACH", "starts_on": date(2012, 7, 1)})
    with pytest.raises(ClubValidationError, match="futuro"):
        await coach_cv.save_event(db, user=coach, data={
            "title": "Amanhã", "event_type": "OTHER", "role": "OTHER", "starts_on": date.today() + timedelta(days=3)})

    history = await coach_cv.sport_history(db, user=coach)
    assert history["belt"]["label"] == "2.º Dan" and history["belt"]["dan"] == 2
    athlete = history["athlete"]
    assert athlete["medals"] == {"GOLD": 1, "SILVER": 0, "BRONZE": 1} and athlete["competitions"] == 3
    assert [(i["title"], i["source"]) for i in athlete["items"]] == [
        ("Nacional de Seniores", "OFFICIAL"), ("Regional de Faro", "OFFICIAL"),
        ("Campeonato Europeu de Juniores", "MANUAL")]
    coach_items = history["coach"]["items"]
    assert {(i["title"], i["role"], i["source"]) for i in coach_items} == {
        ("Torneio Infantil", "COACH", "OFFICIAL"), ("Estágio Nacional de Treinadores", "COACH", "MANUAL")}
    assert [g["label"] for g in history["grades"]] == ["2.º Dan"]
    # Le dichiarazioni non diventano gare del club.
    assert (await db.execute(select(func.count()).select_from(ClubCompetition))).scalar_one() == before

    content = coach_cv.render_pdf(kind="SPORT", payload=history, photo=None, generated_on=date.today())
    assert content.startswith(b"%PDF") and len(content) > 1500
    row = await coach_cv.save_export(db, user=coach, kind="SPORT", note=None)
    assert row.filename.startswith("curriculum-desportivo-") and row.size_bytes > 0
