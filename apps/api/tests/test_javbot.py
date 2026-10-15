"""JAVBOT: l'assistente dell'area privata e del sito.

Le promesse: capisce le domande nelle tre lingue; dice a una famiglia
quanto deve pagare lei, mai un'altra; trova il judogi della taglia giusta
con il prezzo del server e crea l'ordine **solo dopo un sì, una volta
sola**; quello del sito non dice niente di nessuno; le risposte della
segreteria le ha solo chi ha il permesso della segreteria.
"""

import json
import uuid
from datetime import date, time

from sqlalchemy import func, select

from app.core.deps import CurrentUser
from app.domains.club import service as club_service
from app.domains.club.site_models import ClubSite
from app.domains.customers.models import Customer, CustomerProfile
from app.domains.jav_market import service as market
from app.domains.jav_market.models import JavMarketOrder
from app.domains.javbot import intents, service, sizes
from app.domains.javbot import public as public_bot
from app.domains.javbot.models import JavbotTask
from app.domains.javbot.texts import euro, say
from app.domains.javbot.tools import REGISTRY, ToolContext
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate
from tests.test_club_fees import _athlete, _plans, _user


async def _ctx(db, monkeypatch, user, scope, permissions: set[str], lang="it") -> ToolContext:
    async def _codes(*args, **kwargs):
        return permissions

    monkeypatch.setattr(service, "get_permission_codes_for_user", _codes)
    return await service.build_context(
        db, current_user=CurrentUser(user_id=user.id, organization_id=scope.organization_id, roles=[]),
        requested_club=None, lang=lang,
    )


async def _say(db, ctx, text):
    """Manda un messaggio e restituisce la risposta di JAVBOT."""
    _asked, answered = await service.post_message(db, ctx=ctx, text=text)
    return answered


async def _orders(db, user) -> int:
    return (await db.execute(
        select(func.count()).select_from(JavMarketOrder).where(JavMarketOrder.customer_user_id == user.id)
    )).scalar_one()


# --- Capire la domanda ----------------------------------------------------------------------------


def test_intents_in_three_languages():
    cases = {
        ("Quanto devo pagare questo mese?", "it"): "fees_due",
        ("Quanto tenho de pagar?", "pt"): "fees_due",
        ("How much do I owe?", "en"): "fees_due",
        ("Non riesco a caricare la prova del bonifico", "it"): "upload_proof",
        ("Não consigo carregar o comprovativo", "pt"): "upload_proof",
        ("I can't upload the receipt", "en"): "upload_proof",
        ("Vorrei comprare un judogi per mio figlio", "it"): "judogi",
        ("Quero comprar um quimono", "pt"): "judogi",
        ("I want to buy a judogi", "en"): "judogi",
        ("Chi non ha pagato?", "it"): "staff_unpaid",
        ("Quem não pagou?", "pt"): "staff_unpaid",
        ("Há aulas hoje?", "pt"): "lessons_today",
        ("Quando scade il certificato medico?", "it"): "certificates",
        ("Quais são as provas abertas?", "pt"): "competitions",
        ("Voglio parlare con la segreteria", "it"): "secretary",
    }
    for (text, lang), expected in cases.items():
        assert intents.detect(text, lang=lang)[0] == expected, text
    # "prova" è la ricevuta in italiano e una gara in portoghese.
    assert intents.detect("le prove", lang="pt")[0] != "upload_proof"
    assert intents.detect("Ho caricato la prova?", lang="it")[0] == "upload_proof"
    assert intents.detect("asdfgh", lang="it") == (None, 0)

    public = intents.PUBLIC_INTENTS
    assert intents.detect("Quanto custa?", lang="pt", catalog=public)[0] == "prices"
    assert intents.detect("Come mi iscrivo?", lang="it", catalog=public)[0] == "signup"
    assert intents.detect("What's the schedule?", lang="en", catalog=public)[0] == "schedule"


