"""La bacheca del club, gli orari che si correggono e i segni accanto ai nomi.

Le promesse: atleti e famiglie vedono solo le notizie pubblicate del loro
club e solo i documenti che il club ha condiviso; una foto della notizia è
una delle nostre; un orario si corregge senza rifarlo; un adulto che si
allena ed è genitore, istruttore e árbitro ha tutti i suoi segni.
"""

from datetime import date, time

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.club import club_documents, news
from app.domains.club import courses as courses_service
from app.domains.club import people as people_service
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.rbac.models import Role, UserRole
from tests.test_club_fees import _athlete, _plans, _user
from tests.test_club_legacy_features import PDF, _other_club


async def _role(db, scope, user, code):
    """Come test_club_people._role, ma il ruolo si crea una volta sola."""
    role = (await db.execute(
        select(Role).where(Role.organization_id == scope.organization_id, Role.code == code)
    )).scalar_one_or_none()
    if role is None:
        role = Role(organization_id=scope.organization_id, code=code, name=code.title())
        db.add(role)
        await db.flush()
    db.add(UserRole(user_id=user.id, organization_id=scope.organization_id, role_id=role.id))
    await db.commit()


async def test_board_shows_published_news_and_only_shared_documents(db, scope):
    admin = await _user(db, scope, "admin")
    first = await news.create_post(db, scope=scope, actor_user_id=admin.id, data={
        "title": "  Estágio  de Natal ", "body": "Sábado no pavilhão.", "video_url": "https://youtu.be/abc123",
    })
    assert first["title"] == "Estágio de Natal"
    draft = await news.create_post(db, scope=scope, actor_user_id=admin.id,
                                   data={"title": "Bozza", "published": False})
    pinned = await news.create_post(db, scope=scope, actor_user_id=admin.id,
                                    data={"title": "Quotas de dezembro", "pinned": True})

    board = await news.list_posts(db, scope=scope, include_drafts=False)
    assert [p["id"] for p in board] == [pinned["id"], first["id"]]
    assert len(await news.list_posts(db, scope=scope, include_drafts=True)) == 3
    other = await _other_club(db, scope)
    assert await news.list_posts(db, scope=other, include_drafts=False) == []

    # Pubblicata dopo, la bozza va in cima alle non fissate.
    await news.update_post(db, scope=scope, post_id=draft["id"], actor_user_id=admin.id, changes={"published": True})
    assert [p["title"] for p in await news.list_posts(db, scope=scope, include_drafts=False)][:2] == [
        "Quotas de dezembro", "Bozza",
    ]

    with pytest.raises(ClubValidationError):
        await news.create_post(db, scope=scope, actor_user_id=admin.id, data={"title": "  "})
    with pytest.raises(ClubValidationError):
        await news.create_post(db, scope=scope, actor_user_id=admin.id,
                               data={"title": "X", "link_url": "javascript:alert(1)"})
    with pytest.raises(ClubValidationError):
        await news.create_post(db, scope=scope, actor_user_id=admin.id,
                               data={"title": "X", "image_url": "https://example.com/foto.jpg"})
    ours = f"{get_settings().public_app_base_url}/media/club-news/x.jpg"
    assert (await news.create_post(db, scope=scope, actor_user_id=admin.id,
                                   data={"title": "Foto", "image_url": ours}))["image_url"] == ours
    with pytest.raises(ClubNotFoundError):
        await news.delete_post(db, scope=other, post_id=first["id"], actor_user_id=admin.id)
    await news.delete_post(db, scope=scope, post_id=first["id"], actor_user_id=admin.id)

    rules = await club_documents.add_document(
        db, scope=scope, actor_user_id=admin.id, file_bytes=PDF, content_type="application/pdf", filename="r.pdf",
        data={"category": "OTHER", "title": "Regulamento interno", "shared_with_members": True},
    )
    tax = await club_documents.add_document(
        db, scope=scope, actor_user_id=admin.id, file_bytes=PDF, content_type="application/pdf", filename="at.pdf",
        data={"category": "TAX", "title": "Certidão"},
    )
    assert [d.id for d in await club_documents.list_member_documents(db, scope=scope)] == [rules.id]
    with pytest.raises(ClubNotFoundError):
        await club_documents.get_member_document(db, scope=scope, document_id=tax.id)
    with pytest.raises(ClubNotFoundError):
        await club_documents.get_member_document(db, scope=other, document_id=rules.id)
    await club_documents.update_document(db, scope=scope, document_id=tax.id, actor_user_id=admin.id,
                                         changes={"shared_with_members": True})
    assert len(await club_documents.list_member_documents(db, scope=scope)) == 2


