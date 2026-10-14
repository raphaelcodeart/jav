"""I messaggi dal sito pubblico (club/contact.py, docs/club-portal.md,
"Messaggi dal sito").

Le promesse da proteggere: un messaggio a un club lo legge solo quel club,
uno a JudoArteVida solo lo staff della piattaforma; un robot che riempie il
campo trappola non lascia niente; chi scrive troppo viene fermato anche se
Redis non risponde; e senza SMTP il messaggio arriva comunque nella casella,
senza far fallire niente.
"""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.db import utcnow
from app.domains.club import contact as contact_service
from app.domains.club import site as site_service
from app.domains.club.contact_models import ContactMessage
from app.domains.club.scope import ClubScope
from app.domains.club.service import ClubNotFoundError, ClubValidationError
from app.domains.notifications.models import Notification
from app.domains.rbac.models import Role, UserRole
from tests.test_club_fees import _user
from tests.test_club_multi import _other_club

GOOD = {
    "name": "Ana Sousa", "email": "Ana.Sousa@example.demo", "phone": "+351 912 345 678",
    "message": "Olá! O meu filho tem 7 anos: podemos experimentar uma aula?", "consent": True, "locale": "pt",
}


async def _role(db, organization_id, user, code):
    role = (await db.execute(
        select(Role).where(Role.organization_id == organization_id, Role.code == code)
    )).scalars().first()
    if role is None:
        role = Role(organization_id=organization_id, code=code, name=code.title())
        db.add(role)
        await db.flush()
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()


async def _published(db, scope, **content):
    await site_service.get_site(db, scope=scope)
    site = await site_service.update_site(
        db, scope=scope, actor_user_id=None, changes={"published": True, **content},
    )
    return site


async def _slug(db, scope) -> str:
    from app.domains.club.models import Club

    return (await db.get(Club, scope.club_id)).slug


async def _count(db, **filters) -> int:
    stmt = select(func.count()).select_from(ContactMessage)
    for key, value in filters.items():
        stmt = stmt.where(getattr(ContactMessage, key) == value)
    return (await db.execute(stmt)).scalar_one()


async def _notified(db, user) -> list[Notification]:
    return list((await db.execute(
        select(Notification).where(Notification.recipient_user_id == user.id, Notification.type == "CONTACT_MESSAGE")
    )).scalars())


async def test_the_form_rules_speak_to_the_person_writing(db, scope):
    await _published(db, scope)
    slug = await _slug(db, scope)
    for broken in (
        {**GOOD, "consent": False},          # senza consenso non si può rispondere
        {**GOOD, "email": "ana@"},           # l'email è dove arriva la risposta
        {**GOOD, "name": " "},
        {**GOOD, "message": "Olá"},          # troppo corto per essere una domanda
        {**GOOD, "message": "x" * 4001},
        {**GOOD, "phone": "chama-me"},
    ):
        with pytest.raises(ClubValidationError):
            await contact_service.submit(db, data=broken, club_slug=slug, ip="10.0.0.1")
    assert await _count(db) == 0

    # Il nome finisce nell'oggetto dell'email: niente a capo, niente intestazioni nuove.
    saved = await contact_service.submit(
        db, data={**GOOD, "name": "Ana\r\nBcc: tutti@example.demo"}, club_slug=slug, ip="10.0.0.1",
    )
    assert "\n" not in saved.name and "\r" not in saved.name
    assert saved.email == "ana.sousa@example.demo"
    assert saved.consent_at is not None and saved.status == "NEW"
    # Dell'IP resta solo l'impronta.
    assert saved.ip_hash and "10.0.0.1" not in saved.ip_hash


async def test_the_honeypot_drops_the_message_without_saying_so(db, scope):
    await _published(db, scope)
    assert await contact_service.submit(
        db, data={**GOOD, "website": "https://spam.example"}, club_slug=await _slug(db, scope), ip="10.0.0.2",
    ) is None
    assert await _count(db) == 0


