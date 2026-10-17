"""I combattimenti decisi dal server (fight.py è il motore): le gare della
carriera combattute passo a passo e il randori con gli amici del club.
Specifica: docs/games.md, «Combattimenti» e «Randori del club».

Il browser manda solo l'id di una delle opzioni mostrate per lo scambio in
corso (e il numero dello scambio, così una risposta doppia non conta due
volte): il server sa quali sono giuste, tira i dadi e aggiorna il
punteggio. Un incontro finito non accetta più risposte; uno lasciato a metà
scade e conta come perso (kiken), così non si scappa da un randori che va
male.

Le statistiche dei judoca vengono dalla partita di Judo Career salvata
(tecnica, físico, mental, energia, infortunio), sempre riportate tra 0 e
100; chi non ha una carriera combatte con i valori della sua cintura del
gioco. Il randori non cambia la carriera: è un gioco a parte con i suoi
punti (`players.randori_points`).
"""

import math
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.game import content, fight
from app.game import fight_content as fc
from app.game.models import GameCareer, GameFight, GamePlayer
from app.game.service import GameError, GameNotFound, _lang, exams_passed, get_player, top_belt

#: Un incontro passo a passo lasciato a metà scade dopo questo tempo.
FIGHT_TTL = timedelta(minutes=20)
#: Randori: quante volte al giorno si incontrano due amici (in tutte e due le
#: direzioni) e quante sfide lancia un giocatore al giorno.
PAIR_PER_DAY = 3
CHALLENGES_PER_DAY = 10
#: Randori: punti iniziali e quanti passano al massimo/minimo per incontro (alla Elo).
START_POINTS = 1000
K_POINTS = 32
MIN_POINTS = 4

#: Le gare della carriera, come in engine.ts: forza dell'avversario e turni.
LEVEL_BASE = {"REGIONAL": 9, "NACIONAL": 24, "INTERNACIONAL": 40}
LEVEL_ROUNDS = {"REGIONAL": 3, "NACIONAL": 4, "INTERNACIONAL": 5}


def _num(v: object, default: float = 0) -> float:
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return default if math.isnan(x) else fight.clamp(x)


def _belt_defaults(belt: str) -> dict:
    r = content.BELTS.index(belt) if belt in content.BELTS else 0
    return {"tec": 8 + 9 * r, "str": 12 + 7 * r, "men": 15 + 6 * r}


async def fighter_of(db: AsyncSession, player: GamePlayer) -> dict:
    """Il judoca di un giocatore: dalla sua carriera salvata, oppure dalla
    sua cintura del gioco."""
    career = await db.get(GameCareer, player.id)
    hero = (career.state or {}).get("hero") if career else None
    if isinstance(hero, dict):
        belt = hero.get("belt") if hero.get("belt") in content.BELTS else (career.belt if career else "WHITE")
        injury = _num(hero.get("injury"))
        return fight.fighter(player.display_name, belt, tec=_num(hero.get("tecnica")), str_=_num(hero.get("fisico")),
                             men=_num(hero.get("mental")), sta=_num(hero.get("energia"), 100),
                             hp=max(40, 100 - 20 * injury), club=player.club_label)
    belt = top_belt(await exams_passed(db, player_id=player.id))
    d = _belt_defaults(belt)
    return fight.fighter(player.display_name, belt, tec=d["tec"], str_=d["str"], men=d["men"], club=player.club_label)


def _side_public(f: dict) -> dict:
    return {"name": f["name"], "belt": f["belt"], "club": f.get("club"),
            "tec": f["tec"], "str": f["str"], "men": f["men"], "sta": f["sta"], "hp": f["hp"]}


