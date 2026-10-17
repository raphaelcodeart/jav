"""I combattimenti decisi dal server (app/game/fight.py, fights.py; docs/games.md).

Le promesse: ogni situazione ha risposte complete in tutte le lingue; il
browser non vede mai la qualità delle risposte prima di rispondere; il
server accetta solo una delle mosse mostrate, una volta, e niente dopo la
fine; le statistiche e le scelte contano davvero; nel randori i punti
passano dal perdente al vincitore, con un tetto, solo tra amici dello
stesso club e non più di tante volte al giorno; un incontro abbandonato è
perso; un turno di gara della carriera non si rifà.
"""

import random
import uuid
from datetime import timedelta

import pytest

from app.core.db import utcnow
from app.game import fight, fights, service
from app.game import fight_content as fc
from app.game.models import GameFight
from tests.test_club_fees import _user


def test_every_situation_is_complete():
    assert all(fc.BY_KIND[k] for k in fc.KINDS)
    for s in fc.SITUATIONS:
        ids = [o.id for o in s.options]
        assert 3 <= len(ids) <= 4 and len(set(ids)) == len(ids) and "late" not in ids, s.id
        assert max(o.q for o in s.options) >= 2 and min(o.q for o in s.options) <= 1, s.id
        for lang in ("pt", "it", "en"):
            assert s.text[lang]
            for o in s.options:
                assert o.label[lang] and o.why[lang], (s.id, o.id)
        for o in s.options:
            assert o.ok in fc.OK_CODES and o.ko in fc.KO_CODES, (s.id, o.id)
            if o.ok in ("IPPON", "WAZA", "YUKO"):
                assert o.tech, (s.id, o.id)
        if s.kind == "DEF":
            assert s.tech


def _f(level: int, **kw):
    return fight.fighter("X", "GREEN", tec=level, str_=level, men=level, **kw)


def _play(me, opp, seed, chooser):
    rng = random.Random(seed)
    st = fight.new_state(me, opp, rng)
    while not st["over"]:
        sit = fc.BY_ID[st["current"]["situation"]]
        fight.resolve(st, chooser(sit), rng)
    return st


def test_a_match_always_ends_with_a_winner_and_ijf_rules():
    for seed in range(300):
        st = _play(_f(40), _f(40), seed, lambda s, seed=seed: random.Random(seed).choice(s.options).id)
        assert st["winner"] in ("me", "opp") and st["reason"] in ("IPPON", "AWASETE", "HANSOKU", "TIME", "GOLDEN", "DECISION")
        sc = st["score"][st["winner"]]
        loser = st["score"]["opp" if st["winner"] == "me" else "me"]
        if st["reason"] == "AWASETE":
            assert sc["waza"] == 2
        if st["reason"] == "HANSOKU":
            assert loser["shido"] == 3
        if st["reason"] == "TIME":
            assert st["clock"] >= fight.REGULATION and not st["golden"]
        if st["reason"] == "GOLDEN":
            assert st["golden"]


def test_stats_matter():
    strong = sum(_play(_f(75), _f(25), s, lambda sit: sit.options[0].id)["winner"] == "me" for s in range(200))
    weak = sum(_play(_f(25), _f(75), s, lambda sit: sit.options[0].id)["winner"] == "me" for s in range(200))
    assert strong > 150 and weak < 50
    # un infortunato e un judoca senza fiato valgono meno
    assert fight.power(_f(50, hp=60), 100) < fight.power(_f(50), 100)
    assert fight.power(_f(50), 20) < fight.power(_f(50), 100)


def test_choices_matter():
    def best(sit):
        return max(sit.options, key=lambda o: o.q).id

    def worst(sit):
        return min(sit.options, key=lambda o: o.q).id

    good = sum(_play(_f(45), _f(45), s, best)["winner"] == "me" for s in range(200))
    bad = sum(_play(_f(45), _f(45), s, worst)["winner"] == "me" for s in range(200))
    assert good > 130 and bad < 60


def test_transfer_is_capped_and_favours_the_underdog():
    assert fights.transfer(1000, 1000) == 16
    assert fights.transfer(1400, 800) == fights.MIN_POINTS
    assert fights.transfer(800, 1400) >= 30 and fights.transfer(0, 5000) == fights.K_POINTS


async def _club_pair(db, scope):
    a = await _user(db, scope, "a")
    b = await _user(db, scope, "b")
    pa = await service.get_player(db, user_id=a.id)
    pb = await service.get_player(db, user_id=b.id)
    return a, b, pa, pb