async def test_a_message_reaches_only_its_club_and_the_email_never_fails_the_request(db, scope):
    lagos = await _other_club(db, scope.organization_id)
    await _published(db, scope, contact_email="secretaria@clube.demo")
    await _published(db, lagos)
    secretary = await _user(db, scope, "secretaria")
    await _role(db, scope.organization_id, secretary, "SECRETARY")
    lagos_secretary = await _user(db, lagos, "secretaria-lagos")
    await _role(db, scope.organization_id, lagos_secretary, "SECRETARY")
    platform = await _user(db, ClubScope(organization_id=scope.organization_id, club_id=None), "superadmin")
    await _role(db, scope.organization_id, platform, "SUPER_ADMIN")

    # Senza SMTP (i test girano con SMTP_HOST vuoto): salvato, notificato, nessuna email.
    message = await contact_service.submit(db, data=GOOD, club_slug=await _slug(db, scope), ip="10.0.0.3")
    assert message.club_id == scope.club_id and message.emailed_at is None
    assert [n.entity_id for n in await _notified(db, secretary)] == [str(message.id)]
    assert await _notified(db, lagos_secretary) == []
    # Un messaggio a un club è del club: lo staff della piattaforma non riceve la notifica.
    assert await _notified(db, platform) == []

    # La casella del club vede i suoi; quella di Lagos niente; la console (JAV) niente.
    inbox = await contact_service.club_inbox(db, scope=scope)
    assert [m["id"] for m in inbox["items"]] == [message.id] and inbox["counts"]["NEW"] == 1
    assert (await contact_service.club_inbox(db, scope=lagos))["items"] == []
    assert (await contact_service.platform_inbox(db, organization_id=scope.organization_id))["items"] == []
    with pytest.raises(ClubNotFoundError):
        await contact_service.set_club_status(
            db, scope=lagos, message_id=message.id, status="READ", actor_user_id=lagos_secretary.id,
        )
    read = await contact_service.set_club_status(
        db, scope=scope, message_id=message.id, status="ARCHIVED", actor_user_id=secretary.id,
    )
    assert read["status"] == "ARCHIVED"
    assert (await contact_service.club_inbox(db, scope=scope))["items"] == []
    assert len((await contact_service.club_inbox(db, scope=scope, status="ARCHIVED"))["items"]) == 1
    with pytest.raises(ClubValidationError):
        await contact_service.set_club_status(
            db, scope=scope, message_id=message.id, status="DELETED", actor_user_id=secretary.id,
        )


async def test_with_smtp_the_email_goes_to_the_club_and_reply_goes_to_the_sender(db, scope, monkeypatch):
    from app.core import email as email_module

    sent = []
    monkeypatch.setattr(email_module, "send_html_email", lambda **kw: sent.append(kw))
    await _published(db, scope, contact_email="secretaria@clube.demo")
    message = await contact_service.submit(db, data=GOOD, club_slug=await _slug(db, scope), ip="10.0.0.4")
    [mail] = sent
    assert mail["to"] == "secretaria@clube.demo" and mail["reply_to"] == "ana.sousa@example.demo"
    assert "<script" not in mail["html_body"]
    assert message.emailed_at is not None

    # A JudoArteVida: all'indirizzo di JAV.
    jav = await contact_service.submit(db, data=GOOD, organization_id=scope.organization_id, ip="10.0.0.5")
    assert sent[-1]["to"] == "info@judoartevida.com" and jav.club_id is None

    # Il server di posta che rifiuta non fa fallire niente.
    def _broken(**_kw):
        raise OSError("connection refused")

    monkeypatch.setattr(email_module, "send_html_email", _broken)
    failed = await contact_service.submit(db, data=GOOD, club_slug=await _slug(db, scope), ip="10.0.0.6")
    assert failed.emailed_at is None and await _count(db) == 3


async def test_messages_to_jav_are_for_the_platform_staff_only(db, scope, monkeypatch):
    secretary = await _user(db, scope, "secretaria")
    await _role(db, scope.organization_id, secretary, "SECRETARY")
    admin = await _user(db, ClubScope(organization_id=scope.organization_id, club_id=None), "admin")
    await _role(db, scope.organization_id, admin, "ADMIN")
    await _published(db, scope)

    jav = await contact_service.submit(db, data=GOOD, organization_id=scope.organization_id, ip="10.0.0.7")
    club_message = await contact_service.submit(db, data=GOOD, club_slug=await _slug(db, scope), ip="10.0.0.8")
    assert [n.entity_id for n in await _notified(db, admin)] == [str(jav.id)]
    assert [n.entity_id for n in await _notified(db, secretary)] == [str(club_message.id)]
    assert [m["id"] for m in (await contact_service.club_inbox(db, scope=scope))["items"]] == [club_message.id]

    # Attraverso l'API: la segreteria non apre la casella di JAV; un
    # amministratore senza clubs.manage vede solo quelli a JAV; il superadmin
    # può filtrare per club.
    from tests.test_club_api import _client

    for user, granted, expected in (
        (secretary, {"club.manage", "clubs.enter"}, None),
        (admin, {"clubs.enter"}, [str(jav.id)]),
    ):
        monkeypatch.setattr("app.domains.club.contact_router.get_permission_codes_for_user",
                            lambda *a, _g=granted, **k: _async(_g))
        app, client = await _client(db, monkeypatch, user=user, scope=scope, granted=granted)
        try:
            async with client:
                res = await client.get("/contact-messages")
                if expected is None:
                    assert res.status_code == 403
                else:
                    assert res.status_code == 200, res.text
                    assert [m["id"] for m in res.json()["items"]] == expected
                    assert (await client.get(f"/contact-messages?club={scope.club_id}")).status_code == 403
                    assert (await client.patch(f"/contact-messages/{club_message.id}",
                                               json={"status": "READ"})).status_code == 404
                    ok = await client.patch(f"/contact-messages/{jav.id}", json={"status": "READ"})
                    assert ok.status_code == 200 and ok.json()["status"] == "READ"
        finally:
            app.dependency_overrides.clear()

    superadmin = {"clubs.enter", "clubs.manage"}
    monkeypatch.setattr("app.domains.club.contact_router.get_permission_codes_for_user",
                        lambda *a, **k: _async(superadmin))
    app, client = await _client(db, monkeypatch, user=admin, scope=scope, granted=superadmin)
    try:
        async with client:
            res = await client.get(f"/contact-messages?club={scope.club_id}")
            assert [m["id"] for m in res.json()["items"]] == [str(club_message.id)]
            assert res.json()["items"][0]["club"]["slug"] == await _slug(db, scope)
            assert len((await client.get("/contact-messages?club=all")).json()["items"]) == 2
    finally:
        app.dependency_overrides.clear()