def view(f: GameFight, *, extra: dict | None = None) -> dict:
    """L'incontro come lo vede il browser: niente qualità delle risposte
    ancora da dare, niente esiti futuri."""
    st = f.state
    lang = f.lang if f.lang in content.LANGS else "pt"
    return {
        "id": f.id, "kind": f.kind, "mode": f.mode, "status": f.status,
        "me": _side_public(st["me"]), "opp": _side_public(st["opp"]),
        "clock": st["clock"], "regulation": fight.REGULATION, "golden": st["golden"],
        "score": st["score"], "stamina": st["sta"],
        "prompt": fight.public_prompt(st, lang),
        "history": [fight.public_exchange(e, lang) for e in st["history"]],
        "result": {"won": st["winner"] == "me", "reason": st["reason"], "points": f.points} if st["over"] else None,
        "timeline": fight.timeline(st) if st["over"] else [],
        "context": st.get("context"),
        **(extra or {}),
    }


async def _finalize(db: AsyncSession, f: GameFight, now: datetime) -> None:
    """Chiude l'incontro; nel randori i punti passano dal perdente al vincitore."""
    st = f.state
    f.status = "FINISHED"
    f.finished_at = now
    f.won = st["winner"] == "me"
    if f.kind == "RANDORI" and f.opponent_player_id:
        me = await db.get(GamePlayer, f.player_id)
        opp = await db.get(GamePlayer, f.opponent_player_id)
        if me is not None and opp is not None:
            winner, loser = (me, opp) if f.won else (opp, me)
            delta = transfer(winner.randori_points, loser.randori_points)
            delta = min(delta, max(0, loser.randori_points))
            # con UPDATE ... = colonna ± delta due incontri contemporanei non si pestano i piedi
            await db.execute(update(GamePlayer).where(GamePlayer.id == winner.id)
                             .values(randori_points=GamePlayer.randori_points + delta))
            await db.execute(update(GamePlayer).where(GamePlayer.id == loser.id)
                             .values(randori_points=func.greatest(0, GamePlayer.randori_points - delta)))
            f.points = delta
            # l'UPDATE con un'espressione fa scadere il valore in memoria: si rilegge subito
            await db.refresh(winner, ["randori_points"])
            await db.refresh(loser, ["randori_points"])
    # JSONB: un dict modificato sul posto non si vede, si riassegna
    f.state = dict(st)


def transfer(winner_points: int, loser_points: int) -> int:
    """Quanti punti passano: tanti se vince lo sfavorito, pochi se vince il favorito."""
    expected = 1 / (1 + 10 ** ((loser_points - winner_points) / 400))
    return int(max(MIN_POINTS, min(K_POINTS, round(K_POINTS * (1 - expected)))))


async def _expire(db: AsyncSession, player_id: uuid.UUID, now: datetime) -> None:
    """Gli incontri lasciati a metà da troppo tempo: persi per abbandono."""
    stale = (await db.execute(select(GameFight).where(
        GameFight.player_id == player_id, GameFight.status == "ACTIVE", GameFight.updated_at < now - FIGHT_TTL,
    ).with_for_update())).scalars().all()
    for f in stale:
        st = dict(f.state)
        fight.forfeit(st)
        f.state = st
        await _finalize(db, f, now)
    if stale:
        await db.commit()


async def _active(db: AsyncSession, player_id: uuid.UUID) -> GameFight | None:
    return (await db.execute(select(GameFight).where(
        GameFight.player_id == player_id, GameFight.status == "ACTIVE",
    ).order_by(GameFight.created_at.desc()).limit(1))).scalar_one_or_none()


async def _create(db: AsyncSession, *, player: GamePlayer, kind: str, mode: str, me: dict, opp: dict, lang: str,
                  rng: random.Random, now: datetime, context: dict | None = None, context_key: str | None = None,
                  opponent_player_id: uuid.UUID | None = None) -> GameFight:
    st = fight.new_state(me, opp, rng)
    st["context"] = context
    f = GameFight(player_id=player.id, kind=kind, mode=mode, context_key=context_key,
                  opponent_player_id=opponent_player_id, lang=lang, state=st, status="ACTIVE",
                  points=0, created_at=now, updated_at=now)
    db.add(f)
    if mode == "SIM":
        fight.simulate(st, rng)
        f.state = dict(st)
        await _finalize(db, f, now)
    else:
        st["asked_at"] = now.isoformat()
    await db.commit()
    await db.refresh(f)
    return f