async def test_randori_step_is_server_authoritative(db, scope):
    a, _b, pa, pb = await _club_pair(db, scope)
    rng = random.Random(7)
    started = await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="STEP", lang="it", rng=rng)
    prompt = started["prompt"]
    assert started["status"] == "ACTIVE" and prompt and started["result"] is None
    # il browser riceve solo id ed etichetta
    assert all(set(o) == {"id", "label"} for o in prompt["options"])
    fid = started["id"]

    with pytest.raises(service.GameError):
        await fights.act(db, user_id=a.id, fight_id=fid, seq=prompt["seq"], option="ippon-please", rng=rng)
    with pytest.raises(service.GameError):
        await fights.act(db, user_id=a.id, fight_id=fid, seq=prompt["seq"] + 5, option=prompt["options"][0]["id"], rng=rng)
    # un altro combattimento non si apre finché questo è in corso
    with pytest.raises(service.GameError):
        await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="SIM", lang="it", rng=rng)
    # l'altro giocatore non vede né gioca questo incontro
    with pytest.raises(service.GameNotFound):
        await fights.get_fight(db, user_id=_b.id, fight_id=fid)

    res = await fights.act(db, user_id=a.id, fight_id=fid, seq=prompt["seq"], option=prompt["options"][0]["id"], rng=rng)
    assert res["last"]["why"] and res["last"]["quality"] in ("BEST", "GOOD", "RISKY", "BAD")
    with pytest.raises(service.GameError):  # la stessa risposta due volte
        await fights.act(db, user_id=a.id, fight_id=fid, seq=prompt["seq"], option=prompt["options"][0]["id"], rng=rng)

    while res["status"] == "ACTIVE":
        p = res["prompt"]
        res = await fights.act(db, user_id=a.id, fight_id=fid, seq=p["seq"], option=p["options"][0]["id"], rng=rng)
    assert res["result"] is not None and res["timeline"]
    with pytest.raises(service.GameError):
        await fights.act(db, user_id=a.id, fight_id=fid, seq=res["history"][-1]["seq"] + 1, option="block", rng=rng)

    # i punti passano dal perdente al vincitore, e la somma non cambia
    await db.refresh(pa)
    await db.refresh(pb)
    delta = res["result"]["points"]
    assert delta == 16
    assert pa.randori_points + pb.randori_points == 2 * fights.START_POINTS
    assert pa.randori_points == fights.START_POINTS + (delta if res["result"]["won"] else -delta)


async def test_late_answer_counts_as_hesitation(db, scope):
    a, _b, _pa, pb = await _club_pair(db, scope)
    now = utcnow()
    started = await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="STEP", lang="pt", rng=random.Random(1), now=now)
    p = started["prompt"]
    res = await fights.act(db, user_id=a.id, fight_id=started["id"], seq=p["seq"], option=p["options"][0]["id"],
                           rng=random.Random(1), now=now + timedelta(seconds=fight.STEP_SECONDS + fight.STEP_GRACE + 5))
    assert res["last"]["quality"] == "BAD" and res["last"]["choice"] == "Hesitaste…"


async def test_randori_rules_and_limits(db, scope):
    from app.domains.club.models import Club

    a, _b, pa, pb = await _club_pair(db, scope)
    with pytest.raises(service.GameError):
        await fights.challenge(db, user_id=a.id, opponent_id=pa.id, mode="SIM", lang="pt")
    # un giocatore di un altro club non si può sfidare
    other_club = Club(organization_id=scope.organization_id, name="Altro club", slug=f"c-{uuid.uuid4().hex[:8]}", settings={})
    db.add(other_club)
    await db.commit()
    stranger = await _user(db, scope, "x")
    stranger.club_id = other_club.id
    await db.commit()
    ps = await service.get_player(db, user_id=stranger.id)
    with pytest.raises(service.GameNotFound):
        await fights.challenge(db, user_id=a.id, opponent_id=ps.id, mode="SIM", lang="pt")

    for i in range(fights.PAIR_PER_DAY):
        done = await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="SIM", lang="pt", rng=random.Random(i))
        assert done["status"] == "FINISHED" and done["history"] and done["result"]["points"] > 0
    with pytest.raises(service.GameError):
        await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="SIM", lang="pt")
    # il limite vale nelle due direzioni
    with pytest.raises(service.GameError):
        await fights.challenge(db, user_id=_b.id, opponent_id=pa.id, mode="SIM", lang="pt")
    # domani si ricomincia
    tomorrow = utcnow() + timedelta(days=1)
    await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="SIM", lang="pt", now=tomorrow)

    page = await fights.randori_overview(db, user_id=a.id)
    assert page["club_label"] == "Club di prova" and [f["display_name"] for f in page["friends"]] == [pb.display_name]
    assert page["friends"][0]["left_today"] == 0
    assert len(page["history"]) == fights.PAIR_PER_DAY + 1
    board = {r["display_name"]: r for r in page["board"]}
    assert sum(r["wins"] for r in board.values()) == fights.PAIR_PER_DAY + 1
    assert sum(r["points"] for r in board.values()) == 2 * fights.START_POINTS