def test_public_price_and_group_questions():
    """Le domande vere sui prezzi e sui gruppi, nelle tre lingue: tutte
    arrivano alla scheda del club (prices o groups, stessa risposta)."""
    public = intents.PUBLIC_INTENTS
    cases = {
        ("quanto costa la mensilità di Lagos", "it"): "prices",
        ("quanto custa a mensalidade em Lagos", "pt"): "prices",
        ("preço judo Lagos", "pt"): "prices",
        ("quotas", "pt"): "prices",
        ("inscrição", "pt"): "prices",
        ("Quanto custa a inscrição?", "pt"): "prices",
        ("How much is it in Lagos?", "en"): "prices",
        ("grupos e idades", "pt"): "groups",
        ("que idades?", "pt"): "groups",
        ("a partir de que idade?", "pt"): "groups",
        ("da che età si può iniziare?", "it"): "groups",
        ("What age groups do you have?", "en"): "groups",
        ("Como faço para ter um desconto?", "pt"): "discounts",
        ("Come ottengo uno sconto sulla mensilità?", "it"): "discounts",
        ("Is there a family discount for siblings?", "en"): "discounts",
        ("Há desconto para irmãos?", "pt"): "discounts",
        ("O meu filho faz judo adaptado", "pt"): "discounts",
        # Iscriversi resta iscriversi.
        ("Como me inscrevo?", "pt"): "signup",
        ("Come mi iscrivo?", "it"): "signup",
    }
    for (text, lang), expected in cases.items():
        assert intents.detect(text, lang=lang, catalog=public)[0] == expected, text


def test_heights_and_sizes():
    assert intents.extract_height_cm("è alto 145 cm") == 145
    assert intents.extract_height_cm("1,45 m") == 145
    assert intents.extract_height_cm("1.5") == 150
    assert intents.extract_height_cm("ha 9 anni") is None
    assert intents.extract_height_cm("2026") is None
    # La decina sopra; chi è alto esattamente 150 prende il 150.
    assert sizes.size_for_height(145) == 150
    assert sizes.size_for_height(150) == 150
    assert sizes.size_for_height(85) == 100
    assert sizes.size_for_height(212) == 200
    assert sizes.variant_size_cm("150 cm") == 150
    assert sizes.variant_size_cm("Tg. 160") == 160
    assert sizes.variant_size_cm("Taglia 2") == 160
    assert sizes.variant_size_cm("Unica") is None


# --- Quote ----------------------------------------------------------------------------------------


