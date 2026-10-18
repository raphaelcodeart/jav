"""Che cosa esce verso il modello, chi usa JAVBOT, e il genitore che resta
collegato al figlio maggiorenne (javbot/privacy.py, service.available,
athlete_access.become_holder / invite_holder)."""

from datetime import date

from app.core.deps import CurrentUser
from app.domains.club import athlete_access
from app.domains.club import service as club_service
from app.domains.javbot import agent, llm, privacy, service
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from tests.test_club_fees import _athlete, _plans, _user
from tests.test_javbot import _ctx


def test_private_values_never_leave_and_come_back():
    vault = privacy.Vault()
    data = {"athletes": [{"first_name": "Valentina", "height_cm": 173, "due_cents": 4500,
                          "fiscal_code": "123456789", "phone": "+351 912 345 678",
                          "address": {"street": "Rua A", "city": "Lagos"}}], "iban": "PT50 0000 0000 0000 0000 0000 0"}
    masked = privacy.mask(data, vault)
    flat = str(masked)
    for secret in ("4500", "45,00", "123456789", "912", "Rua A", "PT50"):
        assert secret not in flat
    assert masked["athletes"][0]["height_cm"] == 173 and masked["athletes"][0]["first_name"] == "Valentina"
    token = masked["athletes"][0]["due_cents"]
    assert privacy.unmask(f"Tens {token} para pagar ⟦V99⟧", vault) == "Tens 45,00 € para pagar —"
    redacted = privacy.redact_text("Tens 146,00 € para pagar. IBAN PT50 0002 0123 1234 5678 9015 4, liga 912 345 678.")
    assert "146" not in redacted and "PT50" not in redacted and "912" not in redacted


async def test_the_model_sees_tokens_and_the_user_sees_values(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    valentina = await _athlete(db, scope, parent, birth_date=date(1983, 3, 15), first_name="Valentina",
                               today=date.today())
    valentina.height_cm = 173
    await db.commit()
    sent = []
    replies = iter([
        llm.LlmResult(tool_calls=[{"id": "c1", "name": "family_athletes", "args": {}}],
                      message={"role": "assistant", "content": None, "tool_calls": []}),
        None,
    ])

    async def chat(db_, messages, **kwargs):
        sent.append(messages)
        nxt = next(replies)
        if nxt is not None:
            return nxt
        tool = messages[-1]["content"]
        return llm.LlmResult(text=f"A Valentina mede 173 cm. Tool: {tool[:0]}")

    monkeypatch.setattr(llm, "chat", chat)
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    reply = await agent.reply(ctx, type("C", (), {"id": None, "state": {}})(), "quanto è alta Valentina?", llm.Spend())
    assert "173" in reply.text
    tool_message = sent[1][-1]["content"]
    assert "173" in tool_message and parent.email not in tool_message


async def test_minors_do_not_get_javbot(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    kid = await _athlete(db, scope, parent, birth_date=date(date.today().year - 12, 5, 5), first_name="Ariel",
                         today=date.today())
    role = Role(organization_id=scope.organization_id, code="ATHLETE", name="Athlete")
    db.add(role)
    await db.commit()
    await athlete_access.set_login(db, athlete=kid, actor_user_id=parent.id, username="ariel.p", email=None,
                                   password="segreto1")
    await db.refresh(kid)
    kid_user = await db.get(User, kid.user_id)
    assert not await service.available(db, current_user=CurrentUser(user_id=kid_user.id, organization_id=scope.organization_id, roles=[]))
    db.add(UserRole(user_id=parent.id, organization_id=scope.organization_id,
                    role_id=(await db.execute(Role.__table__.select().where(Role.code == "ATHLETE"))).first().id))
    await db.commit()
    assert await service.available(db, current_user=CurrentUser(user_id=parent.id, organization_id=scope.organization_id, roles=[]))


async def test_the_parent_stays_linked_when_the_child_takes_the_account(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    for code in ("ATHLETE", "CUSTOMER"):
        db.add(Role(organization_id=scope.organization_id, code=code, name=code.title()))
    await db.commit()
    parent = await _user(db, scope)
    valentina = await _athlete(db, scope, parent, birth_date=date(1983, 3, 15), first_name="Valentina", today=date.today())

    async def _sent(*args, **kwargs):
        return "https://link", False

    from app.domains.auth import service as auth_service

    monkeypatch.setattr(auth_service, "send_account_invite_email", _sent)
    link = await athlete_access.invite_holder(db, athlete=valentina, guardian_user_id=parent.id,
                                              email="valentina@example.pt", today=date.today())
    assert link == "https://link"
    await db.refresh(valentina)
    area = await athlete_access.area(db, athlete=valentina, viewer_user_id=parent.id, today=date.today())
    assert area["can_invite_holder"] and not area["can_become_holder"]

    await athlete_access.become_holder(db, athlete=valentina, user_id=valentina.user_id, email=None, today=date.today())
    await db.refresh(valentina)
    assert valentina.guardian_user_id == valentina.user_id and valentina.is_self
    # Il padre la vede ancora nella sua famiglia e nella sua area.
    family = await club_service.list_family_athletes(db, scope=scope, guardian_user_id=parent.id)
    assert valentina.id in {a.id for a in family}
    await club_service.get_owned_athlete(db, scope=scope, guardian_user_id=parent.id, athlete_id=valentina.id)
    await athlete_access.area_athlete(db, user_id=parent.id, club_id=scope.club_id, athlete_id=valentina.id)