# --- Le gare della carriera, passo a passo ---------------------------------------------------------------------

async def _career_comp(db: AsyncSession, player: GamePlayer, comp_id: str) -> tuple[dict, dict, GameCareer]:
    """La gara di questa settimana della carriera salvata, se ci si è iscritti."""
    career = await db.get(GameCareer, player.id)
    state = career.state if career else None
    if not isinstance(state, dict) or not isinstance(state.get("hero"), dict):
        raise GameError("Prima inizia la tua carriera in Judo Career.")
    comp = next((c for c in state.get("calendar") or [] if isinstance(c, dict) and c.get("id") == comp_id), None)
    if comp is None or comp.get("level") not in LEVEL_BASE:
        raise GameNotFound("Gara non trovata.")
    if comp.get("week") != state.get("week"):
        raise GameError("Questa gara non è in questa settimana.")
    if comp_id not in (state.get("heroRegs") or []):
        raise GameError("Non sei iscritto a questa gara.")
    if _num(state["hero"].get("injury")) > 0:
        raise GameError("Sei infortunato: questa settimana non puoi combattere.")
    return state, comp, career  # type: ignore[return-value]


def _career_key(state: dict, comp_id: str, rnd: int) -> str:
    return f"career:{state.get('seed')}:{comp_id}:r{rnd}"


async def career_rounds(db: AsyncSession, *, user_id: uuid.UUID, comp_id: str, now: datetime | None = None) -> dict:
    """I turni già combattuti passo a passo di una gara della carriera."""
    now = now or utcnow()
    player = await get_player(db, user_id=user_id)
    await _expire(db, player.id, now)
    career = await db.get(GameCareer, player.id)
    seed = (career.state or {}).get("seed") if career else None
    prefix = f"career:{seed}:{comp_id}:r"
    rows = (await db.execute(select(GameFight).where(
        GameFight.player_id == player.id, GameFight.kind == "CAREER", GameFight.context_key.like(f"{prefix}%"),
    ).order_by(GameFight.created_at))).scalars().all()
    return {"rounds": [view(f) for f in rows]}