async def test_due_summary_is_the_familys_own(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    other = await _user(db, scope, "altro")
    luca = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    await _athlete(db, scope, other, birth_date=date(2015, 1, 1), first_name="Estraneo", last_name="Segreto")

    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    data = await REGISTRY.call("family_dues", ctx)
    own = await club_service.list_fees(db, scope=scope, athlete_ids=[luca.id], guardian_user_id=parent.id, status="DUE")
    assert data["due_cents"] == sum(f.amount_cents for f in own) > 0
    assert {r["athlete_id"] for r in data["fees"]} <= {luca.id, None}

    answer = await _say(db, ctx, "Quanto devo pagare?")
    assert euro(data["due_cents"], "it") in answer.text
    assert "Luca" in answer.text and "Estraneo" not in answer.text
    assert any(a["type"] == "open_pay" for a in answer.actions)

    # In portoghese, la stessa risposta nella sua lingua.
    ctx_pt = await _ctx(db, monkeypatch, parent, scope, {"club.family"}, lang="pt")
    answer = await _say(db, ctx_pt, "Quanto tenho de pagar?")
    assert "No total tens" in answer.text


# --- Judogi ---------------------------------------------------------------------------------------


async def _judogi_shop(db, scope, admin):
    await organizations_service.update_settings(
        db, organization_id=scope.organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456"),
    )
    row = await market.get_settings_row(db, organization_id=scope.organization_id)
    await market.update_settings(db, row=row, actor_user_id=admin.id,
                                 updates={"enabled": True, "shipping_flat_cents": 490, "shipping_days": "3-5"})
    return await market.create_product(
        db, organization_id=scope.organization_id, actor_user_id=admin.id,
        payload={"name": "Judogi Kids", "description": "Cotone 100%", "credit_discount_percentage": 0,
                 "unit_cost_cents": 1500,
                 "variants": [{"label": "140 cm", "price_cents": 3200, "inventory": 5},
                              {"label": "150 cm", "price_cents": 3500, "inventory": 5},
                              {"label": "160 cm", "price_cents": 3800, "inventory": 5}]},
    )


async def _with_address(db, scope, user):
    user.residence_street = "Rua das Flores 10"
    user.residence_city = "Lagos"
    user.residence_province = "FA"
    user.residence_postal_code = "8600-100"
    customer = Customer(organization_id=scope.organization_id, user_id=user.id, kind="PRIVATE", email=user.email,
                        phone="912345678")
    db.add(customer)
    await db.flush()
    db.add(CustomerProfile(customer_id=customer.id, first_name="Maria", last_name="Silva"))
    await db.commit()


async def test_judogi_from_height_to_one_order(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _with_address(db, scope, parent)
    luca = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    await _judogi_shop(db, scope, admin)
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})

    asked = await _say(db, ctx, "Vorrei comprare un judogi")
    assert "Luca" in asked.text and "centimetri" in asked.text  # un atleta solo: chiede subito l'altezza

    offer = await _say(db, ctx, "145")
    variant = next(v for v in await market._variants(db, (await market.list_products(db, organization_id=scope.organization_id))[0].id)
                   if v.label == "150 cm")
    quote = await market.get_quote(db, organization_id=scope.organization_id, customer_user_id=parent.id,
                                   variant_id=variant.id, quantity=1)
    assert "150" in offer.text and "Judogi Kids" in offer.text
    assert euro(quote["amount_cents"], "it") in offer.text  # il prezzo del server, non uno suo
    assert "Rua das Flores 10" in offer.text
    task_id = uuid.UUID(next(a["task_id"] for a in offer.actions if a["type"] == "confirm_task"))
    assert await _orders(db, parent) == 0  # una proposta non è un ordine

    done = await service.decide_task(db, ctx=ctx, task_id=task_id, accept=True)
    assert "JAV-" in done[-1].text
    assert await _orders(db, parent) == 1
    order = (await db.execute(select(JavMarketOrder).where(JavMarketOrder.customer_user_id == parent.id))).scalar_one()
    assert order.athlete_id == luca.id and order.payment_method == "BANK_TRANSFER"
    assert order.amount_cents == quote["amount_cents"]

    # Il doppio tocco, e il "sì" scritto dopo: nessun secondo ordine.
    again = await service.decide_task(db, ctx=ctx, task_id=task_id, accept=True)
    assert market.order_number(order) in again[-1].text
    await _say(db, ctx, "sì")
    assert await _orders(db, parent) == 1
    task = await db.get(JavbotTask, task_id)
    assert task.status == "DONE" and task.result_ref == str(order.id)


