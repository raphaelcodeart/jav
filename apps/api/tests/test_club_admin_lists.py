"""Gli elenchi della segreteria: le prove di pagamento con la ricerca e la
tabella atleti con l'anagrafe (docs/club-portal.md)."""

from datetime import date, timedelta

from app.domains.club import service as club_service
from app.domains.club.records_models import ClubApplication
from app.domains.club.referrals import SOURCE_CLUB_LINK
from app.domains.club.router import _athlete_registry
from app.domains.customers.models import Customer
from app.domains.friend_referrals.models import FriendReferral
from tests.test_club_fees import PNG, _athlete, _fees, _plans, _user


async def _proof(db, scope, parent, athlete):
    fee = (await _fees(db, athlete.id, kind="MONTHLY"))[0]
    return await club_service.upload_payment_proof(
        db, scope=scope, guardian_user_id=parent.id, fee_ids=[fee.id],
        file_bytes=PNG, content_type="image/png", original_filename="bonifico.png",
    )


async def test_proofs_are_found_by_athlete_email_receipt_and_period(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    rossi = await _user(db, scope, "rossi")
    verdi = await _user(db, scope, "verdi")
    luca = await _athlete(db, scope, rossi, birth_date=date(2016, 3, 3), first_name="Luca", last_name="Rossi")
    anna = await _athlete(db, scope, verdi, birth_date=date(2016, 3, 3), first_name="Anna", last_name="Verdi")
    p_luca = await _proof(db, scope, rossi, luca)
    p_anna = await _proof(db, scope, verdi, anna)

    async def ids(**kw):
        return {p.id for p in await club_service.list_proofs(db, scope=scope, **kw)}

    assert await ids(q="luca ross") == {p_luca.id}
    assert await ids(q="verdi") == {p_anna.id}
    assert await ids(q=rossi.email[:10]) == {p_luca.id}
    if p_anna.receipt_number:
        assert await ids(q=p_anna.receipt_number) == {p_anna.id}
    assert await ids(method="CASH") == set()
    assert await ids(method="BANK_TRANSFER") == {p_luca.id, p_anna.id}
    today = date.today()
    assert await ids(date_from=today - timedelta(days=1), date_to=today + timedelta(days=1)) == {p_luca.id, p_anna.id}
    assert await ids(date_from=today + timedelta(days=2)) == set()


async def test_the_athletes_table_says_who_brought_each_family(db, scope):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    friend = await _user(db, scope, "amica")
    invited = await _user(db, scope, "invitata")
    written = await _user(db, scope, "scritto")
    alone = await _user(db, scope, "solo")
    customer = Customer(organization_id=scope.organization_id, user_id=invited.id, kind="PRIVATE",
                        email=invited.email, phone="912345678")
    db.add(customer)
    await db.flush()
    db.add(FriendReferral(organization_id=scope.organization_id, referrer_user_id=friend.id,
                          referred_customer_id=customer.id, code_used="ABC", source=SOURCE_CLUB_LINK))
    a_invited = await _athlete(db, scope, invited, birth_date=date(2015, 1, 1))
    a_invited.member_number = "0042"
    a_written = await _athlete(db, scope, written, birth_date=date(2015, 1, 1))
    a_alone = await _athlete(db, scope, alone, birth_date=date(2015, 1, 1))
    db.add(ClubApplication(organization_id=scope.organization_id, club_id=scope.club_id, full_name="X",
                           athlete_id=a_written.id, referred_by=" Tio João "))
    await db.commit()

    rows = await _athlete_registry(db, [a_invited, a_written, a_alone])
    assert rows[a_invited.id]["invited_by"] == {"kind": "PERSON", "name": friend.email, "user_id": friend.id}
    assert rows[a_invited.id]["guardian_phone"] == "912345678"
    assert rows[a_written.id]["invited_by"] == {"kind": "WRITTEN", "name": "Tio João"}
    assert rows[a_alone.id]["invited_by"] is None
    assert rows[a_alone.id]["guardian_email"] == alone.email

    # La ricerca trova anche per nº de sócio ed email dell'encarregado.
    found = await club_service.search_athletes(db, scope=scope, q="0042")
    assert [a.id for a in found] == [a_invited.id]
    found = await club_service.search_athletes(db, scope=scope, q=written.email[:12])
    assert [a.id for a in found] == [a_written.id]