async def _async(value):
    return value


async def test_too_many_messages_are_stopped_even_without_redis(db, scope):
    await _published(db, scope)
    slug = await _slug(db, scope)
    for _ in range(contact_service.MAX_PER_HOUR):
        await contact_service.submit(db, data=GOOD, club_slug=slug, ip="10.0.0.9")
    with pytest.raises(contact_service.ContactTooManyError):
        await contact_service.submit(db, data=GOOD, club_slug=slug, ip="10.0.0.9")
    # Un altro mittente scrive, e dopo un'ora anche il primo.
    await contact_service.submit(db, data=GOOD, club_slug=slug, ip="10.0.0.10")
    later = utcnow() + timedelta(hours=1, minutes=1)
    await contact_service.submit(db, data=GOOD, club_slug=slug, ip="10.0.0.9", now=later)


async def test_the_public_routes_answer_the_same_and_are_rate_limited(db, scope, monkeypatch):
    """Attraverso l'API: 202 anche con la trappola piena, 404 per un club in
    bozza, 429 oltre il limite per IP (Redis finto: i test non scrivono nel
    Redis vero)."""
    from app.core import rate_limit as rate_limit_module
    from app.core.db import get_db
    from app.main import app

    class FakeRedis:
        def __init__(self):
            self.counts: dict[str, int] = {}

        async def incr(self, key):
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, key, seconds):
            return True

    monkeypatch.setattr(rate_limit_module, "_get_redis", lambda fake=FakeRedis(): fake)
    await _published(db, scope)
    slug = await _slug(db, scope)
    draft = await _other_club(db, scope.organization_id)
    await site_service.get_site(db, scope=draft)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
            trap = await client.post(f"/public-site/clubs/{slug}/message", json={**GOOD, "website": "x"})
            assert trap.status_code == 202 and trap.json() == {"ok": True}
            assert await _count(db) == 0
            ok = await client.post(f"/public-site/clubs/{slug}/message", json=GOOD)
            assert ok.status_code == 202
            bad = await client.post(f"/public-site/clubs/{slug}/message", json={**GOOD, "consent": False})
            assert bad.status_code == 400 and "consenso" in bad.json()["detail"]
            missing = await client.post(f"/public-site/clubs/{await _slug(db, draft)}/message", json=GOOD)
            assert missing.status_code == 404
            jav = await client.post("/public-site/contact", json=GOOD)
            assert jav.status_code in (202, 404)  # 404 solo se il database di test ha più organizzazioni
            limited = await client.post("/public-site/contact", json=GOOD)
            assert limited.status_code == 429
    finally:
        app.dependency_overrides.clear()
    assert await _count(db, club_id=scope.club_id) == 1


async def test_the_jav_courses_unit_receives_no_club_messages(db, organization_id):
    """L'unità dei corsi non è un club sul sito: la sua pagina non esiste
    come pagina di club, e nemmeno il suo modulo. Si scrive a JAV."""
    from tests.test_jav_courses import _unit

    unit, _actor = await _unit(db, organization_id)
    await _published(db, unit)
    with pytest.raises(ClubNotFoundError):
        await contact_service.submit(db, data=GOOD, club_slug=await _slug(db, unit), ip="10.0.0.11")
    assert await _count(db) == 0