async def test_no_order_without_a_yes(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _with_address(db, scope, parent)
    await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Ana")
    await _athlete(db, scope, parent, birth_date=date(2018, 3, 3), first_name="Rui")
    await _judogi_shop(db, scope, admin)
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"}, lang="pt")

    which = await _say(db, ctx, "Quero comprar um judogi")
    assert set(which.quick_replies) == {"Ana", "Rui"}  # due figli: prima per chi
    await _say(db, ctx, "Rui")
    offer = await _say(db, ctx, "1,38 m")
    assert "140" in offer.text
    task_id = uuid.UUID(next(a["task_id"] for a in offer.actions if a["type"] == "confirm_task"))

    # Parlare d'altro non conferma; "não" annulla; dopo, il bottone non fa niente.
    await _say(db, ctx, "Quanto tenho de pagar?")
    await _say(db, ctx, "sim")
    assert await _orders(db, parent) == 0
    cancelled = await service.decide_task(db, ctx=ctx, task_id=task_id, accept=False)
    assert cancelled[-1].text == say("pt", "task.cancelled")
    await service.decide_task(db, ctx=ctx, task_id=task_id, accept=True)
    assert await _orders(db, parent) == 0

    # E il compito di un'altra famiglia non si conferma.
    stranger = await _user(db, scope, "estranho")
    await _with_address(db, scope, stranger)
    ctx_other = await _ctx(db, monkeypatch, stranger, scope, {"club.family"}, lang="pt")
    await _say(db, ctx, "Quero comprar um judogi para a Ana")
    offer = await _say(db, ctx, "150")
    foreign = uuid.UUID(next(a["task_id"] for a in offer.actions if a["type"] == "confirm_task"))
    refused = await service.decide_task(db, ctx=ctx_other, task_id=foreign, accept=True)
    assert refused[-1].text == say("pt", "task.notFound")
    assert await _orders(db, stranger) == 0 and await _orders(db, parent) == 0


async def test_no_judogi_in_the_catalog_offers_to_tell_the_club(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    row = await market.get_settings_row(db, organization_id=scope.organization_id)
    await market.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": True})
    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"}, lang="en")

    await _say(db, ctx, "I want to buy a judogi")
    reply = await _say(db, ctx, "152 cm")
    assert "160" in reply.text and say("en", "judogi.none") in reply.text
    assert [a["type"] for a in reply.actions] == ["confirm_task", "cancel_task"]
    assert (await db.get(JavbotTask, uuid.UUID(reply.actions[0]["task_id"]))).kind == "CLUB_MESSAGE"


# --- Segreteria -----------------------------------------------------------------------------------


async def test_staff_answers_need_the_staff_permission(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _athlete(db, scope, parent, birth_date=date(2016, 3, 3), first_name="Bruno", last_name="Moroso")
    question = "Chi non ha pagato questo mese?"

    secretary = await _ctx(db, monkeypatch, admin, scope, {"club.manage", "club.instruct"})
    answer = await _say(db, secretary, question)
    assert "Bruno Moroso" in answer.text

    coach = await _user(db, scope, "istruttore")
    instructor = await _ctx(db, monkeypatch, coach, scope, {"club.instruct"})
    answer = await _say(db, instructor, question)
    assert answer.text == say("it", "denied.staff")

    other = await _user(db, scope, "genitore2")
    family = await _ctx(db, monkeypatch, other, scope, {"club.family"})
    answer = await _say(db, family, question)
    assert "Bruno" not in answer.text and "Moroso" not in answer.text


# --- Sito pubblico --------------------------------------------------------------------------------


async def test_the_public_bot_never_tells_personal_data(db, scope):
    from app.domains.club.models import Club

    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope, "riservato")
    await _athlete(db, scope, parent, birth_date=date(2014, 7, 21), first_name="Privato", last_name="Riservatissimo",
                   fiscal_code=None)
    club = await db.get(Club, scope.club_id)
    site = ClubSite(**scope.columns(), city="Lagos", contact_email="info@club.example", contact_phone="282 000 000",
                    gallery=[], coaches=[], published=True)
    db.add(site)
    await db.commit()

    ctx = ToolContext(db=db, user_id=None, organization_id=None, scope=None, permissions=frozenset(), lang="it",
                      today=date(2026, 10, 14))
    questions = ["ciao", "Che club ci sono?", "Orari", f"Orari {club.name}", f"Prezzi {club.name}", "che età?",
                 "quanto costa la mensilità di Lagos",
                 "Come mi iscrivo?", "Prossimi eventi", "Perché il judo?", "chi è Privato Riservatissimo?",
                 "quanto deve pagare la famiglia?", "asdf"]
    dumps = []
    for q in questions:
        reply = await public_bot.answer(ctx, q, club_slug=club.slug)
        dumps.append(json.dumps({"t": reply.text, "a": reply.actions, "q": reply.quick_replies}, default=str))
    everything = " ".join(dumps)
    for secret in ("Riservatissimo", parent.email, "21/07/2014", "2014-07-21"):
        assert secret not in everything

    prices = await public_bot.answer(ctx, "Quanto costa?", club_slug=club.slug)
    assert say("it", "pub.pricesHidden", club=club.name) in prices.text  # spento per default
    assert "info@club.example" in prices.text
    site.show_prices = True
    await db.commit()
    prices = await public_bot.answer(ctx, "Quanto costa?", club_slug=club.slug)
    assert euro(4000, "it") in prices.text  # Ragazzi 8-13, dal piano del club

    signup = await public_bot.answer(ctx, "Come mi iscrivo?", club_slug=club.slug)
    assert {"type": "link", "href": f"/c/{club.slug}"}.items() <= signup.actions[0].items()

    # Un club non pubblicato non esiste nemmeno per il bot.
    site.published = False
    await db.commit()
    hidden = await public_bot.answer(ctx, f"Orari {club.name}")
    assert club.name not in hidden.text


async def _lagos(db, scope, *, show_prices: bool, plans: bool = True):
    """Il club della prova con la tabella vera di un club (tre gruppi,
    quote annuali, pagamento entro il 15), un corso per i piccoli e un
    secondo club a Faro: la città nel messaggio deve scegliere Lagos."""
    from app.domains.club import clubs as clubs_service
    from app.domains.club import courses as courses_service
    from app.domains.club.models import Club

    admin = await _user(db, scope, "admin")
    if plans:
        for name, low, high, monthly, note in (
            ("Iniciação", 3, 7, 3500, "Aula avulsa (sem mensalidade, mediante acordo): 7,50 €"),
            ("Formação", 8, 12, 6000, None),
            ("Competição, Manutenção e Veteranos", 13, None, 8500, None),
        ):
            await club_service.create_plan(db, scope=scope, actor_user_id=admin.id, data={
                "name": name, "min_age": low, "max_age": high, "monthly_fee_cents": monthly,
                "enrollment_fee_cents": 12000, "due_day": 15, "description": note,
            })
    await clubs_service.update_club_pricing(db, scope=scope, actor_user_id=admin.id, changes={
        "parent_member_fee_cents": 6000, "family_discount_cents": 500, "family_min_athletes": 2,
        "tier_discount_pct": {"A": 0, "B": 10}, "referral_credit_cents": 0,
        "enrollment_includes": "Sócio Judoca, Taxa de Faltas aos Treinos, inscrição na FPJ e seguro desportivo",
    })
    course = await courses_service.create_course(db, scope=scope, actor_user_id=admin.id,
                                                 data={"name": "Judo Pequenos", "min_age": 3, "max_age": 7})
    await courses_service.add_slot(db, scope=scope, course_id=course.id, actor_user_id=admin.id, weekday=0,
                                   starts_at=time(18, 0), ends_at=time(19, 0), room=None)
    db.add(ClubSite(**scope.columns(), city="Lagos", contact_email="lagos@club.example", gallery=[], coaches=[],
                    published=True, show_prices=show_prices))
    faro = Club(organization_id=scope.organization_id, name="Judo Faro", slug=f"faro-{uuid.uuid4().hex[:6]}",
                settings={})
    db.add(faro)
    await db.flush()
    db.add(ClubSite(organization_id=scope.organization_id, club_id=faro.id, city="Faro", gallery=[], coaches=[],
                    published=True, show_prices=True))
    await db.commit()
    return await db.get(Club, scope.club_id)


def _public_ctx(db, lang="pt") -> ToolContext:
    return ToolContext(db=db, user_id=None, organization_id=None, scope=None, permissions=frozenset(), lang=lang,
                       today=date(2026, 10, 14))


async def test_the_price_card_says_everything_the_club_configured(db, scope):
    club = await _lagos(db, scope, show_prices=True)
    reply = await public_bot.answer(_public_ctx(db), "Quanto custa a mensalidade em Lagos?")
    text = reply.text
    assert reply.intent == "prices" and say("pt", "pub.pricesIntro", club=club.name) in text
    for expected in (
        "• Iniciação (3–7 anos): 35,00 € por mês, inscrição anual 120,00 €",
        "• Formação (8–12 anos): 60,00 € por mês",
        "• Competição, Manutenção e Veteranos (a partir dos 13 anos): 85,00 € por mês",
        "Paga-se até ao dia 15 de cada mês, de setembro a junho.",
        "Aula avulsa (sem mensalidade, mediante acordo): 7,50 €",
        "Treinos: Segunda 18:00–19:00",
        say("pt", "pub.feeParent", age=18, amount=euro(6000, "pt")),
        say("pt", "pub.feeProrata"),
        "A inscrição inclui: Sócio Judoca, Taxa de Faltas aos Treinos, inscrição na FPJ e seguro desportivo",
        say("pt", "pub.discountFamily", n=2, amount=euro(500, "pt")),
        "Escalão: B −10% na mensalidade",
    ):
        assert expected in text, expected
    # Il corso dei piccoli è dei 3-7 anni: non è l'allenamento degli altri gruppi.
    assert text.count("Treinos:") == 1
    # Spenti o a zero: non si nominano.
    assert "Convida um amigo" not in text and "Judo adaptado" not in text and "Faro" not in text
    assert {"type": "link", "href": f"/c/{club.slug}"}.items() <= reply.actions[0].items()

    groups = await public_bot.answer(_public_ctx(db, "it"), "da che età si può iniziare a Lagos?")
    assert groups.intent == "groups" and "Iniciação (3–7 anni): 35,00 € al mese" in groups.text


async def test_without_show_prices_groups_and_ages_but_no_money(db, scope):
    club = await _lagos(db, scope, show_prices=False)
    reply = await public_bot.answer(_public_ctx(db), "quanto custa a mensalidade em Lagos")
    text = reply.text
    assert say("pt", "pub.groupsIntro", club=club.name) in text
    for expected in ("• Iniciação (3–7 anos)", "• Formação (8–12 anos)",
                     "• Competição, Manutenção e Veteranos (a partir dos 13 anos)", "Treinos: Segunda 18:00–19:00",
                     say("pt", "pub.pricesHidden", club=club.name), "lagos@club.example"):
        assert expected in text, expected
    # Nessun importo, nemmeno quello scritto nella descrizione del piano.
    assert "€" not in text and "avulsa" not in text and "dia 15" not in text
    assert (await public_bot.answer(_public_ctx(db), "que idades?", club_slug=club.slug)).text == text


async def test_a_club_without_plans_says_so(db, scope):
    club = await _lagos(db, scope, show_prices=True, plans=False)
    reply = await public_bot.answer(_public_ctx(db), "preço judo Lagos")
    text = reply.text
    assert say("pt", "pub.groupsNone", club=club.name) in text
    assert "lagos@club.example" in text and "18:00–19:00" in text and "€" not in text


async def test_how_to_get_a_discount(db, scope):
    """Gli sconti come li ha impostati il club (A 25 / B 15 / C 5, famiglia
    5 €, invito 5 €), con che cosa fare per averli."""
    from app.domains.club import clubs as clubs_service

    club = await _lagos(db, scope, show_prices=True)
    admin = await _user(db, scope, "admin2")
    await clubs_service.update_club_pricing(db, scope=scope, actor_user_id=admin.id, changes={
        "tier_discount_pct": {"A": 25, "B": 15, "C": 5}, "family_discount_cents": 500, "referral_credit_cents": 500,
    })
    reply = await public_bot.answer(_public_ctx(db), "Como faço para ter um desconto em Lagos?")
    assert reply.intent == "discounts"
    for expected in (
        say("pt", "pub.discountsHow", club=club.name),
        say("pt", "pub.discountTier", tiers="A −25%, B −15%, C −5%"),
        say("pt", "pub.discountAdapted", pct=25),
        say("pt", "pub.discountFamily", n=2, amount=euro(500, "pt")),
        say("pt", "pub.discountReferral", amount=euro(500, "pt")),
    ):
        assert expected in reply.text, expected

    # Senza "mostra i prezzi": quali sconti sì, quanto no.
    site = (await db.execute(select(ClubSite).where(ClubSite.club_id == scope.club_id))).scalars().first()
    site.show_prices = False
    await db.commit()
    hidden = await public_bot.answer(_public_ctx(db, "it"), "come ottengo uno sconto?", club_slug=club.slug)
    assert say("it", "pub.discountsHidden", club=club.name,
               names="escalão, judo adattato, famiglia, invita un amico") in hidden.text
    assert "%" not in hidden.text and "€" not in hidden.text

    # Un club senza sconti lo dice, invece di inventarne.
    await clubs_service.update_club_pricing(db, scope=scope, actor_user_id=admin.id, changes={
        "tier_discount_pct": {"A": 0, "B": 0, "C": 0}, "family_discount_cents": 0, "referral_credit_cents": 0,
    })
    none = await public_bot.answer(_public_ctx(db, "en"), "discounts?", club_slug=club.slug)
    assert say("en", "pub.discountsNone", club=club.name) in none.text


# --- Che cosa sa di me ----------------------------------------------------------------------------


def test_personal_questions_in_three_languages():
    cases = {
        ("Quanto ho pagato quest'anno?", "it"): "payments_made",
        ("Quanto paguei este ano?", "pt"): "payments_made",
        ("How much have I paid?", "en"): "payments_made",
        ("Ho debiti con il club?", "it"): "fees_due",
        ("Tenho dívidas?", "pt"): "fees_due",
        ("Estou em dívida?", "pt"): "fees_due",
        ("Cosa sai di me?", "it"): "overview",
        ("O que sabes de mim?", "pt"): "overview",
        ("Quais são os meus dados?", "pt"): "my_profile",
        ("Che piano ha Luca?", "it"): "my_profile",
        ("Que cinto tem o Rui?", "pt"): "belts",
        ("Quante presenze ha fatto Luca?", "it"): "attendance_stats",
        ("Quantos treinos fez este mês?", "pt"): "attendance_stats",
        ("Quantos pontos tem no ranking?", "pt"): "ranking",
        # Le domande che c'erano prima restano dove erano.
        ("Ho pagato ma non riesco a caricare la ricevuta", "it"): "upload_proof",
        ("Há aulas hoje?", "pt"): "lessons_today",
        ("Quem não pagou?", "pt"): "staff_unpaid",
    }
    for (text, lang), expected in cases.items():
        assert intents.detect(text, lang=lang)[0] == expected, text


async def test_the_bot_knows_the_family_and_only_it(db, scope, monkeypatch):
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _with_address(db, scope, parent)
    other = await _user(db, scope, "altro")
    luca = await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    stranger = await _athlete(db, scope, other, birth_date=date(2015, 1, 1), first_name="Estraneo", last_name="Segreto")
    due = await club_service.list_fees(db, scope=scope, athlete_ids=[luca.id], status="DUE")
    paid = await club_service.mark_fee_paid(db, scope=scope, fee_id=due[0].id, actor_user_id=admin.id, note=None, method="CARD")
    for fee in await club_service.list_fees(db, scope=scope, athlete_ids=[stranger.id], status="DUE"):
        await club_service.mark_fee_paid(db, scope=scope, fee_id=fee.id, actor_user_id=admin.id, note=None, method="CARD")
    await club_service.award_belt(db, athlete=luca, grade="YELLOW", awarded_on=date(2026, 6, 20), actor_user_id=admin.id)

    ctx = await _ctx(db, monkeypatch, parent, scope, {"club.family"})
    money = await REGISTRY.call("family_payments", ctx)
    assert money["totals"]["paid_all_time_cents"] == paid.amount_cents
    assert [r["first_name"] for r in money["recent"]] == ["Luca"]

    answer = await _say(db, ctx, "Quanto ho pagato?")
    assert euro(paid.amount_cents, "it") in answer.text and "Luca" in answer.text
    assert "Estraneo" not in answer.text
    assert any(a.get("target") == "accounts" for a in answer.actions)

    answer = await _say(db, ctx, "Che cintura ha Luca?")
    assert "gialla" in answer.text and "20/06/2026" in answer.text

    answer = await _say(db, ctx, "I miei dati")
    assert "Maria Silva" in answer.text and "Rua das Flores 10" in answer.text and "Luca Bianchi" in answer.text
    assert "Segreto" not in answer.text

    ctx_pt = await _ctx(db, monkeypatch, parent, scope, {"club.family"}, lang="pt")
    answer = await _say(db, ctx_pt, "O que sabes de mim?")
    assert "Olá Maria" in answer.text and "cinto amarelo" in answer.text
    assert euro(paid.amount_cents, "pt") in answer.text and "Estraneo" not in answer.text

    answer = await _say(db, ctx_pt, "Estou em dívida?")
    assert "No total tens" in answer.text  # un genitore parla della sua famiglia, non del club

    answer = await _say(db, ctx_pt, "Quantas presenças tem o Luca?")
    assert "0 treinos este mês" in answer.text


async def test_personal_data_needs_the_family_permission(db, scope, monkeypatch):
    """Lo staff senza famiglia nel club vede solo i suoi dati, non quelli degli atleti."""
    admin = await _user(db, scope, "admin")
    await _plans(db, scope, admin)
    parent = await _user(db, scope)
    await _athlete(db, scope, parent, birth_date=date(2016, 3, 3))
    staff = await _user(db, scope, "istruttore")
    ctx = await _ctx(db, monkeypatch, staff, scope, {"club.instruct"})
    data = await REGISTRY.call("my_profile", ctx)
    assert data["email"] == staff.email and data["athletes"] == []
    answer = await _say(db, ctx, "Quanto ho pagato?")
    assert "Luca" not in answer.text