async def test_a_slot_is_corrected_in_place(db, scope):
    admin = await _user(db, scope, "admin")
    course = await courses_service.create_course(db, scope=scope, actor_user_id=admin.id,
                                                 data={"name": "Grupo 1 · Iniciação"})
    slot = await courses_service.add_slot(db, scope=scope, course_id=course.id, actor_user_id=admin.id,
                                          weekday=1, starts_at=time(18, 0), ends_at=time(18, 30), room=None)
    fixed = await courses_service.update_slot(db, scope=scope, slot_id=slot.id, actor_user_id=admin.id,
                                              weekday=1, starts_at=time(18, 0), ends_at=time(19, 0), room="Dojo")
    assert (fixed.id, fixed.ends_at, fixed.room) == (slot.id, time(19, 0), "Dojo")
    with pytest.raises(ClubValidationError):
        await courses_service.update_slot(db, scope=scope, slot_id=slot.id, actor_user_id=admin.id,
                                          weekday=1, starts_at=time(19, 0), ends_at=time(18, 0), room=None)
    other = await _other_club(db, scope)
    with pytest.raises(ClubNotFoundError):
        await courses_service.update_slot(db, scope=other, slot_id=slot.id, actor_user_id=admin.id,
                                          weekday=1, starts_at=time(18, 0), ends_at=time(19, 0), room=None)


async def test_an_adult_athlete_carries_all_their_kinds(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    adult = await _user(db, scope, "adulto")
    await _role(db, scope, adult, "CUSTOMER")
    await _role(db, scope, adult, "INSTRUCTOR")
    me = await _athlete(db, scope, adult, birth_date=date(1985, 3, 3), first_name="Rita", is_self=True)
    await _athlete(db, scope, adult, birth_date=date(2016, 3, 3), first_name="Tiago")
    referee_parent = await _user(db, scope, "arbitro")
    await _role(db, scope, referee_parent, "CUSTOMER")
    await _athlete(db, scope, referee_parent, birth_date=date(2015, 3, 3), first_name="Ana")

    await people_service.set_referee(db, scope=scope, actor_user_id=admin.id, referee=True, athlete_id=me.id)
    await people_service.set_referee(db, scope=scope, actor_user_id=admin.id, referee=True, user_id=referee_parent.id)
    await people_service.set_referee(db, scope=scope, actor_user_id=admin.id, referee=True, user_id=referee_parent.id)

    rows = {r["name"].split()[0] if r["kind"] == "ATHLETE" else r["email"]: r
            for r in await people_service.list_people(db, scope=scope)}
    assert rows["Rita"]["kinds"] == ["ATHLETE", "PARENT", "COACH", "REFEREE"]
    assert rows["Tiago"]["kinds"] == ["ATHLETE"]
    assert rows[referee_parent.email]["kinds"] == ["PARENT", "REFEREE"]

    await people_service.set_referee(db, scope=scope, actor_user_id=admin.id, referee=False, athlete_id=me.id)
    rows = {r["name"].split()[0]: r for r in await people_service.list_people(db, scope=scope) if r["kind"] == "ATHLETE"}
    assert rows["Rita"]["kinds"] == ["ATHLETE", "PARENT", "COACH"]
    other = await _other_club(db, scope)
    with pytest.raises(ClubNotFoundError):
        await people_service.set_referee(db, scope=other, actor_user_id=admin.id, referee=True, athlete_id=me.id)


async def test_network_posts_platform_posts_likes_and_events_in_the_feed(db, scope):
    from tests.test_club_site import _competition

    admin = await _user(db, scope, "admin")
    other = await _other_club(db, scope)
    other_admin = await _user(db, other, "admin2")
    mine_only = await news.create_post(db, scope=scope, actor_user_id=admin.id, data={"title": "Só para os sócios"})
    for_all = await news.create_post(db, scope=scope, actor_user_id=admin.id, data={"title": "Para o circuito", "audience": "NETWORK"})
    platform = await news.create_post(db, scope=news.Owner(organization_id=scope.organization_id, club_id=None),
                                      actor_user_id=admin.id, data={"title": "JudoArteVida", "audience": "CLUB"})
    assert platform["audience"] == "NETWORK" and platform["club"]["name"] == "JudoArteVida"

    seen = {p["title"] for p in await news.list_posts(db, scope=other, include_drafts=False)}
    assert seen == {"Para o circuito", "JudoArteVida"}
    # Nella sua console il club vede solo i suoi post.
    assert {p["title"] for p in await news.list_owner_posts(db, owner=news.Owner.of(other))} == set()

    reader = await _user(db, other, "socio")
    assert (await news.toggle_like(db, scope=other, post_id=for_all["id"], user_id=reader.id)) == {"likes": 1, "liked": True}
    assert (await news.toggle_like(db, scope=other, post_id=for_all["id"], user_id=reader.id)) == {"likes": 0, "liked": False}
    with pytest.raises(ClubNotFoundError):
        await news.toggle_like(db, scope=other, post_id=mine_only["id"], user_id=reader.id)

    await _competition(db, other, other_admin, starts_on=date(2026, 11, 20), name="Torneio de Natal")
    feed = await news.feed(db, scope=other, user_id=reader.id, today=date(2026, 10, 16))
    kinds = {(i["type"], (i["post"] or {}).get("title") or i["event"]["name"]) for i in feed}
    assert ("EVENT", "Torneio de Natal") in kinds and ("POST", "Para o circuito") in kinds
    assert ("POST", "Só para os sócios") not in kinds