async def test_an_abandoned_fight_is_lost(db, scope):
    a, _b, _pa, pb = await _club_pair(db, scope)
    now = utcnow()
    started = await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="STEP", lang="pt", now=now)
    later = now + fights.FIGHT_TTL + timedelta(minutes=1)
    page = await fights.randori_overview(db, user_id=a.id, now=later)
    assert page["active_fight_id"] is None and page["history"][0]["won"] is False
    f = await db.get(GameFight, started["id"])
    assert f.status == "FINISHED" and f.won is False and f.state["reason"] == "FORFEIT"
    await db.refresh(pb)
    assert pb.randori_points == fights.START_POINTS + 16

    second = await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="STEP", lang="pt", now=later)
    gone = await fights.forfeit(db, user_id=a.id, fight_id=second["id"], now=later)
    assert gone["result"]["won"] is False and gone["result"]["reason"] == "FORFEIT"


async def test_stats_come_from_the_saved_career(db, scope):
    a, _b, pa, pb = await _club_pair(db, scope)
    hero = {"name": "A", "belt": "WHITE", "tecnica": 90, "fisico": 80, "mental": 70, "energia": 100, "injury": 2}
    await service.save_career(db, user_id=a.id, state={"version": 1, "hero": hero}, career_xp=0, week=1, belt="WHITE")
    f = await fights.fighter_of(db, pa)
    assert (f["tec"], f["str"], f["men"], f["hp"]) == (90, 80, 70, 60)
    plain = await fights.fighter_of(db, pb)
    assert plain["belt"] == "WHITE" and plain["hp"] == 100
    with pytest.raises(service.GameError):
        await service.save_career(db, user_id=a.id, state={"version": 1, "hero": {**hero, "tecnica": 500}},
                                  career_xp=0, week=1, belt="WHITE")


async def test_career_rounds_are_fought_once_and_in_order(db, scope):
    kid = await _user(db, scope, "kid")
    comp = {"id": "y1c0", "week": 4, "level": "REGIONAL", "city": "Faro", "minBelt": "WHITE", "fee": 10, "prize": 15}
    hero = {"name": "Kid", "belt": "WHITE", "tecnica": 60, "fisico": 60, "mental": 60, "energia": 100, "injury": 0}
    state = {"version": 1, "seed": 42, "week": 4, "hero": hero, "calendar": [comp], "heroRegs": []}
    await service.save_career(db, user_id=kid.id, state=state, career_xp=0, week=4, belt="WHITE")
    with pytest.raises(service.GameError):  # non iscritto
        await fights.start_career_fight(db, user_id=kid.id, comp_id="y1c0", round_no=1, lang="pt")
    await service.save_career(db, user_id=kid.id, state={**state, "heroRegs": ["y1c0"]}, career_xp=0, week=4, belt="WHITE")
    with pytest.raises(service.GameError):  # prima il primo turno
        await fights.start_career_fight(db, user_id=kid.id, comp_id="y1c0", round_no=2, lang="pt")

    rng = random.Random(3)
    res = await fights.start_career_fight(db, user_id=kid.id, comp_id="y1c0", round_no=1, lang="pt", rng=rng)
    assert res["kind"] == "CAREER" and res["context"]["rounds"] == 3
    again = await fights.start_career_fight(db, user_id=kid.id, comp_id="y1c0", round_no=1, lang="pt", rng=rng)
    assert again["id"] == res["id"]  # si riprende quello in corso
    while res["status"] == "ACTIVE":
        p = res["prompt"]
        best = max(fc.BY_ID[(await db.get(GameFight, res["id"])).state["current"]["situation"]].options, key=lambda o: o.q)
        res = await fights.act(db, user_id=kid.id, fight_id=res["id"], seq=p["seq"], option=best.id, rng=rng)
    with pytest.raises(service.GameError):  # un turno non si rifà
        await fights.start_career_fight(db, user_id=kid.id, comp_id="y1c0", round_no=1, lang="pt")
    rounds = await fights.career_rounds(db, user_id=kid.id, comp_id="y1c0")
    assert [r["result"]["won"] for r in rounds["rounds"]] == [res["result"]["won"]]
    if not res["result"]["won"]:
        with pytest.raises(service.GameError):
            await fights.start_career_fight(db, user_id=kid.id, comp_id="y1c0", round_no=2, lang="pt")


async def test_reopening_a_fight_gives_time_again_but_not_a_longer_life(db, scope):
    a, _b, _pa, pb = await _club_pair(db, scope)
    now = utcnow()
    started = await fights.challenge(db, user_id=a.id, opponent_id=pb.id, mode="STEP", lang="pt", rng=random.Random(2), now=now)
    before = (await db.get(GameFight, started["id"])).updated_at
    again = await fights.get_fight(db, user_id=a.id, fight_id=started["id"], now=now + timedelta(seconds=60))
    assert (await db.get(GameFight, started["id"])).updated_at == before
    p = again["prompt"]
    res = await fights.act(db, user_id=a.id, fight_id=started["id"], seq=p["seq"], option=p["options"][0]["id"],
                           rng=random.Random(2), now=now + timedelta(seconds=65))
    assert res["last"]["choice"] != "Hesitaste…"