async def start_career_fight(db: AsyncSession, *, user_id: uuid.UUID, comp_id: str, round_no: int, lang: str | None,
                             rng: random.Random | None = None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    rng = rng or random.SystemRandom()
    lang = _lang(lang)
    player = await get_player(db, user_id=user_id)
    await _expire(db, player.id, now)
    state, comp, _career = await _career_comp(db, player, comp_id)
    rounds = LEVEL_ROUNDS[comp["level"]]
    if not 1 <= round_no <= rounds:
        raise GameError("Turno non valido.")
    key = _career_key(state, comp_id, round_no)
    existing = (await db.execute(select(GameFight).where(
        GameFight.player_id == player.id, GameFight.context_key == key))).scalar_one_or_none()
    if existing is not None:
        if existing.status == "ACTIVE":
            return view(existing)
        raise GameError("Questo turno l'hai già combattuto.")
    if round_no > 1:
        prev = (await db.execute(select(GameFight).where(
            GameFight.player_id == player.id, GameFight.context_key == _career_key(state, comp_id, round_no - 1),
        ))).scalar_one_or_none()
        if prev is None or prev.status != "FINISHED" or not prev.won:
            raise GameError("Per questo turno devi prima vincere quello prima.")
    if (active := await _active(db, player.id)) is not None:
        raise GameError("Hai già un combattimento in corso: finiscilo prima." if active.kind == "RANDORI"
                        else "Finisci prima il turno in corso.")
    me = await fighter_of(db, player)
    me["name"] = str(state["hero"].get("name") or player.display_name)[:24]
    # l'avversario: forte come nel motore della carriera (engine.ts::winChance)
    target = LEVEL_BASE[comp["level"]] + round_no * 3 + rng.random() * 14
    my_rank = content.BELTS.index(me["belt"])
    min_rank = content.BELTS.index(comp.get("minBelt")) if comp.get("minBelt") in content.BELTS else 0
    opp_belt = content.BELTS[max(min_rank, min(6, my_rank + rng.randint(-1, 1)))]
    opp = fight.fighter(rng.choice(fc.OPPONENT_NAMES), opp_belt, tec=target, str_=target, men=target,
                        club=rng.choice(fc.CITIES))
    f = await _create(db, player=player, kind="CAREER", mode="STEP", me=me, opp=opp, lang=lang, rng=rng, now=now,
                      context={"comp_id": comp_id, "round": round_no, "rounds": rounds, "level": comp["level"],
                               "city": comp.get("city")},
                      context_key=key)
    return view(f)


# --- Randori del club ------------------------------------------------------------------------------------------

def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _today_counts(db: AsyncSession, player_id: uuid.UUID, now: datetime) -> tuple[int, dict[uuid.UUID, int]]:
    """Le sfide lanciate oggi dal giocatore e gli incontri di oggi con ogni amico."""
    since = _day_start(now)
    rows = (await db.execute(select(GameFight.player_id, GameFight.opponent_player_id).where(
        GameFight.kind == "RANDORI", GameFight.created_at >= since,
        or_(GameFight.player_id == player_id, GameFight.opponent_player_id == player_id),
    ))).all()
    launched = sum(1 for p, _o in rows if p == player_id)
    pair: dict[uuid.UUID, int] = {}
    for p, o in rows:
        other = o if p == player_id else p
        if other is not None:
            pair[other] = pair.get(other, 0) + 1
    return launched, pair


async def _friends(db: AsyncSession, player: GamePlayer) -> list[GamePlayer]:
    if not player.club_label:
        return []
    return list((await db.execute(select(GamePlayer).where(
        GamePlayer.club_label == player.club_label, GamePlayer.id != player.id,
    ).order_by(GamePlayer.randori_points.desc(), GamePlayer.display_name))).scalars())


async def challenge(db: AsyncSession, *, user_id: uuid.UUID, opponent_id: uuid.UUID, mode: str, lang: str | None,
                    rng: random.Random | None = None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    rng = rng or random.SystemRandom()
    lang = _lang(lang)
    if mode not in ("SIM", "STEP"):
        raise GameError("Modo non valido.")
    player = await get_player(db, user_id=user_id)
    await _expire(db, player.id, now)
    if opponent_id == player.id:
        raise GameError("Non puoi sfidare te stesso.")
    opp = await db.get(GamePlayer, opponent_id)
    if opp is None or not player.club_label or opp.club_label != player.club_label:
        raise GameNotFound("Puoi sfidare solo gli amici del tuo club.")
    if await _active(db, player.id) is not None:
        raise GameError("Hai già un combattimento in corso: finiscilo prima.")
    launched, pair = await _today_counts(db, player.id, now)
    if launched >= CHALLENGES_PER_DAY:
        raise GameError(f"Oggi hai già lanciato {CHALLENGES_PER_DAY} sfide: torna domani.")
    if pair.get(opp.id, 0) >= PAIR_PER_DAY:
        raise GameError(f"Oggi vi siete già affrontati {PAIR_PER_DAY} volte: sfida un altro amico o torna domani.")
    me_f = await fighter_of(db, player)
    opp_f = await fighter_of(db, opp)
    f = await _create(db, player=player, kind="RANDORI", mode=mode, me=me_f, opp=opp_f, lang=lang, rng=rng, now=now,
                      opponent_player_id=opp.id,
                      context={"stake_win": transfer(player.randori_points, opp.randori_points),
                               "stake_loss": transfer(opp.randori_points, player.randori_points)})
    await db.refresh(player)
    return view(f, extra={"my_points": player.randori_points})


async def _own_fight(db: AsyncSession, player: GamePlayer, fight_id: uuid.UUID, *, lock: bool = False) -> GameFight:
    stmt = select(GameFight).where(GameFight.id == fight_id)
    if lock:
        stmt = stmt.with_for_update()
    f = (await db.execute(stmt)).scalar_one_or_none()
    if f is None or f.player_id != player.id:
        raise GameNotFound("Combattimento non trovato.")
    return f


async def get_fight(db: AsyncSession, *, user_id: uuid.UUID, fight_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or utcnow()
    player = await get_player(db, user_id=user_id)
    await _expire(db, player.id, now)
    f = await _own_fight(db, player, fight_id)
    if f.status == "ACTIVE" and f.mode == "STEP":
        # chi riapre un incontro a metà ha di nuovo il tempo per rispondere
        # (la scadenza dell'incontro intero resta quella di updated_at)
        await db.execute(update(GameFight).where(GameFight.id == f.id).values(
            state={**f.state, "asked_at": now.isoformat()}, updated_at=GameFight.updated_at))
        await db.commit()
        await db.refresh(f)
    await db.refresh(player)
    return view(f, extra={"my_points": player.randori_points})


async def act(db: AsyncSession, *, user_id: uuid.UUID, fight_id: uuid.UUID, seq: int, option: str | None,
              rng: random.Random | None = None, now: datetime | None = None) -> dict:
    """Una risposta allo scambio `seq`. `option` None = tempo scaduto."""
    now = now or utcnow()
    rng = rng or random.SystemRandom()
    player = await get_player(db, user_id=user_id)
    await _expire(db, player.id, now)
    f = await _own_fight(db, player, fight_id, lock=True)
    if f.status != "ACTIVE":
        raise GameError("Questo combattimento è finito.")
    st = dict(f.state)
    cur = st.get("current")
    if not cur or cur["seq"] != seq:
        raise GameError("Questo scambio è già stato giocato.")
    if option is not None and not fight.valid_option(st, option):
        raise GameError("Questa mossa non è tra quelle possibili.")
    asked = datetime.fromisoformat(st["asked_at"]) if st.get("asked_at") else now
    if (now - asked).total_seconds() > fight.STEP_SECONDS + fight.STEP_GRACE:
        option = None  # troppo tardi: hai esitato
    exchange = fight.resolve(st, option, rng)
    st["asked_at"] = now.isoformat()
    f.state = st
    f.updated_at = now
    if st["over"]:
        await _finalize(db, f, now)
    await db.commit()
    await db.refresh(f)
    await db.refresh(player)
    lang = f.lang if f.lang in content.LANGS else "pt"
    return view(f, extra={"last": fight.public_exchange(exchange, lang), "my_points": player.randori_points})


async def forfeit(db: AsyncSession, *, user_id: uuid.UUID, fight_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or utcnow()
    player = await get_player(db, user_id=user_id)
    f = await _own_fight(db, player, fight_id, lock=True)
    if f.status != "ACTIVE":
        raise GameError("Questo combattimento è finito.")
    st = dict(f.state)
    fight.forfeit(st)
    f.state = st
    await _finalize(db, f, now)
    await db.commit()
    await db.refresh(f)
    await db.refresh(player)
    return view(f, extra={"my_points": player.randori_points})


async def randori_overview(db: AsyncSession, *, user_id: uuid.UUID, now: datetime | None = None) -> dict:
    """La pagina del randori: io, gli amici del club da sfidare, la
    classifica del club e gli ultimi incontri."""
    now = now or utcnow()
    player = await get_player(db, user_id=user_id)
    await _expire(db, player.id, now)
    await db.refresh(player)
    me_f = await fighter_of(db, player)
    my_power = fight.power(me_f, me_f["sta"])
    friends = await _friends(db, player)
    launched, pair = await _today_counts(db, player.id, now)
    rows = []
    for fr in friends:
        f = await fighter_of(db, fr)
        ratio = fight.power(f, f["sta"]) / max(1.0, my_power)
        rows.append({
            "player_id": fr.id, "display_name": fr.display_name, "belt": f["belt"], "points": fr.randori_points,
            "edge": "STRONGER" if ratio > 1.15 else "WEAKER" if ratio < 0.87 else "EVEN",
            "left_today": max(0, PAIR_PER_DAY - pair.get(fr.id, 0)),
            "stake_win": transfer(player.randori_points, fr.randori_points),
            "stake_loss": transfer(fr.randori_points, player.randori_points),
            "injured": f["hp"] < 100,
        })

    # la classifica del club: io e gli amici, con vittorie e sconfitte
    everyone = [player, *friends]
    ids = [p.id for p in everyone]
    wins: dict[uuid.UUID, int] = {}
    losses: dict[uuid.UUID, int] = {}
    if ids:
        res = (await db.execute(select(GameFight.player_id, GameFight.opponent_player_id, GameFight.won).where(
            GameFight.kind == "RANDORI", GameFight.status == "FINISHED",
            or_(GameFight.player_id.in_(ids), GameFight.opponent_player_id.in_(ids)),
        ))).all()
        for p, o, won in res:
            winner, loser = (p, o) if won else (o, p)
            wins[winner] = wins.get(winner, 0) + 1
            losses[loser] = losses.get(loser, 0) + 1
    board, position, previous = [], 0, None
    ranked = sorted(everyone, key=lambda p: (-p.randori_points, p.display_name)) if player.club_label else [player]
    for i, p in enumerate(ranked, start=1):
        if p.randori_points != previous:
            position, previous = i, p.randori_points
        board.append({"position": position, "display_name": p.display_name, "points": p.randori_points,
                      "wins": wins.get(p.id, 0), "losses": losses.get(p.id, 0), "is_me": p.id == player.id})

    # gli ultimi incontri, lanciati o subiti
    recent = (await db.execute(select(GameFight).where(
        GameFight.kind == "RANDORI", GameFight.status == "FINISHED",
        or_(GameFight.player_id == player.id, GameFight.opponent_player_id == player.id),
    ).order_by(GameFight.finished_at.desc()).limit(15))).scalars().all()
    names = {p.id: p.display_name for p in everyone}
    missing = {x for f in recent for x in (f.player_id, f.opponent_player_id) if x and x not in names}
    if missing:
        for pid, name in (await db.execute(select(GamePlayer.id, GamePlayer.display_name)
                                           .where(GamePlayer.id.in_(missing)))).all():
            names[pid] = name
    history = []
    for f in recent:
        mine = f.player_id == player.id
        other = f.opponent_player_id if mine else f.player_id
        won = bool(f.won) if mine else not f.won
        history.append({"id": f.id, "at": f.finished_at, "opponent": names.get(other, "—"), "challenger": mine,
                        "won": won, "points": f.points, "mode": f.mode, "reason": (f.state or {}).get("reason"),
                        "can_review": mine})
    active = await _active(db, player.id)
    return {
        "club_label": player.club_label,
        "me": {"display_name": player.display_name, "points": player.randori_points, "fighter": _side_public(me_f),
               "position": next((r["position"] for r in board if r["is_me"]), 1),
               "challenges_left": max(0, CHALLENGES_PER_DAY - launched)},
        "friends": rows, "board": board, "history": history,
        "active_fight_id": active.id if active else None,
        "limits": {"pair_per_day": PAIR_PER_DAY, "challenges_per_day": CHALLENGES_PER_DAY},
    }


__all__ = ["act", "career_rounds", "challenge", "forfeit", "get_fight", "randori_overview", "start_career_fight", "transfer"]
